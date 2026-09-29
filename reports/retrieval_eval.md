# Retrieval Evaluation

Document: `sample_docs/dev_real_world_document.pdf` — 39 labelled questions (`sample_docs/retrieval_eval_set.json`).
A chunk is relevant if it contains the question's evidence phrase. k = 4 (the app's top_k).
Produced by `python retrieval_eval.py`; no LLM calls, fully deterministic.

## Chunking A 300/50 (161 chunks)

| Retriever | Hit@1 | Hit@4 | MRR@10 | Page-Hit@4 |
|---|---|---|---|---|
| BM25 | 0.41 (16/39) | 0.64 (25/39) | 0.54 | 0.82 |
| MiniLM | 0.36 (14/39) | 0.59 (23/39) | 0.48 | 0.92 |
| BGE-small | 0.46 (18/39) | 0.74 (29/39) | 0.59 | 0.92 |
| Hybrid | 0.44 (17/39) | 0.69 (27/39) | 0.57 | 0.90 |

## Chunking Default 800/150 (63 chunks)

| Retriever | Hit@1 | Hit@4 | MRR@10 | Page-Hit@4 |
|---|---|---|---|---|
| BM25 | 0.64 (25/39) | 0.87 (34/39) | 0.75 | 0.90 |
| MiniLM | 0.38 (15/39) | 0.77 (30/39) | 0.56 | 0.82 |
| BGE-small | 0.59 (23/39) | 0.77 (30/39) | 0.68 | 0.79 |
| Hybrid | 0.56 (22/39) | 0.82 (32/39) | 0.70 | 0.82 |

## Chunking B 1000/200 (52 chunks)

| Retriever | Hit@1 | Hit@4 | MRR@10 | Page-Hit@4 |
|---|---|---|---|---|
| BM25 | 0.56 (22/39) | 0.79 (31/39) | 0.69 | 0.85 |
| MiniLM | 0.44 (17/39) | 0.67 (26/39) | 0.58 | 0.77 |
| BGE-small | 0.49 (19/39) | 0.79 (31/39) | 0.63 | 0.85 |
| Hybrid | 0.54 (21/39) | 0.85 (33/39) | 0.69 | 0.87 |

## Questions missed in the top 4

- **BGE-small, A 300/50** (10): #1 What architecture does the paper propose instead of recurrence and convolutions?; #2 What BLEU score did the model reach on English to German translation?; #3 Who suggested using self-attention in place of recurrent networks?; #5 How quickly can the model reach state of the art translation quality?; #18 Which nonlinearity is used inside the feed-forward network?; #19 How big is the inner layer of the feed-forward network?; #20 How is word order information added to the model?; #32 What happened when learned positional embeddings replaced sinusoids?; #37 Who is the author of the Xception paper cited?; #38 What does the attention visualization for the word making show?
- **BM25, A 300/50** (14): #3 Who suggested using self-attention in place of recurrent networks?; #4 Why is it hard to parallelize recurrent models during training?; #6 Which earlier models used convolutions to reduce sequential computation?; #9 How is the decoder stopped from looking at future tokens?; #12 Why are the dot products divided by the square root of the key dimension?; #15 How many attention heads are used?; #18 Which nonlinearity is used inside the feed-forward network?; #19 How big is the inner layer of the feed-forward network?; #20 How is word order information added to the model?; #32 What happened when learned positional embeddings replaced sinusoids?; #33 How many sentences does the WSJ training set for parsing contain?; #35 Where can the training and evaluation code be found?; #36 What future directions beyond text do the authors mention?; #38 What does the attention visualization for the word making show?
- **Hybrid, A 300/50** (12): #2 What BLEU score did the model reach on English to German translation?; #3 Who suggested using self-attention in place of recurrent networks?; #4 Why is it hard to parallelize recurrent models during training?; #5 How quickly can the model reach state of the art translation quality?; #15 How many attention heads are used?; #18 Which nonlinearity is used inside the feed-forward network?; #19 How big is the inner layer of the feed-forward network?; #20 How is word order information added to the model?; #32 What happened when learned positional embeddings replaced sinusoids?; #33 How many sentences does the WSJ training set for parsing contain?; #36 What future directions beyond text do the authors mention?; #37 Who is the author of the Xception paper cited?
- **MiniLM, A 300/50** (16): #1 What architecture does the paper propose instead of recurrence and convolutions?; #2 What BLEU score did the model reach on English to German translation?; #3 Who suggested using self-attention in place of recurrent networks?; #5 How quickly can the model reach state of the art translation quality?; #12 Why are the dot products divided by the square root of the key dimension?; #13 Which two attention functions are most commonly used?; #15 How many attention heads are used?; #16 What is the key and value dimension of each head?; #18 Which nonlinearity is used inside the feed-forward network?; #19 How big is the inner layer of the feed-forward network?; #20 How is word order information added to the model?; #27 What dropout rate did the base model use?; #32 What happened when learned positional embeddings replaced sinusoids?; #36 What future directions beyond text do the authors mention?; #37 Who is the author of the Xception paper cited?; #38 What does the attention visualization for the word making show?
- **BGE-small, B 1000/200** (8): #3 Who suggested using self-attention in place of recurrent networks?; #5 How quickly can the model reach state of the art translation quality?; #9 How is the decoder stopped from looking at future tokens?; #20 How is word order information added to the model?; #25 What hardware were the models trained on?; #33 How many sentences does the WSJ training set for parsing contain?; #35 Where can the training and evaluation code be found?; #36 What future directions beyond text do the authors mention?
- **BM25, B 1000/200** (8): #3 Who suggested using self-attention in place of recurrent networks?; #4 Why is it hard to parallelize recurrent models during training?; #9 How is the decoder stopped from looking at future tokens?; #15 How many attention heads are used?; #16 What is the key and value dimension of each head?; #19 How big is the inner layer of the feed-forward network?; #20 How is word order information added to the model?; #35 Where can the training and evaluation code be found?
- **Hybrid, B 1000/200** (6): #3 Who suggested using self-attention in place of recurrent networks?; #5 How quickly can the model reach state of the art translation quality?; #19 How big is the inner layer of the feed-forward network?; #20 How is word order information added to the model?; #35 Where can the training and evaluation code be found?; #37 Who is the author of the Xception paper cited?
- **MiniLM, B 1000/200** (13): #2 What BLEU score did the model reach on English to German translation?; #3 Who suggested using self-attention in place of recurrent networks?; #5 How quickly can the model reach state of the art translation quality?; #9 How is the decoder stopped from looking at future tokens?; #13 Which two attention functions are most commonly used?; #19 How big is the inner layer of the feed-forward network?; #20 How is word order information added to the model?; #31 How much worse is using a single attention head?; #32 What happened when learned positional embeddings replaced sinusoids?; #33 How many sentences does the WSJ training set for parsing contain?; #35 Where can the training and evaluation code be found?; #36 What future directions beyond text do the authors mention?; #37 Who is the author of the Xception paper cited?
- **BGE-small, Default 800/150** (9): #1 What architecture does the paper propose instead of recurrence and convolutions?; #2 What BLEU score did the model reach on English to German translation?; #3 Who suggested using self-attention in place of recurrent networks?; #5 How quickly can the model reach state of the art translation quality?; #9 How is the decoder stopped from looking at future tokens?; #20 How is word order information added to the model?; #25 What hardware were the models trained on?; #35 Where can the training and evaluation code be found?; #36 What future directions beyond text do the authors mention?
- **BM25, Default 800/150** (5): #3 Who suggested using self-attention in place of recurrent networks?; #4 Why is it hard to parallelize recurrent models during training?; #15 How many attention heads are used?; #20 How is word order information added to the model?; #35 Where can the training and evaluation code be found?
- **Hybrid, Default 800/150** (7): #1 What architecture does the paper propose instead of recurrence and convolutions?; #3 Who suggested using self-attention in place of recurrent networks?; #5 How quickly can the model reach state of the art translation quality?; #20 How is word order information added to the model?; #31 How much worse is using a single attention head?; #35 Where can the training and evaluation code be found?; #37 Who is the author of the Xception paper cited?
- **MiniLM, Default 800/150** (9): #1 What architecture does the paper propose instead of recurrence and convolutions?; #2 What BLEU score did the model reach on English to German translation?; #3 Who suggested using self-attention in place of recurrent networks?; #5 How quickly can the model reach state of the art translation quality?; #20 How is word order information added to the model?; #31 How much worse is using a single attention head?; #35 Where can the training and evaluation code be found?; #36 What future directions beyond text do the authors mention?; #37 Who is the author of the Xception paper cited?

## Chunk embedding time (seconds, CPU)

- MiniLM, A 300/50: 1.78
- BGE-small, A 300/50: 3.41
- MiniLM, Default 800/150: 1.56
- BGE-small, Default 800/150: 3.71
- MiniLM, B 1000/200: 1.21
- BGE-small, B 1000/200: 3.61
