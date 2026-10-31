import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend import main, admin


class AdminWorkflow(unittest.TestCase):
    def test_recalculation_versions_apply_restore_and_restart(self):
        old_data,old_jobs=main.DATA,main.JOBS
        with tempfile.TemporaryDirectory() as tmp:
            main.DATA=Path(tmp);main.JOBS=Path(tmp)/'jobs'
            try:
                with TestClient(main.app) as client:
                    main.app.state.pool.shutdown();main.app.state.pool=ThreadPoolExecutor(max_workers=1)
                    self.assertEqual(client.get('/admin').status_code,200)
                    self.assertEqual(client.get('/api/admin/state').status_code,401)
                    password=(main.DATA/'admin'/'initial_password.txt').read_text().strip()
                    bad=client.post('/api/admin/login',json={'password':'wrong','actor':'테스터'})
                    self.assertEqual(bad.status_code,401)
                    self.assertEqual(client.post('/api/admin/login',headers={'Origin':'https://unrelated.example'},json={'password':password}).status_code,403)
                    response=client.post('/api/admin/login',json={'password':password,'actor':'검증 관리자'})
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertIn('HttpOnly',response.headers['set-cookie'])
                    state=client.get('/api/admin/state').json()
                    old_id=state['active']['JOC'];self.assertEqual(len(state['active']),4)
                    docs=client.get('/api/admin/documents/JOC').json();self.assertEqual(len(docs),25)
                    self.assertEqual(client.post('/api/admin/recalculate',json={'group':'JOC','documents':['../../bad.md','another.md'],'name':'bad','reason':'test'}).status_code,400)
                    body={'group':'JOC','documents':['jo100315j.md','jo100420x.md'],'name':'검증용 JOC 소표본','reason':'관리자 재계산 흐름 검증','min_words':1000}
                    response=client.post('/api/admin/recalculate',json=body);self.assertEqual(response.status_code,202,response.text)
                    job=response.json();jid=job['id'];work=main.DATA/'admin'/'jobs'/jid
                    snap=(work/'markdown'/'jo100315j.md').read_bytes()
                    self.assertEqual(hashlib.sha256(snap).hexdigest(),next(d['sha256'] for d in job['documents'] if d['name']=='jo100315j.md'))
                    for _ in range(240):
                        state=client.get('/api/admin/state').json()
                        result=next(j for j in state['jobs'] if j['id']==jid)
                        if result['status'] in ('completed','failed'):break
                        time.sleep(.1)
                    self.assertEqual(result['status'],'completed',result)
                    new_id=result['baseline_id'];self.assertEqual(state['active']['JOC'],old_id)
                    self.assertEqual(len([v for v in state['versions'] if v['group']=='JOC']),2)
                    b=client.get('/api/admin/versions/'+new_id).json()['baseline']
                    self.assertEqual(len(b['papers']),2)
                    self.assertEqual(b['admin_settings']['documents'],body['documents'])
                    self.assertTrue(b['rule_hashes'])
                    self.assertEqual(client.get('/api/admin/jobs/'+jid+'/download').status_code,200)
                    public=client.get('/api/baselines').json();self.assertNotIn(new_id,[r['id'] for r in public])
                    conflict=client.post('/api/admin/apply',json={'version_id':new_id,'expected_current_id':None,'reason':'stale'})
                    self.assertEqual(conflict.status_code,409)
                    response=client.post('/api/admin/apply',json={'version_id':new_id,'expected_current_id':old_id,'reason':'새 기준 검토 후 적용'})
                    self.assertEqual(response.status_code,200,response.text)
                    public=client.get('/api/baselines').json();self.assertIn(new_id,[r['id'] for r in public]);self.assertNotIn(old_id,[r['id'] for r in public])
                    self.assertEqual(client.post('/api/manuscript',json={'sections':{'INTRO':'This may occur.'},'baseline_id':old_id}).status_code,409)
                    registry=admin.get_state()
                    self.assertEqual(len([h for h in registry['history'] if h['action']=='activated']),1)
                    response=client.post('/api/admin/apply',json={'version_id':old_id,'expected_current_id':new_id,'reason':'검증 후 원래 기준 복원','restore':True})
                    self.assertEqual(response.status_code,200,response.text)
                    history=client.get('/api/admin/state').json()['history']
                    self.assertTrue(any(h['action']=='restored' and h['actor']=='검증 관리자' for h in history))
                    response=client.post('/api/admin/recalculate',json={**body,'name':'실패 경로 검증','reason':'부족한 본문으로 실패 시 기존 기준 보존 확인','min_words':20000})
                    self.assertEqual(response.status_code,202,response.text)
                    failed_id=response.json()['id']
                    for _ in range(150):
                        final=client.get('/api/admin/state').json()
                        failed=next(j for j in final['jobs'] if j['id']==failed_id)
                        if failed['status']=='failed':break
                        time.sleep(.1)
                    self.assertEqual(failed['status'],'failed',failed)
                    self.assertEqual(final['active']['JOC'],old_id)
                    self.assertEqual(len([v for v in final['versions'] if v['group']=='JOC']),2)
                    history=final['history']
                    self.assertEqual(client.post('/api/admin/logout').status_code,200)
                    self.assertEqual(client.get('/api/admin/state').status_code,401)
                with TestClient(main.app) as client:
                    client.post('/api/admin/login',json={'password':password})
                    state=client.get('/api/admin/state').json()
                    self.assertEqual(state['active']['JOC'],old_id)
                    self.assertIn(new_id,[v['id'] for v in state['versions']])
                    self.assertEqual(state['history'],history)
            finally:
                main.DATA,main.JOBS=old_data,old_jobs

    def test_failed_job_preserves_active_and_logs_failure_once(self):
        old_data,old_jobs=main.DATA,main.JOBS
        with tempfile.TemporaryDirectory() as tmp:
            main.DATA=Path(tmp);main.JOBS=Path(tmp)/'jobs'
            try:
                with TestClient(main.app) as client:
                    p=(main.DATA/'admin'/'initial_password.txt').read_text().strip()
                    client.post('/api/admin/login',json={'password':p})
                    old=admin.get_state()['active'].copy()
                    # Failed worker reports are reconciled idempotently after restart or polling.
                    import uuid
                    jid=str(uuid.uuid4());work=main.DATA/'admin'/'jobs'/jid;work.mkdir()
                    job=dict(id=jid,group='CM',name='실패 검증',reason='검증',actor='관리자',base_id=old['CM'],status='failed',created_at=main.now(),documents=[],error='통과 문서 부족')
                    main.save(work/'job.json',job)
                    client.get('/api/admin/state');state=client.get('/api/admin/state').json()
                    self.assertEqual(state['active'],old)
                    self.assertEqual(len([h for h in state['history'] if h['action']=='failed' and h['job_id']==jid]),1)
                    # A modified archive cannot be applied.
                    vid=old['CM'];path=main.DATA/'admin'/'versions'/(vid+'.json');path.write_text('{}')
                    self.assertEqual(client.get('/api/admin/versions/'+vid).status_code,409)
            finally:
                main.DATA,main.JOBS=old_data,old_jobs


if __name__=='__main__':unittest.main()
