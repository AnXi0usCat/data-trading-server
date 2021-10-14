from threading import Thread
import confluent_kafka


class Producer:
    """ Simple wrapper for the Kafka producer which includes
        a producer loop instance in a separate Thread
    """

    def __init__(self, configs):
        self._producer = confluent_kafka.Producer(configs)
        self._cancelled = False
        self._poll_thread = Thread(target=self._poll_loop)
        self._poll_thread.start()

    def _poll_loop(self):
        """  instance of the pooling loop with the Kafka broker
             should be only run in a separate thread,
             otherwise there is no way to cancel
        :return: None
        """
        while not self._cancelled:
            self._producer.poll(0.1)

    def produce(self, topic, key, value, on_delivery=None):
        """ Send messages to the Kafka broker.
            We are using the fire and forget method (due to volumes of data coming form the exchange)
            we don't have the luxury of retrying plus any single price change is not significant
            enough to have an impact on the result of candlestick calculations

        :param topic:
        :param key:
        :param value:
        :param on_delivery:
        :return:
        """
        self._producer.produce(topic=topic,
                               key=key,
                               value=value,
                               on_delivery=on_delivery)

    def close(self):
        """ Close the prodcuer
        """
        self._cancelled = True
        self._poll_thread.join()
