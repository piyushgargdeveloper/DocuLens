"""Measure retrieval quality against a labelled question set -- no LLM calls.

`evaluate.py` compares whole answers from the LLM. This script isolates the
step that decides what the LLM gets to see: retrieval. Every question in the
set has the page(s) that answer it and a short evidence phrase copied from
that page; a retrieved chunk is *relevant* when it contains the phrase.

It compares four retrievers on the same chunks:
  - BM25          keyword baseline (implemented below, no extra dependency)
  - MiniLM        all-MiniLM-L6-v2, the embedding model the app uses
  - BGE-small     BAAI/bge-small-en-v1.5, a second Hugging Face model
  - Hybrid        BM25 + MiniLM fused with reciprocal rank fusion
across three chunking configurations, and reports:
  - Hit@1 / Hit@4   share of questions with a relevant chunk in the top 1 / 4
                    (4 is the app's top_k: what the LLM actually receives)
  - MRR@10          mean reciprocal rank of the first relevant chunk
  - Page-Hit@4      share of questions where a top-4 chunk is from a gold page

Usage:
    python retrieval_eval.py
    python retrieval_eval.py --set <set.json> --output reports/retrieval_eval.md
"""

import argparse
import json
import re
import time
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from chunker import chunk_pages
from pdf_loader import load_pdf_pages
from retriever import BM25, ranking, reciprocal_rank_fusion, tokenize  # noqa: F401 (tokenize re-exported)

TOP_K = 4  # pipeline.DEFAULT_TOP_K -- what the LLM is given
MRR_CUTOFF = 10

CHUNK_CONFIGS = {
    "A 300/50": (300, 50),
    "Default 800/150": (800, 150),
    "B 1000/200": (1000, 200),
}

# name -> (Hugging Face model id, prefix added to queries only). BGE models are
# trained with an instruction prefix on the query side; MiniLM is not.
EMBEDDING_MODELS = {
    "MiniLM": ("sentence-transformers/all-MiniLM-L6-v2", ""),
    "BGE-small": ("BAAI/bge-small-en-v1.5", "Represent this sentence for searching relevant passages: "),
}

SYSTEMS = ["BM25", "MiniLM", "BGE-small", "Hybrid"]


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def question_metrics(order: list[int], relevant: set[int], chunk_pages_: list[int], gold_pages: set[int]) -> dict:
    first = next((r for r, idx in enumerate(order[:MRR_CUTOFF], start=1) if idx in relevant), None)
    return {
        "hit1": float(bool(set(order[:1]) & relevant)),
        "hitk": float(bool(set(order[:TOP_K]) & relevant)),
        "mrr": 1.0 / first if first else 0.0,
        "pagehit": float(any(chunk_pages_[i] in gold_pages for i in order[:TOP_K])),
    }


def validate_labels(pages: dict[int, str], items: list[dict]) -> None:
    """Every evidence phrase must literally occur on one of its gold pages."""
    bad = [
        item["id"]
        for item in items
        if not any(normalize(item["evidence"]) in normalize(pages.get(p, "")) for p in item["pages"])
    ]
    if bad:
        raise SystemExit(f"Evidence phrase not found on its gold page for item(s): {bad}")


def evaluate(pdf_path: str, items: list[dict]) -> dict:
    pages_list = load_pdf_pages(Path(pdf_path).read_bytes())
    validate_labels(dict(pages_list), items)

    models = {name: (SentenceTransformer(model_id), prefix) for name, (model_id, prefix) in EMBEDDING_MODELS.items()}
    results, misses, unreachable, timings = {}, {}, {}, {}

    for config_name, (size, overlap) in CHUNK_CONFIGS.items():
        chunks = chunk_pages(pages_list, chunk_size=size, chunk_overlap=overlap)
        texts = [normalize(c["text"]) for c in chunks]
        pages_of = [c["page"] for c in chunks]
        relevant = {
            item["id"]: {i for i, t in enumerate(texts) if normalize(item["evidence"]) in t} for item in items
        }
        unreachable[config_name] = [i for i, rel in relevant.items() if not rel]

        bm25 = BM25([c["text"] for c in chunks])
        chunk_vectors = {}
        for name, (model, _) in models.items():
            start = time.perf_counter()
            chunk_vectors[name] = model.encode([c["text"] for c in chunks], normalize_embeddings=True)
            timings[(config_name, name)] = time.perf_counter() - start

        per_system = {s: [] for s in SYSTEMS}
        for item in items:
            orders = {"BM25": ranking(bm25.scores(item["question"]))}
            for name, (model, prefix) in models.items():
                q = model.encode([prefix + item["question"]], normalize_embeddings=True)[0]
                orders[name] = ranking(chunk_vectors[name] @ q)
            orders["Hybrid"] = reciprocal_rank_fusion([orders["BM25"], orders["MiniLM"]])
            for system, order in orders.items():
                m = question_metrics(order, relevant[item["id"]], pages_of, set(item["pages"]))
                per_system[system].append(m)
                if not m["hitk"]:
                    misses.setdefault((config_name, system), []).append(item["id"])

        results[config_name] = {
            "num_chunks": len(chunks),
            "systems": {
                s: {k: float(np.mean([m[k] for m in ms])) for k in ("hit1", "hitk", "mrr", "pagehit")}
                for s, ms in per_system.items()
            },
        }
    return {"results": results, "misses": misses, "unreachable": unreachable, "timings": timings}


def format_report(pdf_path: str, items: list[dict], out: dict) -> str:
    lines = [
        "# Retrieval Evaluation",
        "",
        f"Document: `{pdf_path}` — {len(items)} labelled questions (`sample_docs/retrieval_eval_set.json`).",
        f"A chunk is relevant if it contains the question's evidence phrase. k = {TOP_K} (the app's top_k).",
        "Produced by `python retrieval_eval.py`; no LLM calls, fully deterministic.",
        "",
    ]
    for config_name, res in out["results"].items():
        lines += [
            f"## Chunking {config_name} ({res['num_chunks']} chunks)",
            "",
            f"| Retriever | Hit@1 | Hit@{TOP_K} | MRR@{MRR_CUTOFF} | Page-Hit@{TOP_K} |",
            "|---|---|---|---|---|",
        ]
        for system, m in res["systems"].items():
            n = len(items)
            lines.append(
                f"| {system} | {m['hit1']:.2f} ({round(m['hit1'] * n)}/{n}) | {m['hitk']:.2f} "
                f"({round(m['hitk'] * n)}/{n}) | {m['mrr']:.2f} | {m['pagehit']:.2f} |"
            )
        if out["unreachable"][config_name]:
            lines.append(f"\nEvidence split across chunks (unreachable): {out['unreachable'][config_name]}")
        lines.append("")

    lines += ["## Questions missed in the top 4", ""]
    by_id = {item["id"]: item["question"] for item in items}
    for (config_name, system), ids in sorted(out["misses"].items()):
        shown = "; ".join(f"#{i} {by_id[i]}" for i in ids)
        lines.append(f"- **{system}, {config_name}** ({len(ids)}): {shown}")
    lines += ["", "## Chunk embedding time (seconds, CPU)", ""]
    for (config_name, name), seconds in out["timings"].items():
        lines.append(f"- {name}, {config_name}: {seconds:.2f}")
    return "\n".join(lines) + "\n"


# Categorical slots 1-4 of the dataviz reference palette, validated for
# colour-vision deficiency on a light surface. Two sit below 3:1 contrast, so
# every bar carries a visible value label (and the report has the table).
SERIES_COLORS = {"BM25": "#2a78d6", "MiniLM": "#eb6834", "BGE-small": "#1baf7a", "Hybrid": "#eda100"}


def write_svg_chart(results: dict, path: str, metric: str = "hitk") -> None:
    """Grouped bar chart of one metric: chunking configs on x, retrievers as bars.
    Plain SVG, so the report needs no plotting library."""
    width, height = 760, 400
    left, right, top, bottom = 56, 16, 84, 52
    plot_w, plot_h = width - left - right, height - top - bottom
    configs = list(results)
    group_w = plot_w / len(configs)
    bar_w, gap = 34, 2
    y = lambda v: top + plot_h * (1 - v)  # noqa: E731 -- 0..1 metric to pixels

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'font-family="system-ui, -apple-system, Segoe UI, sans-serif" role="img" '
        f'aria-label="Hit@{TOP_K} by retriever and chunking configuration">',
        f'<rect width="{width}" height="{height}" fill="#fcfcfb"/>',
        f'<text x="{left}" y="26" font-size="16" font-weight="700" fill="#1a1a19">'
        f"Share of questions with a relevant chunk in the top {TOP_K} (Hit@{TOP_K})</text>",
    ]
    # Legend, one row under the title.
    lx = left
    for system, color in SERIES_COLORS.items():
        parts.append(f'<rect x="{lx}" y="42" width="12" height="12" rx="2" fill="{color}"/>')
        parts.append(f'<text x="{lx + 18}" y="52" font-size="13" fill="#3d3d3a">{system}</text>')
        lx += 18 + round(7.6 * len(system)) + 26
    # Recessive grid and y labels.
    for v in (0, 0.25, 0.5, 0.75, 1.0):
        parts.append(f'<line x1="{left}" x2="{width - right}" y1="{y(v):.1f}" y2="{y(v):.1f}" '
                     f'stroke="{"#9a998f" if v == 0 else "#e4e3dc"}" stroke-width="1"/>')
        parts.append(f'<text x="{left - 8}" y="{y(v) + 4:.1f}" font-size="12" fill="#6b6a62" '
                     f'text-anchor="end">{v:.2f}</text>')
    # Bars: 4px rounded data-end, square at the baseline, 2px gaps.
    for gi, config in enumerate(configs):
        systems = results[config]["systems"]
        cluster = len(SERIES_COLORS) * bar_w + (len(SERIES_COLORS) - 1) * gap
        x0 = left + gi * group_w + (group_w - cluster) / 2
        for si, (system, color) in enumerate(SERIES_COLORS.items()):
            value = systems[system][metric]
            x, yt, yb, r = x0 + si * (bar_w + gap), y(value), y(0), 4
            parts.append(
                f'<path d="M{x:.1f},{yb:.1f} V{yt + r:.1f} Q{x:.1f},{yt:.1f} {x + r:.1f},{yt:.1f} '
                f'H{x + bar_w - r:.1f} Q{x + bar_w:.1f},{yt:.1f} {x + bar_w:.1f},{yt + r:.1f} V{yb:.1f} Z" '
                f'fill="{color}"><title>{system}, {config}: {value:.2f}</title></path>'
            )
            parts.append(f'<text x="{x + bar_w / 2:.1f}" y="{yt - 6:.1f}" font-size="11" fill="#3d3d3a" '
                         f'text-anchor="middle">{value:.2f}</text>')
        parts.append(f'<text x="{left + gi * group_w + group_w / 2:.1f}" y="{height - bottom + 22}" '
                     f'font-size="13" fill="#3d3d3a" text-anchor="middle">Chunking {config}</text>')
    parts.append("</svg>")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(parts) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--set", default="sample_docs/retrieval_eval_set.json", help="Labelled question set (JSON)")
    parser.add_argument("--output", default=None, help="Write the Markdown report here (default: print it)")
    parser.add_argument("--json", default=None, help="Also write raw metrics as JSON here")
    parser.add_argument("--chart", default=None, help="Also write a Hit@4 bar chart (SVG) here")
    args = parser.parse_args()

    spec = json.loads(Path(args.set).read_text(encoding="utf-8"))
    out = evaluate(spec["document"], spec["items"])
    report = format_report(spec["document"], spec["items"], out)

    if args.chart:
        write_svg_chart(out["results"], args.chart)
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(out["results"], indent=2), encoding="utf-8")
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
