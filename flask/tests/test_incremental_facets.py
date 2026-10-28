import unittest
from unittest import mock

import index

ROLE = 'http://identifiers.org/so/SO:0000167'
DNA = 'http://www.biopax.org/release/biopax-level3.owl#DnaRegion'
CD = 'http://sbols.org/v2#ComponentDefinition'
COLL = 'https://synbiohub.org/user/alice/c/c_collection/1'


def payload_part(subject):
    # The shape SynBioHub's PrepareSubmissionJob sends to /incrementalupdate.
    return {'subject': subject, 'displayId': 'p', 'role': ROLE, 'sboltype': DNA,
            'type': CD, 'graph': 'https://synbiohub.org/user/alice'}


class IncrementalUpdateTests(unittest.TestCase):
    @mock.patch('index.schedule_facet_refresh')
    @mock.patch('index.index_part')
    @mock.patch('index.load_term_list', return_value=[])
    @mock.patch('index.query.query_values_for_subjects', return_value={})
    def test_payload_facets_kept_when_virtuoso_has_nothing_yet(self, values, _terms, index_part, schedule):
        # SynBioHub sends the update before uploading to Virtuoso.
        part = payload_part('s1')
        index.incremental_update({'partsToAdd': [part]}, {})

        indexed = index_part.call_args.args[0]
        self.assertEqual(indexed['facet_role'], [ROLE])
        self.assertEqual(indexed['facet_sboltype'], [DNA])
        self.assertEqual(indexed['facet_type'], [CD])
        self.assertEqual(indexed['facet_collections'], [])
        schedule.assert_called_once_with(['s1'])

    @mock.patch('index.schedule_facet_refresh')
    @mock.patch('index.index_part')
    @mock.patch('index.load_term_list', return_value=[])
    @mock.patch('index.query.query_values_for_subjects')
    def test_no_refresh_when_virtuoso_already_has_collections(self, values, _terms, index_part, schedule):
        values.side_effect = lambda pattern, subjects: (
            {'s1': {COLL}} if 'sbol2:member' in pattern else {'s1': {ROLE, 'http://identifiers.org/so/SO:0000804'}}
            if 'sbol2:role' in pattern else {})
        index.incremental_update({'partsToAdd': [payload_part('s1')]}, {})

        indexed = index_part.call_args.args[0]
        self.assertEqual(indexed['facet_collections'], [COLL])
        self.assertEqual(len(indexed['facet_role']), 2)  # Virtuoso adds the second role
        schedule.assert_called_once_with([])


class RefreshFacetFieldsTests(unittest.TestCase):
    @mock.patch('index.schedule_facet_refresh')
    @mock.patch('index.helpers.bulk')
    @mock.patch('index.elasticsearch_manager')
    @mock.patch('index.query.query_values_for_subjects')
    def test_updates_found_parts_and_reschedules_the_rest(self, values, _es, bulk, schedule):
        values.side_effect = lambda pattern, subjects: (
            {'s1': {COLL}} if 'sbol2:member' in pattern else {'s1': {'Alice'}} if 'dc:creator' in pattern else {})
        index.refresh_facet_fields(['s1', 's2'], (120, 600))

        actions = bulk.call_args.args[1]
        self.assertEqual([a['_id'] for a in actions], ['s1'])
        self.assertEqual(actions[0]['doc'], {'facet_collections': [COLL], 'facet_creator': ['Alice']})
        schedule.assert_called_once_with(['s2'], (120, 600))

    @mock.patch('index.schedule_facet_refresh')
    @mock.patch('index.query.query_values_for_subjects', side_effect=Exception('Virtuoso down'))
    def test_failure_retries_everything_later(self, _values, schedule):
        index.refresh_facet_fields(['s1', 's2'], (600,))
        schedule.assert_called_once_with(['s1', 's2'], (600,))

    def setUp(self):
        index._facet_refresh_pending.clear()

    @mock.patch('index.threading.Thread')
    def test_schedule_stops_when_nothing_left(self, thread):
        index.schedule_facet_refresh([], (30,))
        index.schedule_facet_refresh(['s1'], ())
        thread.assert_not_called()
        self.assertEqual(index._facet_refresh_pending, {})

    @mock.patch('index.threading.Thread')
    def test_submissions_share_one_thread_and_pending_set(self, thread):
        index._facet_refresh_thread = None
        index.schedule_facet_refresh(['s1'], (30, 120))
        index._facet_refresh_thread = thread.return_value  # as if it were still running
        index.schedule_facet_refresh(['s2'], (30, 120))
        thread.assert_called_once()
        self.assertEqual(set(index._facet_refresh_pending), {'s1', 's2'})
        self.assertEqual(index._facet_refresh_pending['s1'][1], (120,))
        index._facet_refresh_thread = None

    @mock.patch('index.refresh_facet_fields')
    @mock.patch('index.time.sleep')
    def test_tick_refreshes_only_due_parts_grouped_by_remaining_delays(self, _sleep, refresh):
        index._facet_refresh_pending.update({
            's1': (0, (120,)), 's2': (0, (120,)), 's3': (1e12, (600,))})
        index._facet_refresh_thread = mock.Mock()
        still_pending = []

        def finish_pass(subjects, remaining):
            still_pending.append(set(index._facet_refresh_pending))
            index._facet_refresh_pending.clear()  # nothing rescheduled, so the thread exits

        refresh.side_effect = finish_pass
        index._run_facet_refreshes()
        refresh.assert_called_once_with(['s1', 's2'], (120,))
        self.assertEqual(still_pending, [{'s3'}])
        self.assertIsNone(index._facet_refresh_thread)


if __name__ == '__main__':
    unittest.main()
