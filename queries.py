"""All MongoDB aggregation pipelines for DairyDost (pure PyMongo, no Streamlit)."""
from datetime import timedelta

import pandas as pd

# Whitelisted group-by fields (label -> document path)
GROUP_FIELDS = {
    "Product": "$product.name",
    "Brand": "$product.brand",
    "Channel": "$sale.channel",
    "Customer location": "$sale.customer_location",
    "Farm location": "$farm.location",
    "Farm size": "$farm.size",
    "Storage": "$product.storage",
}


def build_match(years=(), locations=(), products=(), channels=()) -> dict:
    m = {}
    if years:
        m["year"] = {"$in": list(years)}
    if locations:
        m["farm.location"] = {"$in": list(locations)}
    if products:
        m["product.name"] = {"$in": list(products)}
    if channels:
        m["sale.channel"] = {"$in": list(channels)}
    return m


def _df(col, pipeline) -> pd.DataFrame:
    return pd.DataFrame(list(col.aggregate(pipeline)))


# ---------- dropdown helpers ----------
def distinct_values(col, path: str) -> list:
    return sorted(col.distinct(path))


# ---------- dashboard ----------
def kpis(col, m) -> dict:
    rows = list(col.aggregate([
        {"$match": m},
        {"$group": {"_id": None,
                    "revenue": {"$sum": "$sale.revenue"},
                    "qty_sold": {"$sum": "$sale.qty_sold"},
                    "avg_price": {"$avg": "$sale.price"},
                    "records": {"$sum": 1}}},
    ]))
    r = rows[0] if rows else {}
    return {"revenue": r.get("revenue") or 0, "qty_sold": r.get("qty_sold") or 0,
            "avg_price": r.get("avg_price") or 0, "records": r.get("records") or 0}


def monthly_revenue(col, m) -> pd.DataFrame:
    df = _df(col, [
        {"$match": m},
        {"$group": {"_id": "$month", "revenue": {"$sum": "$sale.revenue"},
                    "qty_sold": {"$sum": "$sale.qty_sold"}}},
        {"$sort": {"_id": 1}},
        {"$project": {"_id": 0, "month": "$_id", "revenue": 1, "qty_sold": 1}},
    ])
    return df


def revenue_by(col, m, label: str) -> pd.DataFrame:
    path = GROUP_FIELDS[label]
    return _df(col, [
        {"$match": m},
        {"$group": {"_id": path, "revenue": {"$sum": "$sale.revenue"},
                    "qty_sold": {"$sum": "$sale.qty_sold"}, "records": {"$sum": 1}}},
        {"$sort": {"revenue": -1}},
        {"$project": {"_id": 0, label: "$_id", "revenue": 1, "qty_sold": 1, "records": 1}},
    ])


# ---------- sales analytics ----------
def product_channel_matrix(col, m) -> pd.DataFrame:
    return _df(col, [
        {"$match": m},
        {"$group": {"_id": {"product": "$product.name", "channel": "$sale.channel"},
                    "revenue": {"$sum": "$sale.revenue"}}},
        {"$project": {"_id": 0, "product": "$_id.product", "channel": "$_id.channel",
                      "revenue": 1}},
    ])


def price_realization(col, m) -> pd.DataFrame:
    """Average (sold price / list price) per product. <1 means discounting."""
    return _df(col, [
        {"$match": m},
        {"$group": {"_id": "$product.name",
                    "ratio": {"$avg": {"$cond": [
                        {"$gt": ["$product.list_price", 0]},
                        {"$divide": ["$sale.price", "$product.list_price"]},
                        None,
                    ]}},
                    "avg_list": {"$avg": "$product.list_price"},
                    "avg_sold": {"$avg": "$sale.price"}}},
        {"$sort": {"ratio": 1}},
        {"$project": {"_id": 0, "product": "$_id", "ratio": 1, "avg_list": 1, "avg_sold": 1}},
    ])


def revenue_per_cow_by_size(col, m) -> pd.DataFrame:
    return _df(col, [
        {"$match": m},
        {"$group": {"_id": "$farm.size",
                    "revenue_per_cow": {"$avg": {"$cond": [
                        {"$gt": ["$farm.cows", 0]},
                        {"$divide": ["$sale.revenue", "$farm.cows"]},
                        None,
                    ]}},
                    "avg_cows": {"$avg": "$farm.cows"}, "records": {"$sum": 1}}},
        {"$project": {"_id": 0, "farm_size": "$_id", "revenue_per_cow": 1,
                      "avg_cows": 1, "records": 1}},
    ])


# ---------- inventory & alerts ----------
def _low_stock_stages(m):
    return [
        {"$match": m},
        {"$addFields": {"shortfall": {"$subtract": ["$inventory.min_threshold",
                                                    "$inventory.in_stock"]}}},
        {"$match": {"shortfall": {"$gt": 0}}},
    ]


def low_stock(col, m, limit=200) -> pd.DataFrame:
    return _df(col, _low_stock_stages(m) + [
        {"$sort": {"shortfall": -1}},
        {"$limit": limit},
        {"$project": {"_id": 0, "date": 1, "product": "$product.name",
                      "brand": "$product.brand", "location": "$farm.location",
                      "in_stock": "$inventory.in_stock",
                      "min_threshold": "$inventory.min_threshold",
                      "shortfall": 1, "reorder_qty": "$inventory.reorder_qty"}},
    ])


def low_stock_by_product(col, m) -> pd.DataFrame:
    return _df(col, _low_stock_stages(m) + [
        {"$group": {"_id": "$product.name", "low_stock_records": {"$sum": 1},
                    "total_shortfall": {"$sum": "$shortfall"},
                    "reorder_total": {"$sum": "$inventory.reorder_qty"}}},
        {"$sort": {"low_stock_records": -1}},
        {"$project": {"_id": 0, "product": "$_id", "low_stock_records": 1,
                      "total_shortfall": 1, "reorder_total": 1}},
    ])


def expiring(col, m, asof, days=30, limit=200) -> pd.DataFrame:
    """Batches that still have stock and expire within `days` after `asof`."""
    mm = dict(m)
    mm["batch.expiry_date"] = {"$gte": asof, "$lte": asof + timedelta(days=days)}
    mm["inventory.in_stock"] = {"$gt": 0}
    return _df(col, [
        {"$match": mm},
        {"$addFields": {"value_at_risk": {"$multiply": ["$inventory.in_stock", "$sale.price"]}}},
        {"$sort": {"value_at_risk": -1}},
        {"$limit": limit},
        {"$project": {"_id": 0, "product": "$product.name", "brand": "$product.brand",
                      "location": "$farm.location", "expiry_date": "$batch.expiry_date",
                      "in_stock": "$inventory.in_stock", "value_at_risk": 1}},
    ])
