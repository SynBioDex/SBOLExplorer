import pickle
import os
class DataManager:
    def __init__(self, clusters_filename='dumps/clusters_dump', uri2rank_filename='dumps/uri2rank_dump',
                 device_baskets_filename='dumps/device_baskets_dump',
                 part_roles_filename='dumps/part_roles_dump'):
        self.clusters_filename = clusters_filename
        self.uri2rank_filename = uri2rank_filename
        self.device_baskets_filename = device_baskets_filename
        self.part_roles_filename = part_roles_filename
        self._clusters = None
        self._uri2rank = None
        self._device_baskets = None
        self._part_roles = None

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

    def save_device_baskets(self, device_baskets):
        """
        Saves the device -> sub-part composition map used for basket recommendations
        Args:
            device_baskets: {device_uri: frozenset(part_uri)}

        Returns:

        """
        self._device_baskets = device_baskets
        self._serialize(self._device_baskets, self.device_baskets_filename)

    def get_device_baskets(self):
        """
        Gets the device -> sub-part composition map
        Returns:

        """
        if self._device_baskets is None:
            self._device_baskets = self._deserialize(self.device_baskets_filename)
        return self._device_baskets

    def save_part_roles(self, part_roles):
        """
        Saves the role of each part seen as a device sub-component
        Args:
            part_roles: {part_uri: role_uri}

        Returns:

        """
        self._part_roles = part_roles
        self._serialize(self._part_roles, self.part_roles_filename)

    def get_part_roles(self):
        """
        Gets the role of each part seen as a device sub-component
        Returns:

        """
        if self._part_roles is None:
            self._part_roles = self._deserialize(self.part_roles_filename)
        return self._part_roles

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
