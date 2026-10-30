"""Integration checks with real media; no user's files or network required."""
import importlib.util
import json
import os
import array
import math
import subprocess
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import asset_index as ix
import montage as m


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.library = self.root / 'library'
        self.library.mkdir()
        self.audio = self.root / 'voice.wav'
        m.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2.4', self.audio])
        self.video = self.library / '演示.mp4'
        m.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=red:s=180x320:r=30:d=4',
               '-c:v', 'libx264', '-pix_fmt', 'yuv420p', self.video])
        self.project = self.root / 'project'
        m.init(Namespace(project=self.project, audio=self.audio, width=180, height=320, fps=30))
        timing = self.root / 'timing.json'
        m.save(timing, {'segments': [{'start': 0.2, 'end': 1.13, 'text': '测试字幕'},
                                     {'start': 1.3, 'end': 2.2, 'text': '另一段字幕'}]})
        m.import_timing(Namespace(project=self.project, timing=timing))
        m.build(Namespace(project=self.project))

    def tearDown(self):
        self.tmp.cleanup()

    def select(self):
        path = self.project / 'plans/edit.json'
        data = m.read(path)
        for s in data['shots']:
            s.update(purpose='检查测试画面', reviewed=True,
                     selection={'rights': {'usage': 'allowed', 'source': 'synthetic test fixture'}, 'path': str(self.video), 'source_start': 0.1 + s['start']})
        m.save(path, data)
        timing = m.read(self.project / 'audio/timing.json')
        timing['reviewed'] = True
        m.save(self.project / 'audio/timing.json', timing)
        return data

    def test_reject_missing_and_out_of_range(self):
        self.assertTrue(m.validate(self.project)[3]['errors'])
        data = self.select()
        self.assertFalse(m.validate(self.project)[3]['errors'])
        data['shots'][0]['selection']['source_start'] = 99
        m.save(self.project / 'plans/edit.json', data)
        self.assertTrue(m.validate(self.project)[3]['errors'])
        with self.assertRaises(ValueError):
            m.check_segments([{'start': 0, 'end': 2, 'text': 'a'},
                              {'start': 1, 'end': 3, 'text': 'b'}], 4)

    def test_only_9_16_sources_at_every_boundary(self):
        landscape = self.library / 'landscape.mp4'
        square = self.library / 'square.mp4'
        for path, size in [(landscape, '320x180'), (square, '320x320')]:
            m.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', f'color=c=blue:s={size}:r=30:d=4',
                   '-c:v', 'libx264', '-pix_fmt', 'yuv420p', path])
            with self.assertRaisesRegex(ValueError, '9:16'):
                m.portrait_geometry(m.probe(path))
        rotated = self.library / 'rotated-portrait.mp4'
        m.run(['ffmpeg', '-v', 'error', '-display_rotation', '90', '-i', landscape, '-c', 'copy', rotated])
        self.assertEqual(m.portrait_geometry(m.probe(rotated))['display_ratio'], '9:16')
        with self.assertRaises(ValueError):
            m.portrait_geometry({'streams': [{'codec_type': 'video', 'width': 180, 'height': 320,
                                              'sample_aspect_ratio': '2:1'}]})
        with self.assertRaises(ValueError):
            m.init(Namespace(project=self.root / 'bad-project', audio=self.audio, width=320, height=180, fps=30))
        db = self.root / 'portrait.sqlite'
        ix.index_library(Namespace(library=self.library, database=db, window=2, scene=0.3))
        stats = m.read(db.with_suffix('.index-report.json'))
        self.assertEqual(len(stats['excluded']), 2)
        self.assertEqual(stats['indexed_files'], 2)
        # Simulate a pre-policy database: retrieval must recheck old entries.
        digest = m.fingerprint(landscape)
        labels = {'description': 'legacy landscape scene', 'tags': []}
        with ix.connect(db) as conn:
            conn.execute('INSERT INTO assets(hash,paths,duration,settings) VALUES(?,?,?,?)',
                         (digest, json.dumps([str(landscape)]), 4, '{}'))
            conn.execute('INSERT INTO clips VALUES(?,?,?,?,?,?,?)',
                         ('legacy', digest, 0, 4, '[]', json.dumps(labels), 1))
        self.assertEqual(ix.search(db, 'legacy landscape'), [])
        data = self.select()
        data['shots'][0]['selection']['path'] = str(landscape)
        m.save(self.project / 'plans/edit.json', data)
        self.assertTrue(any('9:16' in e for e in m.validate(self.project)[3]['errors']))
        with self.assertRaises(ValueError):
            m.render(Namespace(project=self.project, final=False))
        if importlib.util.find_spec('pyJianYingDraft'):
            with self.assertRaises(ValueError):
                m.export_draft(Namespace(project=self.project, name='bad-draft', allow_unreviewed=True))
        # Even a manually retained old candidate cannot bypass choose.
        shot = data['shots'][0]
        m.save(self.project / 'plans/candidates.json', {'shots': [{'shot_id': shot['id'],
            'request_sha256': ix.request_signature(shot), 'candidates': [{'clip_id': 'legacy',
            'rights': {'usage': 'allowed', 'source': 'synthetic test fixture'}, 'path': str(landscape), 'labels_sha256': ix.digest_json(labels)}]}]})
        with self.assertRaises(ValueError):
            ix.choose(Namespace(project=self.project, database=db, shot=shot['id'], clip='legacy'))
        data['shots'][0]['selection']['path'] = str(rotated)
        m.save(self.project / 'plans/edit.json', data)
        m.render(Namespace(project=self.project, final=False))
        self.assertEqual(m.portrait_geometry(m.probe(self.project / 'out/preview.mp4'))['display_ratio'], '9:16')

    def test_render_review_and_no_overwrite(self):
        self.select()
        args = Namespace(project=self.project, final=True)
        m.render(args)
        out = m.probe(self.project / 'out/final.mp4')
        self.assertLess(abs(float(out['format']['duration']) - 2.4), 0.1)
        self.assertEqual(sum(s['codec_type'] == 'audio' for s in out['streams']), 1)
        self.assertIn('00:00:00,200 --> 00:00:01,130', (self.project / 'out/captions.srt').read_text())
        m.review(args)
        self.assertEqual(len(list((self.project / 'qa/frames').glob('*.jpg'))), 15)
        m.render(args)
        self.assertTrue(list((self.project / 'out/history').glob('final-*.mp4')))
        data = m.read(self.project / 'plans/edit.json')
        data['shots'][0]['selection']['source_start'] = 0.2
        m.save(self.project / 'plans/edit.json', data)
        with self.assertRaises(ValueError):
            m.review(args)

    def test_original_audio_toggle_mix_and_silent_source(self):
        self.assertFalse(m.read(self.project / 'project.json')['keep_original_audio'])
        source = self.library / 'with-sound.mp4'
        m.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=180x320:r=30:d=4',
               '-itsoffset', '0.4', '-f', 'lavfi', '-i', 'sine=frequency=880:duration=0.6',
               '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', source])
        self.select()
        m.save(self.project / 'plans/edit.json', {'shots': [
            {'id': 'S001', 'start': 0, 'end': 1.2, 'purpose': '有原声素材', 'reviewed': True,
             'selection': {'rights': {'usage': 'allowed', 'source': 'synthetic test fixture'}, 'path': str(source), 'source_start': 0}},
            {'id': 'S002', 'start': 1.2, 'end': 2.4, 'purpose': '无原声素材', 'reviewed': True,
             'selection': {'rights': {'usage': 'allowed', 'source': 'synthetic test fixture'}, 'path': str(self.video), 'source_start': 0.1}}]})
        def amplitude(path, start, frequency):
            raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(start), '-i', str(path),
                '-t', '0.2', '-map', '0:a:0', '-ac', '1', '-ar', '16000', '-f', 'f32le', '-'],
                capture_output=True, check=True).stdout
            values = array.array('f', raw)
            real = sum(v * math.cos(2 * math.pi * frequency * i / 16000) for i, v in enumerate(values))
            imag = sum(v * math.sin(2 * math.pi * frequency * i / 16000) for i, v in enumerate(values))
            return 2 * math.hypot(real, imag) / len(values)
        args = Namespace(project=self.project, final=True)
        m.render(args)
        output = self.project / 'out/final.mp4'
        self.assertLess(amplitude(output, 0.4, 880), 0.01)
        self.assertGreater(amplitude(output, 0.4, 440), 0.04)
        m.set_audio(Namespace(project=self.project, keep_original_audio=True))
        with self.assertRaises(ValueError):
            m.review(args)  # Audio setting changes invalidate the old render.
        output.rename(self.project / 'out/default-muted.mp4')
        m.render(args)
        self.assertGreater(amplitude(output, 0.4, 880), 0.04)
        self.assertGreater(amplitude(output, 0.4, 440), 0.04)
        self.assertLess(amplitude(output, 0.05, 880), 0.01)
        self.assertLess(amplitude(output, 1.6, 880), 0.01)
        self.assertGreater(amplitude(output, 1.6, 440), 0.04)
        report = m.read(self.project / 'qa/final-render.json')
        self.assertTrue(report['keep_original_audio'])
        self.assertEqual(report['original_audio_missing_shots'], ['S002'])
        if importlib.util.find_spec('pyJianYingDraft'):
            m.export_draft(Namespace(project=self.project, name='sound-on', allow_unreviewed=False))
            draft = m.read(self.project / 'out/sound-on/draft_content.json')
            video = next(t for t in draft['tracks'] if t['type'] == 'video')
            self.assertTrue(all(s['volume'] == 1 for s in video['segments']))
        m.set_audio(Namespace(project=self.project, keep_original_audio=False))
        self.assertFalse(m.read(self.project / 'project.json')['keep_original_audio'])

    def test_index_cache_and_content_retrieval(self):
        db = self.root / 'index.sqlite'
        args = Namespace(library=self.library, database=db, window=2, scene=0.3)
        ix.index_library(args)
        self.assertEqual(ix.search(db, '收纳盒'), [])
        data = m.read(db.with_suffix('.label-queue.json'))
        first = data['clips'][0]
        first['labels'].update(description='手把插排放进白色收纳盒', action='放入插排', tags=['白色款'])
        first['reviewed'] = True
        labels = self.root / 'labels.json'
        m.save(labels, {'clips': [first]})
        ix.import_labels(Namespace(database=db, labels=labels))
        missing_frame = Path(first['frames'][0])
        missing_frame.unlink()
        ix.index_library(args)
        stats = m.read(db.with_suffix('.index-report.json'))
        self.assertEqual(stats['cached_files'], 1)
        self.assertEqual(stats['clips_created'], 0)
        self.assertEqual(stats['repaired_frames'], 1)
        self.assertTrue(missing_frame.exists())
        self.assertTrue(ix.search(db, '把插排放进收纳盒', required=['白色']))
        self.assertEqual(ix.search(db, '插排', forbidden=['白色']), [])
        self.assertEqual(ix.search(db, '插排', minimum=99), [])
        edit = m.read(self.project / 'plans/edit.json')
        edit['shots'][1]['query'] = '手把插排放进收纳盒'
        m.save(self.project / 'plans/edit.json', edit)
        ix.candidates(Namespace(project=self.project, database=db, limit=5))
        found = m.read(self.project / 'plans/candidates.json')['shots'][1]['candidates']
        self.assertTrue(found)
        ix.choose(Namespace(project=self.project, database=db, shot='S002', clip=found[0]['clip_id']))
        selected = m.read(self.project / 'plans/edit.json')['shots'][1]
        self.assertTrue(selected['selection'])
        self.assertFalse(selected['reviewed'])
        self.assertTrue((self.project / 'plans/edit.backup-1.json').exists())
        edited = m.read(self.project / 'plans/edit.json')
        edited['shots'][1]['query'] = 'a completely different action'
        m.save(self.project / 'plans/edit.json', edited)
        with self.assertRaises(ValueError):
            ix.choose(Namespace(project=self.project, database=db, shot='S002', clip=found[0]['clip_id']))
        # Changed content at the same path must never reuse stale labels.
        self.video.write_bytes(b'changed')
        self.assertEqual(ix.search(db, '插排'), [])

    def test_english_spanish_labels_and_accents(self):
        db = self.root / 'multilingual.sqlite'
        ix.index_library(Namespace(library=self.library, database=db, window=2, scene=0.3))
        data = m.read(db.with_suffix('.label-queue.json'))
        first = data['clips'][0]
        first['labels'].update(description='白色收纳盒放入插排',
            descriptions={'en': 'Hands place cables in a white storage box',
                          'es': 'Manos colocan cables dentro de una caja blanca junto al sofá'},
            aliases=['cable organizer', 'organizador de cables'])
        first['reviewed'] = True
        path = self.root / 'multilingual-labels.json'
        m.save(path, {'clips': [first]})
        ix.import_labels(Namespace(database=db, labels=path))
        self.assertTrue(ix.search(db, 'white storage box', required=['white']))
        self.assertTrue(ix.search(db, 'caja blanca sofa', required=['sofá']))
        self.assertTrue(ix.search(db, 'organizador de cables'))
        self.assertEqual(ix.search(db, 'cables', forbidden=['SOFA']), [])
        self.assertEqual(ix.search(db, 'the and la los'), [])
        self.assertIn('niño', ix.tokens('NIÑO'))
        self.assertNotEqual(ix.normalize('año'), ix.normalize('ano'))
        self.assertFalse(ix.contains('covered normal', 'red'))
        self.assertFalse(ix.contains('covered normal', 'no'))

    def test_latin_phrase_boundaries_and_subtitles(self):
        text = [' Dr.', ' García', ' paid', ' 19.', '99', ' dollars.', " Don't", ' split', ' words.']
        words = [{'start': i * 0.3, 'end': (i + 1) * 0.3, 'text': w} for i, w in enumerate(text)]
        groups = m.phrases([{'start': 0, 'end': 2.7, 'text': ''.join(text), 'words': words}], language='es')
        self.assertTrue(groups[0]['text'].startswith('Dr. García'))
        self.assertIn('19.99', groups[0]['text'])
        self.assertTrue(groups[1]['text'].startswith("Don't"))
        caption = m.subtitle_text('¡Atención! El organizador mantiene los cables juntos y la mesa está limpia.')
        self.assertIn('¡Atención!', caption)
        self.assertIn('está', caption)
        self.assertLessEqual(len(caption.splitlines()), 2)

    def test_preflight_reference_and_stream_duration(self):
        m.preflight(Namespace(project=self.project))
        self.assertTrue(m.read(self.project / 'qa/preflight.json')['audio']['sha256_matches'])
        reference = self.root / 'reference.txt'
        reference.write_text('¡Atención! La mesa está limpia y cuesta 19.99 dólares.')
        data = m.read(self.project / 'audio/timing.json')
        data['segments'][0]['text'] = '¡Atención! La mesa esta limpia y cuesta 29.99 dólares.'
        m.save(self.project / 'audio/timing.json', data)
        m.compare_script(Namespace(project=self.project, script=reference))
        report = m.read(self.project / 'qa/transcript-comparison.json')
        self.assertFalse(report['exact_token_match'])
        diffs = json.dumps(report['differences'], ensure_ascii=False)
        self.assertIn('está', diffs)
        self.assertIn('29', diffs)
        self.assertEqual(m.read(self.project / 'audio/timing.json')['segments'][0]['text'], data['segments'][0]['text'])
        self.assertEqual(m.media_duration({'streams': [{'codec_type': 'video', 'duration': '3'}],
                                         'format': {'duration': '8'}}, 'video'), 3)

    @unittest.skipUnless(os.environ.get('MONTAGE_TEST_MODEL') and importlib.util.find_spec('faster_whisper'),
                         'set MONTAGE_TEST_MODEL to run local ASR integration')
    def test_english_and_spanish_real_transcription(self):
        for language, keywords in [('en', ['storage', 'cables']), ('es', ['caja', 'cables'])]:
            with self.subTest(language=language):
                project = self.root / language
                audio = Path(__file__).parent / f'fixtures/{"english" if language == "en" else "spanish"}.wav'
                m.init(Namespace(project=project, audio=audio, width=180, height=320, fps=30, language=language))
                m.transcribe(Namespace(project=project, model=os.environ['MONTAGE_TEST_MODEL'], language=None, prompt=None))
                data = m.read(project / 'audio/timing.json')
                self.assertEqual(data['language'], language)
                self.assertEqual(data['provenance']['task'], 'transcribe')
                actual = ' '.join(s['text'] for s in data['segments']).casefold()
                for keyword in keywords:
                    self.assertIn(keyword, actual)
                for segment in data['segments']:
                    self.assertLessEqual(len(segment['text']), 78)
                self.assertFalse(data['reviewed'])

    @unittest.skipUnless(os.environ.get('MONTAGE_TEST_MODEL') and importlib.util.find_spec('faster_whisper'),
                         'set MONTAGE_TEST_MODEL to run local ASR integration')
    def test_auto_language_and_silent_audio(self):
        project = self.root / 'auto-es'
        audio = Path(__file__).parent / 'fixtures/spanish.wav'
        m.init(Namespace(project=project, audio=audio, width=180, height=320, fps=30, language='auto'))
        m.transcribe(Namespace(project=project, model=os.environ['MONTAGE_TEST_MODEL'], language=None, prompt=None))
        data = m.read(project / 'audio/timing.json')
        self.assertEqual(data['language'], 'es')
        silence = self.root / 'silence.wav'
        m.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'anullsrc=r=16000:cl=mono', '-t', '1', silence])
        silent_project = self.root / 'silent'
        m.init(Namespace(project=silent_project, audio=silence, width=180, height=320, fps=30, language='en'))
        with self.assertRaisesRegex(ValueError, '静音'):
            m.transcribe(Namespace(project=silent_project, model=os.environ['MONTAGE_TEST_MODEL'], language=None, prompt=None))
        self.assertFalse((silent_project / 'audio/timing.json').exists())

    @unittest.skipUnless(os.environ.get('MONTAGE_TEST_MODEL') and importlib.util.find_spec('faster_whisper'),
                         'set MONTAGE_TEST_MODEL to run local ASR integration')
    def test_chinese_transcription_with_real_local_model(self):
        audio = Path(__file__).parent / 'fixtures/chinese.wav'
        project = self.root / 'speech-project'
        m.init(Namespace(project=project, audio=audio, width=180, height=320, fps=30))
        args = Namespace(project=project, model=os.environ['MONTAGE_TEST_MODEL'], language='zh',
                         prompt='插排、收纳盒、电线、盖子')
        m.transcribe(args)
        data = m.read(project / 'audio/timing.json')
        text = ''.join(s['text'] for s in data['segments'])
        self.assertIn('插排', text)
        self.assertIn('收纳盒', text)
        self.assertGreaterEqual(len(data['segments']), 3)
        self.assertFalse(data['reviewed'])
        self.assertTrue((project / 'audio/raw-transcript.json').exists())
        for segment in data['segments']:
            self.assertTrue(segment['words'])
            self.assertEqual(segment['start'], segment['words'][0]['start'])
            self.assertEqual(segment['end'], segment['words'][-1]['end'])
        with self.assertRaises(ValueError):
            m.transcribe(args)

    @unittest.skipUnless(importlib.util.find_spec('pyJianYingDraft'), 'draft dependency unavailable')
    def test_draft_tracks_paths_and_unique_ids(self):
        self.select()
        for name in ['draft-a', 'draft-b']:
            m.export_draft(Namespace(project=self.project, name=name, allow_unreviewed=False))
        a = m.read(self.project / 'out/draft-a/draft_content.json')
        b = m.read(self.project / 'out/draft-b/draft_content.json')
        self.assertNotEqual(a['id'], b['id'])
        self.assertEqual({t['type'] for t in a['tracks']}, {'video', 'audio', 'text'})
        self.assertEqual(a['duration'], 2400000)
        for kind in ['videos', 'audios']:
            for material in a['materials'][kind]:
                self.assertTrue(Path(material['path']).is_file())
        vids = next(t for t in a['tracks'] if t['type'] == 'video')['segments']
        self.assertEqual(len(vids), 5)
        for segment in vids:
            self.assertEqual(segment['source_timerange']['duration'], segment['target_timerange']['duration'])
            self.assertEqual(segment['volume'], 0)
        import pyJianYingDraft as draft
        loaded = draft.DraftFolder(str(self.project / 'out')).load_template('draft-a')
        self.assertEqual(loaded.duration, 2400000)
        self.assertEqual(len(loaded.imported_tracks), 3)
        with self.assertRaises(ValueError):
            m.export_draft(Namespace(project=self.project, name='draft-a', allow_unreviewed=False))


if __name__ == '__main__':
    unittest.main(verbosity=2)
