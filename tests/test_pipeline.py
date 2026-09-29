import os

import pytest

import pipeline

requires_api_key = pytest.mark.skipif(
    not os.environ.get("LLM_API_KEY"),
    reason="LLM_API_KEY not set; skipping tests that call a real LLM API",
)


def test_ingest_invalid_pdf_returns_none():
    assert pipeline.ingest(b"not a real pdf") is None


def test_ingest_valid_pdf_returns_populated_index_state(sample_pdf_bytes):
    state = pipeline.ingest(sample_pdf_bytes)
    assert state.num_pages == 4
    assert state.num_chunks > 0


@requires_api_key
def test_answer_end_to_end_is_grounded_and_cites_the_right_page(sample_pdf_bytes):
    state = pipeline.ingest(sample_pdf_bytes)
    result = pipeline.answer("What is Jupiter known for?", state)
    assert "jupiter" in result["answer"].lower()
    assert result["sources"]
    assert result["sources"][0]["page"] == 3


def test_retrieve_merges_documents_and_keeps_top_k_best_first(sample_pdf_bytes):
    a = pipeline.ingest(sample_pdf_bytes, name="a.pdf")
    b = pipeline.ingest(sample_pdf_bytes, name="b.pdf")
    hits = pipeline.retrieve(["What is Jupiter known for?"], [a, b], top_k=4)
    assert len(hits) == 4
    assert {h["doc"] for h in hits} == {"a.pdf", "b.pdf"}
    assert [h["score"] for h in hits] == sorted((h["score"] for h in hits), reverse=True)


def test_single_document_retrieval_matches_the_plain_vector_search(sample_pdf_bytes):
    # Guards the documented evaluate.py results: one query + one document must
    # behave exactly as before multi-document support was added.
    state = pipeline.ingest(sample_pdf_bytes)
    query = "Which planet has the largest mass?"
    direct = state.store.search(pipeline.embedder.embed([query])[0], top_k=3)
    assert pipeline.retrieve([query], [state], top_k=3) == direct
    assert "doc" not in direct[0]


def test_follow_up_retrieval_also_uses_the_previous_question(sample_pdf_bytes, monkeypatch):
    seen = {}
    monkeypatch.setattr(pipeline, "retrieve", lambda queries, states, top_k: seen.setdefault("q", queries) and [])
    monkeypatch.setattr(pipeline.llm_client, "ask", lambda q, p, history=None: "ok")
    state = pipeline.ingest(sample_pdf_bytes)
    history = [{"question": "Tell me about Saturn", "answer": "Saturn has rings."}]
    pipeline.answer("How many moons does it have?", state, history=history)
    assert seen["q"] == ["How many moons does it have?", "Tell me about Saturn How many moons does it have?"]


def test_summarize_samples_chunks_across_the_document(sample_pdf_bytes, monkeypatch):
    monkeypatch.setattr(pipeline.llm_client, "summarize", lambda passages: f"{len(passages)} passages")
    state = pipeline.ingest(sample_pdf_bytes, chunk_size=200, chunk_overlap=20)
    result = pipeline.summarize(state)
    pages = {s["page"] for s in result["sources"]}
    assert len(result["sources"]) == min(pipeline.SUMMARY_SAMPLE_CHUNKS, state.num_chunks)
    assert pages == {1, 2, 3, 4}


# --- Whole-document questions are routed away from similarity search -------

OVERVIEW = [
    "What is the main contribution of this paper, in simple words?",
    "What is this document about?",
    "Summarize the key findings.",
    "whats the paper about",
    "Give me a short summary",
    "tl;dr please",
]
SPECIFIC = [
    "How many heads are used?",
    "What is the summary statistic used in table 2?",
    "Explain multi-head attention to a beginner.",
    "What is the key size dk?",
]


@pytest.mark.parametrize("question", OVERVIEW)
def test_overview_questions_are_detected(question):
    assert pipeline.is_overview_question(question)


@pytest.mark.parametrize("question", SPECIFIC)
def test_specific_questions_are_not_treated_as_overview(question):
    assert not pipeline.is_overview_question(question)


def test_overview_sample_starts_with_the_opening_and_spans_the_document(sample_pdf_bytes):
    state = pipeline.ingest(sample_pdf_bytes, chunk_size=120, chunk_overlap=20)
    sample = pipeline.overview_sample(state, count=5)
    chunks = state.store.chunks
    assert len(sample) == 5
    assert sample[:2] == chunks[:2]  # abstract / introduction always included
    positions = [chunks.index(c) for c in sample]
    assert positions == sorted(positions)  # document order
    assert sample[-1]["page"] > sample[0]["page"]  # reaches past the opening


def test_overview_question_uses_the_sample_not_retrieval(sample_pdf_bytes, monkeypatch):
    def no_retrieval(*args, **kwargs):
        raise AssertionError("similarity search should not run for an overview question")

    seen = {}
    monkeypatch.setattr(pipeline, "retrieve", no_retrieval)
    monkeypatch.setattr(pipeline.llm_client, "ask", lambda q, p, history=None: seen.setdefault("p", p) and "ok")
    state = pipeline.ingest(sample_pdf_bytes)
    result = pipeline.answer("What is this document about?", state)
    assert result["sources"] and all(s["score"] is None for s in result["sources"])
    assert seen["p"][0]["page"] == 1
