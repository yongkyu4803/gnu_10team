"""Executed from a job's frozen rules directory; source Markdown is already snapshotted."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime,timezone


def main():
    work=Path(sys.argv[1]).resolve();root=Path(sys.argv[2]).resolve();rules=work/'rules'
    sys.path.insert(0,str(rules));sys.path.insert(1,str(root))
    import spacy
    from backend import stage1
    job=json.loads((work/'job.json').read_text(encoding='utf-8'))
    for name,digest in job['rules'].items():
        if hashlib.sha256((rules/name).read_bytes()).hexdigest()!=digest:raise ValueError('분석 규칙 스냅샷 해시 불일치')
    for item in job['documents']:
        if hashlib.sha256((work/'markdown'/item['name']).read_bytes()).hexdigest()!=item['sha256']:raise ValueError('입력 마크다운 스냅샷 해시 불일치')
    nlp=spacy.load('en_core_web_sm')
    if spacy.__version__!='3.8.11' or nlp.meta['version']!='3.8.0':raise ValueError('spaCy 3.8.11 / en_core_web_sm 3.8.0 환경이 필요합니다')
    spec=importlib.util.spec_from_file_location('frozen_markdown_adapter',rules/'build_markdown_baselines.py')
    adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter);adapter.ROOT=root
    gate=adapter.prepare(job['group'],source_dir=work/'markdown',output_dir=work/'analysis',documents=[d['name'] for d in job['documents']],min_words=job['min_words'])
    passed=[r for r in gate if r['result']=='Pass']
    if len(passed)<2:raise ValueError(f'마크다운 구조 검사를 통과한 논문이 {len(passed)}편입니다. 2편 이상 필요합니다.')
    output=work/'analysis'/'2_baseline'
    subprocess.run([sys.executable,str(rules/'hedge_baseline.py'),str(work/'analysis'/'1_markdown_input'),str(output),'--max-papers',str(len(job['documents']))],check=True)
    checks=json.loads((output/'checks.json').read_text(encoding='utf-8'))
    failed=[r['check'] for r in checks['items'] if r['result']=='Fail']
    if failed:raise ValueError('분석 처리 검사 실패: '+', '.join(failed))
    # Recompute every published metric to verify the CLI output before registering a version.
    import statistics
    rows=stage1.csv_rows(output/'per_paper.csv')
    for row in stage1.csv_rows(output/'baseline.csv'):
        values=[float(r[row['metric']]) for r in rows if r['section']==row['section'] and r[row['metric']]!='']
        if len(values)!=int(row['n_papers']) or round(statistics.median(values),2)!=float(row['median']) or min(values)!=float(row['min']) or max(values)!=float(row['max']):
            raise ValueError('통계 재검산 실패')
    b=stage1.import_baseline(output,job['name'],job['baseline_id'],datetime.now(timezone.utc).isoformat())
    b.update(group=job['group'],input_kind='markdown',input_papers=len(gate),excluded_papers=len(gate)-len(passed),needs_review=True,
             markdown_gate=gate,input_fingerprint=hashlib.sha256(json.dumps(job['documents'],sort_keys=True).encode()).hexdigest(),
             admin_settings={'min_words':job['min_words'],'documents':[d['name'] for d in job['documents']]},
             admin_job=job['id'],parent_version=job['base_id'],rule_hashes=job['rules'],environment={'python':platform.python_version(),'spacy':spacy.__version__,'model':'en_core_web_sm','model_version':nlp.meta['version']},pdf_quality_gate='not_applicable')
    b['limitations'][:0]=['마크다운 기반 예비값입니다. PDF 인용 회수·배치 검사는 적용하지 않았습니다.','문장 순서·표 안 본문·자동 판정은 연구자 검토가 필요합니다.']
    payload=json.dumps(b,ensure_ascii=False,indent=2).encode('utf-8');target=work/'baseline.json';temp=work/'baseline.tmp';temp.write_bytes(payload);temp.replace(target)
    if hashlib.sha256(target.read_bytes()).digest()!=hashlib.sha256(payload).digest():raise ValueError('저장 후 해시 검증 실패')
    print(json.dumps({'included':len(b['papers']),'excluded':b['excluded_papers'],'baseline_id':b['id']},ensure_ascii=False))


if __name__=='__main__':main()
