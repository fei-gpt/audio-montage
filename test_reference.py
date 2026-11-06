import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from montage import fingerprint
from workbench.reference import analyze

class ReferenceTests(unittest.TestCase):
    def test_reference_cut_aligns_to_third_frame_without_moving_the_end(self):
        from montage import save
        from workbench.reference_structure import align_to_picture
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            save(root/'boundaries.json',{'candidates':[{'at':.095,'score':.9}]})
            raw=bytes(3*24*40)+bytes([130])*(27*24*40)
            with patch('workbench.reference_structure.subprocess.run',return_value=SimpleNamespace(stdout=raw)):
                result=align_to_picture({'beats':[dict(start=0,end=.15),dict(start=.15,end=1)]},root/'ref',root)
            self.assertEqual(result['beats'],[dict(start=0,end=.1),dict(start=.1,end=1)])

    def test_shortlist_audit_caches_by_reference_and_exact_cut(self):
        from workbench.reference import audit_choices,span_key
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            app=SimpleNamespace(wroot=lambda w:root/w,asset_path=lambda w,a:root/a,
                                config=lambda:{'provider':'codex','model':'gpt-6-luna'})
            batch={'workspace_id':'w','reference':{'path':str(root/'ref'),'duration':1,'sha256':'ref'}}
            part={'asset_id':'source','asset_sha256':'hash','start':0,'frames':30}
            verdict={'checks':[{'index':1,'verdict':'possible_same','evidence':'相同运镜与背景'}]}
            with patch('workbench.reference.comparison_sheet'),patch('vision_api.call',return_value=verdict) as call:
                result=audit_choices(app,batch,[[part]],True,lambda:None)
                self.assertEqual(result[span_key(part)]['verdict'],'possible_same')
                self.assertEqual(audit_choices(app,batch,[[part]],False,lambda:None),result)
                self.assertEqual(call.call_count,1)
                call.return_value={'checks':[]}
                with self.assertRaisesRegex(ValueError,'不完整'):
                    audit_choices(app,batch,[[dict(part,start=.5)]],True,lambda:None)

    def test_reencoded_mirrored_excerpt_at_an_offset(self):
        from montage import run
        from workbench.reference import fingerprints, shared_excerpt
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);ref=root/'ref.mp4';alias=root/'part.mp4';other=root/'other.mp4'
            run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=180x320:r=30:d=4','-c:v','libx264',ref])
            run(['ffmpeg','-v','error','-ss','1','-i',ref,'-t','2','-vf','hflip,scale=144:256','-crf','28',alias])
            run(['ffmpeg','-v','error','-f','lavfi','-i','color=white:s=180x320:r=30:d=2','-vf','drawbox=x=30:y=30:w=50:h=80:color=black:t=fill',other])
            def samples(path, seconds):
                return fingerprints(path,fingerprint(path),0,seconds,root)
            source=samples(ref,4)
            self.assertEqual(shared_excerpt(source,samples(alias,2))['basis'],'similar_sample_run')
            self.assertIsNone(shared_excerpt(source,samples(other,2)))
            self.assertEqual(shared_excerpt(source,[])['basis'],'insufficient_samples')

    def test_reference_version_and_invalid_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'video.mp4';source.write_bytes(b'source')
            upload={'path':str(source),'sha256':fingerprint(source),'duration':1}
            app=SimpleNamespace(wroot=lambda w:root/w,config=lambda:{'model':'test'})
            def render(args,**kw):Path(args[-1]).write_bytes(b'frame')
            beat={'start':0,'end':1,'purpose':'演示','subject':'产品','action':'旋转','composition':'近景'}
            with patch('workbench.reference.subprocess.run',side_effect=render),patch('vision_api.call',return_value={'beats':[beat]}):
                result=analyze(app,'A',upload,False)
                self.assertFalse(result['boundaries_verified'])
                self.assertTrue((root/'A'/'reference-evidence').is_dir())
            with patch('vision_api.call',return_value={'beats':[dict(beat,end=2)]}),self.assertRaisesRegex(ValueError,'区间无效'):analyze(app,'A',upload,False)
            source.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'已改变'):analyze(app,'A',upload,False)

    def test_reference_length_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'a';source.write_bytes(b'a')
            with self.assertRaisesRegex(ValueError,'120秒'):
                analyze(None,'A',{'path':str(source),'sha256':fingerprint(source),'duration':121},False)
