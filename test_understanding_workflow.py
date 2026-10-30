import unittest
from argparse import Namespace
from pathlib import Path
import montage as m
import asset_index as ix
import understanding as u
import library_tools as tools
import test_pipeline as fixtures


class UnderstandingIntegration(unittest.TestCase):
    setUp = fixtures.PipelineTest.setUp
    tearDown = fixtures.PipelineTest.tearDown

    def test_observe_ingest_search_contact_similarity_feedback(self):
        db = self.root / 'index.sqlite'
        ix.index_library(Namespace(library=self.library, database=db, window=1, scene=.3))
        output = self.root / 'understanding'
        u.prepare(Namespace(database=db, output=output))
        record_path = next((output / 'assets').glob('*.json'))
        u.observe(Namespace(record=record_path, start=0, end=4, every=1))
        manifest = next((output / 'evidence').glob('*/observation-*.json'))
        evidence = m.read(manifest)['evidence']
        record = m.read(record_path)
        record['status'] = 'reviewed'
        record['asset']['review']['product_identity'] = True
        record['asset']['product']['reuse_scope'] = 'generic_context'
        record['asset']['rights'] = {'usage': 'allowed', 'source': 'synthetic fixture'}
        record['asset']['segments'] = [{'id': 'whole', 'start': 0, 'end': 4,
            'facts': {'description': 'red demonstration', 'tags': [], 'aliases': []},
            'usable_ranges': [{'start': 0, 'end': 4, 'kind': 'static'}],
            'review': {'facts': True, 'action_boundaries': True}, 'evidence': evidence}]
        m.save(record_path, record)
        u.import_understanding(Namespace(record=record_path, database=db))
        found = ix.search(db, 'red', minimum=3, product_model='OTHER')
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]['source_end'], 4)
        self.assertEqual(found[0]['policy_warnings'], [])
        tools.contact(Namespace(database=db, output=self.root / 'contact'))
        self.assertTrue((self.root / 'contact/contact.html').exists())
        tools.similar(Namespace(database=db, distance=6))
        self.assertTrue(db.with_suffix('.similar.json').exists())
        tools.feedback(Namespace(database=db, clip=found[0]['clip_id'], project=self.project,
                                 decision='selected', reason='fixture'))
        self.assertEqual(ix.search(db, 'red')[0]['feedback_score'], 1)
