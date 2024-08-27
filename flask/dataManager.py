import pickle
import os
class DataManager:
    def __init__(self, clusters_filename='dumps/clusters_dump', uri2rank_filename='dumps/uri2rank_dump'):
        self.clusters_filename = clusters_filename
        self.uri2rank_filename = uri2rank_filename
        self._clusters = None
        self._uri2rank = None

    def save_clusters(self, clusters):
        """
        Save clusters of parts
        Args:
            new_clusters: Clusters to be saved

        Returns:

        """
        self._clusters = clusters
        self._serialize(self._clusters, self.clusters_filename)

    def get_clusters(self):
        if self._clusters is None:
            self._clusters = self._deserialize(self.clusters_filename)
        return self._clusters

    def save_uri2rank(self, uri2rank):
        """
        Saves the pagerank of all URI's
        Args:
            new_uri2rank:

        Returns:

        """
        self._uri2rank = uri2rank
        self._serialize(self._uri2rank, self.uri2rank_filename)

    def get_uri2rank(self):
        """
        Gets all pageranks of URI's
        Returns:

        """
        if self._uri2rank is None:
            self._uri2rank = self._deserialize(self.uri2rank_filename)
        return self._uri2rank

    @staticmethod
    def _serialize(data, filename):
        """
        Serializes some data to a file
        Args:
            data: Data to be written
            filename: File to be written to

        Returns:

        """
        with open(filename, 'wb') as f:
            pickle.dump(data, f)

    @staticmethod
    def _deserialize(filename):
        """
        Deserializes data from a serialized file
        Args:
            filename: Serialized file

        Returns: Deserialized data from file

        """
        if os.path.exists(filename):
            with open(filename, 'rb') as f:
                return pickle.load(f)
        return {}
