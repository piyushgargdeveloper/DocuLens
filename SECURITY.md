# Security Policy

## Supported versions

Releases are tagged on `main` (`vX.Y.Z`, see the GitHub Releases page),
but there are no maintained release branches. Only the latest release —
which is what runs at https://ai-doc-assistant.duckdns.org — is
supported. Security fixes land on `main` and ship as a new patch release.

## What this project already does

For context before reporting an issue, see the "Security notes" section of
`README.md`. In short:

- Retrieved document passages are fenced in the LLM prompt and declared
  untrusted data, so instructions embedded in an uploaded document should not
  be obeyed as instructions (verified against injection payloads — see
  `DECISIONS.md`).
- The LLM API key is read only from the environment (`LLM_API_KEY`), never
  logged, rendered, or committed. `.env` is gitignored; only `.env.example`
  (placeholders) is tracked.
- The session cookie is `httponly`, `samesite=lax`, and `Secure` over HTTPS.
- Error responses never include exception text or stack traces; details are
  logged on the server only.
- Resources are bounded: 25MB uploads (never read past the limit), 1000-
  character questions, 5 documents per session, 50 sessions, 2-hour expiry.
- Document and model text is inserted into the page with `textContent` /
  text nodes only, never as HTML or markdown.
- Dependencies are watched by Dependabot, and CodeQL scans every push.

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
