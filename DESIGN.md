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
separated by a hairline, the way entries in a notebook are.

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

Motion is almost absent, which lets the one motion land: when a citation is
clicked, a highlighter stroke sweeps across its passage in the margin. The
same stroke appears when a PDF is dragged over the drop area. Everything else
changes state instantly.

**Is not:** a chat app, a SaaS dashboard, or a dark-mode "AI" product with
glowing accents. Kills on sight: speech bubbles, blue primary buttons,
gradients, drop shadows, cards inside cards.

**Signature move:** every answer carries its evidence in the margin, and
clicking a yellow page tab sweeps a highlighter across the exact passage
beside it.
