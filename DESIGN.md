# Design Direction

Written before the v1.4.0 frontend changes, following the design-direction
method: interrogate the brief, commit to one named direction, and name what
it is not. When a visual decision is hard, this document decides it.

## Brief

- **Purpose:** let someone check an answer against the document in one
  glance. The answer and the passage it came from must be visible together.
- **Audience:** students and reviewers reading on a laptop or phone,
  skeptical of AI answers, wanting proof rather than prose.
- **Tone:** scholarly, exact, calm. **Not:** chatty, techy, glossy.
- **Constraints:** vanilla HTML/CSS/JS, no build step; WCAG AA; works at
  375px; untrusted document text is only ever inserted as text.
- **Default we deviate from:** the chat-app template (coloured bubbles,
  blue accent, sidebar + card, centred upload card). We deviate in
  structure (sources in a margin), colour (no UI accent at all) and scale
  (a title-page headline).

# Annotated Margin

This interface believes an answer is only as good as its footnote. Its
ancestors are the scholar's annotated copy and the printed edition with
marginal notes: the text runs down the page, and the evidence for each claim
sits beside it in the margin, not behind a click.

Structure follows the page, not the chat window. On a wide screen every
answer is a two-column spread: the answer in a readable measure on the
left, its source passages as numbered-by-page margin notes on the right. On
a phone the margin folds under the answer. Questions are not bubbles; they
are set like the question in a printed interview, and each exchange is
separated by a hairline, the way entries in a notebook are. An answer is
read from its first line: when one arrives, the page turns to its
question rather than to the bottom of the conversation.

Colour is ink on paper and nothing else. The interface itself is
achromatic: dark ink for text, buttons and focus, soft ink for secondary
text, a cool paper surface on a slightly darker desk. The only chroma in the
product is highlighter yellow, and it appears only where the document is
being cited: the page tabs inside answers and the passage they point to
(plus the wordmark, which is itself a drawing of a highlighted line).
Because nothing else is coloured, the yellow always means "this is the
evidence".

Type has two voices. Source Serif carries everything that is reading —
answers, passages, the title page — in a bookish, unhurried register.
Atkinson Hyperlegible carries everything that is operating — buttons,
filenames, page numbers — plainly and legibly. The empty screen is a title
page: a large serif statement several times the body size, set left,
without a card around it.

Motion only ever answers something the reader did, and never decorates.
The signature motion is the highlighter: when a citation is clicked, a stroke
sweeps across its passage in the margin, and the same stroke appears when a
PDF is dragged over the drop area. Around it, quieter motion shows what just
changed: a new question, answer or document rises a few pixels into place;
an answer's margin notes follow one after another, as if being pinned beside
it; while the documents are searched, a thin ink line reads across under
"Searching…". The title page arrives in reading order whenever it is shown. Nothing moves on
scroll, nothing loops except the reading line, and all of it switches off
under reduced motion.

Suggested questions and the "Explain more simply" / "Go deeper" actions
are set as quiet ink text and outlined serif prompts — the same register as
the conversation, never as coloured chips — so they read as part of the page.

The footer credits the author ("Made with ❤️ by Piyush Garg"), links the
repository and names the release. Its heart is the one colour outside the
highlighter — a deliberate exception, kept small and in the footer, where it
can't be mistaken for evidence.

**Is not:** a chat app, a SaaS dashboard, or a dark-mode "AI" product with
glowing accents. Kills on sight: speech bubbles, blue primary buttons,
gradients, drop shadows, cards inside cards.

**Signature move:** every answer carries its evidence in the margin, and
clicking a yellow page tab sweeps a highlighter across the exact passage
beside it.
