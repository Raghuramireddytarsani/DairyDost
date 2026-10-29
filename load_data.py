"""Clean the CSV and load it into MongoDB as nested documents.

Usage:  python load_data.py [path/to/dairy_dataset.csv] [--replace]
"""
import argparse
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from pymongo import ASCENDING, MongoClient

PROJECT_DIR = Path(__file__).resolve().parent

RENAME = {
    "Location": "location", "Total Land Area (acres)": "land_acres",
    "Number of Cows": "cows", "Farm Size": "farm_size", "Date": "date",
    "Product ID": "product_id", "Product Name": "product", "Brand": "brand",
    "Quantity (liters/kg)": "produced_qty", "Price per Unit": "list_price",
    "Total Value": "total_value", "Shelf Life (days)": "shelf_life_days",
    "Storage Condition": "storage", "Production Date": "production_date",
    "Expiration Date": "expiry_date", "Quantity Sold (liters/kg)": "qty_sold",
    "Price per Unit (sold)": "sold_price", "Approx. Total Revenue(INR)": "revenue",
    "Customer Location": "customer_location", "Sales Channel": "channel",
    "Quantity in Stock (liters/kg)": "in_stock",
    "Minimum Stock Threshold (liters/kg)": "min_threshold",
    "Reorder Quantity (liters/kg)": "reorder_qty",
}


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=RENAME)
    for c in df.select_dtypes(include=["object", "string"]).columns:
        df[c] = df[c].astype(str).str.strip()
    for c in ("date", "production_date", "expiry_date"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df = df.dropna(subset=["date", "production_date", "expiry_date"]).drop_duplicates()
    num = ["land_acres", "cows", "produced_qty", "list_price", "total_value", "qty_sold",
           "sold_price", "revenue", "in_stock", "min_threshold", "reorder_qty"]
    df[num] = df[num].clip(lower=0)
    return df


def to_doc(r) -> dict:
    """One CSV row -> one nested MongoDB document."""
    return {
        "date": r.date.to_pydatetime(),
        "month": r.date.strftime("%Y-%m"),
        "year": int(r.date.year),
        "farm": {"location": r.location, "land_acres": float(r.land_acres),
                 "cows": int(r.cows), "size": r.farm_size},
        "product": {"id": int(r.product_id), "name": r.product, "brand": r.brand,
                    "storage": r.storage, "shelf_life_days": int(r.shelf_life_days),
                    "list_price": float(r.list_price)},
        "batch": {"produced_qty": float(r.produced_qty), "total_value": float(r.total_value),
                  "production_date": r.production_date.to_pydatetime(),
                  "expiry_date": r.expiry_date.to_pydatetime()},
        "sale": {"qty_sold": int(r.qty_sold), "price": float(r.sold_price),
                 "revenue": float(r.revenue), "customer_location": r.customer_location,
                 "channel": r.channel},
        "inventory": {"in_stock": int(r.in_stock), "min_threshold": float(r.min_threshold),
                      "reorder_qty": float(r.reorder_qty)},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv",
        nargs="?",
        type=Path,
        default=PROJECT_DIR / "data" / "dairy_dataset.csv",
        help="CSV file to import (default: data/dairy_dataset.csv)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Drop and replace the existing dairydost.sales collection",
    )
    args = parser.parse_args()

    load_dotenv(PROJECT_DIR / ".env")
    uri = os.getenv("MONGODB_URI")
    if not uri:
        parser.error("Set MONGODB_URI in .env first (see .env.example).")
    if not args.csv.is_file():
        parser.error(f"CSV file not found: {args.csv}")

    df = clean(pd.read_csv(args.csv))
    docs = [to_doc(r) for r in df.itertuples(index=False)]

    with MongoClient(uri, serverSelectionTimeoutMS=8000) as client:
        col = client["dairydost"]["sales"]
        existing_count = col.count_documents({})
        if existing_count and not args.replace:
            parser.error(
                f"dairydost.sales already contains {existing_count} documents. "
                "Use --replace only if you intend to delete and reload them."
            )
        if args.replace:
            col.drop()

        for i in range(0, len(docs), 1000):
            col.insert_many(docs[i:i + 1000])

        col.create_index([("date", ASCENDING)])
        col.create_index([("month", ASCENDING)])
        col.create_index([("product.name", ASCENDING), ("month", ASCENDING)])
        col.create_index([("farm.location", ASCENDING)])
        col.create_index([("sale.channel", ASCENDING)])
        col.create_index([("batch.expiry_date", ASCENDING)])
        print(f"Loaded {col.count_documents({})} documents into dairydost.sales")


if __name__ == "__main__":
    main()
