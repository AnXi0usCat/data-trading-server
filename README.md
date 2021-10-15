# Streaming Data Processing Pipeline - Udacity Data Engineering NanoDegree Capstone Project

## Purpose of the project

I have built a cryptocurrency algorithmic trading system, which requires 12 most recent 5 minute prices in the 
candlestick format (open, high, low, close). At first, I was relying on the candle stick data provided by the exchange 
through the REST API endpoint, but quickly realised that I can experience delays of up to 10 seconds to get the
latest data which made it unusable since even one second of delay is an eternity in the world of algorithmic trading.

The solution is to create my own data source. I have to open up a TCP connection to exchange, stream the raw tick data
and create candle stick prices on the fly.

There are several challenges associated with building such a system:
1) It has to be fast - average event processing latency should not be over ~500ms
2) It must handle high volumes of data - at peak times it can receive >= 25000 events per minute per asset.
3) it should be easily scalable without increase in latency or loss of throughput - it has to be distributed
4) it has to be fault-tolerant and ideally should provide exactly once guarantees

## Technologies used

* **Aiohttp Web Server (producer)**: asynchronous web server written in python which is responsible for maintaining an open TCP socket connection with the exchange and receiving 
the stream of raw tick data, doing the data quality check, converting it to JSON format and passing it to Kafka producer. The server exposes two REST endpoints 
`start` and `stop` which provide a way of controlling the data flow through the entire system.
* **Apache Kafka**: Distributed, fault tolerant streaming data streaming system which is responsible for storing the JSON converted tick data in their own partitions (queues). 
I decided to store the data in Kafka prior starting the ETL because of the ability to replay any failed offsets from the Kafka partition in case of downstream ETL failure
which would have been impossible if we did ETL on the data received directly from TCP sockets.
* **Apache Spark - Structured Streaming (consumer)**: Distributed data processing system which I used for the ETL process. In my setup it is split into three parts.
  1) Master Node (1 container): responsible for assigning tasks to the worker nodes.
  2) Worker Node (1 or more containers): Creates Kafka Consumer to read the data from the broker, performs ETL process and writes results to the sink.
  3) Driver Node (localhost): consists of the local `spark-submit` facility and the `candle_stick_data_etl.py` which specifies the configuration and the ETL process itself.
* **Postgres 13**: SQL Database which is used to store the ETL results (Cassandra would have been better because its distributed and hence optimised for concurrent writes, 
but the whole thing already took 40+ hours to set up as it is and the author is  tired and doesn't care anymore :) ).
* **Docker**: Every service in this list is running within its own Docker container which provides dependencies isolation and lets each component run on its own virtual machine.
* **Docker Compose**: Orchestration tool for docker containers, which allows me tto spin up and shut down all the distributed components at the same time.

## Data sources and formats

I have used two external data sources in the form of TCP socket streams from the cryptocurrency exchange for the assets BTCUSDT and ETHUSDT. 
The data payload arrives in the form of binary encoded string:
```bash
b'{
  "u":400900217,     // order book updateId
  "s":"BNBUSDT",     // symbol
  "b":"25.35190000", // best bid price
  "B":"31.21000000", // best bid qty
  "a":"25.36520000", // best ask price
  "A":"40.66000000"  // best ask qty
}'
```
Internally the raw data is stored in a Kafka partition as a JSON string which acts as a data source for the
ETL run bt Spark Structured Streaming worker:
```bash
'{"bid": "23456.60", "ask": "23457.60", "pair": "BTCUSDT", "2021-01-01 23:34:45.000"}'
```

## Data quality controls

I have used two data quality checks for this project. Both of the checks are implemented before writing data to a persistence layer.

* I do a first data quality check before writing a JSON converted tick data to a Kafka topic. I check if the bid and ask price contain
missing values and if they could be converted to a numeric type. The check is implemented before writing to Kafka because it's hard to
deal with corrupted data once it is committed to a partition. Since more than one consumer group can read from any partition they will all have to
implement a data quality checks of their own if it is not performed beforehand.
* Second quality check is done before persisting the ETL results postgres database. Spark workers do the transformation on the raw data in micro-batches
and results for every time window are constantly updated with every new batch of data and persisted to the database. 
I have a unique constraint in the database on the `currency_pair` name and the `open_time`, so in order to satisfy it and avoid duplicates or errors
i perform an upsert operation if the data already exist. This way at the end of the 5 minute window, we will have only the latest 
version of data persisted in the database.

## ETL

Every Spark worker starts a Kafka consumer, which will continuously poll the broker for the fresh data which will arrive in micro-batches (1-20 events).
All events arriving from Kafka will come as key, value pairs. Where the key would be the name of the currency pair e.g `BTCUSDT` and the value would be a
JSON encoded string:
```bash
'{"bid": "23456.60", "ask": "23457.60", "pair": "BTCUSDT", "2021-01-01 23:34:45.000"}'
```
* The first step is to calculate the mid-market price for each event (bid + ask) / 2.
* Create a window function which will group by the currency pair and aggregate the prices into five minute intervals which will overlap every minute
```
     window start    |     window end
---------------------+---------------------
 2021-10-14 18:54:00 | 2021-10-14 18:59:00
 2021-10-14 18:55:00 | 2021-10-14 19:00:00
 2021-10-14 18:56:00 | 2021-10-14 19:01:00
 2021-10-14 18:57:00 | 2021-10-14 19:02:00
 2021-10-14 18:58:00 | 2021-10-14 19:03:00
```
* then we calculate the min(), max(), first(), last() values for every window
* write updated results from every received batch in to the custom postgres sink
* where final result is a continuously updated table in the postgres database, which is ready to be queried for trading:
```bash
adingdata=> select * from candle_stick_five_min order by currency_pair, open_time limit 30;
  id  | currency_pair | open_price | high_price | low_price | close_price |      open_time      |     close_time
------+---------------+------------+------------+-----------+-------------+---------------------+--------------------- 
    3 | BTCUSDT       |    58000.0 |    58059.0 |   57996.0 |     58036.0 | 2021-10-14 18:54:00 | 2021-10-14 18:59:00
    5 | BTCUSDT       |    58000.0 |    58059.0 |   57980.0 |     58029.0 | 2021-10-14 18:55:00 | 2021-10-14 19:00:00
    1 | BTCUSDT       |    58000.0 |    58059.0 |   57912.0 |     57923.0 | 2021-10-14 18:56:00 | 2021-10-14 19:01:00
    2 | BTCUSDT       |    58000.0 |    58059.0 |   57867.5 |     57923.0 | 2021-10-14 18:57:00 | 2021-10-14 19:02:00
    4 | BTCUSDT       |    58000.0 |    58059.0 |   57848.0 |     57878.0 | 2021-10-14 18:58:00 | 2021-10-14 19:03:00
   55 | BTCUSDT       |    58036.0 |    58045.0 |   57848.0 |     57881.0 | 2021-10-14 18:59:00 | 2021-10-14 19:04:00
  188 | BTCUSDT       |    58029.0 |    58040.0 |   57848.0 |     57917.0 | 2021-10-14 19:00:00 | 2021-10-14 19:05:00
  310 | BTCUSDT       |    57923.0 |    57939.5 |   57848.0 |     57896.0 | 2021-10-14 19:01:00 | 2021-10-14 19:06:00
  465 | BTCUSDT       |    57923.0 |    57928.0 |   57830.0 |     57863.0 | 2021-10-14 19:02:00 | 2021-10-14 19:07:00
  584 | BTCUSDT       |    57878.0 |    57920.0 |   57830.0 |     57855.0 | 2021-10-14 19:03:00 | 2021-10-14 19:08:00
  695 | BTCUSDT       |    57881.0 |    57920.0 |   57810.0 |     57834.0 | 2021-10-14 19:04:00 | 2021-10-14 19:09:00
  845 | BTCUSDT       |    57917.0 |    57920.0 |   57801.0 |     57821.0 | 2021-10-14 19:05:00 | 2021-10-14 19:10:00
 1004 | BTCUSDT       |    57896.0 |    57920.0 |   57637.0 |     57729.0 | 2021-10-14 19:06:00 | 2021-10-14 19:11:00
 1183 | BTCUSDT       |    57863.0 |    57920.0 |   57516.0 |     57601.0 | 2021-10-14 19:07:00 | 2021-10-14 19:12:00
 1336 | BTCUSDT       |    57855.0 |    57855.0 |   57476.0 |     57559.0 | 2021-10-14 19:08:00 | 2021-10-14 19:13:00
 1476 | BTCUSDT       |    57834.0 |    57837.0 |   57476.0 |     57520.5 | 2021-10-14 19:09:00 | 2021-10-14 19:14:00
 1570 | BTCUSDT       |    57821.0 |    57824.5 |   57252.0 |     57269.0 | 2021-10-14 19:10:00 | 2021-10-14 19:15:00
 1690 | BTCUSDT       |    57729.0 |    57755.0 |   56820.0 |     57048.5 | 2021-10-14 19:11:00 | 2021-10-14 19:16:00
 1797 | BTCUSDT       |    57601.0 |    57620.0 |   56820.0 |     57306.0 | 2021-10-14 19:12:00 | 2021-10-14 19:17:00
 1911 | BTCUSDT       |    57558.5 |    57600.0 |   56820.0 |     57246.0 | 2021-10-14 19:13:00 | 2021-10-14 19:18:00
 2011 | BTCUSDT       |    57520.5 |    57562.0 |   56820.0 |     57306.0 | 2021-10-14 19:14:00 | 2021-10-14 19:19:00
   14 | ETHUSDT       |     3798.0 |     3800.0 |    3798.0 |      3799.0 | 2021-10-14 18:54:00 | 2021-10-14 18:59:00
   11 | ETHUSDT       |     3798.0 |     3802.0 |    3796.0 |      3800.0 | 2021-10-14 18:55:00 | 2021-10-14 19:00:00
    9 | ETHUSDT       |     3798.0 |     3802.0 |    3793.0 |      3794.0 | 2021-10-14 18:56:00 | 2021-10-14 19:01:00
   15 | ETHUSDT       |     3798.0 |     3802.0 |    3792.0 |      3797.0 | 2021-10-14 18:57:00 | 2021-10-14 19:02:00
    8 | ETHUSDT       |     3798.0 |     3802.0 |    3792.0 |      3798.0 | 2021-10-14 18:58:00 | 2021-10-14 19:03:00
   51 | ETHUSDT       |     3799.0 |     3806.0 |    3792.0 |      3803.0 | 2021-10-14 18:59:00 | 2021-10-14 19:04:00
  189 | ETHUSDT       |     3800.0 |     3807.0 |    3792.0 |      3807.0 | 2021-10-14 19:00:00 | 2021-10-14 19:05:00
  316 | ETHUSDT       |     3794.0 |     3807.0 |    3792.0 |      3803.0 | 2021-10-14 19:01:00 | 2021-10-14 19:06:00
  466 | ETHUSDT       |     3797.0 |     3807.0 |    3793.0 |      3801.0 | 2021-10-14 19:02:00 | 2021-10-14 19:07:00
  589 | ETHUSDT       |     3798.0 |     3807.0 |    3797.0 |      3797.0 | 2021-10-14 19:03:00 | 2021-10-14 19:08:00
  697 | ETHUSDT       |     3803.0 |     3807.0 |    3796.0 |      3797.0 | 2021-10-14 19:04:00 | 2021-10-14 19:09:00
  840 | ETHUSDT       |     3807.0 |     3807.0 |    3794.0 |      3795.0 | 2021-10-14 19:05:00 | 2021-10-14 19:10:00
 1003 | ETHUSDT       |     3803.0 |     3803.0 |    3786.0 |      3794.0 | 2021-10-14 19:06:00 | 2021-10-14 19:11:00
 1174 | ETHUSDT       |     3801.0 |     3802.0 |    3782.5 |      3790.0 | 2021-10-14 19:07:00 | 2021-10-14 19:12:00
 1343 | ETHUSDT       |     3797.0 |     3799.0 |    3782.5 |      3788.0 | 2021-10-14 19:08:00 | 2021-10-14 19:13:00
 1471 | ETHUSDT       |     3797.0 |     3797.0 |    3782.5 |      3787.0 | 2021-10-14 19:09:00 | 2021-10-14 19:14:00
```

## Addressing other scenarios

### Data increases by 100x
The only way the data increase the amount of data by 100x is to add additional 100 currency pairs to the data stream.
Our system will be able to handle this load, but we will have to horizontally scale out several components in order to
keep things running smoothly.
* The exchange allows to open up to 1024 data streams per single TCP connections in theory we should be able to 
handle the increased load, or we can start several producers each opening their own stream and receiving a subset 
of cryptocurrency pairs.
* We will have to increase the number of partitions in our Kafka topic, ideally we will do one partition per currency pair
so if we have any issues with some pairs it will not affect the data flow for the other ones.
* Kafka supports a single consumer in every consumer group per one partition, so we can scale up our Spark cluster to a 100
workers, where every worker would be responsible for processing a single currency pair. This way we will not sacrifice the
processing speed latency or data throughput.
* The only bottleneck would be the Postgres persistence layer because we cannot scale it out horizontally it will be dealing with
a 100x concurrent writes to a single table. This could be fine but in that scenario I would be inclined to substitute Postgres with
Apache Cassandra. Since Cassandra is distributed, it is optimised for concurrent writes and increasing the number of nodes
will correspond to a one to one increase in data throughput.

### The pipelines would be run on a daily basis by 7 am every day

This is a streaming pipeline, it runs constantly, so this scenario is irrelevant.

### The database needed to be accessed by 100+ people

If the database has to be accessed by a 100 people a day I would suggest on creating a dedicated read replica database for this purpose,
so the users won't lock the main table on the production database with their queries.

## Starting the pipeline locally

Make sure you have Docker and docker-compose installed on your machine.

1) Make sure that you have python 3.6 running on your computer. The Bitnami Spark docker images are running on python3.6. 
It is a requirement to have the same version of python on both the Spark cluster (in containers) and the spark Driver (localhost)
2) Make sure you have Apache Spark installed locally, since we will use the local `spark-submit` facility to submit the spark job to 
containerised Spark cluster
3) Install python dependencies on your computer
```bash
pip3 install -t requirementts.txt
```
4) Set the actual host of the Spark driver in the configuration so the Spark workers can communicate with it
```python
# i know i should set this with environment variables but im f**king tired and just don't care anymore
spark = (SparkSession.builder
         .config("spark.master", "spark://0.0.0.0:7077")
         .config("spark.driver.host", "192.168.0.13") # change this to your hostname
         .config("spark.submit.deployMode", "client")
         .config("spark.driver.bindAddress", "192.168.0.13") # change this to your hostname
         .config("spark.executor.memory", "512m")
         .getOrCreate())
```

5) go to the base directory and start your service with docker compose (it will take a while to start):
```bash
docker-compose up --build -d
```
if everything is fine you should see all of the components running in docker containers with `docker ps -a`:
```bash
MihhailFjodorovs-MacBook-Pro:data-trading-server mihhailf$ docker ps -a
CONTAINER ID   IMAGE                           COMMAND                  CREATED        STATUS        PORTS                                                                                  NAMES
4061a61b2c9a   data-trading-server_producer    "python3.9 -u app.py"    17 hours ago   Up 17 hours   8082/tcp, 0.0.0.0:8082->8080/tcp, :::8082->8080/tcp                                    data-trading-server_producer_1
2e1c7245bf0d   wurstmeister/kafka:2.13-2.6.0   "start-kafka.sh"         17 hours ago   Up 17 hours   0.0.0.0:9094->9094/tcp, :::9094->9094/tcp, 0.0.0.0:56174->9092/tcp                     data-trading-server_kafka_1
caba1d29d6e9   postgres:13.3-alpine            "docker-entrypoint.s…"   17 hours ago   Up 17 hours   0.0.0.0:5433->5432/tcp, :::5433->5432/tcp                                              data-trading-server_postgres_1
408c0c0cb4c9   bitnami/spark:3                 "/opt/bitnami/script…"   17 hours ago   Up 17 hours                                                                                          data-trading-server_spark-worker_1
9e094db6ac7c   wurstmeister/zookeeper          "/bin/sh -c '/usr/sb…"   17 hours ago   Up 17 hours   22/tcp, 2888/tcp, 3888/tcp, 0.0.0.0:2181->2181/tcp, :::2181->2181/tcp                  data-trading-server_zookeeper_1
6a9cba984fc5   bitnami/spark:3                 "/opt/bitnami/script…"   17 hours ago   Up 17 hours   0.0.0.0:7077->7077/tcp, :::7077->7077/tcp, 0.0.0.0:8084->8080/tcp, :::8084->8080/tcp   data-trading-server_spark_1
```
6) At this point you can start ingesting the data from the exchange in to oyu prodcuer, converting it to JSON and storing in the Kafka topic. Producer is exposing `start` endpoint
which can be reached from `http:localhost:8082/start` and the data ingestion can be stopped by hitting the `http:localhost:8082/stop` endpoint.
7) if everything worked correctly 🤞 then we should be able to log in to our postgres container `psql -h localhost -p 5433 -d tradingdata -U anonymous` 
(You can find the password in the `postgres-startup-scripts/create_db.sql`) and see the table being constantly updated with the results:
```bash
tradingdata=> select * from candle_stick_five_min order by currency_pair, open_time limit 5;
 id | currency_pair | open_price | high_price | low_price | close_price |      open_time      |     close_time
----+---------------+------------+------------+-----------+-------------+---------------------+---------------------
  3 | BTCUSDT       |    58000.0 |    58059.0 |   57996.0 |     58036.0 | 2021-10-14 18:54:00 | 2021-10-14 18:59:00
  5 | BTCUSDT       |    58000.0 |    58059.0 |   57980.0 |     58029.0 | 2021-10-14 18:55:00 | 2021-10-14 19:00:00
  1 | BTCUSDT       |    58000.0 |    58059.0 |   57912.0 |     57923.0 | 2021-10-14 18:56:00 | 2021-10-14 19:01:00
  2 | BTCUSDT       |    58000.0 |    58059.0 |   57867.5 |     57923.0 | 2021-10-14 18:57:00 | 2021-10-14 19:02:00
  4 | BTCUSDT       |    58000.0 |    58059.0 |   57848.0 |     57878.0 | 2021-10-14 18:58:00 | 2021-10-14 19:03:00
(5 rows)
```
