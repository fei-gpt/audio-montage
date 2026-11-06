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
    create=fixtures.EditingTest.create
    task=fixtures.EditingTest.task
    proposal=fixtures.EditingTest.proposal


def history(self,count):
    b=self.create();t=self.task(b)
    t['plan']=self.app.editing.validate_plan(b,t,self.proposal())
    for i in range(count):
        old=dict(t,id='past-'+str(i),output={'sha256':'successful-output'},status='completed')
        self.app.store.put('edit_task',self.w['id'],old)
    return b,t


def test_three_successful_outputs_cap_whole_source_and_sync_is_idempotent(self):
    b,t=history(self,3)
    self.assertEqual(self.app.editing.candidates(self.p['id'],self.w['id']),[])
    with self.assertRaisesRegex(ValueError,'3次'):check(self.app.store,t,b)
    before=(self.library/'clip.mp4').read_bytes()
    sync(self.app.store);sync(self.app.store)
    index=json.loads((self.library/'素材引用次数索引.json').read_text(encoding='utf-8'))
    doc=index['素材'][self.asset['sha256']]
    self.assertEqual(doc['引用次数'],3);self.assertFalse(doc['可继续引用'])
    self.assertEqual(len(doc['references']),3)
    self.assertEqual((self.library/'clip.mp4').read_bytes(),before)
    # A different shot range or filename with the same source hash cannot reset it.
    self.shot.update(id='another-shot',start=1,end=2)
    self.app.store.put('shot',self.w['id'],self.shot)
    self.assertEqual(self.app.editing.candidates(self.p['id'],self.w['id']),[])


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


UsageTest.test_three_successful_outputs_cap_whole_source_and_sync_is_idempotent=test_three_successful_outputs_cap_whole_source_and_sync_is_idempotent
UsageTest.test_preview_failure_and_duplicate_parts_do_not_inflate_count=test_preview_failure_and_duplicate_parts_do_not_inflate_count
UsageTest.test_concurrent_reservation_protects_last_slot_and_failed_job_releases_it=test_concurrent_reservation_protects_last_slot_and_failed_job_releases_it
