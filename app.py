from datetime import date, datetime, time, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import queries as Q
from db import get_db
from forecast import fit_and_forecast

st.set_page_config(page_title="DairyDost", page_icon="🥛", layout="wide")


def inr(x: float) -> str:
    """Format rupees in lakh / crore."""
    x = float(x or 0)
    if x >= 1e7:
        return f"₹{x / 1e7:,.2f} Cr"
    if x >= 1e5:
        return f"₹{x / 1e5:,.2f} L"
    return f"₹{x:,.0f}"


col = get_db()["sales"]


@st.cache_data(ttl=300, show_spinner=False)
def run(fn_name: str, filt: tuple, extra: tuple = ()):
    """Cached call into queries.py. `filt` = (years, locations, products, channels)."""
    return getattr(Q, fn_name)(get_db()["sales"], Q.build_match(*filt), *extra)


@st.cache_data(ttl=600, show_spinner=False)
def options():
    c = get_db()["sales"]
    first = c.find_one(sort=[("date", 1)])
    last = c.find_one(sort=[("date", -1)])
    return {
        "years": Q.distinct_values(c, "year"),
        "locations": Q.distinct_values(c, "farm.location"),
        "products": Q.distinct_values(c, "product.name"),
        "channels": Q.distinct_values(c, "sale.channel"),
        "customer_locations": Q.distinct_values(c, "sale.customer_location"),
        "brands": Q.distinct_values(c, "product.brand"),
        "storage": Q.distinct_values(c, "product.storage"),
        "sizes": Q.distinct_values(c, "farm.size"),
        "last_date": last["date"] if last else datetime.today(),
        "count": c.count_documents({}),
    }


opt = options()
if opt["count"] == 0:
    st.warning("The database is empty. Run `python load_data.py` first.")
    st.stop()

# ---------------- sidebar ----------------
st.sidebar.title("🥛 DairyDost")
page = st.sidebar.radio(
    "Go to", ["Dashboard", "Sales Analytics", "Inventory & Alerts", "Forecast", "Add Record"]
)
st.sidebar.divider()
st.sidebar.subheader("Filters")
f_years = st.sidebar.multiselect("Year", opt["years"])
f_loc = st.sidebar.multiselect("Farm location", opt["locations"])
f_prod = st.sidebar.multiselect("Product", opt["products"])
f_chan = st.sidebar.multiselect("Sales channel", opt["channels"])
st.sidebar.caption("Leave a filter empty to include everything.")
filt = (tuple(f_years), tuple(f_loc), tuple(f_prod), tuple(f_chan))


def show_empty():
    st.info("No data for these filters. Try widening them.")


# ---------------- Dashboard ----------------
if page == "Dashboard":
    st.title("Dairy sales & inventory dashboard")
    k = run("kpis", filt)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Revenue", inr(k["revenue"]))
    c2.metric("Quantity sold", f"{k['qty_sold']:,.0f} L/kg")
    c3.metric("Avg selling price", f"₹{k['avg_price']:,.2f}")
    c4.metric("Sales records", f"{k['records']:,}")

    monthly = run("monthly_revenue", filt)
    if monthly.empty:
        show_empty()
    else:
        st.plotly_chart(px.line(monthly, x="month", y="revenue", markers=True,
                                title="Monthly revenue (₹)"))
        a, b = st.columns(2)
        by_prod = run("revenue_by", filt, ("Product",))
        a.plotly_chart(px.bar(by_prod, x="Product", y="revenue", title="Revenue by product"))
        by_chan = run("revenue_by", filt, ("Channel",))
        b.plotly_chart(px.pie(by_chan, names="Channel", values="revenue", hole=0.45,
                              title="Revenue by sales channel"))
        by_cust = run("revenue_by", filt, ("Customer location",)).head(10)
        st.plotly_chart(px.bar(by_cust, x="revenue", y="Customer location", orientation="h",
                               title="Top 10 customer locations by revenue")
                        .update_yaxes(autorange="reversed"))

# ---------------- Sales Analytics ----------------
elif page == "Sales Analytics":
    st.title("Sales analytics")
    t1, t2, t3, t4 = st.tabs(["Product × channel", "Pricing", "Farm size", "Brands & storage"])

    with t1:
        mat = run("product_channel_matrix", filt)
        if mat.empty:
            show_empty()
        else:
            pivot = mat.pivot(index="product", columns="channel", values="revenue").fillna(0)
            st.plotly_chart(px.imshow(pivot, text_auto=".3s", aspect="auto",
                                      title="Revenue heatmap (₹)"))

    with t2:
        pr = run("price_realization", filt)
        if pr.empty:
            show_empty()
        else:
            st.caption("Selling price ÷ list price. Below 1.0 means you sold under list price.")
            st.plotly_chart(px.bar(pr, x="product", y="ratio", title="Price realization by product")
                            .add_hline(y=1.0, line_dash="dash"))
            st.dataframe(pr.round(3), hide_index=True)

    with t3:
        sz = run("revenue_per_cow_by_size", filt)
        if sz.empty:
            show_empty()
        else:
            st.plotly_chart(px.bar(sz, x="farm_size", y="revenue_per_cow",
                                   title="Average revenue per cow, per record (₹)"))
            st.dataframe(sz.round(2), hide_index=True)

    with t4:
        left, right = st.columns(2)
        br = run("revenue_by", filt, ("Brand",))
        st_ = run("revenue_by", filt, ("Storage",))
        if br.empty:
            show_empty()
        else:
            left.plotly_chart(px.bar(br, x="Brand", y="revenue", title="Revenue by brand"))
            right.plotly_chart(px.bar(st_, x="Storage", y="revenue", title="Revenue by storage type"))

# ---------------- Inventory & Alerts ----------------
elif page == "Inventory & Alerts":
    st.title("Inventory & alerts")
    k = run("kpis", filt)
    low = run("low_stock", filt, (200,))
    summ = run("low_stock_by_product", filt)
    n_low = int(summ["low_stock_records"].sum()) if not summ.empty else 0
    pct = (n_low / k["records"] * 100) if k["records"] else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Batches below minimum stock", f"{n_low:,}")
    c2.metric("Share of all batches", f"{pct:.1f}%")
    c3.metric("Suggested reorder (total)",
              f"{summ['reorder_total'].sum():,.0f} L/kg" if not summ.empty else "0")

    st.subheader("🔴 Low-stock alerts")
    if summ.empty:
        st.success("No batches are below their minimum stock threshold.")
    else:
        st.plotly_chart(px.bar(summ, x="product", y="low_stock_records",
                               title="Low-stock batches by product"))
        st.caption("Top 200 by shortfall (minimum threshold − current stock).")
        st.dataframe(low.round(2), hide_index=True)

    st.subheader("⏳ Expiry risk")
    st.caption("The data ends in " + opt["last_date"].strftime("%b %Y") +
               ", so choose the 'as of' date you want to check from.")
    d1, d2 = st.columns(2)
    asof_d = d1.date_input("As-of date", value=opt["last_date"].date())
    days = d2.slider("Expiring within (days)", 7, 90, 30)
    asof = datetime.combine(asof_d, time.min)
    exp = run("expiring", filt, (asof, days))
    if exp.empty:
        st.success("No batches with remaining stock expire in this window.")
    else:
        e1, e2 = st.columns(2)
        e1.metric("Batches at risk", f"{len(exp):,}")
        e2.metric("Value at risk", inr(exp["value_at_risk"].sum()))
        st.dataframe(exp.round(2), hide_index=True)

# ---------------- Forecast ----------------
elif page == "Forecast":
    st.title("Revenue forecast")
    monthly = run("monthly_revenue", filt)
    horizon = st.slider("Months to forecast", 3, 12, 6)
    res = fit_and_forecast(monthly, horizon) if not monthly.empty else None
    if res is None:
        st.info("Need at least 24 months of data for the current filters. Widen the filters.")
    else:
        hist = res["history"].assign(type="Actual")
        fc = res["forecast"].assign(type="Forecast")
        st.plotly_chart(px.line(pd.concat([hist, fc]), x="month", y="revenue", color="type",
                                markers=True, title="Monthly revenue: actual and forecast (₹)"))
        c1, c2 = st.columns(2)
        c1.metric("Model error on last 12 months (MAPE)", f"{res['mape']:.1f}%")
        c2.metric("Naive 'average month' baseline error", f"{res['baseline_mape']:.1f}%")
        better = res["mape"] < res["baseline_mape"]
        st.caption(
            "Model: linear trend + month-of-year seasonality, trained on all but the last 12 "
            "months and tested on those 12. "
            + ("It beats the baseline, but treat the forecast as a rough guide." if better
               else "It does not beat the baseline, so treat the forecast with caution.")
        )
        with st.expander("Hold-out check (actual vs predicted)"):
            st.dataframe(res["holdout"].round(0), hide_index=True)
        st.dataframe(res["forecast"].round(0), hide_index=True)

# ---------------- Add Record ----------------
else:
    st.title("Add a sales record")
    st.caption("Writes a new document to MongoDB. Revenue and stock are calculated for you.")
    with st.form("add"):
        a, b, c = st.columns(3)
        sale_date = a.date_input("Date", value=date.today())
        prod = b.selectbox("Product", opt["products"])
        brand = c.selectbox("Brand", opt["brands"])

        a, b, c = st.columns(3)
        loc = a.selectbox("Farm location", opt["locations"])
        cows = b.number_input("Number of cows", 1, 10000, 50)
        size = c.selectbox("Farm size", opt["sizes"])

        a, b, c = st.columns(3)
        land = a.number_input("Land area (acres)", 0.1, 100000.0, 100.0)
        storage = b.selectbox("Storage", opt["storage"])
        shelf = c.number_input("Shelf life (days)", 1, 365, 30)

        a, b, c = st.columns(3)
        produced = a.number_input("Quantity produced (L/kg)", 1.0, 1e6, 500.0)
        list_price = b.number_input("List price per unit (₹)", 0.1, 10000.0, 50.0)
        prod_date = c.date_input("Production date", value=date.today())

        a, b, c = st.columns(3)
        sold = a.number_input("Quantity sold (L/kg)", 0, 1000000, 200)
        sold_price = b.number_input("Selling price per unit (₹)", 0.1, 10000.0, 48.0)
        channel = c.selectbox("Sales channel", opt["channels"])

        a, b, c = st.columns(3)
        cust = a.selectbox("Customer location", opt["customer_locations"])
        min_thr = b.number_input("Minimum stock threshold", 0.0, 1e6, 50.0)
        reorder = c.number_input("Reorder quantity", 0.0, 1e6, 100.0)
        go = st.form_submit_button("Save record")

    if go:
        if sold > produced:
            st.error("Quantity sold cannot be more than quantity produced.")
        else:
            pid_doc = col.find_one({"product.name": prod}, {"product.id": 1})
            d = datetime.combine(sale_date, time.min)
            pd_ = datetime.combine(prod_date, time.min)
            col.insert_one({
                "date": d, "month": d.strftime("%Y-%m"), "year": d.year,
                "farm": {"location": loc, "land_acres": float(land), "cows": int(cows), "size": size},
                "product": {"id": pid_doc["product"]["id"] if pid_doc else 0, "name": prod,
                            "brand": brand, "storage": storage, "shelf_life_days": int(shelf),
                            "list_price": float(list_price)},
                "batch": {"produced_qty": float(produced), "total_value": float(produced * list_price),
                          "production_date": pd_, "expiry_date": pd_ + timedelta(days=int(shelf))},
                "sale": {"qty_sold": int(sold), "price": float(sold_price),
                         "revenue": float(sold * sold_price), "customer_location": cust,
                         "channel": channel},
                "inventory": {"in_stock": int(produced - sold), "min_threshold": float(min_thr),
                              "reorder_qty": float(reorder)},
            })
            st.cache_data.clear()
            st.success(f"Saved. Revenue {inr(sold * sold_price)}, stock left {int(produced - sold)}.")
            if produced - sold < min_thr:
                st.warning("This batch is already below its minimum stock threshold.")
