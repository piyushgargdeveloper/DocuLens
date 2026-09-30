# Design Direction

Rewritten for v2.4.0. The v2.1–v2.3 "Modern product" look was honest but,
by its own author's admission, generic: Inter everywhere, an indigo accent
(`#5B5BD6`), 12px radius on everything, soft shadows, fade-up entrances — the
exact conjunction the anti-generic checklist calls the default-AI template.
This direction keeps the app's clarity but gives it a point of view, so it
reads as *made*, not *generated*.

## Brief

- **Purpose:** check an AI answer against the document in one glance — the
  answer and the passage it came from, together, with its page.
- **Audience:** students and reviewers, skeptical of AI, wanting proof.
- **Tone:** an editor's reading room — considered, literate, warm. **Not:** a
  SaaS dashboard, an "AI startup" landing page, a cold grey admin panel.
- **Constraints:** vanilla HTML/CSS/JS, no build step; WCAG AA; works at
  360px; untrusted text only ever inserted as text; nothing from other
  origins (fonts self-hosted).

# Reading Room

The reference is a study desk in a good library: warm paper, a serif that
was *drawn* rather than defaulted-to, and one confident ink. The interface
should feel like reading a well-set journal where every claim carries its
footnote — because that is exactly what the product does.

**Type carries the character.** Headlines, the wordmark and every section
label are set in **Fraunces** — a high-contrast "old-style" display serif
with optical sizing and a deliberate wonk, so a headline has voice instead
of the flat Inter grotesque every AI page ships. The interface and answers
stay in **Inter** for legibility, and all numerals — page citations,
similarity scores, the version — are set in a monospace so figures line up
like a ledger. The jump from the body to the Fraunces headline is large and
intentional (6×+), the single loudest signal that a person chose this.

**Colour is warm, not grey.** The neutral ramp is tinted paper — warm
off-whites and a near-black that leans brown, never the cold zinc of the
default. There is exactly one accent, an **ink green** (`#15725A`) for
everything the reader acts on: the primary button, the send control, focus,
links. It is defensibly *not* blue and not indigo. And there is one reserved
signal — **highlighter amber** — used nowhere except where the document is
being cited: the `p. N` chips and the source they point to. Because amber
means "evidence" and nothing else, the eye learns it instantly.

**Structure stays honest.** Two surfaces — a documents rail and the
conversation — on warm paper. The reader's question is an ink-green bubble;
the answer sits under a small serif "AI" mark with its sources as cards
beside it on wide screens, folded under on narrow ones. The composer is a
single rounded field that floats above the paper. No glassmorphism, no
gradient blobs, no three-equal-feature-card band for its own sake.

**The footer is a footer.** It is not a bar bolted to the bottom of the
app. On the opening page it sits at the end of the page, reached by
scrolling, the way a colophon closes a book: the credit, the stack it's
built on, the version, the links. Inside a conversation it steps aside
entirely — the composer is the floor of a chat — and the live provider and
version move into the top bar.

**Motion is editorial, not decorative.** Things arrive the way a page is
laid down: a slight settle with a soft spring, staggered for a list, never
the uniform fade-up-on-everything. A citation chip inks in; hovering a
source card lifts it and warms its border; the model's thinking shimmers
while it streams. All of it obeys `prefers-reduced-motion`.

**Is not:** an indigo-accented SaaS template, a glassmorphism demo, a cold
grey dashboard, or a plain ink-on-white text dump. Kills on sight: Inter
headlines, indigo/blue primary buttons, gradient hero backgrounds, uniform
fade-up motion, emoji section bullets.

**Signature move:** Fraunces editorial headlines and amber-highlighter
citations on warm paper — describable from memory, and findable in a folder
of twenty AI-tool screenshots in under three seconds.
