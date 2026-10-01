# Design Direction

Rewritten for v3.3.0. The v2.4–v3.2 "Reading Room" look (warm paper, a
Fraunces editorial serif, ink-green accent, springy motion) had character but
read as *fancy* — "trying too hard", closer to a styled demo than a tool you'd
trust with work. This direction is the correction: **quiet, minimal,
professional** — the register of Linear, Vercel and Claude — where the craft
is in precision and restraint, not decoration.

## Brief

- **Purpose:** ask a document questions and see exactly where each answer came
  from, with zero friction and nothing to distract.
- **Audience:** students and reviewers who want a tool that feels real and
  trustworthy, not a flashy toy.
- **Tone:** calm, precise, understated. **Not:** decorative, "editorial",
  playful, or over-animated.
- **Constraints:** vanilla HTML/CSS/JS, no build step; WCAG AA; works at
  360px; untrusted text only ever inserted as text; nothing from other origins.

# Clean Minimal

**Neutral by default, colour with intent.** Surfaces are a clean, near-white
neutral ramp (and a true neutral dark), not warm cream. There is exactly one
accent — a restrained blue (`#2563EB`) — and it is spent only where it earns
attention: the primary button, the send control, links, the focus ring, and
the page-citation chips. Everything structural stays greyscale, so the accent
never feels loud.

**One typeface, clear hierarchy.** Inter throughout — body, headings and the
wordmark — with hierarchy from weight and size, not from a second display
face. All numerals (page citations, similarity, version) are monospace so
figures line up. No serif, no optical-size theatrics; the headline is simply
Inter at a larger size with tight tracking.

**Quiet surfaces.** Depth comes from hairline borders and light shadows, with
small radii (7–12px). No gradients, no glassmorphism, no heavy drop shadows.
The documents rail and the conversation are two plain cards on the page.

**The conversation reads like a good chat app.** The reader's question is a
subtle neutral bubble on the right (not a loud colour); the answer sits under
a small, monochrome "AI" mark and renders as proper Markdown — headings, lists,
code, tables, bold — with page citations as small accent chips that open the
exact source passage beside the answer. A clean composer floats at the bottom.

**Motion is subtle and functional.** Things fade and ease into place quickly;
nothing springs, bounces, loops or beats. The one motion that must never stop
is the loading spinner — it keeps turning even under `prefers-reduced-motion`,
because a frozen spinner reads as broken.

**Is not:** a warm "editorial" theme, a serif-headline design, a gradient/
glass "AI" landing page, or an over-animated showcase. Kills on sight: display
serifs, decorative looping animation, more than one accent colour, heavy
shadows, colour used where grey would do.

**Signature restraint:** almost everything is neutral; the single blue accent
and the page-citation chips are the only colour, so the eye always knows where
to look and the tool feels calm and trustworthy.
