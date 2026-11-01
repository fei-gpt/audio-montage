"""Human backfill and re-selection must keep history and never bypass the gates."""
import json
import unittest
from argparse import Namespace

import test_pipeline as fixtures
import montage as m
import content_recognition as c

BASE = {k: 'pass' for k in ['content_legibility', 'temporal_integrity',
                            'technical_usability', 'evidence_sufficiency']}


class ReviewBackfillTest(unittest.TestCase):
    setUp = fixtures.PipelineTest.setUp
    tearDown = fixtures.PipelineTest.tearDown

    def task(self):
        root = self.root / 'review-task'
        c.prepare(Namespace(video=self.video, request='保留红色展示', output=root))
        path = root / 'task.json'
        task = m.read(path)
        task['rights']['usage'] = 'allowed'
        task['analysis'].update(reviewed=True, coverage=[[0, 2], [2, 4]])
        task['requirements'].update(confirmed=True, hard=[{'id': 'H1', 'text': '必须看到主体',
                                                           'source_quote': '保留红色展示'}])
        evidence = m.read(next((root / 'evidence').glob('*/observation-*.json')))['evidence']

        def shot(sid, start, end, decision, reviewed, user):
            return dict(id=sid, start=start, end=end, facts='合成红色画面', reason='满足要求',
                        decision=decision, boundary_reviewed=reviewed,
                        assessment={'base': dict(BASE), 'user': user},
                        evidence=[next(e for e in evidence if start <= e['time'] <= end)])

        task['segments'] = [
            shot('A', 0, 1, 'keep', True, [{'id': 'H1', 'result': 'pass'}]),
            shot('B', 1, 2, 'keep', True, [{'id': 'H1', 'result': 'unknown'}]),
            shot('C', 2, 3, 'uncertain', False, [{'id': 'H1', 'result': 'pass'}]),
        ]
        m.save(path, task)
        return root, path

    def decisions(self, root, payload, name='decisions.json'):
        path = root / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
        return path

    def test_unknown_condition_waits_then_backfill_exports_and_keeps_history(self):
        root, path = self.task()
        c.extract(Namespace(task=path))
        self.assertEqual([row['id'] for row in m.read(root / 'extraction.json')['clips']], ['A'])
        pending = m.read(root / 'uncertain-review.json')['segments']
        self.assertEqual([row['id'] for row in pending], ['B', 'C'])
        self.assertIn('H1', pending[0]['review_reason'])
        self.assertEqual(m.read(root / 'progress.json')['status'], 'needs_manual_review')

        # Marking keep is refused while the hard condition is still unverified.
        weak = self.decisions(root, [{'id': 'B', 'decision': 'keep', 'boundary_reviewed': True}])
        with self.assertRaisesRegex(ValueError, 'H1'):
            c.review_segments(Namespace(task=path, decisions=weak, no_extract=True))
        # Explicit boundary confirmation is required as well.
        no_boundary = self.decisions(root, [{'id': 'C', 'decision': 'keep',
                                             'user': [{'id': 'H1', 'result': 'pass'}]}])
        with self.assertRaisesRegex(ValueError, 'boundary_reviewed'):
            c.review_segments(Namespace(task=path, decisions=no_boundary, no_extract=True))
        self.assertFalse((root / 'history').exists())

        good = self.decisions(root, [
            {'id': 'B', 'decision': 'keep', 'boundary_reviewed': True,
             'facts': '人工核对：红色主体完整',
             'user': [{'id': 'H1', 'result': 'pass', 'reason': '人工看过画面'}],
             'note': '人工回填'},
            {'id': 'C', 'decision': 'keep', 'boundary_reviewed': True,
             'user': [{'id': 'H1', 'result': 'pass'}]},
        ])
        c.review_segments(Namespace(task=path, decisions=good))
        manifest = m.read(root / 'extraction.json')
        self.assertEqual([row['id'] for row in manifest['clips']], ['A', 'B', 'C'])
        self.assertEqual(m.read(root / 'progress.json')['status'], 'completed')
        updated = next(s for s in m.read(path)['segments'] if s['id'] == 'B')
        self.assertEqual(updated['facts'], '人工核对：红色主体完整')
        self.assertEqual(updated['review_method'], 'manual_backfill')
        self.assertEqual(updated['requirement_match'], 'match')
        self.assertTrue(list((root / 'history').glob('task-*.json')))
        log = m.read(root / 'review-log.json')['entries']
        self.assertEqual(len(log), 2)
        self.assertEqual(log[0]['id'], 'B')
        self.assertEqual(log[0]['before']['facts'], '合成红色画面')
        self.assertEqual(log[0]['after']['facts'], '人工核对：红色主体完整')
        self.assertEqual(log[0]['note'], '人工回填')

    def test_reselect_validates_observed_range_and_keeps_original_interval(self):
        root, path = self.task()
        c.extract(Namespace(task=path))
        self.assertEqual(len(list((root / 'clips').glob('*.mp4'))), 1)
        moved = self.decisions(root, [{'id': 'A', 'start': 2.0, 'end': 3.5, 'reason': '更靠后的完整动作'}], 's1.json')
        c.reselect_segments(Namespace(task=path, selections=moved))
        updated = next(s for s in m.read(path)['segments'] if s['id'] == 'A')
        self.assertEqual((updated['start'], updated['end']), (2.0, 3.5))
        self.assertEqual((updated['original_start'], updated['original_end']), (0, 1))
        self.assertEqual(updated['boundary_history'][0]['from'], [0, 1])
        self.assertEqual(updated['boundary_history'][0]['to'], [2.0, 3.5])
        self.assertEqual(updated['review_method'], 'manual_reselect')
        self.assertTrue(updated['evidence'])
        self.assertTrue(all(2.0 <= e['time'] <= 3.5 for e in updated['evidence']))
        self.assertEqual(len(list((root / 'clips').glob('*.mp4'))), 1)
        exported = m.read(root / 'extraction.json')['clips'][0]
        self.assertAlmostEqual(exported['end'] - exported['start'], 1.5, delta=.01)

        # A selection outside the recorded observation is refused and changes nothing.
        task = m.read(path)
        task['analysis']['coverage'] = [[0, 1]]
        m.save(path, task)
        too_far = self.decisions(root, [{'id': 'A', 'start': 2.0, 'end': 3.5, 'reason': '越界'}], 's2.json')
        with self.assertRaisesRegex(ValueError, '已观察范围'):
            c.reselect_segments(Namespace(task=path, selections=too_far, no_extract=True))
        self.assertEqual(next(s for s in m.read(path)['segments'] if s['id'] == 'A')['start'], 2.0)
        # Missing reason is refused too.
        no_reason = self.decisions(root, [{'id': 'A', 'start': 0.2, 'end': 0.9}], 's3.json')
        with self.assertRaisesRegex(ValueError, '原因'):
            c.reselect_segments(Namespace(task=path, selections=no_reason, no_extract=True))

    def test_reselect_into_out_of_range_duration_goes_to_manual_review(self):
        root, path = self.task()
        c.extract(Namespace(task=path))
        short_pick = self.decisions(root, [{'id': 'A', 'start': 0, 'end': .5, 'reason': '保留短动作原区间'}], 's4.json')
        c.reselect_segments(Namespace(task=path, selections=short_pick))
        pending = m.read(root / 'manual-review.json')['segments']
        self.assertEqual([row['id'] for row in pending], ['A'])
        self.assertAlmostEqual(pending[0]['duration'], .5, delta=.01)
        self.assertEqual(m.read(root / 'progress.json')['status'], 'needs_manual_review')
        self.assertTrue(pending[0]['review_video'])
        self.assertEqual(len(list((root / 'clips').glob('*.mp4'))), 0)

    def test_backfill_rejects_unknown_id_and_bad_decision(self):
        root, path = self.task()
        ghost = self.decisions(root, [{'id': 'ZZ', 'decision': 'keep'}], 'g.json')
        with self.assertRaisesRegex(ValueError, '没有该片段'):
            c.review_segments(Namespace(task=path, decisions=ghost, no_extract=True))
        wrong = self.decisions(root, [{'id': 'A', 'decision': 'maybe'}], 'w.json')
        with self.assertRaises(ValueError):
            c.review_segments(Namespace(task=path, decisions=wrong, no_extract=True))
        self.assertEqual(m.read(path)['segments'][0]['decision'], 'keep')

    def test_export_gate_runs_before_the_task_is_mutated(self):
        root, path = self.task()
        task = m.read(path)
        task['rights']['usage'] = 'unknown'
        m.save(path, task)
        good = self.decisions(root, [{'id': 'B', 'decision': 'keep', 'boundary_reviewed': True,
                                      'user': [{'id': 'H1', 'result': 'pass'}]}], 'ok.json')
        with self.assertRaisesRegex(ValueError, '使用权限'):
            c.review_segments(Namespace(task=path, decisions=good))
        self.assertFalse((root / 'history').exists())
        self.assertNotIn('review_method', m.read(path)['segments'][1])
        # --no-extract still allows recording the human decision without exporting.
        c.review_segments(Namespace(task=path, decisions=good, no_extract=True))
        self.assertEqual(m.read(path)['segments'][1]['review_method'], 'manual_backfill')


if __name__ == '__main__':
    unittest.main()
