# Design Direction

Rewritten for v2.1.0. The earlier "Annotated Margin" direction (v1.4–v2.0:
ink on paper, serif answers, no UI colour) read as too plain in use — the
footer and the controls didn't look like a finished product. The owner chose
a new direction from three options; this document records it. When a visual
decision is hard, this document decides it.

## Brief

- **Purpose:** let someone check an answer against the document in one
  glance. The answer and the passage it came from must be visible together.
- **Audience:** students and reviewers reading on a laptop or phone,
  skeptical of AI answers, wanting proof rather than prose.
- **Tone:** clean, confident, calm — a tool you'd trust at work.
  **Not:** playful, glossy, "AI-glow".
- **Constraints:** vanilla HTML/CSS/JS, no build step; WCAG AA; works at
  375px; untrusted document text is only ever inserted as text; nothing
  loaded from other origins (fonts are self-hosted).

# Modern Product

The reference is a well-made SaaS tool in the Notion/Linear family: quiet
neutral surfaces, one accent colour used with intent, depth from hairline
borders and soft shadows rather than gradients.

**Surfaces.** A light zinc page holds two white cards: the documents sidebar
on the left and the conversation on the right. Cards have a 1px border, a
16px radius and a soft shadow; nothing is nested more than one card deep.
Dark mode swaps to near-black surfaces with the same structure.

**Colour.** Zinc neutrals for everything structural and one iris accent
(`#5B5BD6`, lighter in dark mode) for what the reader acts on or should
notice: the primary button, the reader's question bubble, send, focus rings,
citation chips. Highlighter yellow is kept for exactly one job — the source
passage a clicked citation points to — so yellow still means "this is the
evidence". Green is only a status dot (what's being searched, the live
version). The footer's heart is red.

**Type.** Inter (self-hosted variable font) everywhere, 15px body, tight
negative tracking on the hero headline. Hierarchy comes from weight and
colour (text / soft / faint), not from switching typefaces.

**Conversation.** The reader's question is a right-aligned accent bubble;
the assistant's reply sits on the left behind a small "AI" avatar, as plain
readable text. On a wide conversation each answer has a **Sources** column
of cards beside it (page, similarity, clamped passage); on a phone the
cards fold under the answer behind "Show sources". Page citations inside
the answer are small accent pills (`p. 3`); clicking one lights up its
source card in yellow. Follow-ups ("Explain more simply", "Go deeper") and
Copy are outlined pill buttons under the answer; suggested questions are a
grid of small cards. An answer is read from its first line: when one
arrives, the view scrolls to its question, not to the bottom.

**Composer.** A floating rounded box with a soft shadow holds attach, the
question and a round send button; it gains an accent focus ring. Send
becomes Stop while an answer streams, and a thin accent caret marks where
the next words land. Beneath it: a green dot with what will be searched,
and keyboard hints (hidden on phones).

**Start page.** Centred: an accent "eyebrow" badge, a large bold headline,
a short explanation, a white drop card with an upload icon, three feature
cards (Grounded / Multi-document / Private) and the privacy note. On a
phone it scrolls rather than running under the footer.

**Footer** (two tiers since v2.2.0). Top: brand + tagline, the live
**AI providers** row (a pill per provider with a green dot when available,
a slowly pulsing amber dot while it cools down after a rate limit), and
the links (GitHub, Releases, Report an issue, Privacy — which opens a
dialog). Below a dashed hairline: the credit "Made with ❤️ by Piyush Garg",
the stack in mono (FastAPI · FAISS · MiniLM · BM25 · Gemini · gpt-oss) and a
version badge linking to the release notes. On a phone the brand, the stack
and the label are dropped; providers, links and the credit remain.

**Small comforts** (v2.2.0). A light / dark / system toggle in the top bar
(remembered in this browser; applied before first paint by `theme.js`).
Every answer ends with a quiet "Groq · gpt-oss-120b" tag naming who wrote
it. Short confirmations (copied, exported, removed, theme) appear as a
toast under the top bar instead of cluttering the conversation. Scrolling
to an answer is smooth; scrolled away from the bottom, a round
jump-to-latest button appears. While an answer is being prepared, two
soft skeleton lines breathe under "Searching your documents…".

**Motion** answers what the reader did: views fade in; the start page
rises in reading order; messages, documents and source cards rise a few
pixels into place (cards staggered); hover lifts cards and buttons by a
pixel; the dialog pops in; the heart beats slowly. All of it is switched
off under `prefers-reduced-motion`.

**Is not:** a gradient-heavy "AI" landing page, a glassmorphism demo, or a
dashboard of widgets. Kills on sight: gradients, glowing accents, more than
one accent colour, cards inside cards, colour used only for decoration.

**Signature move:** every answer carries its sources beside it, and
clicking a `p. N` citation lights up the exact passage it came from.
