from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import StructType, DecimalType, TimestampType, StringType
import psycopg2


class ForeachPostgresWriter:

    def __init__(self, dbname, username, password, host, port):
        self._dbname = dbname
        self._username = username
        self._password = password
        self._host = host
        self._port = port
        self._conn = None
        self._query = f"""INSERT INTO public.candle_stick_five_min (currency_pair, open_price, high_price, low_price, 
                              close_price, open_time, close_time) VALUES (%s, %s, %s, %s, %s, %s, %s) 
                          ON CONFLICT (currency_pair, open_time) 
                          DO UPDATE SET 
                              open_price =  EXCLUDED.open_price,
                              high_price =  EXCLUDED.high_price,
                              low_price =   EXCLUDED.low_price,
                              close_price=  EXCLUDED.close_price; """

    def open(self, partition_id, epoch_id):
        # Open connection. This method is optional in Python.
        self._conn = psycopg2.connect(
            f"""dbname={self._dbname} user={self._username} 
            password={self._password} host={self._host} port={self._port}"""
        )
        return True

    def process(self, row):
        # Write row to connection. This method is not optional in Python.
        cursor = self._conn.cursor()
        cursor.execute(self._query,
                             (row.currency_pair,
                              row.open_price,
                              row.high_price,
                              row.low_price,
                              row.close_price,
                              row.open_time,
                              row.close_time))
        self._conn.commit()
        cursor.close()

    def close(self, error):
        # Close the connection. This method is optional in Python.
        self._conn.close()


if __name__ == '__main__':
    spark = (SparkSession.builder
             .config("spark.master", "spark://0.0.0.0:7077")
             .config("spark.driver.host", "192.168.0.13")
             .config("spark.submit.deployMode", "client")
             .config("spark.driver.bindAddress", "192.168.0.13")
             .config("spark.executor.memory", "512m")
             .getOrCreate())

    # set log level to WARN
    spark.sparkContext.setLogLevel('WARN')

    # define a schema for the value returned from Kafka
    schema = (StructType()
              .add("bid", DecimalType())
              .add("ask", DecimalType())
              .add("pair", StringType())
              .add("timestamp", TimestampType()))

    # start streaming data from the kafka broker
    df = (spark
          .readStream
          .format("kafka")
          .option("kafka.bootstrap.servers", "0.0.0.0:9094,kafka:9092")
          .option("subscribe", "price_changes1")
          .option("startingOffsets", "latest")
          .load())

    # parse kafka message value and convert it to a data frame
    # calculate the mid market price for each element
    df_parsed = (df.withColumn("value", from_json(col("value").cast("string"), schema)).select(
        ((col("value.bid") + col("value.ask")) / 2.0).alias("mid_price"),
        col("value.timestamp"),
        col("value.pair"))
    )

    # group by pair and calculate a 5 minute candlestick (open, low, high, close) price and other
    # statistics overlapping every 1 minute
    df_parsed = df_parsed.groupby("pair", window("timestamp", "5 minute", "1 minute")).agg(
        count("*").alias("count"),
        mean("mid_price").alias("mean"),
        min("mid_price").alias("low_price"),
        max("mid_price").alias("high_price"),
        first("mid_price").alias("open_price"),
        last("mid_price").alias("close_price"))

    # split the window function results in to the start and end timestamp
    df_parsed = df_parsed.select(
        col("pair").alias("currency_pair"),
        col("open_price"),
        col("high_price"),
        col("low_price"),
        col("close_price"),
        col("window.start").alias("open_time"),
        col("window.end").alias("close_time")
    )

    # create a Postgres sink
    postgres_writer = ForeachPostgresWriter(
        dbname="tradingdata",
        username="anonymous",
        password="fedjikrejnkifdngkjrew",
        host="192.168.0.13",
        port=5433)

    # write the results in to the postgres sink
    query = (df_parsed.writeStream
             .outputMode("update")
             .foreach(postgres_writer)
             .start().
             awaitTermination())
