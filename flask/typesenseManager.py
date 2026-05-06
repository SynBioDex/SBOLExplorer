import typesense

class TypesenseManager:
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self._client = None

    def get_client(self):
        if self._client is None:
            self._client = typesense.Client(self.config_manager.get_typesense_config())
        return self._client

    def get_collection(self):
        name = self.config_manager.get_typesense_collection_name()
        return self.get_client().collections[name]
