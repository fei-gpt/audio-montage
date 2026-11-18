import json
import unittest
from pathlib import Path
from unittest.mock import patch
import test_editing as fixtures
from workbench.usage import check,ledger,sync,sources


class UsageTest(unittest.TestCase):
    setUpClass=classmethod(fixtures.EditingTest.setUpClass.__func__)
    tearDownClass=classmethod(fixtures.EditingTest.tearDownClass.__func__)
    setUp=fixtures.EditingTest.setUp
    tearDown=fixtures.EditingTest.tearDown
    add_minimum_source=fixtures.EditingTest.add_minimum_source
    create=fixtures.EditingTest.create
    task=fixtures.EditingTest.task
    proposal=fixtures.EditingTest.proposal

    def test_replacement_keeps_portable_history_under_original_hash(self):
        from montage import save
        from workbench.usage import SCHEMA
        file=Path(self.asset['path']);old=self.asset['sha256']
        sidecar=Path(str(file)+'.usage.json')
        save(sidecar,{'schema':SCHEMA,'source_sha256':old,'references':[{'task_id':'external-output','ranges':[[0,30]]}]})
        with file.open('ab') as stream:stream.write(b'new version')
        w=self.w['id']
        self.app.scan(self.p['id'],w)
        asset=self.app.store.get('asset',self.asset['id'],w)
        current=asset['sha256']
        self.assertIn(old,asset.pop('previous_hashes'))
        self.app.store.put('asset',w,asset)  # Catalog from before replacement hashes were recorded.
        events=ledger(self.app.store,workspace=w)
        self.assertIn('external-output',events[old])
        self.assertFalse(events.get(current))
        with patch('workbench.usage.save',side_effect=OSError('index unavailable')):
            self.assertTrue(sync(self.app.store,{current},workspace=w)['errors'])
        self.assertEqual(json.loads(sidecar.read_text('utf-8'))['source_sha256'],old)
        self.assertFalse(sync(self.app.store,{current},workspace=w)['errors'])
        self.assertEqual(json.loads(sidecar.read_text('utf-8'))['source_sha256'],current)
        for _ in range(2):
            sync(self.app.store,{current},workspace=w)
            self.assertEqual(set(ledger(self.app.store,workspace=w)[old]),{'external-output'})

    def test_unrelated_bad_usage_file_does_not_block_or_get_overwritten(self):
        b,t=history(self,0)
        from montage import save
        from workbench.usage import SCHEMA
        bad=next(a for a in self.app.visible_assets(self.w['id']) if a['id']!=self.asset['id'])
        sidecar=Path(bad['path']+'.usage.json')
        save(sidecar,{'schema':SCHEMA,'source_sha256':'wrong-hash','references':[]})
        before=sidecar.read_bytes()
        self.assertTrue(self.app.editing.candidates(self.p['id'],self.w['id']))
        check(self.app.store,t,b)
        wrong=dict(t,intro=bad['path'],intro_sha256=bad['sha256'])
        with self.assertRaisesRegex(ValueError,'引用记录与素材不一致'):check(self.app.store,wrong,b)
        sync(self.app.store,workspace=self.w['id'])
        self.assertEqual(sidecar.read_bytes(),before)


def history(self,count):
    b=self.create();t=self.task(b)
    t['plan']=self.app.editing.validate_plan(b,t,self.proposal())
    for i in range(count):
        old=dict(t,id='past-'+str(i),output={'sha256':'successful-output'},status='completed')
        self.app.store.put('edit_task',self.w['id'],old)
    return b,t


def test_three_successful_outputs_cap_overlapping_range_and_sync_is_idempotent(self):
    b,t=history(self,3)
    with patch.object(self.app.store,'get',wraps=self.app.store.get) as get:
        self.assertEqual(len(ledger(self.app.store)[self.asset['sha256']]),3)
        get.assert_called_once_with('edit_batch',b['id'],self.w['id'])
    self.assertTrue(self.app.editing.candidates(self.p['id'],self.w['id']))
    with self.assertRaisesRegex(ValueError,'3次'):check(self.app.store,t,b)
    before=(self.library/'clip.mp4').read_bytes()
    sync(self.app.store);sync(self.app.store)
    index=json.loads((self.library/'素材引用次数索引.json').read_text(encoding='utf-8'))
    doc=index['素材'][self.asset['sha256']]
    self.assertEqual(doc['引用次数'],3);self.assertFalse(doc['可继续引用'])
    self.assertEqual(len(doc['references']),3)
    self.assertEqual((self.library/'clip.mp4').read_bytes(),before)


def test_preview_failure_and_duplicate_parts_do_not_inflate_count(self):
    b,t=history(self,2)
    check(self.app.store,t,b)
    draft=dict(t,id='preview-only',preview={'sha256':'preview'},status='needs_attention')
    self.app.store.put('edit_task',self.w['id'],draft)
    self.assertEqual(len(ledger(self.app.store)[self.asset['sha256']]),2)
    t['id']='third';t.update(output={'sha256':'third-output'},status='completed')
    t['plan']['parts']*=2
    self.app.store.put('edit_task',self.w['id'],t)
    self.assertEqual(len(ledger(self.app.store)[self.asset['sha256']]),3)


def test_concurrent_reservation_protects_last_slot_and_failed_job_releases_it(self):
    b,t=history(self,2)
    peer=dict(t,id='reserved',status='running',dedup_reserved=True)
    self.app.store.put('edit_task',self.w['id'],peer)
    with self.assertRaisesRegex(ValueError,'3次'):check(self.app.store,t,b)
    peer['status']='needs_attention';self.app.store.put('edit_task',self.w['id'],peer)
    check(self.app.store,t,b)
    self.app.editing.action(self.p['id'],self.w['id'],b['id'],'preview',{'task_ids':[peer['id']]})
    check(self.app.store,t,b)


UsageTest.test_three_successful_outputs_cap_overlapping_range_and_sync_is_idempotent=test_three_successful_outputs_cap_overlapping_range_and_sync_is_idempotent
UsageTest.test_preview_failure_and_duplicate_parts_do_not_inflate_count=test_preview_failure_and_duplicate_parts_do_not_inflate_count
UsageTest.test_concurrent_reservation_protects_last_slot_and_failed_job_releases_it=test_concurrent_reservation_protects_last_slot_and_failed_job_releases_it
