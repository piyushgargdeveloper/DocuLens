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
- Answer: The Transformer is built on a stack of self‑attention layers followed by point‑wise, fully‑connected layers in both its encoder and decoder [Page 3]. The passages do not state what components it removes.
- Sources: p3(0.59), p2(0.48), p10(0.48)

**B - large chunks, higher top-k**
- Answer: The Transformer is built on a stack of identical layers that use **self‑attention** followed by a position‑wise feed‑forward network, with residual connections and layer‑normalization around each sub‑layer. It **dispenses with recurrence**, relying entirely on attention to capture dependencies between input and output positions. [Page 3] [Page 2]
- Sources: p3(0.42), p2(0.34), p5(0.32), p9(0.31), p8(0.30)

### Q: How many identical layers are in the Transformer's encoder stack?

**A - small chunks, low top-k**
- Answer: I could not find the answer to this question in the document.
- Sources: p3(0.65), p3(0.62), p3(0.57)

**B - large chunks, higher top-k**
- Answer: The Transformer’s encoder stack contains 6 identical layers. [Page 3]
- Sources: p3(0.62), p5(0.45), p3(0.44), p6(0.41), p5(0.41)

### Q: What BLEU score did the Transformer (big) model achieve on the WMT 2014 English-to-French translation task?

**A - small chunks, low top-k**
- Answer: The Transformer (big) model scored **41.0 BLEU** on the WMT 2014 English‑to‑French translation task. [Page 8]
- Sources: p8(0.80), p8(0.79), p8(0.78)

**B - large chunks, higher top-k**
- Answer: The Transformer (big) model reached a BLEU score of **41.8** on the WMT 2014 English‑to‑French translation task. [Page 1]
- Sources: p8(0.77), p8(0.66), p8(0.65), p1(0.63), p8(0.59)

### Q: How long did it take to train the Transformer model that achieved a new state-of-the-art on English-to-French translation, and on what hardware?

**A - small chunks, low top-k**
- Answer: I could not find the answer to this question in the document.
- Sources: p8(0.73), p8(0.65), p8(0.62)

**B - large chunks, higher top-k**
- Answer: The big Transformer that set the new English‑to‑French state‑of‑the‑art was trained for **3.5 days on eight NVIDIA P100 GPUs**. [Page 8]
- Sources: p8(0.62), p8(0.62), p8(0.59), p1(0.55), p8(0.49)

### Q: Who proposed scaled dot-product attention and multi-head attention?

**A - small chunks, low top-k**
- Answer: I could not find the answer to this question in the document.
- Sources: p4(0.79), p4(0.71), p4(0.66)

**B - large chunks, higher top-k**
- Answer: Noam proposed both the scaled dot‑product attention and the multi‑head attention mechanisms. [Page 1]
- Sources: p4(0.60), p4(0.58), p4(0.56), p3(0.55), p1(0.48)

### Q: What was the total monetary cost, in US dollars, of training the Transformer models?

**A - small chunks, low top-k**
- Answer: I could not find the answer to this question in the document.
- Sources: p8(0.51), p8(0.48), p8(0.43)

**B - large chunks, higher top-k**
- Answer: I could not find the answer to this question in the document.
- Sources: p8(0.47), p8(0.40), p8(0.35), p8(0.34), p9(0.33)
