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

## Price engine

`backend/app/services/price_fetcher.py` ingests the price files that Israeli
retail chains must publish under the food-price transparency law
(חוק קידום התחרות בענף המזון, 2014). Eleven chains are wired up and verified
against the live portals:

- **Shufersal** — public Azure blob, indexed at `prices.shufersal.co.il`
- **Ten chains via the shared Cerberus portal** (`url.publishedprices.co.il`):
  רמי לוי, יוחננוף, אושר עד, טיב טעם, דור אלון, קשת טעמים, פרש מרקט,
  סטופ מרקט, סאלח דבאח, פוליצר

Both serve the same mandated XML (`Root/Items/Item`), keyed by barcode
(`ItemCode`). Data lands in the `products`, `chains` and `store_prices` tables.

### Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/healthcheck` | Liveness probe |
| `GET` | `/api/chains` | Chains the engine can scan |
| `POST` | `/api/sync-prices` | Scan the portals and upsert into Supabase |
| `GET` | `/api/products` | Ingested products with their price per chain |

Sync specific barcodes across every chain:

```bash
curl -X POST http://localhost:8000/api/sync-prices \
  -H "Content-Type: application/json" \
  -d '{"barcodes":["7290004131074"],"max_files_per_chain":1}'
```

Omit `barcodes` to seed an empty database from the newest published files
(`max_products` caps how many items per chain are taken). Restrict the run with
`{"chains":["shufersal","rami_levy"]}`. A chain that fails is reported in
`errors` rather than failing the whole call.

Read the results, cheapest chain first per product:

```bash
curl "http://localhost:8000/api/products?priced_only=true&limit=10"
```

Each chain publishes per-store files, so a sync samples the newest
`max_files_per_chain` stores and stores the modal price as the chain price.
Raising that value costs time but widens coverage. Promotional prices live in
separate `PromoFull` files, which are not ingested yet — `is_discount` is
therefore always `false`.


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
| `SUPABASE_URL` | — | Supabase project URL |
| `SUPABASE_KEY` | — | Supabase API key |

| Frontend (`frontend/.env.local`) | Default | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Base URL of the backend |
| `NEXT_PUBLIC_SUPABASE_URL` | — | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | — | Supabase anon/publishable key |

## Other frontend commands

```bash
npm run build   # production build
npm start       # serve the production build
npm run lint    # eslint
```
