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
    df_parsed = (df.withColumn("value", from_json(col("value").cast("string"), schema))
                 .select(col("value.*")))

    # print output to the console
    (df_parsed.writeStream
     .format("console")
     .outputMode("append")
     .start()
     .awaitTermination())
