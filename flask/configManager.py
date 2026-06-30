import json
import datetime

class ConfigManager:
    def __init__(self, config_file='config.json'):
        self.config_file = config_file
        self._config = None

    # Numeric config values that silently break indexing if set wrong.
    # Each entry: (low, high, example) -- value must satisfy low < x <= high.
    # - pagerank_tolerance: a convergence threshold; >= 0.1 barely iterates
    #   (the incident value 1 stopped pagerank after one iteration).
    # - uclust_identity: a fraction; vsearch --id fatally rejects anything > 1.0
    #   (the incident value 1.8 made clustering error out / reuse stale data).
    _NUMERIC_RANGES = {
        'pagerank_tolerance': (0.0, 0.1, '0.0001'),
        'uclust_identity': (0.0, 1.0, '0.8'),
    }

    @classmethod
    def _validate_config(cls, new_config):
        """Rejects out-of-range numeric values that silently break indexing."""
        for key, (low, high, example) in cls._NUMERIC_RANGES.items():
            if key not in new_config:
                continue
            try:
                value = float(new_config[key])
            except (TypeError, ValueError):
                raise ValueError(f"Config '{key}' must be a number, got {new_config[key]!r}")
            if not (low < value <= high):
                raise ValueError(
                    f"Config '{key}' must be in ({low}, {high}] (e.g. {example}), got {value}"
                )

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
        self._validate_config(new_config)
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
