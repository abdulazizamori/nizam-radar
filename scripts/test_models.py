"""Send one tiny request to each Nemotron model on Token Factory.

Run this on your own computer (the key must never be committed):
  1. pip install -r requirements.txt
  2. cp .env.example .env   and put your key after NEBIUS_API_KEY=
  3. python scripts/test_models.py
"""

import os
import time

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    base_url=os.environ.get("NEBIUS_BASE_URL", "https://api.tokenfactory.nebius.com/v1/"),
    api_key=os.environ["NEBIUS_API_KEY"],
)

PROMPT = "أجب بجملة واحدة: ما هي ضريبة القيمة المضافة؟ ثم أعد الإجابة بالإنجليزية."

for env_name in ["MODEL_NANO", "MODEL_SUPER", "MODEL_ULTRA"]:
    model = os.environ.get(env_name)
    if not model:
        print(f"{env_name}: not set in .env")
        continue
    start = time.time()
    try:
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": PROMPT}],
            max_tokens=300,
        )
        ms = int((time.time() - start) * 1000)
        text = (r.choices[0].message.content or "").strip()
        print(f"\n{env_name} = {model}  ({ms} ms, {r.usage.prompt_tokens} in / {r.usage.completion_tokens} out)")
        print(text[:500])
    except Exception as e:  # show the error and keep testing the other models
        print(f"\n{env_name} = {model}  FAILED: {e}")

embed = os.environ.get("MODEL_EMBED")
if embed:
    try:
        e = client.embeddings.create(model=embed, input=["شهادة صحية للعاملين", "health certificate for workers"])
        print(f"\nMODEL_EMBED = {embed}  dimensions: {len(e.data[0].embedding)}")
    except Exception as err:
        print(f"\nMODEL_EMBED = {embed}  FAILED: {err}")
