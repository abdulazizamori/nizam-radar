# Decisions (week-1 checks, spec section 16)

## Models (checked 2026-10-07 in the Token Factory catalog)
| Env var | Routing key (API model ID) | Context | Price per 1M tokens (in / out) |
|---|---|---|---|
| MODEL_NANO | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | 262K | $0.06 / $0.24 |
| MODEL_SUPER | `nvidia/nemotron-3-super-120b-a12b` | 256K | $0.30 / $0.90 |
| MODEL_ULTRA | `nvidia/Nemotron-3-Ultra-550b-a55b` | 1,024K | $1.00 / $3.00 |
| MODEL_EMBED | `Qwen/Qwen3-Embedding-8B` | 4,096 dimensions | $0.01 / n/a |

- Base URL: `https://api.tokenfactory.nebius.com/v1/` (OpenAI-compatible; use the `openai` Python client).
- Routing keys differ in capitalization and prefix from the display names. Copy them exactly.
- **Can Ultra take a whole regulation?** Yes, 1M tokens. The longest record so far, Balady at 83K characters, fits in one call. Sending only the relevant sections is still cheaper.
- Public endpoints say "for tests, not production", and the region can change. That's fine for the hackathon.

## Rough cost per analysis (estimate, not measured)
Using the spec's example of about 6,100 tokens in and 900 out:
- Nano filter (about 800 in / 50 out): about $0.0001
- Ultra reasoning (about 6,000 in / 900 out): about $0.009
- Super writer (about 1,500 in / 600 out): about $0.001
- **Routed total: about $0.01 per relevant item.** An item the filter drops costs about $0.0001.
- With Ultra doing every step, each item costs about $0.013, and irrelevant items cost the full amount instead of the filter price. That gap is the "routing saves money" story for the video. Replace these estimates with the logged numbers later.

## Sources (data collection)
- Arabic government PDFs extract with swapped letter pairs. Prefer HTML pages or the official English version, or OCR with Tesseract `ara` plus repair.
- sfda.gov.sa news links return 404. The old pages live on `oldsfda.sfda.gov.sa`.
- See `data/regulations/NOTES.md`.

## Ownership change
Abdulaziz (A) owns data collection (`collector/`) as well as the pipeline and API. Wesam (B) owns web, eval labels, the video and the README.

## Embeddings
- `Qwen/Qwen3-Embedding-8B` is the only embedding model on the platform. It is multilingual, Arabic included, and returns 4,096 dimensions. It isn't an NVIDIA model, which is fine because the Nemotron models do the reasoning.
- pgvector can't build an HNSW or IVFFlat index on more than 2,000 dimensions. At hackathon scale (a few thousand chunks) an exact search with no index is fast enough. Alternatively, ask for fewer dimensions if the API accepts a `dimensions` parameter (Qwen3 embeddings support shortening). Test this on Day 2.
