# Security Policy

## Supported versions

Releases are tagged on `main` (`vX.Y.Z`, see the GitHub Releases page),
but there are no maintained release branches. Only the latest release —
which is what runs at https://doculens.duckdns.org — is
supported. Security fixes land on `main` and ship as a new patch release.

## What this project already does

For context before reporting an issue, see the "Security notes" section of
`README.md`. In short:

- **Prompt injection hardening** — retrieved document passages are fenced in
  the LLM prompt (`<<<BEGIN PASSAGES>>> … <<<END PASSAGES>>>`) and declared
  untrusted data. **Fence tokens in uploaded text and filenames are
  sanitized** (replaced with inert Unicode lookalikes) so they cannot break
  the prompt structure. **Conversation history is explicitly labelled as
  untrusted reference only** ("Earlier user question (untrusted reference
  only):") so a prior model answer cannot silently become a higher-priority
  rule. Every question prompt ends with a reminder of that rule after the
  passages, so instructions embedded in an uploaded document should not be
  obeyed (verified against injection payloads — see `tests/test_prompt_injection.py`).
- LLM provider keys are read only from the environment (`GEMINI_API_KEY`,
  `GROQ_API_KEY` or `LLM_API_KEY`, `OPENROUTER_API_KEY`, `NVIDIA_API_KEY`, `HF_TOKEN`); the
  public `/api/status` shows provider names, models and availability only.
  Keys are never
  logged, rendered, or committed. `.env` is gitignored; only `.env.example`
  (placeholders) is tracked.
- The session cookie is `httponly`, `samesite=lax`, and `Secure` over HTTPS.
  **Active API responses refresh the cookie's max-age without rotating the
  session ID**, so a user stays logged in during active use.
- Error responses never include exception text or stack traces; details are
  logged on the server only.
- Uploaded PDFs are never written to disk; their extracted text lives only
  in memory and is deleted on removal or after 2 hours of inactivity (a
  background task enforces this every 5 minutes).
- Resources are bounded: 25MB uploads (never read past the limit), 1000-
  character questions, 5 documents per session, 50 sessions, 2-hour expiry.
  **Aggregate chunk budget (`MAX_TOTAL_CHUNKS=75000` default) caps per-session
  memory; a 503 is returned before embedding if the budget would be
  exceeded.**
- Document and model text is inserted into the page with `textContent` /
  text nodes only, never as HTML or markdown.
- Strict Content-Security-Policy and other security headers on every
  response; HSTS over HTTPS; API docs endpoints disabled; no third-party
  requests from the page (fonts are self-hosted).
- Per-client rate limits on LLM-backed endpoints and uploads, and caps on
  concurrent LLM calls and ingestions. **Client IP comes from `X-Real-IP`,
  trusted only from configured CIDR networks (`TRUSTED_PROXIES`, default
  loopback only).** Behind Docker/Nginx, add the proxy network to the CIDR
  list.
- Cross-site API requests are refused (Origin / Sec-Fetch-Site), the
  session cookie is `__Host-` prefixed over HTTPS, and JSON bodies are
  capped at 16KB.
- CI runs `pip-audit`; a known vulnerability in any installed dependency
  fails the build and blocks merging.
- Uploads are checked for a real PDF signature, filenames are sanitised, and
  oversized documents are rejected before embedding. OCR of scanned PDFs is
  bounded (at most 30 pages) so an upload can't turn into unbounded CPU work.
- The upload screen discloses that questions and relevant passages are sent
  to the LLM provider.
- **RAG abstention**: non-overview questions where all retrieved passages
  score below `RETRIEVAL_SCORE_FLOOR` (default 0.30, calibrated from
  `retrieval_eval.py`) receive empty context and the model refuses with "I
  could not find the answer..." instead of hallucinating.
- **Streaming resilience**: stream read errors are wrapped in `LLMRequestError`
  so provider failover and cooldown trigger correctly when a connection drops
  mid-stream. Reasoning deltas are preserved and streamed to the UI.
- Dependencies are watched by Dependabot, and CodeQL scans every push.
- The container runs as an unprivileged user (uid 10001), not root, so a
  hypothetical code-execution bug in a dependency is not already root inside
  the container (v2.2.2).
- In deployment the app binds only to `127.0.0.1`; Nginx terminates TLS
  (1.2/1.3 only), overwrites `X-Real-IP` with the real peer so the rate limit
  can't be spoofed, and answers HTTPS only for the site's own hostname.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for a security vulnerability.

GitHub's private vulnerability reporting is not currently enabled on this
repository, so please report privately by contacting the maintainer
directly via GitHub —
[@piyushgargog](https://github.com/piyushgargog) — instead of filing a
public issue.

Please include:
- A description of the issue and its potential impact.
- Steps to reproduce, or a minimal example (a crafted PDF or prompt, for
  example — not real personal data).
- Which part of the app is affected (ingestion, retrieval, the LLM call, the
  UI, etc.).

## Scope

In scope: this application's own code — prompt construction and grounding,
handling of uploaded files, secret handling, the FastAPI backend
(`main.py`), and the frontend (`static/`).

Out of scope: the underlying third-party LLM provider's model behavior or
infrastructure (e.g. Groq, OpenAI, or any other OpenAI-compatible endpoint
you configure). Report those directly to the provider.

## Response expectations

This is a small project maintained in spare time — there's no guaranteed
response time or SLA, but security reports will be prioritized over feature
requests and general bugs.
