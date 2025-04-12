import streamlit as st
from kafka import KafkaConsumer
import json
import pandas as pd
import altair as alt
import pyodbc
import plotly.express as px
import unidecode

# Kafka Configuration
KAFKA_TOPIC = "skippy"
KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"

st.set_page_config(page_title="Live Kafka Stream Dashboard", layout="wide")
st.image("logo.png", width=230) 
st.title("📡 Skippy Live")
st.markdown(f"Listening to Kafka topic: `{KAFKA_TOPIC}`")

# SQL Server connection
@st.cache_resource
def get_store_data():
    conn = pyodbc.connect(
        r"Driver={ODBC Driver 17 for SQL Server};"
        r"Server=DESKTOP-GU1M2GE\SQLEXPRESS;"
        r"Database=Skippy;"
        r"Trusted_Connection=yes;"
    )
    return pd.read_sql("SELECT [Store ID], [Store Name], Country, City FROM dbo.stores", conn)

@st.cache_resource
def get_product_data():
    conn = pyodbc.connect(
        r"Driver={ODBC Driver 17 for SQL Server};"
        r"Server=DESKTOP-GU1M2GE\SQLEXPRESS;"
        r"Database=Skippy;"
        r"Trusted_Connection=yes;"
    )
    return pd.read_sql("SELECT [Product ID], [Description EN] FROM dbo.products", conn)

@st.cache_resource
def get_employee_data():
    conn = pyodbc.connect(
        r"Driver={ODBC Driver 17 for SQL Server};"
        r"Server=DESKTOP-GU1M2GE\SQLEXPRESS;"
        r"Database=Skippy;"
        r"Trusted_Connection=yes;"
    )
    return pd.read_sql("SELECT [Employee ID], Name FROM dbo.employees", conn)

# Load metadata
store_df = get_store_data()
product_df = get_product_data()
employee_df = get_employee_data()

store_df["Store ID"] = store_df["Store ID"].astype(str)
product_df["Product ID"] = product_df["Product ID"].astype(str)
employee_df["Employee ID"] = employee_df["Employee ID"].astype(str)

exchange_rates = {
    "USD": 1,
    "EUR": 1 / 0.92,
    "CNY": 1 / 6.45,
    "GBP": 1 / 0.82
}

# Kafka Consumer
try:
    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="latest",
        enable_auto_commit=True,
        group_id="streamlit-dashboard"
    )
    st.success("Connected to Kafka successfully!")
except Exception as e:
    st.error(f"Failed to connect to Kafka: {e}")
    st.stop()

placeholder = st.empty()
data = []

for message in consumer:
    record = message.value
    data.append(record)

    if len(data) > 1000:
        data = data[-1000:]

    df = pd.DataFrame(data)

    if not df.empty:
        df = df.drop_duplicates()
        df["Quantity"] = pd.to_numeric(df.get("Quantity"), errors="coerce").fillna(0)
        df["Invoice Total"] = pd.to_numeric(df.get("Invoice Total"), errors="coerce").fillna(0)
        df["Date"] = pd.to_datetime(df.get("Date"), errors="coerce").dt.date
        df["Time"] = df.get("Time")
        df["Store ID"] = df["Store ID"].astype(str)

        df = df.merge(store_df, on="Store ID", how="left")

        df["Invoice Total (USD)"] = df.apply(
            lambda row: row["Invoice Total"] * exchange_rates.get(row["Currency"], 1),
            axis=1
        )

        total_sales = df["Invoice Total (USD)"].sum()
        total_quantity = df["Quantity"].sum()

        city_sales = df.groupby("City")["Invoice Total (USD)"].sum().reset_index()
        country_sales = df.groupby("Country")["Invoice Total (USD)"].sum().reset_index().sort_values(by="Invoice Total (USD)", ascending=False)

        top_sold_products = df.groupby("Product ID")["Quantity"].sum().reset_index().sort_values(by="Quantity", ascending=False).head(7)
        top_sold_products = top_sold_products.merge(product_df, on="Product ID", how="left")
        top_sold_products.rename(columns={"Description EN": "Product"}, inplace=True)

        top_cashiers = df.groupby("Employee ID")["Invoice Total (USD)"].sum().reset_index().sort_values(by="Invoice Total (USD)", ascending=False).head(5)
        top_cashiers = top_cashiers.merge(employee_df, on="Employee ID", how="left")
        top_cashiers["Name"] = top_cashiers["Name"].apply(lambda x: unidecode.unidecode(x))

        payment_method_sales = df.groupby("Payment Method")["Invoice Total (USD)"].sum().reset_index()
        payment_method_dist = df['Payment Method'].value_counts().reset_index()
        payment_method_dist.columns = ['Payment Method', 'Count']

        discount_summary = df.groupby("Discount")["Invoice Total (USD)"].agg(
            Total_Sales='sum',
            Transaction_Count='count'
        ).reset_index()
        discount_summary["Discount"] = discount_summary["Discount"].apply(lambda x: "No Discount" if x == 0 else str(x))

        with placeholder.container():
            st.subheader("📊 KPIs")
            col1, col2 = st.columns(2)
            col1.metric("Total Sales (USD)", f"${total_sales:,.2f}")
            col2.metric("Total Quantity", f"{total_quantity:,}")

            if not df["Time"].isna().all():
                st.subheader("📈 Sales Over Time")
                df["Time"] = pd.to_datetime(df["Time"], format="%H:%M:%S", errors="coerce").dt.time
                sales_chart = alt.Chart(df).mark_line().encode(
                    x=alt.X("Time:T", title="Time of Day"),
                    y=alt.Y("Invoice Total (USD):Q", title="Sales in USD"),
                    tooltip=["Time", "Invoice Total (USD)"]
                ).interactive()
                st.altair_chart(sales_chart, use_container_width=True)

            if not city_sales.empty or not country_sales.empty:
                st.subheader("🌍 Sales by City and Country")
                col1, col2 = st.columns(2)

                if not city_sales.empty:
                    col1.subheader("🌆 Top 5 Cities by Sales")
                    top_cities = city_sales.head(5)
                    chart_city = alt.Chart(top_cities).mark_bar(color="#DDA0DD").encode(
                        y=alt.Y("City:N", sort="-y"),
                        x=alt.X("Invoice Total (USD):Q"),
                        tooltip=["City", "Invoice Total (USD)"]
                    ).properties(width=350, height=400)
                    col1.altair_chart(chart_city, use_container_width=True)

                if not country_sales.empty:
                    col2.subheader("🌍 Top 5 Countries by Sales")
                    top_countries = country_sales.head(5)
                    chart_country = alt.Chart(top_countries).mark_bar(color="#40E0D0").encode(
                        y=alt.Y("Country:N"),
                        x=alt.X("Invoice Total (USD):Q"),
                        tooltip=["Country", "Invoice Total (USD)"]
                    ).properties(width=350, height=400)
                    col2.altair_chart(chart_country, use_container_width=True)

            if not top_sold_products.empty:
                st.subheader("🔥 Top 7 Sold Products")
                st.dataframe(top_sold_products[["Product ID", "Product", "Quantity"]], use_container_width=True)

            if not top_cashiers.empty:
                st.subheader("💼 Top 5 Cashiers with the Largest Bill")
                st.dataframe(top_cashiers[["Employee ID", "Name", "Invoice Total (USD)"]], use_container_width=True)

            st.subheader("💸 Sales by Discount")
            st.dataframe(discount_summary, use_container_width=True)

            discount_chart = alt.Chart(discount_summary).mark_bar(color="#87CEFA").encode(
                x=alt.X("Discount:O", title="Discount Rate"),
                y=alt.Y("Total_Sales:Q", title="Total Sales in USD"),
                tooltip=["Discount", "Total_Sales", "Transaction_Count"]
            ).properties(
                title="🛍️ Total Sales by Discount Rate",
                width=600,
                height=400
            )
            # join store names and id
            store_sales = df.groupby("Store ID")["Invoice Total (USD)"].sum().reset_index()
            store_sales = store_sales.merge(store_df[["Store ID", "Store Name"]], on="Store ID", how="left")
            top_store_sales = store_sales.sort_values(by="Invoice Total (USD)", ascending=False).head(7)
            # store sales chart
            store_sales_chart = alt.Chart(top_store_sales).mark_bar(color="#40E0D0").encode(
                x=alt.X("Invoice Total (USD):Q", title="Total Sales in USD"),
                y=alt.Y("Store Name:N", title="Store Name", sort="-x"),  # هنا بنعرض اسم المحل
                tooltip=["Store Name", "Invoice Total (USD)"]
            ).properties(
                title="🏬 Store Sales Comparison",
                width=600,
                height=400
            )
            st.subheader("🏬 Store Sales Comparison")
            st.altair_chart(store_sales_chart, use_container_width=True)
            st.altair_chart(discount_chart, use_container_width=True)

            st.subheader("💳 Payment Method Distribution")
            payment_method_pie = px.pie(
                payment_method_sales,
                names="Payment Method",
                values="Invoice Total (USD)",
                title="💳 Payment Method Distribution"
            )
            st.plotly_chart(payment_method_pie, use_container_width=True)


            st.subheader("🧾 Latest Transactions")
            st.dataframe(df.tail(20), use_container_width=True)
    else:
        st.warning("No data received from Kafka yet.")
