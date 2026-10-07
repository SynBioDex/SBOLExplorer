import unittest
from unittest import mock

import elasticsearchManager


class FakeConfig:
    def get_es_endpoint(self):
        return 'http://elasticsearch:9200/'


class GetEsTests(unittest.TestCase):
    @mock.patch('elasticsearchManager.time.sleep')
    @mock.patch('elasticsearchManager.Elasticsearch')
    def test_waits_until_elasticsearch_answers(self, es_class, sleep):
        # ES not up yet (refused / 503), then ready: startup must survive.
        es_class.return_value.ping.side_effect = [False, False, True]
        manager = elasticsearchManager.ElasticsearchManager(FakeConfig())

        es = manager.get_es(timeout=60, interval=3)

        self.assertIs(es, es_class.return_value)
        self.assertEqual(sleep.call_count, 2)
        self.assertIs(manager.get_es(), es)  # cached, no new client
        self.assertEqual(es_class.call_count, 1)

    @mock.patch('elasticsearchManager.time.sleep')
    @mock.patch('elasticsearchManager.time.monotonic')
    @mock.patch('elasticsearchManager.Elasticsearch')
    def test_gives_up_after_timeout_and_retries_on_next_call(self, es_class, monotonic, sleep):
        es_class.return_value.ping.return_value = False
        monotonic.side_effect = [0, 1, 2, 3, 10, 11]  # deadline = 0 + 3
        manager = elasticsearchManager.ElasticsearchManager(FakeConfig())

        with self.assertRaises(ValueError):
            manager.get_es(timeout=3, interval=1)
        self.assertIsNone(manager._es)  # a failed client is not cached

        es_class.return_value.ping.return_value = True
        self.assertIs(manager.get_es(timeout=3, interval=1), es_class.return_value)


if __name__ == '__main__':
    unittest.main()
