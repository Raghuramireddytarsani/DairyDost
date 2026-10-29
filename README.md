# 🥛 DairyDost

A web app that helps dairy farmers and small dairy businesses track **sales, stock and expiry**, spot problems early, and forecast revenue. Built with **MongoDB**, **PyMongo**, **Streamlit**, **Plotly** and **scikit-learn**.

## Problem statement
Small dairy producers record sales and stock in notebooks or scattered sheets. As a result they miss low-stock situations, let batches expire unsold, cannot see which products, channels and regions earn the most, and cannot plan ahead. DairyDost puts all of this in one place on a flexible MongoDB database and adds an ML revenue forecast.

## Features
| Page | What it does |
|---|---|
| Dashboard | Revenue, quantity sold, average price, monthly trend, product / channel / location breakdowns |
| Sales Analytics | Product × channel heatmap, price realization (sold price ÷ list price), revenue per cow by farm size, brand and storage views |
| Inventory & Alerts | Batches below minimum stock with reorder quantities, and batches that will expire with stock still unsold (value at risk) |
| Forecast | Monthly revenue forecast (trend + seasonality) with a 12-month hold-out check against a naive baseline |
| Add Record | Insert a new sale/batch into MongoDB; revenue and stock are calculated automatically |

All pages respond to the sidebar filters (year, farm location, product, channel).

## Why MongoDB
- **Nested documents:** each record embeds `farm`, `product`, `batch`, `sale` and `inventory` sub-documents, so one read returns the full picture.
- **Aggregation pipeline:** `$match`, `$group`, `$addFields`, `$divide`, `$multiply`, `$sort`, `$project` power every chart and alert (see `queries.py`).
- **Indexes:** on date, month, `product.name + month`, `farm.location`, `sale.channel` and `batch.expiry_date`.
- **Flexible schema:** new fields (for example per-animal records) can be added later without a migration.

## Project structure
```
app.py          Streamlit UI (5 pages)
queries.py      All MongoDB aggregation pipelines
forecast.py     Revenue forecasting (scikit-learn)
db.py           MongoDB connection
load_data.py    Clean the CSV and load it into MongoDB
data/           dairy_dataset.csv
```

## Run it locally
1. Create a free cluster on [MongoDB Atlas](https://www.mongodb.com/atlas). Add a database user, and under Network Access allow your IP.
2. Copy `.env.example` to `.env` in the project root (next to `app.py`) and paste your connection string into `MONGODB_URI`. Never commit `.env`.
3. Install dependencies and load the sample data once:
   ```bash
   python -m pip install -r requirements.txt
   python load_data.py
   ```
   The loader refuses to overwrite an existing collection. To intentionally replace its contents, pass `--replace`.
4. Start the app:
   ```bash
   streamlit run app.py
   ```

## Deploy to Streamlit Community Cloud
1. Push the project to GitHub. Include `app.py`, the other Python modules, `requirements.txt`, and `data/dairy_dataset.csv`. Do **not** commit `.env` or `.streamlit/secrets.toml`; both are git-ignored.
2. Before deploying, create the Atlas database user and load the sample data from a trusted machine with `python load_data.py`. The deployed app does not import the CSV automatically. Do not run `python load_data.py --replace` unless you intend to delete and reload the `dairydost.sales` collection.
3. Create an app on [Streamlit Community Cloud](https://streamlit.io/cloud), select this GitHub repository and branch, and set the main file to `app.py`.
4. In the app's **Settings → Secrets**, add the URI as TOML:
   ```toml
   MONGODB_URI = "mongodb+srv://<user>:<url-encoded-password>@<cluster-host>/?retryWrites=true&w=majority"
   ```
   Use your actual Atlas values; do not include angle brackets. Keep the URI private.
5. In Atlas **Network Access**, allow the app to reach the cluster. Community Cloud does not provide a fixed outbound IP for a simple IP allowlist setup, so `0.0.0.0/0` may be required. If you use it, protect the cluster with a strong database password and a database user limited to `readWrite` on `dairydost`; never use an Atlas admin account.
6. Open the deployed app and confirm the dashboard shows sales records. If it reports that the database is empty, load the data into the same Atlas cluster and database named `dairydost`.

### Public-app security
The app currently has no login or user-level authorization. Anyone who can reach a deployed instance can view its dashboard data and use **Add Record** to write to the database. Deploy only synthetic/public demo data until authentication and access controls are added.

## Data
`data/dairy_dataset.csv` has 4,325 records (2019-2022) across 15 states and 10 dairy products, with sales, pricing, stock and expiry fields. In the loader, rows are cleaned (trimmed text, parsed dates, duplicates dropped, negatives clipped) and stored as nested documents.

## Limitations (be upfront about these)
- The data looks **synthetic**: values such as land area (10-1000 acres), cow count (10-100) and prices (₹10-100) are spread almost evenly, and every record has a unique farm. So the app treats each record as a sales/stock batch, not as a tracked farm.
- It has **no per-cow data** (milk yield, vaccination, breeding). Herd management is future work.
- The forecast beats a naive baseline on the hold-out year but is a rough guide, since the data has little real trend.
- Expiry alerts use an adjustable "as-of" date because the data ends in December 2022.

## Future work
Per-animal milk logging and health tracking, user login for multiple farmers, a RAG vet assistant on MongoDB Atlas Vector Search, WhatsApp/SMS alerts, Hindi and Punjabi UI.

## Talking points for interviews
- Modeled denormalized, nested documents and explained why that suits read-heavy dashboards.
- Wrote aggregation pipelines for KPIs, price realization, low-stock and expiry-risk alerts.
- Validated the forecast on a held-out year against a baseline instead of just reporting a fit.
