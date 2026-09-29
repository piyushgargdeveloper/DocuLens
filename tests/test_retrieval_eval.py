"""Tests for retrieval_eval.py's own logic (no embedding models are loaded)."""

import json
from pathlib import Path

import pytest

import retrieval_eval as re_eval
from pdf_loader import load_pdf_pages

ROOT = Path(__file__).resolve().parent.parent


def test_bm25_ranks_the_chunk_with_the_rare_query_term_first():
    texts = [
        "the model uses attention and attention again",
        "dropout rate of 0.1 was applied to every sub-layer",
        "the model is trained on eight GPUs",
    ]
    order = re_eval.ranking(re_eval.BM25(texts).scores("what dropout rate was used"))
    assert order[0] == 1


def test_bm25_gives_zero_for_unknown_terms():
    assert not re_eval.BM25(["alpha beta", "gamma"]).scores("zeta").any()


def test_reciprocal_rank_fusion_rewards_agreement():
    # Chunk 2 is second in both lists; chunks 0 and 1 are each first in one list
    # but last (10th) in the other, so consistent agreement should win.
    fused = re_eval.reciprocal_rank_fusion([[0, 2, 3, 4, 5, 6, 7, 8, 9, 1], [1, 2, 3, 4, 5, 6, 7, 8, 9, 0]])
    assert fused[0] == 2


def test_question_metrics():
    order = [5, 3, 7, 1, 9]
    pages = {5: 1, 3: 2, 7: 2, 1: 4, 9: 4}
    m = re_eval.question_metrics(order, relevant={7}, chunk_pages_=pages, gold_pages={2})
    assert m == {"hit1": 0.0, "hitk": 1.0, "mrr": pytest.approx(1 / 3), "pagehit": 1.0}

    miss = re_eval.question_metrics(order, relevant={42}, chunk_pages_=pages, gold_pages={9})
    assert miss == {"hit1": 0.0, "hitk": 0.0, "mrr": 0.0, "pagehit": 0.0}


def test_every_label_in_the_eval_set_is_backed_by_its_page():
    spec = json.loads((ROOT / "sample_docs" / "retrieval_eval_set.json").read_text(encoding="utf-8"))
    pages = dict(load_pdf_pages((ROOT / spec["document"]).read_bytes()))
    re_eval.validate_labels(pages, spec["items"])  # raises SystemExit on a bad label
    assert len({item["id"] for item in spec["items"]}) == len(spec["items"])
    assert all(len(item["evidence"]) <= 45 for item in spec["items"])


def test_a_wrong_label_is_rejected():
    with pytest.raises(SystemExit):
        re_eval.validate_labels({1: "some page text"}, [{"id": 1, "pages": [1], "evidence": "not there"}])
