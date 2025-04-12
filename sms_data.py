import pyodbc
import csv
from kafka import KafkaConsumer
import json
import os

# SQL Server connection
def get_customer_info(customer_id):
    conn = pyodbc.connect(
        r"Driver={ODBC Driver 17 for SQL Server};"
        r"Server=DESKTOP-GU1M2GE\SQLEXPRESS;"
        r"Database=Skippy;"
        r"Trusted_Connection=yes;"
    )
    
    query = """
    SELECT [Telephone], [Name] FROM [Skippy].[dbo].[customers] WHERE [Customer ID] = ?
    """
    cursor = conn.cursor()
    cursor.execute(query, customer_id)
    result = cursor.fetchone()
    conn.close()
    
    if result:
        return result[0], result[1]  # Return both Telephone and Name
    return None, None

# Kafka Consumer
consumer = KafkaConsumer(
    'skippy',  # Topic
    bootstrap_servers='localhost:9092',  # Kafka server
    group_id='your_group_id',
    value_deserializer=lambda x: json.loads(x.decode('utf-8'))
)

# Open the CSV file in append mode
file_exists = os.path.exists('for_push.csv')

# Track processed customer IDs to avoid duplication
processed_customer_ids = set()

with open('for_push.csv', mode='a', newline='', encoding='utf-8') as csv_file:
    fieldnames = ['Telephone', 'Message']
    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

    # Write header if the file doesn't already exist
    if not file_exists:
        writer.writeheader()

    for message in consumer:
        data = message.value

        # Check if the customer ID has already been processed
        customer_id = data['Customer ID']
        if customer_id in processed_customer_ids:
            continue  # Skip this record if it's already processed

        # Get customer phone number and name from the database
        customer_phone, customer_name = get_customer_info(customer_id)

        if customer_phone and customer_name:
            # Prepare the personalized message
            thank_you_message = f"Dear {customer_name}, thank you for visiting Skippy, we wish you a wonderful day!"

            # Write to the CSV file
            writer.writerow({'Telephone': customer_phone, 'Message': thank_you_message})
            csv_file.flush()  # Ensure immediate write
            print(f"Saved: {customer_phone} - {thank_you_message}")

            # Mark this customer ID as processed
            processed_customer_ids.add(customer_id)
        else:
            print(f"Phone number or name for Customer ID {customer_id} not found.")
