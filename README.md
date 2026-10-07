# Nizam Radar

Regulation alerts for food and beverage businesses in Saudi Arabia. Nizam Radar collects new rules from official sources (Balady, SFDA, ZATCA, HRSD and others). It checks whether each rule applies to a specific cafe or restaurant, then explains what to do and by when, in Arabic and English, citing the source.

Built for the Nebius x NVIDIA Global AI Hackathon (Best Apps and Agents track).

**Team:** Person A = Abdulaziz (AI pipeline, backend, data collection). Person B = Wesam (web app, evaluation, video).

## How it works
1. **Collect:** official pages become `RegulationRecord` files in `data/regulations/`.
2. **Analyze:** three NVIDIA Nemotron models on Nebius Token Factory, routed by job size:
   - Nano filters out irrelevant rules cheaply.
   - Ultra decides whether the rule applies, finds deadlines and penalties, and cites the text.
   - Super writes the Arabic and English summary and the checklist.
3. **Serve:** a FastAPI backend gives the web app alerts, details and chat.

| Role | Model (Token Factory routing key) |
|---|---|
| Filter | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` |
| Reasoning | `nvidia/Nemotron-3-Ultra-550b-a55b` |
| Writer and chat | `nvidia/nemotron-3-super-120b-a12b` |
| Embeddings | `Qwen/Qwen3-Embedding-8B` |

## Repository layout
```
contracts/   shared data formats (models.py), JSON Schemas and fixtures; change only by agreement
collector/   official sources to RegulationRecord           (Abdulaziz)
pipeline/    Nano filter, Ultra reasoning, Super writer     (Abdulaziz)
api/         FastAPI backend                                (Abdulaziz)
notifier/    daily email digest                             (Abdulaziz)
web/         frontend, Arabic/English with RTL              (Wesam)
eval/        labeled test cases and metrics                 (Wesam labels, Abdulaziz runs)
data/        collected regulations
docs/        decisions.md and feedback.md
scripts/     helper scripts
```

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env              # then add your own NEBIUS_API_KEY (never commit .env)
python scripts/test_models.py     # one test call per model
python -m contracts.validate_fixtures
python -m contracts.export_schemas
```

*Information, not legal advice.*
