# Deploying the API (CP1 hello world)

Goal: `GET <url>/api/v1/health` returns `{"status":"ok"}` and
`GET <url>/api/v1/health/db` returns the Postgres and pgvector versions.

## 1. Database (Neon)
1. Sign up at neon.tech with GitHub and create project `nizam-radar`.
2. Copy the connection string (Connect button), starting `postgresql://`.
3. Put it in your local `.env` as `DATABASE_URL=...`. Never commit it or paste it in chat.
4. Check: `python scripts/check_db.py` should print `Database OK ... pgvector ...`.

## 2. Run the API on your Mac
```
uvicorn api.main:app --reload --port 8000
```
Open http://localhost:8000/api/v1/health and http://localhost:8000/api/v1/health/db.

## 3. Container image (automatic)
Every push to `main` that touches the API builds the image with GitHub
Actions (`.github/workflows/api-image.yml`) and publishes it as
`ghcr.io/abdulazizamori/nizam-radar-api:latest`.
After the first build: GitHub → your profile → Packages → `nizam-radar-api`
→ Package settings → Change visibility → Public (so Nebius can pull it
without registry credentials; the image contains no secrets).

## 4. Nebius Serverless Endpoint
Console: Serverless AI → Endpoints → Create endpoint → Custom.
- Image: `ghcr.io/abdulazizamori/nizam-radar-api:latest`
- Container port: `8000`
- Platform: CPU, the smallest preset
- Environment variables: `DATABASE_URL` (as a secret if offered),
  `CORS_ORIGINS=http://localhost:3000` (add Wesam's web domain later)
- Authentication: none for the hello world (add a token before real data)

CLI equivalent (docs.nebius.com/serverless/endpoints/manage):
```
nebius ai endpoint create --name nizam-api \
  --image ghcr.io/abdulazizamori/nizam-radar-api:latest \
  --platform cpu-d3 --preset <smallest> --container-port 8000 \
  --env CORS_ORIGINS=http://localhost:3000 --env-secret DATABASE_URL=<secret>
```
The public HTTPS URL is in the endpoint's **Network** section.

## Fallback: Render
New → Web Service → connect the GitHub repo → it detects the Dockerfile.
Add `DATABASE_URL` and `CORS_ORIGINS` as environment variables.
