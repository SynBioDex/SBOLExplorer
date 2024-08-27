import datetime
import os
class Logger:
    def __init__(self, log_file='log.txt', indexing_log_file='indexing_log.txt'):
        self.log_file = log_file
        self.indexing_log_file = indexing_log_file

    def log(self, message, to_indexing_log=False):
        """
        Writes a message to the log
        Args:
            message: Message to write

        Returns:
        """
        log_message = f'[{datetime.datetime.now().isoformat()}] {message}\n'
        print(log_message, end='')  # Output to console

        file = self.indexing_log_file if to_indexing_log else self.log_file
        with open(file, 'a+') as f:
            f.write(log_message)

    def get_log(self):
        """
        Gets a copy of the log
        Returns: Stream from the read() method

        """
        return self._read_file(self.log_file)

    def get_indexing_log(self):
        return self._read_file(self.indexing_log_file)

    @staticmethod
    def _read_file(filename):
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                return f.read()
        return ""
