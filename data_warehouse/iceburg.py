from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("iceberg-local") \
    .config("spark.jars",
            "/home/rohan/projects/airflow/data_warehouse/iceberg-spark-runtime-4.0_2.13-1.10.1.jar") \
    .config("spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions") \
    .config("spark.sql.catalog.local",
            "org.apache.iceberg.spark.SparkCatalog") \
    .config("spark.sql.catalog.local.type", "hadoop") \
    .config("spark.sql.catalog.local.warehouse",
            "/home/rohan/projects/airflow/data_warehouse/iceberg_warehouse") \
    .getOrCreate()

spark.sparkContext.setLogLevel("ERROR")
print("Iceberg ready:", spark.version)


# Ensure namespace exists
spark.sql("CREATE NAMESPACE IF NOT EXISTS local.db")

# Create table
spark.sql("""
    CREATE TABLE IF NOT EXISTS local.db.sales (
        order_id   BIGINT,
        customer   STRING,
        product    STRING,
        amount     DOUBLE,
        region     STRING,
        order_ts   TIMESTAMP
    ) USING iceberg
    PARTITIONED BY (region)
""")

from datetime import datetime
from pyspark.sql import Row

data = [
    Row(1, "Alice", "Laptop",  85000.0, "West",  datetime(2024, 1, 10)),
    Row(2, "Bob",   "Phone",   32000.0, "East",  datetime(2024, 1, 11)),
    Row(3, "Carol", "Tablet",  45000.0, "West",  datetime(2024, 2, 5)),
    Row(4, "Dave",  "Monitor", 18000.0, "South", datetime(2024, 2, 20)),
]

df = spark.createDataFrame(
    data,
    ["order_id","customer","product","amount","region","order_ts"]
)

# Write data
df.writeTo("local.db.sales").append()

# Queries
spark.sql("SELECT * FROM local.db.sales").show(truncate=False)
spark.sql("SELECT * FROM local.db.sales.history").show(truncate=False)
spark.sql("SELECT * FROM local.db.sales.snapshots").show(truncate=False)