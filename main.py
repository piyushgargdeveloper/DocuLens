"""FastAPI backend for the AI Document Assistant.

Wraps the RAG pipeline (pdf_loader -> chunker -> embedder -> vector_store ->
llm_client -> pipeline) with a minimal HTTP API and serves the static
frontend from the same origin (so no CORS setup is needed). Nothing in this
file touches retrieval, chunking, embedding, or prompt logic -- it only adapts
pipeline.ingest()/answer()/summarize() to HTTP and holds per-session state.
"""

import asyncio
import json
import os
import re
import secrets
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.concurrency import iterate_in_threadpool, run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import pipeline
import providers
from llm_client import LLMConfigError, LLMRequestError, answered_by

load_dotenv()

STATIC_DIR = Path(__file__).parent / "static"

# The release version. static/index.html repeats it (asset ?v= query, footer,
# release link) and tests/test_api.py fails if the two ever disagree.
APP_VERSION = "2.2.1"

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25MB -- unchanged from the previous UI's limit
MAX_QUESTION_CHARS = 1000  # unchanged from the previous UI's limit
MAX_DOCS_PER_SESSION = 5
MAX_SESSIONS = 50  # oldest-idle session is evicted beyond this, bounding server memory
MAX_STORED_TURNS = 10  # conversation turns kept per session (only the last few reach the LLM)
SESSION_TTL_SECONDS = 2 * 60 * 60  # 2 hours of inactivity
CLEANUP_INTERVAL_SECONDS = 5 * 60
# ~360 pages of text at the default chunking. Bounds the memory and embedding
# time one upload can take: a 25MB text-heavy PDF could otherwise hold
# gigabytes across sessions on a 2GB server.
MAX_CHUNKS_PER_DOC = 1500
MAX_FILENAME_CHARS = 120

# Per-client request limits: (max requests, window in seconds). Every
# LLM-backed call spends the shared provider quota (on Groq's free tier, a
# daily token budget), so one script could otherwise take the assistant down
# for everyone; ingestion is CPU-heavy (embedding).
RATE_LIMITS = {
    "llm": [(10, 60), (100, 60 * 60)],  # /api/ask, /api/summary, /api/suggestions
    "ingest": [(10, 10 * 60)],  # /api/ingest
}

# Sent with every response. The page loads nothing from other origins (fonts
# are self-hosted), so the policy can be 'self' throughout; the favicon is an
# inline SVG data: URL.
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}

# JSON request bodies are a question and a few ids; anything bigger is abuse.
MAX_JSON_BYTES = 16 * 1024

# How many LLM calls and ingestions may run at once. The server has 2 CPUs and
# 2GB of RAM, and the LLM provider has per-minute limits: beyond these, extra
# requests wait briefly and then get a clear "busy" answer instead of piling up
# threads and memory until everything slows down together.
LLM_CONCURRENCY = 4
INGEST_CONCURRENCY = 2
QUEUE_WAIT_SECONDS = 20
_llm_slots = asyncio.Semaphore(LLM_CONCURRENCY)
_ingest_slots = asyncio.Semaphore(INGEST_CONCURRENCY)


async def _sweep_expired_sessions() -> None:
    """Delete expired sessions on a timer, not only when a request arrives.

    Uploaded PDFs are never written to disk; their extracted text and
    embeddings live only in `_sessions`. Pruning used to run only at the start
    of a request, so with no traffic an expired session's document text could
    stay in memory indefinitely. This makes the 2-hour limit a real deadline.
    """
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        _prune_sessions()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.environ.get("LLM_API_KEY", "").strip():
        # Not fatal: uploads and retrieval still work, and every LLM-backed
        # endpoint answers 503 with a clear message. Refusing to start would
        # also break the credential-free test suite and CI.
        print("WARNING: LLM_API_KEY is not set -- questions, summaries and suggestions will fail.")
    sweeper = asyncio.create_task(_sweep_expired_sessions())
    try:
        yield
    finally:
        sweeper.cancel()


# The interactive API docs (/docs, /redoc, /openapi.json) are off: they would
# publish a map of every endpoint, and nothing here needs them in production.
app = FastAPI(
    title="AI Document Assistant",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


@app.middleware("http")
async def api_request_guard(request: Request, call_next):
    """Reject cross-site and oversized API requests before any handler runs.

    CSRF: the session cookie is already SameSite=Lax, which stops browsers
    sending it on cross-site POSTs; this is the second layer. A browser always
    sends Origin on a POST fetch and Sec-Fetch-Site on modern engines, so a
    request that another site triggers is refused outright. Requests with no
    Origin at all (curl, scripts, the test client) aren't from a browser page
    and can't carry a victim's cookie, so they pass.
    """
    if request.url.path.startswith("/api/") and request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("sec-fetch-site") == "cross-site" or not _same_origin(request):
            return _error("Cross-site requests are not allowed.", 403)
        if request.url.path != "/api/ingest":
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > MAX_JSON_BYTES:
                return _error("Request is too large.", 413)
    return await call_next(request)


@app.middleware("http")
async def response_headers(request: Request, call_next):
    """Security headers on every response, plus revalidation of the frontend.

    Without a Cache-Control header, browsers cache static files heuristically
    and may skip asking the server at all -- after the v1.2.0 deploy a browser
    kept running the old app.js against the new index.html and hung on
    "Reading and indexing document". With no-cache, an unchanged file still
    costs only a 304.
    """
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    if _is_https(request):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@dataclass
class Session:
    docs: dict[str, pipeline.IndexState] = field(default_factory=dict)  # doc_id -> index
    history: list[dict] = field(default_factory=list)  # [{"question", "answer"}], oldest first
    last_used: float = field(default_factory=time.time)


# In-memory sessions keyed by a random cookie value. A single-process
# in-memory store is the simplest sensible choice at this project's scale (a
# personal/portfolio tool, not a multi-instance service). Sessions are lost on
# restart and are not shared across processes -- see README "Known limitations".
_sessions: dict[str, Session] = {}


def _prune_sessions() -> None:
    now = time.time()
    for sid in [sid for sid, s in _sessions.items() if now - s.last_used > SESSION_TTL_SECONDS]:
        del _sessions[sid]
    while len(_sessions) > MAX_SESSIONS:
        oldest = min(_sessions, key=lambda sid: _sessions[sid].last_used)
        del _sessions[oldest]
    # Rate-limit history older than the longest window is no longer needed.
    longest = max(window for limits in RATE_LIMITS.values() for _, window in limits)
    for key in [k for k, hits in _rate_log.items() if not hits or now - hits[-1] > longest]:
        del _rate_log[key]


# (client, bucket) -> timestamps of recent allowed requests, oldest first.
_rate_log: dict[tuple[str, str], deque] = {}


def _client_ip(request: Request) -> str:
    """The caller's address. The app only listens on 127.0.0.1 in production,
    so a loopback peer is Nginx, which overwrites X-Real-IP with the real
    client address; the header is ignored from anyone else, so it can't be
    spoofed to dodge the rate limit."""
    peer = request.client.host if request.client else "unknown"
    if peer in ("127.0.0.1", "::1"):
        return request.headers.get("x-real-ip", peer)
    return peer


def _rate_limited(request: Request, bucket: str) -> JSONResponse | None:
    """A 429 response if this client is over any of the bucket's limits,
    otherwise None (and the request is counted)."""
    now = time.time()
    hits = _rate_log.setdefault((_client_ip(request), bucket), deque())
    longest = max(window for _, window in RATE_LIMITS[bucket])
    while hits and now - hits[0] > longest:
        hits.popleft()
    for limit, window in RATE_LIMITS[bucket]:
        recent = [t for t in hits if now - t <= window]
        if len(recent) >= limit:
            retry_after = int(window - (now - recent[0])) + 1
            response = _error(
                f"Too many requests. Please wait about {max(1, round(retry_after / 60))} "
                f"minute(s) and try again.",
                429,
            )
            response.headers["Retry-After"] = str(retry_after)
            return response
    hits.append(now)
    return None


def _cookie_name(request: Request) -> str:
    """Over HTTPS the session cookie uses the __Host- prefix: browsers then
    only accept it if it is Secure, has Path=/ and no Domain, so no subdomain
    or plain-HTTP response can set or overwrite it. (Plain-HTTP local runs
    can't use the prefix.)"""
    return "__Host-session" if _is_https(request) else "session_id"


def _get_session(request: Request) -> Session | None:
    session = _sessions.get(request.cookies.get(_cookie_name(request), ""))
    if session is not None:
        session.last_used = time.time()
    return session


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True
    return urlsplit(origin).netloc == request.headers.get("host", "")


async def _take_slot(slots: asyncio.Semaphore) -> bool:
    try:
        await asyncio.wait_for(slots.acquire(), timeout=QUEUE_WAIT_SECONDS)
        return True
    except asyncio.TimeoutError:
        return False


def _busy() -> JSONResponse:
    response = _error("The assistant is busy right now. Please try again in a few seconds.", 503)
    response.headers["Retry-After"] = "10"
    return response


def _is_https(request: Request) -> bool:
    """True if this request reached us over HTTPS, directly or via Nginx.

    Nginx (see DECISIONS.md) forwards X-Forwarded-Proto based on its own
    $scheme, so the session cookie is marked Secure exactly when the browser
    is on HTTPS, with no code change needed between local and deployed runs.
    """
    if request.url.scheme == "https":
        return True
    forwarded_proto = request.headers.get("x-forwarded-proto", "")
    return forwarded_proto.split(",")[0].strip().lower() == "https"


def _error(message: str, status_code: int) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status_code)


async def _json_body(request: Request) -> dict:
    """Parsed JSON object body, or {} for a missing/invalid/non-object/oversized
    body (the size check also covers bodies sent without Content-Length)."""
    raw = await request.body()
    if len(raw) > MAX_JSON_BYTES:
        return {}
    try:
        body = json.loads(raw)
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


async def _question_request(request: Request) -> tuple[Session, str, list] | JSONResponse:
    """Validate an ask request: a session with documents, a question, and an
    optional `doc_ids` list choosing which of the session's documents to search."""
    session = _get_session(request)
    if session is None or not session.docs:
        return _error("No document is loaded. Please upload a PDF first.", 400)

    body = await _json_body(request)
    question = body.get("question")
    question = question.strip() if isinstance(question, str) else ""
    if not question:
        return _error("Please enter a question.", 400)
    if len(question) > MAX_QUESTION_CHARS:
        return _error(f"Question is too long (max {MAX_QUESTION_CHARS} characters).", 400)

    doc_ids = body.get("doc_ids")
    if doc_ids is None:
        states = list(session.docs.values())
    else:
        if not isinstance(doc_ids, list):
            return _error("doc_ids must be a list.", 400)
        # Only ids from this session count: another session's ids simply don't match.
        states = [session.docs[d] for d in doc_ids if isinstance(d, str) and d in session.docs]
        if not states:
            return _error("Choose at least one of your documents to search.", 400)
    return session, question, states


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _documents(session: Session) -> list[dict]:
    return [
        {"id": doc_id, "filename": s.name, "num_pages": s.num_pages, "num_chunks": s.num_chunks}
        for doc_id, s in session.docs.items()
    ]


def _unique_name(session: Session, filename: str) -> str:
    """Filenames label sources in answers, so two uploads of 'notes.pdf'
    become 'notes.pdf' and 'notes.pdf (2)'."""
    taken = {s.name for s in session.docs.values()}
    name, n = filename, 2
    while name in taken:
        name, n = f"{filename} ({n})", n + 1
    return name


def _clean_filename(raw: str | None) -> str:
    """Basename only, no control characters, at most MAX_FILENAME_CHARS
    (keeping the extension). Filenames are shown in the UI and label passages
    in the prompt, so an attacker-chosen name must stay short and inert."""
    name = re.sub(r"[\x00-\x1f\x7f]", "", Path(raw or "").name).strip()
    if len(name) > MAX_FILENAME_CHARS:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: MAX_FILENAME_CHARS - len(ext) - 2] + "…" + dot + ext) if dot else name[:MAX_FILENAME_CHARS]
    return name


def _server_error(e: Exception, action: str, message: str, status_code: int) -> JSONResponse:
    """Log the real error with a short reference and return a generic message
    carrying the same reference, so a user's report can be matched to the log
    without exposing internals (CodeQL py/stack-trace-exposure)."""
    reference = secrets.token_hex(4)
    print(f"[{reference}] Error while {action}: {e!r}")
    return _error(f"{message} (reference {reference})", status_code)


def _llm_error_response(e: Exception, action: str) -> JSONResponse:
    if isinstance(e, LLMConfigError):
        return _server_error(
            e, action, "The assistant is not configured correctly. Please contact the site administrator.", 503
        )
    if isinstance(e, LLMRequestError):
        return _server_error(e, action, "The LLM API request failed. Please try again in a moment.", 502)
    return _server_error(e, action, f"Something went wrong while {action}. Please try again.", 500)


@app.post("/api/ingest")
async def ingest(request: Request, file: UploadFile = File(...)):
    _prune_sessions()
    if limited := _rate_limited(request, "ingest"):
        return limited

    filename = _clean_filename(file.filename)
    if not filename.lower().endswith(".pdf"):
        return _error("Please upload a PDF file.", 400)

    session = _get_session(request)
    if session is not None and len(session.docs) >= MAX_DOCS_PER_SESSION:
        return _error(f"You can load up to {MAX_DOCS_PER_SESSION} documents at once. Remove one first.", 400)

    # Read at most one byte past the limit, so an oversized upload is never
    # held in memory in full.
    pdf_bytes = await file.read(MAX_UPLOAD_BYTES + 1)
    # Uploads over 1MB are spooled by Starlette to an anonymous temporary
    # file; close it now rather than at the end of the request, so no copy
    # of the PDF outlives this read. From here on only the extracted text is
    # kept, in memory, until the document is removed or the session expires.
    await file.close()
    if len(pdf_bytes) > MAX_UPLOAD_BYTES:
        return _error("File is too large. The limit is 25MB.", 413)
    # The extension is only a claim; a PDF starts with "%PDF-" within its
    # first 1024 bytes (the spec allows leading junk).
    if b"%PDF-" not in pdf_bytes[:1024]:
        return _error("That file isn't a PDF. Please upload a PDF file.", 400)

    name = _unique_name(session, filename) if session else filename
    if not await _take_slot(_ingest_slots):
        return _busy()
    try:
        # Extraction + embedding is CPU-bound; running it in a worker thread
        # keeps the event loop free to serve other users meanwhile.
        index_state = await run_in_threadpool(
            pipeline.ingest, pdf_bytes, name=name, max_chunks=MAX_CHUNKS_PER_DOC
        )
    except pipeline.DocumentTooLargeError:
        return _error(
            "This PDF has too much text to process here (roughly 360 pages is the limit). "
            "Try a shorter document or split it.",
            413,
        )
    except Exception as e:
        # Previously this fell through to the "couldn't extract any text"
        # message, which misreported server faults as a bad PDF.
        return _server_error(e, "reading the document", "Something went wrong while reading this PDF.", 500)
    finally:
        _ingest_slots.release()

    if index_state is None:
        return _error(
            "Couldn't extract any text from this PDF. It may be empty, image-only "
            "(scanned without OCR), password-protected, or corrupted.",
            422,
        )

    # Look the session up again: it may have expired or been evicted while
    # this upload was being indexed.
    session = _get_session(request)
    is_new_session = session is None
    if is_new_session:
        session_id = secrets.token_urlsafe(32)
        session = Session()
        _sessions[session_id] = session
        _prune_sessions()

    doc_id = secrets.token_urlsafe(8)
    session.docs[doc_id] = index_state

    response = JSONResponse(
        {
            "id": doc_id,
            "filename": index_state.name,
            "num_pages": index_state.num_pages,
            "num_chunks": index_state.num_chunks,
            "documents": _documents(session),
        }
    )
    if is_new_session:
        response.set_cookie(
            _cookie_name(request),
            session_id,
            httponly=True,
            samesite="lax",
            secure=_is_https(request),
            max_age=SESSION_TTL_SECONDS,
        )
    return response


@app.get("/api/session")
async def get_session(request: Request):
    """Current documents and conversation, so a page reload can restore the UI."""
    session = _get_session(request)
    if session is None:
        return {"documents": [], "history": []}
    return {"documents": _documents(session), "history": session.history}


def _turn(question: str, answer: str, by: dict | None) -> dict:
    """One conversation turn as stored in the session (and restored on reload)."""
    turn = {"question": question, "answer": answer}
    if by:
        turn["answered_by"] = by
    return turn


@app.get("/api/status")
async def status():
    """The AI providers this server can use and whether each is usable right
    now, for the footer. Names and models only -- never keys or URLs."""
    return {"version": APP_VERSION, "providers": providers.status()}


@app.get("/api/health")
async def health():
    """Liveness check for the container (no LLM call)."""
    return {"ok": True}


@app.post("/api/ask")
async def ask(request: Request):
    """Answer as one JSON response (the UI uses /api/ask/stream)."""
    _prune_sessions()
    if limited := _rate_limited(request, "llm"):
        return limited
    checked = await _question_request(request)
    if isinstance(checked, JSONResponse):
        return checked
    session, question, states = checked

    if not await _take_slot(_llm_slots):
        return _busy()
    try:
        result = await run_in_threadpool(pipeline.answer, question, states, history=list(session.history))
    except Exception as e:
        return _llm_error_response(e, "answering that question")
    finally:
        _llm_slots.release()

    by = answered_by(result["answer"])
    session.history.append(_turn(question, result["answer"], by))
    del session.history[:-MAX_STORED_TURNS]
    return {"answer": result["answer"], "sources": result["sources"], "answered_by": by}


@app.post("/api/ask/stream")
async def ask_stream(request: Request):
    """Answer as server-sent events: `sources` first, then `route` (which
    provider and model is answering), then `token` events as the model
    writes, then `done` (or `error`).

    Retrieval and the first piece of the answer are fetched *before* the
    response starts, so a missing API key, a rate limit or a provider failure
    still produces a proper HTTP status and message instead of a stream that
    breaks halfway. If the client disconnects (the Stop button), the turn is
    not saved to the conversation history.
    """
    _prune_sessions()
    if limited := _rate_limited(request, "llm"):
        return limited
    checked = await _question_request(request)
    if isinstance(checked, JSONResponse):
        return checked
    session, question, states = checked

    if not await _take_slot(_llm_slots):
        return _busy()
    try:
        sources, pieces = await run_in_threadpool(
            pipeline.answer_stream, question, states, history=list(session.history)
        )
        first = await run_in_threadpool(next, pieces, "")
    except Exception as e:
        _llm_slots.release()
        return _llm_error_response(e, "answering that question")

    by = answered_by(first)

    async def events():
        parts = [first] if first else []
        completed = False
        try:
            yield _sse("sources", sources)
            if by:
                yield _sse("route", by)
            if first:
                yield _sse("token", {"text": first})
            async for piece in iterate_in_threadpool(pieces):
                parts.append(piece)
                yield _sse("token", {"text": piece})
            completed = True
            answer = "".join(parts)
            session.history.append(_turn(question, answer, by))
            del session.history[:-MAX_STORED_TURNS]
            yield _sse("done", {})
        except Exception as e:
            reference = secrets.token_hex(4)
            print(f"[{reference}] Error while streaming an answer: {e!r}")
            yield _sse("error", {"error": f"The answer was interrupted. Please try again. (reference {reference})"})
        finally:
            if not completed:
                try:
                    pieces.close()  # stop reading from the provider
                except ValueError:
                    pass  # still running in its worker thread; it ends on its own
            _llm_slots.release()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        # X-Accel-Buffering stops Nginx from holding the stream back until it ends.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/summary")
async def summary(request: Request):
    if limited := _rate_limited(request, "llm"):
        return limited
    session = _get_session(request)
    if session is None or not session.docs:
        return _error("No document is loaded. Please upload a PDF first.", 400)

    body = await _json_body(request)
    index_state = session.docs.get(body.get("id"))
    if index_state is None:
        return _error("That document is not loaded.", 404)

    if not await _take_slot(_llm_slots):
        return _busy()
    try:
        result = await run_in_threadpool(pipeline.summarize, index_state)
    except Exception as e:
        return _llm_error_response(e, "summarizing the document")
    finally:
        _llm_slots.release()
    return {
        "filename": index_state.name,
        "summary": result["summary"],
        "sources": result["sources"],
        "answered_by": answered_by(result["summary"]),
    }


@app.post("/api/suggestions")
async def suggestions(request: Request):
    """Starter questions for a document, written by the LLM from a sample of it."""
    if limited := _rate_limited(request, "llm"):
        return limited
    session = _get_session(request)
    if session is None or not session.docs:
        return _error("No document is loaded. Please upload a PDF first.", 400)

    body = await _json_body(request)
    index_state = session.docs.get(body.get("id"))
    if index_state is None:
        return _error("That document is not loaded.", 404)

    if not await _take_slot(_llm_slots):
        return _busy()
    try:
        questions = await run_in_threadpool(pipeline.suggest_questions, index_state)
    except Exception as e:
        return _llm_error_response(e, "suggesting questions")
    finally:
        _llm_slots.release()
    return {"questions": questions}


@app.post("/api/remove")
async def remove(request: Request):
    """Remove one document (body {"id": ...}) or, with no id, everything."""
    session_id = request.cookies.get(_cookie_name(request), "")
    session = _sessions.get(session_id)
    doc_id = (await _json_body(request)).get("id")

    if session is not None and doc_id is not None:
        session.docs.pop(doc_id, None)
        if session.docs:
            return {"ok": True, "documents": _documents(session)}

    _sessions.pop(session_id, None)
    response = JSONResponse({"ok": True, "documents": []})
    response.delete_cookie(_cookie_name(request), secure=_is_https(request), httponly=True, samesite="lax")
    return response


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")
