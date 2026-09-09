# The Right Basket

Monorepo scaffolding: a **FastAPI** backend and a **Next.js + Tailwind CSS** frontend.

```
the-right-basket/
├── backend/          FastAPI service
│   ├── main.py       app entrypoint + /healthcheck
│   ├── app/config.py settings loaded from .env
│   ├── requirements.txt
│   └── .env.example
└── frontend/         Next.js (App Router, TypeScript, Tailwind CSS v4)
    ├── src/app/
    └── .env.example
```

## Requirements

- Python 3.11+
- Node.js 20+

## Running the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

The API runs on **http://localhost:8000**.

- Healthcheck: http://localhost:8000/healthcheck
- Interactive docs: http://localhost:8000/docs

```bash
curl http://localhost:8000/healthcheck
# {"status":"ok","service":"the-right-basket-backend","version":"0.1.0","environment":"development"}
```

## Running the frontend

In a second terminal:

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

The app runs on **http://localhost:3000**. The home page calls the backend's
`/healthcheck` and shows whether the API is reachable, so you can confirm both
services are wired together.

## Environment variables

Both `.env.example` files are committed as templates; the real `.env` /
`.env.local` files are gitignored.

| Backend (`backend/.env`) | Default | Purpose |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | Deployment environment name |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | Server bind address |
| `DATABASE_URL` | `sqlite:///./local.db` | Database connection string |
| `SECRET_KEY` | `dev-secret-change-me` | Signs tokens/sessions — change it |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |

| Frontend (`frontend/.env.local`) | Default | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Base URL of the backend |

## Other frontend commands

```bash
npm run build   # production build
npm start       # serve the production build
npm run lint    # eslint
```
