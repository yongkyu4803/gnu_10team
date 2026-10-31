import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend import main, stage1


class Stage1(unittest.TestCase):
    def test_bundled_csv_and_same_engine_manuscript(self):
        old_data,old_jobs=main.DATA,main.JOBS
        with tempfile.TemporaryDirectory() as tmp:
            main.DATA=Path(tmp);main.JOBS=Path(tmp)/'jobs'
            try:
                with TestClient(main.app) as client:
                    choices=client.get('/api/baselines').json()
                    choice=next(b for b in choices if b['id']==stage1.BUILTIN_ID)
                    self.assertEqual(choice['kind'],'stage1');self.assertEqual(choice['papers'],5)
                    b=client.get('/api/baselines/'+choice['id']).json()
                    self.assertEqual(b['metrics']['RD']['hedge_per1000']['median'],3.1)
                    self.assertEqual(b['metrics']['RD']['hedge_per1000']['n'],5)
                    self.assertEqual(b['metrics']['RD']['hedge_per1000']['max'],10.95)
                    self.assertEqual(b['source_hashes']['baseline.csv'],__import__('hashlib').sha256((stage1.EXAMPLE/'baseline.csv').read_bytes()).hexdigest())
                    self.assertTrue(all(not row['sentence'] for row in stage1.csv_rows(stage1.EXAMPLE/'evidence.csv')))
                    sections={'INTRO':'This reaction may proceed. These results clearly demonstrate a new pathway [1].\n\n1H NMR (400 MHz): this may be recorded.','M':'The sample may be heated and stirred.','RD':'In general, this pathway may occur. The solvent is probably important.'}
                    response=client.post('/api/manuscript',json={'sections':sections,'baseline_id':choice['id']})
                    self.assertEqual(response.status_code,200,response.text)
                    result=response.json();stage=result['stage1'];self.assertEqual(stage['unit'],1000)
                    self.assertEqual(stage['excluded_nonprose'],1)
                    intro,method,rd=stage['sections']
                    self.assertEqual(intro['metrics']['hedge'],1)
                    self.assertEqual(method['metrics']['hedge_per1000'],None)
                    self.assertEqual(rd['metrics']['hedge'],3) # phrase + modal + adverb
                    self.assertEqual(rd['baseline']['hedge_per1000']['median'],3.1)
                    self.assertEqual(result['baseline_literature'],None)
                    self.assertTrue(all(s['comparison'] is None for s in result['sections']))
                    saved=json.loads((main.DATA/'manuscripts'/(result['id']+'.json')).read_text())
                    self.assertEqual(saved['stage1'],stage)
                    rejected=client.post('/api/jobs',data={'mode':'stage1'},files={'files':('one.pdf',b'%PDF-')})
                    self.assertEqual(rejected.status_code,400)
            finally:
                main.DATA,main.JOBS=old_data,old_jobs

    def test_quality_gate_blocks_and_preserves_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            def fake(script,args,**kwargs):
                if script=='render_layout.py':
                    return ''
                output=directory/'stage1';output.mkdir()
                (output/'extract_gate.json').write_text(json.dumps([dict(document_id='bad',result='Fail',cite_recovery=.5,open_sentences=.2,leaks=0)]))
                return 'quality gate run'
            with patch.object(stage1,'run_cli',side_effect=fake):
                with self.assertRaisesRegex(ValueError,'2편 미만'):
                    stage1.generate(directory,'test','id','now')
                self.assertTrue((directory/'stage1'/'extract_gate.json').exists())


if __name__=='__main__':
    unittest.main()
