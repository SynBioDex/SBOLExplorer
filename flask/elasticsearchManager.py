import logging
import time

from elasticsearch import Elasticsearch

logger = logging.getLogger(__name__)

class ElasticsearchManager:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self._es = None

    def get_es(self, timeout=120, interval=3):
        """
        Gets an instance of elasticsearch

        The first call waits for Elasticsearch to answer, retrying every
        `interval` seconds for up to `timeout` seconds. When the whole stack
        starts at once (VM reboot, docker-compose up), Explorer reaches ES
        before ES is ready (~12 s); a single ping made startup crash.

        Returns: The instance of elasticsearch
        """
        if self._es is None:
            endpoint = self.config_manager.get_es_endpoint()
            es = Elasticsearch([endpoint], verify_certs=True)
            deadline = time.monotonic() + timeout
            while not es.ping():
                if time.monotonic() >= deadline:
                    raise ValueError(f'Elasticsearch connection failed: no response from {endpoint} within {timeout}s')
                logger.warning(f'Elasticsearch at {endpoint} is not ready yet; retrying in {interval}s')
                time.sleep(interval)
            # Only cache a client that answered, so a failed attempt is retried
            # on the next call instead of returning an unchecked client.
            self._es = es
        return self._es
