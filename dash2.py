import streamlit as st
from kafka import KafkaConsumer
import json
import pandas as pd
import altair as alt
import pyodbc
import unidecode  # For transliterating non-Latin characters

# Kafka Configuration
KAFKA_TOPIC = "your_topic"
KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"

st.set_page_config(page_title="Live Kafka Stream Dashboard", layout="wide")
st.title("📡 Live Fashion Sales Dashboard")
st.markdown(f"Listening to Kafka topic: `{KAFKA_TOPIC}`")

# SQL Server connection
@st.cache_resource
def get_store_data():
    conn = pyodbc.connect(
        r"Driver={ODBC Driver 17 for SQL Server};"
        r"Server=DESKTOP-GU1M2GE\SQLEXPRESS;"
        r"Database=fashion;"
        r"Trusted_Connection=yes;"
    )
    query = "SELECT Store_ID, Country, City FROM dbo.stores"
    return pd.read_sql(query, conn)

@st.cache_resource
def get_product_data():
    conn = pyodbc.connect(
        r"Driver={ODBC Driver 17 for SQL Server};"
        r"Server=DESKTOP-GU1M2GE\SQLEXPRESS;"
        r"Database=fashion;"
        r"Trusted_Connection=yes;"
    )
    query = "SELECT Product_ID, Description_EN FROM dbo.products"
    return pd.read_sql(query, conn)

@st.cache_resource
def get_employee_data():
    conn = pyodbc.connect(
        r"Driver={ODBC Driver 17 for SQL Server};"
        r"Server=DESKTOP-GU1M2GE\SQLEXPRESS;"
        r"Database=fashion;"
        r"Trusted_Connection=yes;"
    )
    query = "SELECT Employee_ID, Name FROM dbo.employees"
    return pd.read_sql(query, conn)

# Load store, product, and employee data
store_df = get_store_data()
product_df = get_product_data()
employee_df = get_employee_data()

store_df["Store_ID"] = store_df["Store_ID"].astype(str)
product_df["Product_ID"] = product_df["Product_ID"].astype(str)
employee_df["Employee_ID"] = employee_df["Employee_ID"].astype(str)

# Define currency exchange rates to USD
exchange_rates = {
    "USD": 1,
    "EUR": 1 / 0.92,   # 1 EUR to USD
    "CNY": 1 / 6.45,   # 1 CNY to USD
    "GBP": 1 / 0.82    # 1 GBP to USD
}

# Kafka Consumer setup
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

        # Merge store metadata
        df = df.merge(store_df, left_on="Store ID", right_on="Store_ID", how="left")

        # Convert Invoice Total to USD based on the currency
        def convert_to_usd(row):
            currency = row["Currency"]
            if currency in exchange_rates:
                return row["Invoice Total"] * exchange_rates[currency]
            else:
                return row["Invoice Total"]

        df["Invoice Total (USD)"] = df.apply(convert_to_usd, axis=1)

        total_sales = df["Invoice Total (USD)"].sum()
        total_quantity = df["Quantity"].sum()

        city_sales = df.groupby("City")["Invoice Total (USD)"].sum().reset_index()
        country_sales = df.groupby("Country")["Invoice Total (USD)"].sum().reset_index().sort_values(by="Invoice Total (USD)", ascending=False)

        top_sold_products = df.groupby("Product ID")["Quantity"].sum().reset_index().sort_values(by="Quantity", ascending=False).head(7)
        top_cashiers = df.groupby("Employee ID")["Invoice Total (USD)"].sum().reset_index().sort_values(by="Invoice Total (USD)", ascending=False).head(5)

        # Merge product descriptions into top_sold_products
        top_sold_products = top_sold_products.merge(product_df[['Product_ID', 'Description_EN']], 
                                                   left_on="Product ID", 
                                                   right_on="Product_ID", 
                                                   how="left")

        # Rename Description_EN column to Product
        top_sold_products.rename(columns={"Description_EN": "Product"}, inplace=True)

        # Merge employee names into top_cashiers
        top_cashiers = top_cashiers.merge(employee_df[['Employee_ID', 'Name']], 
                                          left_on="Employee ID", 
                                          right_on="Employee_ID", 
                                          how="left")

        # Transliterate employee names to Latin letters
        top_cashiers["Name"] = top_cashiers["Name"].apply(lambda x: unidecode.unidecode(x))

        with placeholder.container():
            # KPIs
            st.subheader("📊 KPIs")
            col1, col2 = st.columns(2)
            col1.metric("Total Sales (USD)", f"${total_sales:,.2f}")
            col2.metric("Total Quantity", f"{total_quantity:,}")

            # Charts
            if not df["Time"].isna().all():
                st.subheader("📈 Sales Over Time")
                df["Time"] = pd.to_datetime(df["Time"], format="%H:%M:%S", errors="coerce").dt.time
                sales_chart = alt.Chart(df).mark_line().encode(
                    x=alt.X("Time:T", title="Time of Day"),
                    y=alt.Y("Invoice Total (USD):Q", title="Sales in USD"),
                    tooltip=["Time", "Invoice Total (USD)"]
                ).interactive()
                st.altair_chart(sales_chart, use_container_width=True)

            if not city_sales.empty:
                st.subheader("🌆 Sales by City (Column Chart)")
                top_cities = city_sales.head(5)
                column_chart_city = alt.Chart(top_cities).mark_bar().encode(
                    y=alt.Y("City:N", sort="-y", title="City"),
                    x=alt.X("Invoice Total (USD):Q", title="Sales in USD"),
                    tooltip=["City", "Invoice Total (USD)"],
                    color=alt.Color("City:N", legend=None)
                ).properties(width=800, height=400)
                st.altair_chart(column_chart_city, use_container_width=True)

            if not country_sales.empty:
                st.subheader("🌍 Top 5 Countries by Sales (Bar)")
                top_countries = country_sales.head(5)
                bar_chart = alt.Chart(top_countries).mark_bar().encode(
                    x=alt.X("Country:N", title="Country"),
                    y=alt.Y("Invoice Total (USD):Q", title="Sales in USD"),
                    tooltip=["Country", "Invoice Total (USD)"],
                    color="Country:N"
                )
                st.altair_chart(bar_chart, use_container_width=True)

            if not top_sold_products.empty:
                st.subheader("🔥 Top 7 Sold Products")
                st.dataframe(top_sold_products[['Product ID', 'Product', 'Quantity']], use_container_width=True)

            if not top_cashiers.empty:
                st.subheader("💼 Top 5 Cashiers with the Largest Bill")
                st.dataframe(top_cashiers[['Employee_ID', 'Name', 'Invoice Total (USD)']], use_container_width=True)

            st.subheader("🧾 Latest Transactions")
            st.dataframe(df.tail(20), use_container_width=True)

    else:
        st.warning("No data received from Kafka yet.")
