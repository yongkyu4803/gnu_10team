"""Local administrator sessions, immutable baseline versions and atomic change history."""
from datetime import datetime, timezone
import hashlib
import base64
import hmac
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
from uuid import uuid4, UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from typing import Literal

GROUPS={'CM':'재료화학','IC':'무기화학','JOC':'유기화학','JPC_C':'물리화학·재료'}
COOKIE='baseline_admin'
router=APIRouter(prefix='/api/admin')


def ctx():
    from backend import main
    return main


def directory():
    return ctx().DATA/'admin'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def identifier(value):
    try:
        if str(UUID(value))!=value:raise ValueError()
    except (ValueError,TypeError):
        raise HTTPException(404,'항목을 찾을 수 없습니다')
    return value


def commit_state(state,action,actor,reason,group=None,before=None,after=None,job_id=None,at=None):
    state['revision']+=1
    state['history'].append(dict(id=str(uuid4()),at=at or ctx().now(),action=action,actor=actor,reason=reason,group=group,
                                 before=before,after=after,job_id=job_id,revision=state['revision']))
    ctx().save(directory()/'registry.json',state)


def version_record(baseline,actor,reason,job_id=None):
    m=ctx();vid=identifier(baseline['id']);path=directory()/'versions'/(vid+'.json')
    if path.exists():
        if read(path)!=baseline:raise ValueError('동일 ID의 버전 내용이 다릅니다')
    else:
        m.save(path,baseline)
    return dict(id=vid,group=baseline['group'],name=baseline['name'],created_at=baseline['created_at'],actor=actor,reason=reason,
                job_id=job_id,papers=len(baseline['papers']),excluded=baseline.get('excluded_papers',0),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),engine=baseline.get('version'),
                settings=baseline.get('admin_settings',{'min_words':1000}),source_fingerprint=baseline.get('input_fingerprint'))


def initialize():
    m=ctx();base=directory();base.mkdir(exist_ok=True,parents=True)
    for name in ('versions','jobs'):(base/name).mkdir(exist_ok=True)
    credentials=base/'credentials.json'
    if not credentials.exists():
        password=secrets.token_urlsafe(18);salt=secrets.token_hex(16)
        m.save(credentials,dict(salt=salt,password_hash=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),300000).hex(),secret=secrets.token_hex(32)))
        credentials.chmod(0o600)
        p=base/'initial_password.txt';p.write_text(password+'\n',encoding='utf-8');p.chmod(0o600)
    registry=base/'registry.json'
    if not registry.exists():
        state=dict(schema=1,revision=0,active={},versions=[],history=[])
        for group in GROUPS:
            candidates=[read(p) for p in (m.DATA/'baselines').glob('*.json')]
            candidates=[b for b in candidates if b.get('group')==group and b.get('input_kind')=='markdown']
            if not candidates:continue
            b=max(candidates,key=lambda b:b['created_at'])
            record=version_record(b,'system','기존 마크다운 기준선 등록')
            state['versions'].append(record);state['active'][group]=b['id']
            state['revision']+=1;state['history'].append(dict(id=str(uuid4()),at=m.now(),action='initialized',actor='system',reason='기존 마크다운 기준선 등록',group=group,before=None,after=b['id'],job_id=None,revision=state['revision']))
        m.save(registry,state)
    for path in (base/'jobs').glob('*/job.json'):
        job=read(path)
        if job['status'] in ('queued','running'):
            job.update(status='failed',error='서버 종료로 재계산이 중단되었습니다. 다시 실행하세요.',updated_at=m.now())
            m.save(path,job)
    reconcile()


_failures={}

def check_origin(request):
    origin=request.headers.get('origin')
    if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
        raise HTTPException(403,'다른 사이트에서 관리자 작업을 요청할 수 없습니다')


def authenticated(request:Request):
    check_origin(request)
    token=request.cookies.get(COOKIE,'')
    try:
        raw,signature=token.rsplit('.',1)
        credential=read(directory()/'credentials.json')
        expected=hmac.new(bytes.fromhex(credential['secret']),raw.encode(),hashlib.sha256).hexdigest()
        issued,actor=base64.urlsafe_b64decode(raw+'='*((-len(raw))%4)).decode('utf-8').split(':',1)
        if not hmac.compare_digest(signature,expected) or not 0<=time.time()-int(issued)<8*3600:raise ValueError()
        return actor
    except (ValueError,KeyError,FileNotFoundError,UnicodeDecodeError):
        raise HTTPException(401,'관리자 로그인이 필요합니다')


class Login(BaseModel):
    password:str=Field(min_length=1,max_length=200)
    actor:str=Field(default='관리자',min_length=1,max_length=40,pattern=r'^[^:\r\n]+$')


@router.post('/login')
def login(body:Login,request:Request,response:Response):
    check_origin(request)
    if not body.actor.strip():raise HTTPException(400,'기록에 남길 이름을 입력하세요')
    key=request.client.host if request.client else 'local'
    with ctx().LOCK:
        recent=[t for t in _failures.get(key,[]) if time.time()-t<60]
        if len(recent)>=10:raise HTTPException(429,'로그인 시도가 많습니다. 1분 뒤 다시 시도하세요.')
        credential=read(directory()/'credentials.json')
        value=hashlib.pbkdf2_hmac('sha256',body.password.encode(),bytes.fromhex(credential['salt']),300000).hex()
        if not hmac.compare_digest(value,credential['password_hash']):
            _failures[key]=recent+[time.time()];raise HTTPException(401,'비밀번호가 올바르지 않습니다')
        _failures.pop(key,None)
    raw=base64.urlsafe_b64encode((str(int(time.time()))+':'+body.actor.strip()).encode('utf-8')).decode('ascii').rstrip('=')
    signature=hmac.new(bytes.fromhex(credential['secret']),raw.encode(),hashlib.sha256).hexdigest()
    response.set_cookie(COOKIE,raw+'.'+signature,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=8*3600,path='/api/admin')
    response.headers['Cache-Control']='no-store'
    return {'actor':body.actor.strip()}


@router.post('/logout')
def logout(response:Response,actor=Depends(authenticated)):
    response.delete_cookie(COOKIE,path='/api/admin')
    return {'ok':True}


def get_state():
    return read(directory()/'registry.json')


def checked_version(state,vid):
    vid=identifier(vid)
    record=next((v for v in state['versions'] if v['id']==vid),None)
    if record is None:raise HTTPException(404,'기준 버전을 찾을 수 없습니다')
    path=directory()/'versions'/(vid+'.json')
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=record['sha256']:
        raise HTTPException(409,'보관된 버전의 해시가 일치하지 않습니다')
    return record,read(path)


def reconcile():
    """Only the server updates the registry; workers publish result files atomically."""
    with ctx().LOCK:
        state=get_state();known={v['job_id'] for v in state['versions'] if v.get('job_id')}
        for path in sorted((directory()/'jobs').glob('*/job.json')):
            job=read(path)
            if job['status']=='completed' and job['id'] not in known:
                result=path.parent/'baseline.json'
                if hashlib.sha256(result.read_bytes()).hexdigest()!=job['result_sha256']:
                    job.update(status='failed',error='재계산 결과 해시가 일치하지 않습니다',updated_at=ctx().now());ctx().save(path,job)
                else:
                    b=read(result);record=version_record(b,job['actor'],job['reason'],job['id'])
                    ctx().save(ctx().DATA/'baselines'/(b['id']+'.json'),b)
                    state['versions'].append(record)
                    commit_state(state,'recalculated',job['actor'],job['reason'],group=job['group'],before=job['base_id'],after=b['id'],job_id=job['id'],at=job.get('updated_at'))
                    known.add(job['id'])
            if job['status']=='failed' and not any(h.get('job_id')==job['id'] and h['action']=='failed' for h in state['history']):
                commit_state(state,'failed',job['actor'],job.get('error','재계산 실패'),group=job['group'],before=job['base_id'],job_id=job['id'],at=job.get('updated_at'))


@router.get('/state')
def state(actor=Depends(authenticated)):
    reconcile()
    with ctx().LOCK:
        value=get_state();value['actor']=actor
        value['groups']=GROUPS
        value['jobs']=sorted([read(p) for p in (directory()/'jobs').glob('*/job.json')],key=lambda j:j['created_at'],reverse=True)
        return value


@router.get('/versions/{vid}')
def detail(vid:str,actor=Depends(authenticated)):
    with ctx().LOCK:
        record,b=checked_version(get_state(),vid)
        return dict(version=record,baseline=b)


@router.get('/documents/{group}')
def documents(group:Literal['CM','IC','JOC','JPC_C'],actor=Depends(authenticated)):
    rows=[]
    for path in sorted((ctx().ROOT/group).glob('*.md')):
        content=path.read_text(encoding='utf-8');title=next((line.lstrip('# ').strip() for line in content.splitlines() if line.startswith('#')),path.stem)
        rows.append(dict(name=path.name,title=title,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),characters=len(content)))
    return rows


class Recalculate(BaseModel):
    group:Literal['CM','IC','JOC','JPC_C']
    documents:list[str]=Field(min_length=2,max_length=100)
    name:str=Field(min_length=1,max_length=120)
    reason:str=Field(min_length=1,max_length=1000)
    min_words:int=Field(default=1000,ge=1000,le=20000)


@router.post('/recalculate',status_code=202)
def recalculate(body:Recalculate,request:Request,actor=Depends(authenticated)):
    m=ctx()
    if not body.name.strip() or not body.reason.strip():raise HTTPException(400,'기준 이름과 변경 사유를 입력하세요')
    names=list(dict.fromkeys(body.documents))
    if len(names)<2:raise HTTPException(400,'서로 다른 마크다운 문서를 2편 이상 선택하세요')
    paths=[]
    for name in names:
        if Path(name).name!=name or not name.endswith('.md'):raise HTTPException(400,'문서 이름이 올바르지 않습니다')
        path=m.ROOT/body.group/name
        if not path.is_file() or path.is_symlink():raise HTTPException(404,'선택한 문서를 찾을 수 없습니다')
        paths.append(path)
    with m.LOCK:
        reconcile()
        if any(read(p)['status'] in ('queued','running') for p in (directory()/'jobs').glob('*/job.json')):
            raise HTTPException(409,'진행 중인 재계산이 있습니다. 완료 후 다시 실행하세요')
        state=get_state();jid=str(uuid4());work=directory()/'jobs'/jid
        (work/'markdown').mkdir(parents=True);(work/'rules').mkdir()
        manifest=[]
        for path in paths:
            content=path.read_bytes();(work/'markdown'/path.name).write_bytes(content)
            manifest.append(dict(name=path.name,sha256=hashlib.sha256(content).hexdigest()))
        rules={}
        for name in ('hedge_baseline.py','engine_local.py','rvtool.py','extract_pdf.py'):
            source=m.ROOT/'section-verb-hedge-baseline'/'scripts'/name
            content=source.read_bytes();(work/'rules'/name).write_bytes(content);rules[name]=hashlib.sha256(content).hexdigest()
        for source in (m.ROOT/'scripts'/'build_markdown_baselines.py',m.ROOT/'backend'/'admin_worker.py'):
            content=source.read_bytes();(work/'rules'/source.name).write_bytes(content);rules[source.name]=hashlib.sha256(content).hexdigest()
        job=dict(id=jid,group=body.group,name=body.name.strip(),reason=body.reason.strip(),actor=actor,base_id=state['active'].get(body.group),
                 status='queued',created_at=m.now(),updated_at=m.now(),documents=manifest,rules=rules,min_words=body.min_words,
                 input_kind='markdown',baseline_id=str(uuid4()))
        m.save(work/'job.json',job)
        commit_state(state,'recalculation_started',actor,job['reason'],group=body.group,before=job['base_id'],job_id=jid)
        try:
            request.app.state.pool.submit(run_job,str(work))
        except Exception as exc:
            job.update(status='failed',error=str(exc));m.save(work/'job.json',job);reconcile()
            raise HTTPException(503,'재계산 작업을 시작하지 못했습니다')
        return job


def run_job(work_path):
    """ProcessPool entry point, independent of request context and mutable inputs."""
    from backend.main import save,now
    work=Path(work_path);job=read(work/'job.json')
    try:
        job.update(status='running',updated_at=now());save(work/'job.json',job)
        root=Path(__file__).resolve().parents[1]
        python=root/'.venv-baseline'/'bin'/'python'
        if not python.exists():python=Path(sys.executable)
        with (work/'run.log').open('w',encoding='utf-8') as log:
            result=subprocess.run([str(python),str(work/'rules'/'admin_worker.py'),str(work),str(root)],stdout=log,stderr=subprocess.STDOUT,timeout=1800)
        if result.returncode:
            lines=[line.strip() for line in (work/'run.log').read_text(encoding='utf-8').splitlines() if line.strip()]
            message=lines[-1] if lines else '분석에 실패했습니다'
            raise ValueError(message.removeprefix('ValueError: ')[:1000])
        b=read(work/'baseline.json')
        if b['id']!=job['baseline_id'] or b['group']!=job['group']:raise ValueError('재계산 결과의 버전 정보가 일치하지 않습니다')
        job.update(status='completed',updated_at=now(),papers=len(b['papers']),excluded=b['excluded_papers'],result_sha256=hashlib.sha256((work/'baseline.json').read_bytes()).hexdigest())
    except Exception as exc:
        job.update(status='failed',error=str(exc),updated_at=now())
    save(work/'job.json',job)


class Apply(BaseModel):
    version_id:str
    expected_current_id:str|None
    reason:str=Field(min_length=1,max_length=1000)
    restore:bool=False


@router.post('/apply')
def apply(body:Apply,actor=Depends(authenticated)):
    if not body.reason.strip():raise HTTPException(400,'적용 사유를 입력하세요')
    with ctx().LOCK:
        reconcile();state=get_state();record,b=checked_version(state,body.version_id);group=record['group'];old=state['active'].get(group)
        if body.expected_current_id!=old:raise HTTPException(409,'현재 기준이 변경되었습니다. 새로고침 후 다시 적용하세요')
        if old==record['id']:raise HTTPException(409,'이미 적용 중인 기준입니다')
        if b.get('version')!=ctx().stage1.VERSION:
            raise HTTPException(409,'현재 원고 분석기와 기준 버전이 다릅니다. 분석기를 맞춘 후 적용하세요.')
        for name,expected in b.get('rule_hashes',{}).items():
            if name in ('hedge_baseline.py','engine_local.py','rvtool.py','extract_pdf.py') and hashlib.sha256((ctx().stage1.SCRIPTS/name).read_bytes()).hexdigest()!=expected:
                raise HTTPException(409,'분석 규칙이 재계산 시점과 달라졌습니다. 다시 계산한 뒤 적용하세요.')
        if body.restore and not any(h.get('after')==record['id'] and h['action'] in ('initialized','activated','restored') for h in state['history']):
            raise HTTPException(400,'이전에 적용한 버전만 복원할 수 있습니다')
        ctx().save(ctx().DATA/'baselines'/(b['id']+'.json'),b)
        state['active'][group]=record['id']
        commit_state(state,'restored' if body.restore else 'activated',actor,body.reason.strip(),group=group,before=old,after=record['id'])
        return {'active':state['active'],'revision':state['revision']}


@router.get('/jobs/{job_id}/download')
def download(job_id:str,actor=Depends(authenticated)):
    import zipfile
    from starlette.background import BackgroundTask
    work=directory()/'jobs'/identifier(job_id)
    if not (work/'job.json').exists():raise HTTPException(404,'작업을 찾을 수 없습니다')
    if read(work/'job.json')['status'] in ('queued','running'):raise HTTPException(409,'작업이 아직 진행 중입니다')
    target=directory()/('export-'+str(uuid4())+'.zip')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for p in work.rglob('*'):
            if p.is_file():archive.write(p,p.relative_to(work))
    return FileResponse(target,filename='baseline-recalculation.zip',background=BackgroundTask(target.unlink,missing_ok=True))


def public_baselines(include_archived=False):
    m=ctx()
    with m.LOCK:
        state=get_state() if (directory()/'registry.json').exists() else {'active':{},'versions':[]}
        records={v['id']:v for v in state['versions']}
        values={b['id']:b for b in [read(p) for p in (m.DATA/'baselines').glob('*.json')]}
        for vid in records:
            values[vid]=checked_version(state,vid)[1]
        result=[]
        for b in values.values():
            group=b.get('group');active=state['active'].get(group)
            if active and b['id']!=active and not include_archived:continue
            result.append(dict(id=b['id'],name=b['name'],kind=b.get('kind','legacy'),group=group,input_kind=b.get('input_kind'),
                               needs_review=b.get('needs_review',True),papers=len(b['papers']),created_at=b['created_at'],source_jobs=b.get('source_jobs',[]),is_active=b['id']==active))
        return result
