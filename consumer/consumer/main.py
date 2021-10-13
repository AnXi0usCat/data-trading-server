from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import StructType, DecimalType, TimestampType, StringType

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

    # group by pair and calculate a 5 minute candlestick (open, low, hight, close) price and other
    # statistics overlapping every 1 minute
    df_parsed = df_parsed.groupby("pair", window("timestamp", "5 minute", "1 minute")).agg(
        count("*").alias("count"),
        mean("mid_price").alias("mean"),
        min("mid_price").alias("min"),
        max("mid_price").alias("max"),
        first("mid_price").alias("open"),
        last("mid_price")).alias("close")

    # print output to the console
    (df_parsed.writeStream
     .format("console")
     .outputMode("update")
     .option("checkpointLocation", "...")
     # .option("failOnDataLoss", "false")
     .option("truncate", "false")
     .start()
     .awaitTermination())
