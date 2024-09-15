import json
import datetime

class ConfigManager:
    def __init__(self, config_file='config.json'):
        self.config_file = config_file
        self._config = None

    def load_config(self):
        """
        Gets a copy of the config file
        Returns: Config file in JSON

        """
        if self._config is None:
            with open(self.config_file) as f:
                self._config = json.load(f)
        return self._config

    def save_config(self, new_config):
        """
        Overwrites the existing config with a new config file
        Args:
            new_config: New config file with the updated information
        Returns:
        """
        config = self.load_config()
        config.update(new_config)
        with open(self.config_file, 'w') as f:
            json.dump(config, f)

    def save_time(self, attribute):
        """
        Saves the current time to an attribute in the config
        Args:
            attribute: Config attribute to save current time to

        Returns:

        """
        config = self.load_config()
        config[attribute] = datetime.datetime.now().isoformat()
        self.save_config(config)

    def get_es_endpoint(self):
        return self.load_config().get('elasticsearch_endpoint')
    
    def save_update_end_time(self):
        """
        Save end time of indexing
        Returns:

        """
        return self.save_time("last_update_end")


    def save_update_start_time(self):
        """
        Save start time of indexing
        Returns:

        """
        return self.save_time("last_update_start")
