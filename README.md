# JuContract ERP (Django)

Contract manager and mini-ERP for a small creative business: cash flow with installments, payment
receipts, an AI contract drafter, a contract archive and an AI market analyst.

This is a Django port of the Streamlit app [`st_jucontract`](https://github.com/VicourtBitt/st_jucontract).
The UI is in Brazilian Portuguese.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set GEMINI_API_KEY to use the AI features
python manage.py migrate
python manage.py seed_demo      # optional: sample data + user demo / demo12345
python manage.py createsuperuser
python manage.py runserver
```

Run the tests with `python manage.py test`.

WeasyPrint (contract PDF export) needs the Pango system libraries. On Debian/Ubuntu, install
`libpango-1.0-0 libpangoft2-1.0-0`. On macOS, run `brew install pango`.

## Module map (Streamlit → Django)

| Streamlit page | Django app / URL | Notes |
|---|---|---|
| `main.py` home | `core` · `/` | Now a real overview: monthly KPIs, overdue and upcoming installments, recent receipts. |
| `views/sales.py` | `finance` · `/financeiro/` | KPIs, 4 charts (Chart.js), new entry form, validate pending receipts/expenses, "pay all of the month". |
| `views/transactions.py` | `finance` · `/financeiro/auditoria/` | Transactions, installments (with status filter) and per-category tabs; transaction detail/edit/delete. |
| *(Supabase only)* | `finance` · `/financeiro/categorias/` | Category CRUD. The old app had no screen for this. |
| `views/receipt.py` | `receipts` · `/recibos/` | Multi-item receipts, ReportLab PDF, filters, edit (regenerates PDF), delete. |
| `views/creator.py` | `contracts` · `/contratos/criador/` | AI drafting from free text or a template; drafts are now **saved** (`/contratos/gerados/`). |
| `views/contract_manager.py` | `contracts` · `/contratos/modelos/` | Template CRUD. The two hardcoded photography bases are seeded by a migration. |
| `views/analyzer.py` + `components/upload_form.py` | `contracts` · `/contratos/arquivo/` | Upload, filter, preview, download, edit, delete. |
| `views/autentique.py`, `views/zapsign.py` | `contracts` · `/contratos/assinaturas/` | One page linking to both providers. |
| `views/market.py` | `market` · `/mercado/` | yfinance quote + Gemini analysis, persisted history, Chart.js price chart. |
| `ping_dbs.py` | — | Removed: there are no Supabase/Mongo free tiers to keep alive anymore. |

## What was refactored (and why)

- **One database instead of Supabase + MongoDB.** All data lives in the Django ORM (SQLite locally,
  Postgres via `DATABASE_URL`). Files are `FileField`s instead of binaries inside Mongo documents.
- **Authentication.** The Streamlit app was open to anyone with the URL. Every page now requires
  login (`core/middleware.py`). Users are managed in `/admin/`.
- **Money as `Decimal`, not float.** The installment split rounds to cents and the last installment
  absorbs the difference, so installments always add up to the total.
- **"Overdue" status actually works.** The old styling expected an `overdue` status that was never
  stored. It is now derived from the date (pending and past due) and shown everywhere.
- **Payments can be reverted** ("Estornar"). Editing a transaction rebuilds its schedule, but only
  while none of its installments are paid.
- **Destructive actions** use POST plus a confirmation step. Before, a single click deleted
  contracts, receipts and templates.
- **AI contract creator:**
  - Generated contracts are persisted, with draft and final states. They can be edited as HTML,
    downloaded as PDF, DOCX or HTML, and saved to the contract archive as a PDF.
  - The fields to fill are read from the template itself. The model's JSON list is only a fallback,
    so mismatches no longer leave placeholders unrendered.
  - Templates render in a Jinja **sandbox** with autoescaping, and `<script>` tags are stripped.
    Previews are served with a `Content-Security-Policy: sandbox` header.
  - The prompt no longer injects the CSS twice or wraps itself in JSON for no reason.
  - The DOCX export no longer prints the CSS as body text.
- **Market analysis:**
  - Ticker detection is fixed. The old rule appended `.SA` to anything of 6 characters or fewer,
    which broke `AAPL` and `MSFT`.
  - The real currency is displayed.
  - Recent closing prices go into the prompt.
  - AI markdown is sanitised before rendering.
  - Quotes are cached for 10 minutes.
- **E-signature pages** used iframes that Autentique and ZapSign block. They are now links that
  open in a new tab, next to the latest archived PDFs.
- **Receipts** use proper line items (`ReceiptItem`). The PDF uses a Portuguese long date without
  depending on the server locale, and the payee is prefilled from the last receipt.
- `requirements.txt` went from about 160 pinned packages to the ones the project actually uses.

## Migrating your existing data

```bash
pip install supabase pymongo
SUPABASE_URL=... SUPABASE_KEY=... MONGO_URI=... MONGO_DB=... \
  python manage.py import_legacy --dry-run   # check first
SUPABASE_URL=... SUPABASE_KEY=... MONGO_URI=... MONGO_DB=... \
  python manage.py import_legacy
```

The importer reads Supabase `categories`, `transactions`, `installments`, `contract_template` and
`search_history`, plus Mongo `contracts_dashboard` and `receipts_dashboard`. Issued receipt PDFs are
kept as they were, not re-rendered. Transactions without a category go to a "Sem Categoria"
category.

## Deploying (Heroku-like)

- The `Procfile` runs migrations on release and serves the app with gunicorn. WhiteNoise serves the
  static files.
- Set `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`
  and `GEMINI_API_KEY`.
- Heroku's disk is ephemeral, so uploaded contracts and receipt PDFs need object storage. Install
  `django-storages[boto3]` and set `AWS_STORAGE_BUCKET_NAME` and the related variables. This works
  with any S3-compatible service, including Supabase Storage and Cloudflare R2.
- For WeasyPrint on Heroku, add the `heroku-community/apt` buildpack. It installs the packages
  listed in `Aptfile`.
