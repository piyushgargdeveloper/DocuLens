"""Phase 6: orchestration — wires loader, chunker, embedder, vector store, LLM."""

import re
from dataclasses import dataclass

import embedder
import llm_client
from chunker import chunk_pages
from pdf_loader import load_pdf_pages
from vector_store import VectorStore

DEFAULT_CHUNK_SIZE = 800
DEFAULT_CHUNK_OVERLAP = 150
DEFAULT_TOP_K = 4
MAX_HISTORY_TURNS = 3  # earlier Q/A turns sent to the LLM for follow-up questions
SUMMARY_SAMPLE_CHUNKS = 10  # evenly spaced chunks fed to the summary prompt
OVERVIEW_CHUNKS = 8  # passages given to the LLM for a whole-document question
OVERVIEW_LEAD_CHUNKS = 2  # always include the opening (abstract/introduction)

# Questions about the document as a whole ("what is this about?", "main
# contribution", "summarize the key findings"). Similarity search is the wrong
# tool for these: no single passage resembles the question, so it returns
# whatever shares a word with it -- in testing, the reference list.
OVERVIEW_PATTERN = re.compile(
    r"\b(summari[sz](e|ing)"  # "summarize", "summarising" (verb, not "summary statistic")
    r"|summary(?= of| please|\s*\?|\s*$)|(give|write|need|want)( me)? (a |the )?(short |quick |brief )?summary"
    r"|overview|gist|tl;?dr|in a nutshell"
    r"|(main|key|central|overall|primary|core|biggest) (idea|point|message|contribution|finding|takeaway|argument|goal|topic|theme)s?"
    r"|what('?s| is| are)? (this|the) (document|paper|pdf|file|report|article|book|text)s? (about|for)"
    r"|what does (this|the) (document|paper|pdf|file|report|article|book|text) (do|say|propose|cover))\b",
    re.IGNORECASE,
)


class DocumentTooLargeError(ValueError):
    """The document would produce more chunks than the caller allows."""


@dataclass
class IndexState:
    store: VectorStore
    num_pages: int
    num_chunks: int
    chunk_size: int
    chunk_overlap: int
    name: str | None = None


def ingest(
    pdf_bytes: bytes,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    name: str | None = None,
    max_chunks: int | None = None,
) -> IndexState | None:
    """Run extraction -> chunking -> embedding -> indexing. Returns None if the
    PDF has no extractable text (invalid/empty PDF).

    With `max_chunks`, raises DocumentTooLargeError *before* embedding, so an
    oversized document never costs the memory or CPU time of being indexed.

    `name` (e.g. the uploaded filename) is tagged onto every chunk so answers
    across several documents can say which document a passage came from."""
    pages = load_pdf_pages(pdf_bytes)
    if not pages:
        return None

    chunks = chunk_pages(pages, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if not chunks:
        return None
    if max_chunks is not None and len(chunks) > max_chunks:
        raise DocumentTooLargeError(f"{len(chunks)} chunks > {max_chunks}")
    if name:
        for chunk in chunks:
            chunk["doc"] = name

    vectors = embedder.embed([c["text"] for c in chunks])
    store = VectorStore(chunks, vectors)
    return IndexState(
        store=store,
        num_pages=len(pages),
        num_chunks=len(chunks),
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        name=name,
    )


def retrieve(queries: list[str], states: list[IndexState], top_k: int = DEFAULT_TOP_K) -> list[dict]:
    """Search every document with every query and return the overall top_k
    passages, best first. A passage found by more than one query keeps its
    highest score. With one query and one document this is exactly
    `store.search(query, top_k)`."""
    query_vectors = embedder.embed(queries)
    best: dict[tuple, dict] = {}
    for state in states:
        for vector in query_vectors:
            for hit in state.store.search(vector, top_k=top_k):
                key = (hit.get("doc"), hit["page"], hit["text"])
                if key not in best or hit["score"] > best[key]["score"]:
                    best[key] = hit
    return sorted(best.values(), key=lambda h: h["score"], reverse=True)[:top_k]


def is_overview_question(question: str) -> bool:
    """True for questions about a whole document rather than a specific fact."""
    return bool(OVERVIEW_PATTERN.search(question))


def overview_sample(index_state: IndexState, count: int = OVERVIEW_CHUNKS) -> list[dict]:
    """The opening chunks (abstract/introduction) plus evenly spaced chunks
    from the rest, in document order -- a cheap stand-in for reading it all."""
    chunks = index_state.store.chunks
    if len(chunks) <= count:
        return list(chunks)
    lead = chunks[:OVERVIEW_LEAD_CHUNKS]
    rest = chunks[OVERVIEW_LEAD_CHUNKS:]
    picks = count - len(lead)
    step = len(rest) / picks
    return lead + [rest[int(i * step)] for i in range(picks)]


def answer(
    question: str,
    index_state: IndexState | list[IndexState],
    top_k: int = DEFAULT_TOP_K,
    history: list[dict] | None = None,
) -> dict:
    """Retrieve relevant chunks and generate a grounded answer.

    `index_state` may be one document or a list of documents. `history` is a
    list of earlier {"question", "answer"} turns, oldest first. For a
    follow-up, retrieval also runs on the previous question + this one, so
    "what about its moons?" can still find the passages about "it".

    A whole-document question ("what is this paper about?") is routed to an
    overview sample of each document instead of similarity search.

    Returns {"answer": str, "sources": [{"page", "text", "score", ["doc"]}, ...]}.
    """
    states = index_state if isinstance(index_state, list) else [index_state]
    recent = (history or [])[-MAX_HISTORY_TURNS:]

    if is_overview_question(question):
        per_doc = max(3, OVERVIEW_CHUNKS // len(states))
        sources = [{**c, "score": None} for state in states for c in overview_sample(state, per_doc)]
        answer_text = llm_client.ask(question, sources, history=recent)
        return {"answer": answer_text, "sources": sources}

    queries = [question]
    if recent:
        queries.append(f"{recent[-1]['question']} {question}")

    sources = retrieve(queries, states, top_k=top_k)
    answer_text = llm_client.ask(question, sources, history=recent)
    return {"answer": answer_text, "sources": sources}


def summarize(index_state: IndexState) -> dict:
    """Summarize one document from evenly spaced chunks across it (a full
    map-reduce over every chunk would cost one LLM call per chunk, which
    free-tier rate limits don't allow for larger PDFs).

    Returns {"summary": str, "sources": [...]} in the same shape as answer()."""
    chunks = index_state.store.chunks
    count = min(SUMMARY_SAMPLE_CHUNKS, len(chunks))
    step = len(chunks) / count
    sample = [chunks[int(i * step)] for i in range(count)]
    summary_text = llm_client.summarize(sample)
    return {"summary": summary_text, "sources": [{**c, "score": None} for c in sample]}


def suggest_questions(index_state: IndexState) -> list[str]:
    """Up to 4 starter questions for a document, written by the LLM from an
    overview sample of it."""
    return llm_client.suggest_questions(overview_sample(index_state))
