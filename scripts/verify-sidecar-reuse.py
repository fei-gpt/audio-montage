"""Verify one completed job's portable document without any model or Hypit calls."""
import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO))
from montage import save
from video_document import document_path
from workbench.backend import Workbench


def main():
    parser=argparse.ArgumentParser();parser.add_argument('job');args=parser.parse_args()
    state=REPO/'.workbench-data'
    with sqlite3.connect(state/'catalog.sqlite') as connection:
        def get(ident):return json.loads(connection.execute('SELECT body FROM objects WHERE id=?',(ident,)).fetchone()[0])
        job=get(args.job);asset=get(job['asset_ids'][0]);product=get(job['product_id']);workspace=get(job['workspace_id'])
    config=json.loads((state/'vision-config.json').read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory(prefix='sidecar-move-test-') as folder:
        root=Path(folder);media=root/'moved';media.mkdir()
        video=media/Path(asset['path']).name
        shutil.copy2(asset['path'],video)
        shutil.copy2(document_path(asset['path']),document_path(video))
        app=Workbench(root/'state',executor=False)
        save(app.root/'vision-config.json',{k:v for k,v in config.items() if k in {'model','base_url','api_key_env'}})
        app.store.put('product','root',product)
        app.store.put('workspace',product['id'],workspace)
        lib=app.attach_library(product['id'],workspace['id'],str(media),asset['kind'])
        moved=dict(asset,path=str(video),library_id=lib['id'])
        app.store.put('asset',workspace['id'],moved)
        with patch('vision_api.call',side_effect=AssertionError('Unexpected API request')) as network, patch('hypit_adapter.analyze',side_effect=AssertionError('Unexpected Hypit rerun')) as hypit:
            app.process_asset(job,moved,product)
            network.assert_not_called();hypit.assert_not_called()
        shots=app.store.all('shot',workspace['id'])
        assert shots and shots[0].get('visual_details')
        assert shots[0]['review_decision']=='uncertain'
        print('Moved video + document: restored results; 0 API calls; 0 Hypit reruns; review remains pending.')


if __name__=='__main__':main()
