"""Adapter for the unmodified section-verb-hedge-baseline CLI and CSV artifacts."""
import csv
import hashlib
import importlib.util
from functools import lru_cache
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from uuid import UUID, uuid5

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT / 'section-verb-hedge-baseline'
SCRIPTS = REPO / 'scripts'
EXAMPLE = REPO / 'examples' / 'IC_2010-2015_5편'
VERSION = 'hedge-baseline-0.4.4'
MODEL = 'en_core_web_sm'
MODEL_VERSION = '3.8.0'
KEYS = {'INTRO':'INT','M':'MET','RD':'RD','CONCL':'CON'}
LABELS = {'INT':'서론','MET':'방법(실험·계산)','RES':'결과','DIS':'논의','RD':'결과·논의','CON':'결론'}
BUILTIN_ID = str(uuid5(UUID('3217d716-7436-40b7-a45a-c6ebd454d7f9'), 'IC-2010-2015-5-0.4.4'))


def csv_rows(path):
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def number(value):
    return float(value) if value not in ('',None) else None


def import_baseline(directory, name, identifier, created_at, gate=None, source_jobs=None):
    baseline = csv_rows(directory/'baseline.csv')
    per = csv_rows(directory/'per_paper.csv')
    common = csv_rows(directory/'common_verbs.csv')
    if not baseline or not per:
        raise ValueError('기준선 CSV가 비어 있습니다. 추출 품질 검사 결과를 확인하세요.')
    metrics = {}
    for row in baseline:
        metrics.setdefault(row['section'], {})[row['metric']] = dict(n=int(row['n_papers']), median=number(row['median']),min=number(row['min']),max=number(row['max']),values=row['values'])
    verbs = {}
    for row in common:
        verbs.setdefault(row['section'], []).append(dict(lemma=row['lemma'],papers=int(row['papers_with']),n=int(row['papers_in_section']),median_per1000=number(row['median_per1000']),total=int(row['total'])))
    checks_path = directory/'checks.json'
    checks = json.loads(checks_path.read_text(encoding='utf-8')) if checks_path.exists() else {}
    provenance = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.iterdir()) if p.is_file()}
    return dict(id=identifier,name=name,kind='stage1',created_at=created_at,source_jobs=source_jobs or [],
                papers=[dict(id=pid) for pid in sorted({r['document_id'] for r in per})], metrics=metrics,common_verbs=verbs,
                per_paper=per,gate=gate or [],checks=checks,source='https://github.com/angela0420/section-verb-hedge-baseline',
                spacy_version='3.8.11',version=checks.get('version',VERSION),model=checks.get('model',MODEL),model_version=MODEL_VERSION,
                unit=1000,statistic='median',word_definition='spaCy token.is_alpha',source_hashes=provenance,
                limitations=['추출·규칙 기반 예비판정이며 연구자 검토가 필요합니다.','공통 동사 CSV에는 절반 이상 논문에 나온 동사만 있습니다. 미수록 동사는 출현 0건이라는 뜻이 아닙니다.','선행연구 토픽·인용 기능 기준 데이터는 이 기준선에 포함되지 않습니다.'])


def run_cli(script, arguments, timeout=1800):
    completed=subprocess.run([sys.executable,str(SCRIPTS/script),*map(str,arguments)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
    if completed.returncode:
        raise ValueError((completed.stderr or completed.stdout)[-3000:] or 'Stage 1 분석에 실패했습니다')
    return completed.stdout


@lru_cache
def extractor():
    spec=importlib.util.spec_from_file_location('stage1_extract_pdf',SCRIPTS/'extract_pdf.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manuscript(sections, baseline):
    """Write the repository's standard sentence inputs and run its exact analysis CLI."""
    from backend.analysis import language, paragraphs
    if baseline.get('version')!=VERSION or baseline.get('model')!=MODEL:
        raise ValueError('기준선 엔진 또는 모델 버전이 현재 분석기와 다릅니다')
    import spacy
    if spacy.__version__!='3.8.11':
        raise ValueError('기준선과 동일한 spaCy 3.8.11이 필요합니다. requirements.txt를 설치하세요.')
    if language().meta.get('version')!=MODEL_VERSION:
        raise ValueError(f'기준선과 동일한 {MODEL} {MODEL_VERSION} 모델이 필요합니다')
    with tempfile.TemporaryDirectory(prefix='stage1-manuscript-') as tmp:
        directory=Path(tmp); extracted=directory/'input'; extracted.mkdir()
        lines=['# document_id: manuscript', '# extractor: web-manuscript-1']
        rows=[]; order=0
        for section_index,(key,section) in enumerate(KEYS.items(),1):
            sequence=0
            # Keep citation text for the original reporting-verb attribution rules.
            text=re.sub(r'⟦c:([^⟧]*)⟧',r'[\1]',sections.get(key,''))
            for pi,paragraph in enumerate(paragraphs(text),1):
                for si,sentence in enumerate(extractor().split_sents(paragraph),1):
                    order+=1;sequence+=1;sid=f'{section_index}-{sequence:03d}'
                    clean=re.sub(r'\s+',' ',sentence).strip()
                    lines.append(sid+'\t'+clean)
                    rows.append(dict(document_id='manuscript',sentence_id=sid,order=order,section_type=section,
                                     section_label=LABELS[section],section_title=LABELS[section],paragraph_id=f'{section_index}-{pi}',
                                     sentence_in_paragraph=si,word_count=len(clean.split()),prose=str(not extractor().NONPROSE.search(clean)).lower()))
        if not rows:
            raise ValueError('분석할 문장이 없습니다')
        (extracted/'manuscript_input.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        with (extracted/'manuscript_structure.tsv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]),delimiter='\t');writer.writeheader();writer.writerows(rows)
        output=directory/'output'
        run_cli('hedge_baseline.py',[extracted,output])
        per=csv_rows(output/'per_paper.csv'); evidence=csv_rows(output/'evidence.csv')
        top=csv_rows(output/'common_verbs.csv')
        return dict(version=VERSION,model=MODEL,model_version=MODEL_VERSION,spacy_version='3.8.11',unit=1000,statistic='median',baseline_name=baseline['name'],input_kind=baseline.get('input_kind','pdf'),baseline_papers=len(baseline['papers']),baseline_excluded=baseline.get('excluded_papers',0),needs_review=baseline.get('needs_review',True),
                    source=baseline['source'],limitations=baseline['limitations'],checks=baseline.get('checks',{}),gate=baseline.get('gate',[]),sections=[dict(section=r['section'],label=LABELS.get(r['section'],r['section']),
                        metrics={k:number(r.get(k)) for k in ('words','hedge','booster','reporting','verbs','hedge_per1000','booster_per1000','reporting_per1000','verbs_per1000')},
                        baseline=baseline['metrics'].get(r['section'],{}),
                        common_verbs=baseline['common_verbs'].get(r['section'],[]),
                        verbs_all={t['lemma']:dict(count=int(t['total']),per1000=number(t['median_per1000'])) for t in top if t['section']==r['section']},
                        top=[dict(lemma=t['lemma'],count=int(t['total']),per1000=number(t['median_per1000'])) for t in top if t['section']==r['section']][:10],
                        evidence=[e for e in evidence if e['section']==r['section']]) for r in per],
                    excluded_nonprose=sum(row['prose']=='false' for row in rows),input_notice='원본 추출기의 문장 분리·NONPROSE 규칙을 원고에도 적용합니다. NMR·원소분석 데이터로 판별된 문장은 분모와 합계에서 제외합니다.')


def generate(directory, name, identifier, created_at):
    import pymupdf
    for path in (directory/'pdf').glob('*.pdf'):
        with pymupdf.open(path) as pdf:
            if len(pdf)<2:
                raise ValueError(f'{path.name}: Stage 1 추출기는 2쪽 이상의 텍스트 연구논문 PDF가 필요합니다')
            if not any(page.get_text().strip() for page in list(pdf)[1:]):
                raise ValueError(f'{path.name}: 본문 텍스트를 찾을 수 없습니다. 스캔 PDF는 OCR이 필요합니다')
    output=directory/'stage1'
    log=run_cli('run_stage1.py',[directory/'pdf',output])
    (output/'run.log').write_text(log,encoding='utf-8')
    run_cli('render_layout.py',[directory/'pdf',output/'1_extract',output/'layout'])
    gate=json.loads((output/'extract_gate.json').read_text(encoding='utf-8'))
    if sum(row['result']=='Pass' for row in gate)<2:
        raise ValueError('추출 품질 검사를 통과한 논문이 2편 미만입니다. 검증 결과를 확인하고 PDF를 다시 구성하세요.')
    baseline=import_baseline(output/'2_baseline',name,identifier,created_at,gate=gate,source_jobs=[directory.name])
    failed=[item for item in baseline['checks'].get('items',[]) if item['result']=='Fail']
    if failed:
        raise ValueError('기준선 처리 검사 실패: '+', '.join(item['check'] for item in failed))
    return baseline
