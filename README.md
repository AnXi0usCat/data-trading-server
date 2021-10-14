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

* **Aiohttp Web Server**: asynchronous web server written in python which is responsible for maintaining an open TCP socket connection with the exchange and receiving 
the stream of raw tick data, doing the data quality check, converting it to JSON format and passing it to Kafka producer. The server exposes two REST endpoints 
`start` and `stop` which provide a way of controlling the data flow through the entire system.
* **Apache Kafka**: Distributed, fault tolerant streaming data streaming system which is responsible for storing the JSON converted tick data in their own partitions (queues). 
I decided to store the data in Kafka prior starting the ETL because of the ability to replay any failed offsets from the Kafka partition in case of downstream ETL failure
which would have been impossible if we did ETL on the data received directly from TCP sockets.
* **Apache Spark - Structured Streaming**: Distributed data processing system which I used for the ETL process. In my setup it is split into three parts.
  1) Master Node (1 container): responsible for assigning tasks to the worker nodes.
  2) Worker Node (1 or more containers): Creates Kafka Consumer to read the data from the broker, performs ETL process and writes results to the sink.
  3) Driver Node (localhost): consists of the local `spark-submit` facility and the `candle_stick_data_etl.py` which specifies the configuration and the ETL process itself.
* **Postgres 13**: SQL Database which is used to store the ETL results (Cassandra would have been better because its distributed and hence optimised for concurrent writes, 
but the whole thing already took 40+ hours to set up as it is and the author is  tired and doesn't care anymore :) ).
* **Docker**: Every service in this list is running within its own Docker container which provides dependencies isolation and lets each component run on its own virtual machine.
* **Docker Compose**: Orchestration tool for docker containers, which allows me tto spin up and shut down all the distributed components at the same time.

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

## Data sources

## Data quality controls

## Addressing other scenarios