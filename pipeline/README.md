Pipeline: filter.py (Nano), reason.py (Ultra), write.py (Super) (owner: Abdulaziz).

- `llm.py`: every model call goes through `chat()`, which caches responses
  (`USE_LLM_CACHE=true`, stored in `.cache/llm/`) and logs model, tokens,
  cost and latency to `logs/llm_calls.jsonl`.
- `filter.py`: step 1. Profile + title + first 2,000 chars → `FilterResult`.
  Prompt: `prompts/filter_v1.md`. Fails open (relevant=true) if Nano's answer
  can't be read, because Ultra checks again.

Try it: `python scripts/run_filter.py` (needs your key). Offline tests: `python -m pytest tests`.
