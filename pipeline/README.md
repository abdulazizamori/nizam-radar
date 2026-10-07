Pipeline (owner: Abdulaziz). Entry point: `run.analyze(profile, reg) -> AnalysisResult`.

1. `filter.py`: Nano. Profile + title + first 2,000 chars → `FilterResult`. Fails open.
2. `reason.py`: Ultra reads the whole regulation → applicability, confidence,
   reasoning and obligations. **Citation check in code**: every quote must be
   found in `full_text` (exact, or with whitespace differences only; the stored
   quote is always the original text, ≤300 chars). Any failed check →
   `needs_review`.
3. `write.py`: Super turns the checked analysis into the summary (≤80 words,
   ar/en) and a checklist. Rejects Chinese characters in Arabic and retries once,
   then falls back to Ultra's reasoning. Checklist dates are capped at the deadline.
4. `run.py`: joins the steps, computes `next_deadline` and `priority`
   (urgent = applies + penalty stated or deadline within 30 days), and sums usage.

- `llm.py`: every model call is cached (`USE_LLM_CACHE=true`, `.cache/llm/`) and logged
  to `logs/llm_calls.jsonl` (model, tokens, cost, latency).
- Prompts live in `prompts/` and are versioned by file name.

Try it: `python scripts/run_filter.py`, `python scripts/run_analysis.py`. Offline tests: `python -m pytest tests`.
