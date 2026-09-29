# Chunking/Retrieval Configuration Comparison

Document: `sample_docs/dev_real_world_document.pdf`

## A - small chunks, low top-k
chunk_size=300, chunk_overlap=50, top_k=3

Indexed: 15 pages -> 161 chunks.

## B - large chunks, higher top-k
chunk_size=1000, chunk_overlap=200, top_k=5

Indexed: 15 pages -> 52 chunks.

## Per-question comparison

### Q: What is the Transformer architecture based on, and what does it dispense with?

**A - small chunks, low top-k**
- Answer: The Transformer architecture is built on stacked self‑attention mechanisms together with point‑wise, fully‑connected feed‑forward layers for both the encoder and the decoder [Page 3].  

The passages do not specify what components the Transformer discards (e.g., recurrence or convolution), so that part is not covered in the provided documents.
- Sources: p3(0.59), p2(0.48), p9(0.36)

**B - large chunks, higher top-k**
- Answer: The Transformer is built entirely on attention mechanisms, using stacked self‑attention and feed‑forward layers. It dispenses with recurrence and convolutional layers. [Page 1] [Page 3]
- Sources: p3(0.42), p1(0.23), p2(0.34), p1(0.22), p10(0.27)

### Q: How many identical layers are in the Transformer's encoder stack?

**A - small chunks, low top-k**
- Answer: The Transformer's encoder stack consists of **6 identical layers**. This follows from the passage that says the decoder “is also composed of a stack of N = 6 identical layers,” implying the encoder uses the same number of layers [Page 3].
- Sources: p3(0.57), p3(0.65), p3(0.62)

**B - large chunks, higher top-k**
- Answer: The Transformer’s encoder stack contains 6 identical layers. [Page 3]
- Sources: p3(0.62), p3(0.44), p5(0.45), p5(0.41), p7(0.28)

### Q: What BLEU score did the Transformer (big) model achieve on the WMT 2014 English-to-French translation task?

**A - small chunks, low top-k**
- Answer: The Transformer (big) model was reported to reach a BLEU score of roughly **41 – 42** on the WMT 2014 English‑to‑French task: one passage cites a score of **41.0** [Page 8], while another notes a **41.8** BLEU score as the new single‑model state‑of‑the‑art [Page 1].
- Sources: p8(0.80), p8(0.69), p1(0.76)

**B - large chunks, higher top-k**
- Answer: The Transformer (big) model achieved a BLEU score of **41.8** on the WMT 2014 English‑to‑French translation task. [Page 8] Table 2
- Sources: p8(0.77), p8(0.66), p1(0.63), p8(0.65), p10(0.53)

### Q: How long did it take to train the Transformer model that achieved a new state-of-the-art on English-to-French translation, and on what hardware?

**A - small chunks, low top-k**
- Answer: I could not find the answer to this question in the document.
- Sources: p8(0.73), p10(0.57), p8(0.65)

**B - large chunks, higher top-k**
- Answer: The Transformer that set the new single‑model English‑to‑French BLEU score was trained for **3.5 days on eight GPUs**. [Page 1]
- Sources: p1(0.55), p8(0.62), p8(0.59), p10(0.46), p10(0.44)

### Q: Who proposed scaled dot-product attention and multi-head attention?

**A - small chunks, low top-k**
- Answer: Noam is credited with proposing both scaled dot‑product attention and multi‑head attention【Page 1】.
- Sources: p4(0.79), p4(0.71), p1(0.63)

**B - large chunks, higher top-k**
- Answer: Noam proposed both the scaled dot‑product attention and the multi‑head attention mechanisms. [Page 1]
- Sources: p4(0.60), p4(0.58), p1(0.48), p4(0.56), p9(0.46)

### Q: What was the total monetary cost, in US dollars, of training the Transformer models?

**A - small chunks, low top-k**
- Answer: I could not find the answer to this question in the document.
- Sources: p8(0.51), p1(0.41), p8(0.38)

**B - large chunks, higher top-k**
- Answer: I could not find the answer to this question in the document.
- Sources: p8(0.34), p8(0.40), p8(0.35), p5(0.33), p7(0.23)
