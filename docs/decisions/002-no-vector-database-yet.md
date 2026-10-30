# 002. No vector database yet

**Status:** accepted, 30 Oct 2026
**Built in:** #25 (similarity ranking)

## Context

The last step of matching ranks the lots that could work by how well they match the buyer's own
words, and keeps the top 10. That needs vectors (embeddings) for the want and every lot, and a
similarity score for each pair.

## Options

| | Option | For | Against |
|---|---|---|---|
| A | A vector database (Qdrant, pgvector, a hosted one) | Built for millions of vectors; fast approximate search | Another service to run, configure and keep in step with the lots table; a second place stock can be wrong |
| B | **NumPy in memory** | No extra service; exact scores; one line of maths | Every vector lives in memory, and each query scores every lot |

## Decision

Option B, with the model run locally (bge-small-en-v1.5 through fastembed: no API key, nothing
sent anywhere).

## Measured on the seeded market (Apple M2, 30 Oct)

| | |
|---|---|
| Embed all 1,494 lot titles | 3.6 s, once |
| Embed 500 wants | 1.7 s |
| Rank **every** lot for **all** 500 wants | 46 ms in total, about 92 µs per want |
| Memory for the lot vectors | 2.3 MB (1,494 × 384 numbers) |

And the funnel only ranks what's left after the cheap steps: after the SQL filters and skipping
impossible deals, a buyer has about 47 candidates on average (23,348 for 500 buyers), not 1,494.

## When to change

- **More lots than fit comfortably in memory.** Each lot costs 1.5 KB (384 × 4 bytes). At Fleek's
  size, with 2,000+ suppliers, a few hundred thousand live listings would still be a few hundred MB.
  The trigger is more likely millions of lots, or many processes each holding a copy.
- **Stock changing faster than we re-embed.** Today the funnel's SQL filters decide what's in
  stock, and ranking only orders what's left. A vector database would need the same filters
  inside it.
- **Then:** pgvector first, because the lots already live in a SQL database. The filter and the
  ranking stay in one query, and there's no second store to keep in step.

## Consequences

- Ranking quality depends on the small model. The test checks one known case (the Levi's 501 lot
  comes first for "Levi's 501 jeans, grade A") and that meaning is captured ("denim" is closer to
  "jeans" than to "t-shirts"). It doesn't measure ranking quality across the market; the
  simulation later is where that gets checked.
- Lots are ranked on their titles. Seller-written text could be stuffed with keywords to rank
  higher. Titles here are generated; with real sellers, rank on structured fields plus a cleaned
  title.
