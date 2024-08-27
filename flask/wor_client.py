import requests
from logger import Logger

logger_ = Logger()
class WORClient:
    @staticmethod
    def get_wor_instances():
        """
        Gets all instances of SynBioHub from the Web of Registries
        Returns:

        """
        try:
            response = requests.get('https://wor.synbiohub.org/instances/')
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            logger_.log('[ERROR] Web of Registries had a problem!')
            return []