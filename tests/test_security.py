"""Security controls from the pre-deploy / attacker-perspective review
(see DECISIONS.md, 2026-09-29 security audit)."""

import re

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    return TestClient(main.app)


def _upload(client, data, name="a.pdf", headers=None):
    return client.post("/api/ingest", files={"file": (name, data, "application/pdf")}, headers=headers or {})


# --- Headers and exposure ----------------------------------------------------


@pytest.mark.parametrize("path", ["/", "/static/app.js", "/api/session"])
def test_security_headers_on_every_response(client, path):
    headers = client.get(path).headers
    assert "default-src 'self'" in headers["content-security-policy"]
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert "strict-transport-security" not in headers  # plain HTTP here


def test_hsts_only_over_https(client):
    headers = client.get("/", headers={"X-Forwarded-Proto": "https"}).headers
    assert headers["strict-transport-security"].startswith("max-age=31536000")


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_docs_are_not_published(client, path):
    assert client.get(path).status_code == 404


def test_page_loads_nothing_from_other_origins(client):
    html = client.get("/").text
    css = client.get("/static/style.css").text
    assert not re.search(r"(src|href)=\"https?://(?!github\.com)", html)  # only the footer links leave the site
    assert "https://" not in css
    assert client.get("/static/fonts/inter-variable.woff2").status_code == 200


# --- Uploads -----------------------------------------------------------------


def test_file_that_is_not_really_a_pdf_is_rejected(client):
    response = _upload(client, b"MZ\x90\x00 an executable renamed to .pdf", name="invoice.pdf")
    assert response.status_code == 400
    assert "isn't a PDF" in response.json()["error"]


def test_document_with_too_much_text_is_rejected_before_embedding(client, sample_pdf_bytes, monkeypatch):
    monkeypatch.setattr(main, "MAX_CHUNKS_PER_DOC", 1)
    embedded = []
    monkeypatch.setattr(main.pipeline.embedder, "embed", lambda texts: embedded.append(texts))
    response = _upload(client, sample_pdf_bytes)
    assert response.status_code == 413
    assert embedded == []  # never reached the embedding model


def test_filenames_are_shortened_and_stripped_of_control_characters():
    long = "x" * 300 + ".pdf"
    assert len(main._clean_filename(long)) <= main.MAX_FILENAME_CHARS
    assert main._clean_filename(long).endswith(".pdf")
    assert main._clean_filename("../../etc/re\x00port\n.pdf") == "report.pdf"


def test_unexpected_ingestion_failure_is_a_500_with_a_reference_not_a_bad_pdf(client, sample_pdf_bytes, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("embedding model failed to load: /internal/path")

    monkeypatch.setattr(main.pipeline, "ingest", boom)
    response = _upload(client, sample_pdf_bytes)
    assert response.status_code == 500
    error = response.json()["error"]
    assert re.search(r"reference [0-9a-f]{8}", error)
    assert "/internal/path" not in error


# --- Rate limiting -----------------------------------------------------------


def test_ingest_is_rate_limited_per_client(client, sample_pdf_bytes, monkeypatch):
    monkeypatch.setitem(main.RATE_LIMITS, "ingest", [(2, 600)])
    assert _upload(client, sample_pdf_bytes).status_code == 200
    assert _upload(client, sample_pdf_bytes).status_code == 200
    third = _upload(client, sample_pdf_bytes)
    assert third.status_code == 429
    assert int(third.headers["retry-after"]) > 0


def test_llm_endpoints_share_a_rate_limit(client, sample_pdf_bytes, monkeypatch):
    import llm_client

    monkeypatch.setitem(main.RATE_LIMITS, "llm", [(2, 60)])
    monkeypatch.setattr(llm_client, "ask", lambda q, p, timeout=30, history=None: "ok")
    monkeypatch.setattr(llm_client, "suggest_questions", lambda p, timeout=30: ["Q?"])
    doc = _upload(client, sample_pdf_bytes).json()
    assert client.post("/api/ask", json={"question": "a?"}).status_code == 200
    assert client.post("/api/suggestions", json={"id": doc["id"]}).status_code == 200
    assert client.post("/api/ask", json={"question": "b?"}).status_code == 429


def test_x_real_ip_from_a_non_proxy_peer_cannot_dodge_the_limit(client, sample_pdf_bytes, monkeypatch):
    monkeypatch.setitem(main.RATE_LIMITS, "ingest", [(1, 600)])
    assert _upload(client, sample_pdf_bytes, headers={"X-Real-IP": "1.1.1.1"}).status_code == 200
    # A different claimed address from the same (non-loopback) peer is the same client.
    assert _upload(client, sample_pdf_bytes, headers={"X-Real-IP": "2.2.2.2"}).status_code == 429


# --- Access control ----------------------------------------------------------


def test_one_session_cannot_reach_another_sessions_document(sample_pdf_bytes, monkeypatch):
    import llm_client

    monkeypatch.setattr(llm_client, "summarize", lambda p, timeout=30: "secret summary")
    alice, mallory = TestClient(main.app), TestClient(main.app)
    doc = _upload(alice, sample_pdf_bytes).json()
    _upload(mallory, sample_pdf_bytes)
    # Mallory knows (or guesses) Alice's document id but has her own session.
    assert mallory.post("/api/summary", json={"id": doc["id"]}).status_code == 404
    assert mallory.post("/api/remove", json={"id": doc["id"]}).json()["documents"] != []
    assert alice.post("/api/summary", json={"id": doc["id"]}).status_code == 200
