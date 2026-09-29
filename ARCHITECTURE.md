# Architecture — AI Document Assistant

_Current as of v1.5.0._

## Overview

A small FastAPI backend implementing a Retrieval-Augmented Generation (RAG)
pipeline from explicit, individually-inspectable steps rather than a
framework's black-box chain (see `DECISIONS.md` decision #1). Each pipeline
stage is a plain function you can point to and explain. The same process
serves a static HTML/CSS/JS frontend, so API and page share one origin and
no CORS configuration exists anywhere.

The UI was originally Streamlit, replaced by FastAPI + a static frontend
for mobile usability; the frontend has since been redesigned twice (v1.3.0,
v1.4.0 — see `DESIGN.md`). None of those changes touched the retrieval or
prompting code, and the single-document path is guarded by tests so the
documented chunking evaluation stays valid.

## Components

1. **Backend / API** (`main.py`, FastAPI)

   | Endpoint | Does |
   |---|---|
   | `POST /api/ingest` | Upload a PDF (≤25MB). Adds it to the session (creating one and setting the cookie if needed), max 5 documents. |
   | `POST /api/ask` | `{question}` → answer + sources, searched across all loaded documents, with the last 3 turns as context. |
   | `POST /api/summary` | `{id}` → a short summary of one document. |
   | `POST /api/remove` | `{id}` removes one document; no id (or removing the last one) clears the session and cookie. |
   | `GET /api/session` | The session's documents and conversation, so a page reload restores the UI. |
   | `GET /`, `/static/*` | The frontend, sent with `Cache-Control: no-cache` so browsers never run a stale script after a deploy. |

   State is an in-memory `dict[str, Session]` keyed by an `httponly`,
   `samesite=lax` cookie (`Secure` when the request arrived over HTTPS,
   directly or via Nginx's `X-Forwarded-Proto`). A `Session` holds up to 5
   documents (each its own `IndexState`) and the last 10 Q/A turns. Sessions
   expire after 2 hours idle — enforced by a background task (started in the
   app's `lifespan`) every 5 minutes, not only when a request arrives — and at
   most 50 are kept (oldest-idle evicted), so memory is bounded. Uploaded PDFs
   are never written to disk: the upload's temporary spool file is closed
   right after reading, and only extracted text and embeddings are kept, in
   memory, for the life of the session. Ingestion and LLM calls run in a worker thread
   (`run_in_threadpool`) so one slow request never blocks the event loop.
   Errors use real status codes (400/404/413/422/502/503/500) with a fixed,
   generic message; exception text is logged server-side only.

2. **Frontend** (`static/index.html`, `static/style.css`, `static/app.js`)
   Vanilla, no framework or build step. The design ("Annotated Margin",
   `DESIGN.md`): answers are set in a reading serif with their retrieved
   passages as margin notes beside them on wide screens (a CSS container
   query on the conversation pane) and folded under them on narrow ones.
   Page references the model writes (`【file, Page 3】`, `(Page 3)`,
   `[Page 3]`, …) are parsed into yellow "p. 3" tabs; clicking one
   highlights the matching passage. Every dynamic string is inserted with
   `textContent` or text nodes, never `innerHTML`. All requests go through
   one `api()` helper that turns network failures and non-JSON proxy error
   pages into readable messages instead of a stuck UI.

3. **Document loader** (`pdf_loader.py`)
   PyMuPDF extracts text page by page into `[(page_number, text), ...]`,
   skipping empty pages. An invalid, encrypted or image-only PDF yields an
   empty list rather than an exception.

4. **Chunker** (`chunker.py`)
   A character sliding window per page (`chunk_size`, `chunk_overlap`).
   Every chunk keeps its page number: `{"text", "page"}`.

5. **Embedder** (`embedder.py`)
   `sentence-transformers/all-MiniLM-L6-v2`, L2-normalized 384-dim vectors.
   The model is a module-level singleton (loaded once per process), plain
   Python so it works the same from `main.py`, `evaluate.py` and tests.

6. **Vector store** (`vector_store.py`)
   One FAISS `IndexFlatIP` per document; on normalized vectors inner product
   equals cosine similarity. `search()` returns `{text, page, score}` plus
   any extra chunk keys (e.g. `doc`).

7. **LLM client** (`llm_client.py`)
   One OpenAI-compatible chat-completions call over `requests`, configured
   only by `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`. Builds the grounding
   prompt (below), retries HTTP 429 honoring `Retry-After` (both numeric and
   HTTP-date forms, capped at 30s), and wraps every failure in
   `LLMConfigError` / `LLMRequestError`. Also has a separate summary prompt.

8. **Orchestration** (`pipeline.py`)
   `ingest()`, `retrieve()`, `answer()` and `summarize()` — the only place
   the stages are wired together.

## Data Flow

```
PDF upload ──► POST /api/ingest
                 │ pdf_loader: [(page, text), ...]
                 │ chunker:    [{text, page, doc}, ...]
                 │ embedder:   384-dim vectors
                 ▼
               IndexState (FAISS index + chunks) ──► session.docs[doc_id]

question ──► POST /api/ask
               │ queries = [question] (+ "previous question + question" for a follow-up)
               │ for each document × each query: FAISS top-k
               │ merge, keep best score per passage, overall top-k
               ▼
             prompt = system rules + fenced passages "[file.pdf, Page N] ..."
                      + last 3 turns (if any) + question
               │ LLM API
               ▼
             {answer, sources} ──► app.js: answer text with page tabs,
                                   sources as margin notes
```

## RAG Pipeline (detail)

**Ingestion (once per uploaded PDF).** Extract per page, chunk with overlap
so an answer spanning a boundary isn't lost, tag each chunk with the
document's filename, embed, and build that document's FAISS index. Two
uploads with the same filename are named `a.pdf` and `a.pdf (2)` so sources
stay unambiguous.

**Retrieval (per question).** The question is embedded with the same model.
Each loaded document's index is searched and the hits are merged, keeping
the overall top-k by score (`DEFAULT_TOP_K = 4`). For a follow-up, retrieval
also runs on "previous question + current question", so "how many moons
does it have?" still finds the passage about the planet named one turn
earlier; a passage found by both queries keeps its higher score. With one
document and no history this reduces exactly to a plain `store.search()`,
which a test enforces.

**Generation.** The system prompt allows answers only from the passages,
defines one exact refusal string ("I could not find the answer to this
question in the document."), and declares the passages untrusted content —
they are fenced between `<<<BEGIN PASSAGES>>>` / `<<<END PASSAGES>>>`, so an
instruction inside a PDF is reported, not obeyed (see
`tests/test_prompt_injection.py`). When earlier turns are sent, one more
rule is added: they may be used only to resolve references, never as a
source of facts. Without history the prompt is byte-identical to the one the
evaluation used.

**Sources.** The retrieved passages are returned with every answer,
independent of whether the model cites a page itself, so the user can
always check what the answer was (or wasn't) based on.

**Summary.** `summarize()` sends 10 evenly spaced chunks to a separate
summary prompt. A full map-reduce over every chunk would cost one LLM call
per chunk, which free-tier rate limits don't allow for longer PDFs.

## Technology Choices

| Choice | Why |
|--------|-----|
| **FastAPI + vanilla HTML/CSS/JS** | The smallest setup with full control over responsive layout; a SPA framework would add a build step and `node_modules` for one page. Same origin means no CORS. |
| **PyMuPDF** | Reliable page-level extraction, fast, no external binary. |
| **`all-MiniLM-L6-v2`** | Small (~80MB), fast on CPU, a well-known semantic-similarity baseline. |
| **FAISS `IndexFlatIP`, one per document** | Exact search is fine at a few documents × low thousands of chunks. Per-document indexes make removing one document a dict delete instead of re-embedding. |
| **OpenAI-compatible client via env vars** | No hardcoded provider; works with Groq (default), OpenAI or any compatible endpoint. |
| **No LangChain/LangGraph** | Every stage stays visible and explainable; see `DECISIONS.md` #1. |
| **Retrieval on concatenated queries, not LLM query rewriting** | Rewriting would double LLM calls per question on a rate-limited free tier. |

## Chunking Configuration

`pipeline.py` defaults — `chunk_size=800`, `chunk_overlap=150`, `top_k=4` —
come from the two-configuration evaluation in `DECISIONS.md` (small 300-char
chunks refused 4 of 5 answerable questions; 1000-char chunks answered all
5), and are backed by the measured retrieval evaluation (`retrieval_eval.py`:
Hit@4 0.59 at 300 characters vs 0.77 at 800 for the app's retriever). They are not exposed in the UI; `pipeline.ingest()`
and `pipeline.answer()` accept overrides, which `evaluate.py` uses to rerun
the comparison against any PDF.

## Evaluation Tooling

Two scripts sit beside the app and call the pipeline modules directly:

- `evaluate.py` — answer-level: runs a question set through the full
  pipeline (LLM included) under two chunk/top-k configurations and
  reports answers and sources side by side.
- `retrieval_eval.py` — retrieval-level, no LLM: Hit@1/Hit@4/MRR@10 on a
  labelled question set for a BM25 baseline, MiniLM, BGE-small and a
  BM25 + MiniLM hybrid (reciprocal rank fusion), across three chunk
  settings. Results: `reports/retrieval_eval.md`.

## Failure Handling

| Situation | Handled in | User sees |
|---|---|---|
| Not a `.pdf`, or over 25MB | `main.py` (reads at most 25MB+1 bytes) | 400 / 413 with a message |
| PDF with no extractable text | `pdf_loader` → `ingest()` returns `None` | 422 "Couldn't extract any text…" |
| More than 5 documents | `main.py` | 400 |
| Invalid JSON / missing question | `main.py` `_json_body()` | 400 |
| Missing API key | `LLMConfigError` | 503, generic message |
| LLM network/HTTP failure, 429 past the retry cap | `LLMRequestError` | 502, "try again" |
| Anything unexpected | generic `except` in `main.py` | 500, generic message; details only in server log |
| Proxy returns an HTML error page | `app.js` `api()` | readable error, never a frozen screen |
| Stale cached frontend after a deploy | `Cache-Control: no-cache` + `?v=` asset URLs | always the current script |
| Question not answerable from the document | system prompt | the exact refusal string |
| Instructions embedded in a PDF | fenced passages + untrusted-content rule | reported as document text, not obeyed |

## Deployment

A single AWS EC2 `t3.small` behind Nginx (HTTPS via Let's Encrypt,
`client_max_body_size 25m`, 120s proxy timeouts), running the container with
`--restart unless-stopped` and the API key passed via `--env-file`. The
`Dockerfile` installs CPU-only PyTorch to avoid ~GBs of unused CUDA wheels.
Because sessions live in process memory, the app is designed for one
instance; scaling out would need a shared session store. Details and the
platform comparison are in `README.md` and `DECISIONS.md`.
