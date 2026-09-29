# Architecture — AI Document Assistant

_Current as of v2.1.0._

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
   | `POST /api/ask/stream` | `{question, doc_ids?}` → server-sent events: `sources`, then `token` pieces as the model writes, then `done` (or `error`). Used by the UI. |
   | `POST /api/ask` | Same request → one JSON `{answer, sources}`. |
   | `POST /api/summary` | `{id}` → a short summary of one document. |
   | `POST /api/suggestions` | `{id}` → up to 4 starter questions the LLM writes from a sample of the document. |
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
   Vanilla, no framework or build step. The design ("Modern product",
   `DESIGN.md`, v2.1.0): a documents sidebar card and a conversation card;
   answers carry their retrieved passages as source cards beside them on
   wide screens (a CSS container
   query on the conversation pane) and folded under them on narrow ones.
   Page references the model writes (`【file, Page 3】`, `(Page 3)`,
   `[Page 3]`, …) are parsed into "p. 3" chips; clicking one
   highlights the matching passage in yellow. Every dynamic string is inserted with
   `textContent` or text nodes, never `innerHTML`. All requests go through
   one `api()` helper that turns network failures and non-JSON proxy error
   pages into readable messages instead of a stuck UI. The release version
   lives once in `main.py` (`APP_VERSION`, also the FastAPI app version);
   the page repeats it in its asset URLs and footer, and a test fails if
   they drift apart.

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

**Retrieval (per question) — hybrid since v2.0.0.** All chunks of the
selected documents are ranked twice per query: by BM25 (`retriever.py`;
term statistics taken over the selected documents together, so scores are
comparable across them) and by cosine similarity of the MiniLM embeddings.
Every ranking is fused with reciprocal rank fusion (k = 60) and the top 4
kept (`DEFAULT_TOP_K`). For a follow-up there are two queries — the question
and "previous question + question" — so four rankings are fused. Each
passage keeps its cosine similarity as the displayed `score`. With one
document and one query this is exactly the "Hybrid" retriever measured in
`retrieval_eval.py` (Hit@4 0.82, MRR@10 0.70 vs 0.77 / 0.56 for embeddings
alone); a test pins that equivalence, and `retrieval_eval.py` imports the
same functions.

**Routing whole-document questions.** Similarity search answers "where
does the document talk about X". A question about the document as a whole
("what is this paper about?", "main contribution", "summarize the key
findings") resembles no passage — in testing it retrieved the reference
list, and the assistant refused. `pipeline.is_overview_question()` (a
regular expression, tested against both kinds of question) routes these to
`overview_sample()`: the document's first two chunks (abstract/introduction)
plus evenly spaced chunks, eight passages in total, split across documents.

**Generation (v1.7.0 prompt).** The LLM's job is to answer, not to quote. The
system prompt asks for a direct answer first, then explanation in its own
words, combining passages where that helps; to match the level the user asks
for; plain text with `- ` bullets (no LaTeX, tables or headings); a page
citation after each claim; and, when the passages cover only part of the
question, to answer that part and say what's missing. The grounding
contract is unchanged: no facts, numbers or examples beyond the passages,
one exact refusal string when nothing is relevant, and passages declared
untrusted content fenced between `<<<BEGIN PASSAGES>>>` / `<<<END
PASSAGES>>>`, so an instruction inside a PDF is reported, not obeyed
(`tests/test_prompt_injection.py`). With earlier turns, one more rule says
they may resolve references but are never evidence.

**Streaming.** `llm_client.ask_stream()` sends `stream: true` and yields
content deltas from the provider's SSE stream (decoded as UTF-8 explicitly —
providers omit the charset and `requests` would otherwise assume
ISO-8859-1). `main.py` fetches the sources and the *first* piece before
opening the response, so configuration, rate-limit and provider errors still
return a normal HTTP status; after that, a failure becomes an `error` event.
The turn is saved to the history only when the stream completes, so a
stopped answer never becomes context. The response carries
`X-Accel-Buffering: no` so Nginx passes events through immediately.

**Fallback model.** If the main model is still rate limited after retries
(on Groq's free tier this is usually the 200k-tokens-per-day quota), and
`LLM_FALLBACK_MODEL` is set, the same messages go once to the fallback model
(`openai/gpt-oss-20b`, which has its own quota). An empty reply — which
reasoning models occasionally return — is retried once, then reported as an
error rather than shown as a blank answer.

**Follow-up actions and suggestions.** "Explain more simply" and "Go deeper"
send an ordinary follow-up (so the last turns resolve "that"), each
restating the grounding rule, since asking for "more" invited padding from
outside knowledge in testing. Suggested questions come from a separate
prompt over the overview sample; any failure just omits them.

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

## Security Controls

| Threat | Control |
|---|---|
| Quota or CPU exhaustion by one client | Per-IP rate limits (`RATE_LIMITS`): LLM endpoints 10/min and 100/h, uploads 10/10 min; IP from `X-Real-IP` only when the peer is the loopback proxy |
| Memory exhaustion by a huge document | `MAX_CHUNKS_PER_DOC` (1500 ≈ 360 pages) checked before embedding; 5 docs/session; 50 sessions |
| Non-PDF uploads | `%PDF-` signature check in the first 1024 bytes |
| Hostile filenames | Basename only, control characters stripped, 120-character cap |
| XSS / clickjacking / injection of external resources | CSP `default-src 'self'` with no inline code, `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`; all dynamic text via `textContent` |
| Downgrade to HTTP | HSTS (1 year) over HTTPS; Nginx redirects plain HTTP, including requests to the raw IP |
| Reconnaissance | `/docs`, `/redoc`, `/openapi.json` disabled; Nginx `server_tokens off` |
| Leaking internals in errors | Generic message + reference code; details only in the server log |
| Cross-site request forgery | SameSite=Lax cookie, plus a middleware that refuses API POSTs whose `Origin` isn't this host or whose `Sec-Fetch-Site` is `cross-site` |
| Session cookie tampering | `__Host-session` over HTTPS: must be Secure, Path=/, no Domain, so no subdomain or HTTP response can set it |
| Oversized JSON bodies | 16KB cap (`Content-Length` check in middleware, and on the body actually read) |
| Overload (smoothness) | Semaphores: 4 concurrent LLM calls, 2 concurrent ingestions; wait ≤ 20s, then 503 "busy" with `Retry-After` |
| Vulnerable dependencies | Dependabot updates; `pip-audit` in CI fails the build on any known advisory |
| Cross-session access (IDOR) | Document ids are looked up only inside the caller's own session (256-bit cookie) |
| Prompt injection via PDF text | Passages fenced and declared untrusted (see Generation) |
| Third-party data flow | Page loads nothing external; only the question + retrieved passages go to the LLM provider, disclosed on the upload screen |

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
