# KilimoBiashara Extension Portal

A Flask application for recording farm visits and viewing each farmer's report history. Each new assessment becomes an immutable dated visit, so officers can follow changes in farm conditions, advice, notes, and follow-up dates.

## Run locally

1. Create and activate a virtual environment.
2. Install dependencies: `pip install -r requirements.txt`
3. Optional: set `OPENAI_API_KEY` to generate AI-backed reports. Without it, the app saves records and produces a clear offline advisory template.
4. Start: `python app.py`
5. Open `http://127.0.0.1:5000`.

Local data is stored in `kilimobiashara.db`. It is for local testing only; do not use local SQLite to run a shared county service.

## Deploy on Render

1. Put these files in a GitHub repository and push them.
2. In Render, choose **New → Blueprint** and select the repository. Render reads `render.yaml` and creates both the web service and managed PostgreSQL database.
3. Add the `OPENAI_API_KEY` secret in the web service environment settings if you want AI-generated advice. It is intentionally not stored in the repository.
4. Deploy. Open the service's `onrender.com` URL.

The blueprint passes Render Postgres's internal connection string into `DATABASE_URL`, so the farmer history survives service redeploys. The included health endpoint is `/healthz`.

## Important before production

This starter intentionally has no authentication so it is easy to demonstrate. Before putting real farmer data online, add officer accounts, passwords/roles, backup policy, and access controls. Do not enter personal farmer data into a public demo.

The AI text is decision support only. Officers should validate health, feeding, and treatment guidance locally.
