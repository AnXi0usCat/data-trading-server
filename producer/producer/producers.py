from threading import Thread
import confluent_kafka


class Producer:
    def __init__(self, configs):
        self._producer = confluent_kafka.Producer(configs)
        self._cancelled = False
        self._poll_thread = Thread(target=self._poll_loop)
        self._poll_thread.start()

    def _poll_loop(self):
        while not self._cancelled:
            self._producer.poll(0.1)

    def close(self):
        self._cancelled = True
        self._poll_thread.join()

    def produce(self, topic, key, value, on_delivery=None):
        self._producer.produce(topic=topic,
                               key=key,
                               value=value,
                               on_delivery=on_delivery)
