from pyspark.sql import SparkSession

if __name__ == '__main__':

    spark = (SparkSession.builder
             .config("spark.master", "spark://0.0.0.0:7077")
             .config("spark.driver.host", "192.168.0.13")
             .config("spark.submit.deployMode", "client")
             .config("spark.driver.bindAddress", "192.168.0.13")
             .config("spark.executor.memory", "512m")
             .getOrCreate())

    # spark = (SparkSession.builder
    #          # .config("spark.master", "spark://0.0.0.0:7077")
    #          # .config("spark.driver.host", "192.168.0.13")
    #          # .config("spark.submit.deployMode", "client")
    #          # .config("spark.driver.bindAddress", "192.168.0.13")
    #          # .config("spark.executor.memory", "512m")
    #          .getOrCreate())

    df = (spark
          .readStream
          .format("kafka")
          .option("kafka.bootstrap.servers", "0.0.0.0:9094,kafka:9092")
          .option("subscribe", "price_changes1")
          .load())

    (df.writeStream
        .format("console")
        .outputMode("append")
        .start()
        .awaitTermination())
