import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from vision_json import decode_response
from vision_api import call
from asset_index import digest_json
from montage import save,read


def response(text,finish='stop'):return {'choices':[{'message':{'content':text},'finish_reason':finish}],'usage':{'total_tokens':12}}


class JsonRecoveryTest(unittest.TestCase):
    def test_single_missing_quote_recovered_without_changing_text(self):
        raw=response('{"events":[{"description":"LED is blue.}],"unknowns":["sound"]}')
        parsed,audit=decode_response(raw)
        self.assertEqual(parsed,{'events':[{'description':'LED is blue.'}],'unknowns':['sound']})
        self.assertEqual(audit['inserted'],'"');self.assertFalse(audit['content_inferred'])
    def test_strict_json_and_code_fences(self):
        for text in ('{"events":[]}','```json\n{"events":[]}\n```'):
            self.assertEqual(decode_response(response(text)),({'events':[]},None))
    def test_truncation_and_missing_values_never_repaired(self):
        for text,finish in [('{"events":[{"description":"blue.}],"other":[]}','length'),('{"events":[{"description":"blue.}],"other":[]}',None),('{"name":"unfinished','stop'),('{"value":}','stop')]:
            with self.assertRaises(ValueError):decode_response(response(text,finish))
    def test_cached_raw_recovered_without_key_fee_or_network(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=Path(folder);config={'base_url':'http://localhost:9999/v1','model':'fake'}
            ident=digest_json({'endpoint':config['base_url']+'/chat/completions','model':'fake','prompt':'test','frames':[]})
            raw=response('{"events":[{"description":"blue.}],"other":[]}');save(cache/(ident+'.raw.json'),raw)
            with patch('urllib.request.build_opener') as net:
                result=call(config,'test',[],cache,False);net.assert_not_called()
            self.assertEqual(result['events'][0]['description'],'blue.')
            self.assertEqual(read(cache/(ident+'.raw.json')),raw)
            self.assertEqual(read(cache/(ident+'.usage.json')),{'total_tokens':12})
            self.assertTrue((cache/(ident+'.recovery.json')).is_file())
    def test_invalid_raw_is_not_resent_automatically(self):
        with tempfile.TemporaryDirectory() as folder:
            cache=Path(folder);cfg={'base_url':'http://localhost:9999/v1','model':'fake'}
            ident=digest_json({'endpoint':cfg['base_url']+'/chat/completions','model':'fake','prompt':'test','frames':[]})
            save(cache/(ident+'.raw.json'),response('{"v":}'))
            with patch('urllib.request.build_opener') as net:
                with self.assertRaises(ValueError):call(cfg,'test',[],cache,True)
                net.assert_not_called()
