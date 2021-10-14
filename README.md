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

* **aiohttp web server**: asynchronous web server written in python which is responsible for maintaining an open TCP socket connection with the exchange and receiving 
the stream of raw tick data, doing the data quality check, converting it to JSON format and passing it to Kafka producer. The server exposes two REST endpoints 
`start` and `stop` which provide a way of controlling the data flow through the entire system
* **Apache Kafka**: Distributed, fault tolerant streaming data streaming system which is responsible for storing the JSON converted tick data in their own partitions (queues). 
I decided to store the data in Kafka prior starting the ETL because of the ability to replay any failed offsets from the Kafka partition in case of downstream ETL failure
which would have been impossible if we did ETL on the data received directly from TCP sockets.
* **Apache Spark: Structured Streaming** Distributed data processing system which I used for the ETL process. In my setup it is split into three parts.
  1) Master Node (1 container): responsible for assigning tasks to the worker nodes
  2) Worker Node (1 or more containers): Creates Kafka Consumer to read the data from the broker, performs ETL process and writes results to the sink
  3) Driver Node (localhost): consists of the local `spark-submit` facility and the `candle_stick_data_etl.py` which specifies the configuration and the ETL process itself
* **Postgres 13**: SQL Database which is used to store the ETL results (Cassandra would have been better because its distributed and hence optimised for concurrent writes, 
but the whole thing already took 40+ hours to set up as it is and the author is  tired and doesn't care anymore :) )
* **Docker**: Every service in this list is running within its own Docker container which provides dependencies isolation and lets each component run on its own virtual machine.
* **Docker Compose**: Orchestration tool for docker containers, which allows me tto spin up and shut down all the distributed components at the same time

## ETL

## Data sources

## Data quality controls

## Addressing other scenarios