from elasticsearch import Elasticsearch

class ElasticsearchManager:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self._es = None

    def get_es(self):
        """
        Gets an instance of elasticsearch
        Returns: The instance of elasticsearch
        """
        if self._es is None:
            self._es = Elasticsearch([self.config_manager.get_es_endpoint()], verify_certs=True)
            if not self._es.ping():
                raise ValueError('Elasticsearch connection failed')
        return self._es