import csv,hashlib,json,sys
from pathlib import Path
from uuid import uuid5,UUID
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend import stage1
from backend.main import save
OUT=ROOT/'baselines_markdown'
NAMES={'CM':'재료화학','IC':'무기화학','JOC':'유기화학','JPC_C':'물리화학·재료 (JPC C)'}
index=['# 마크다운 기반 4개 분야 기준선','','입력은 CM·IC·JOC·JPC_C 폴더의 기존 마크다운 100편입니다. PDF를 다시 추출하지 않았습니다.','','**규칙 기반 예비 기준선입니다.** 마크다운에서 표 안에 들어간 본문·열 순서 혼합·문장 잘림이 남아 있어 연구용 확정 기준선으로 사용하기 전 원문 검토가 필요합니다. PDF 인용 회수율·레이아웃 검사는 적용하지 않았습니다.','','- 환경: Python 3.12.10, spaCy 3.8.11, en_core_web_sm 3.8.0','- 엔진: hedge-baseline-0.4.4. 문장 분리·비문장 제외·표현 판정은 스킬 코드 사용.','- 집계: 알파벳 토큰 분모, 1,000단어당 중간값과 최소–최대, 섹션별 n. 평균·표준편차를 쓰지 않습니다.','- 25편 전체 검토를 위해 집계 CLI의 입력 편수 검사만 --max-papers 25로 확장했습니다. 집계·판정 규칙은 유지했습니다.','- 누락 섹션은 0건으로 채우지 않았습니다. 각 분야의 markdown_gate.json에 포함/제외 사유를 기록했습니다.','- 공통 동사·헷지·강조·보고동사만 이 스킬의 기준선이며 선행연구 토픽 기준선은 포함하지 않습니다.','','| 분야 | 입력 | 포함 | 제외 | 서론 헷지 /1k · n | 결과·논의 헷지 /1k · n |','|---|---:|---:|---:|---|---|']
summary=[]
for group,name in NAMES.items():
 folder=OUT/group;result=folder/'2_baseline';gate=json.loads((folder/'markdown_gate.json').read_text())
 checks=json.loads((result/'checks.json').read_text());assert not [c for c in checks['items'] if c['result']=='Fail'],group
 passed=[a for a in gate if a['result']=='Pass'];excluded=[a for a in gate if a['result']=='Fail']
 fingerprint=hashlib.sha256(''.join(a['sha256'] for a in gate).encode()).hexdigest()
 identifier=str(uuid5(UUID('83205714-d11b-45e0-bb0d-4371163941be'),group+fingerprint))
 baseline=stage1.import_baseline(result,f'{name} · {group} · 마크다운 기준선',identifier,datetime.now(timezone.utc).isoformat())
 assert len(baseline['papers'])==len(passed)
 baseline.update(input_kind='markdown',group=group,needs_review=True,markdown_gate=gate,input_papers=25,excluded_papers=len(excluded),
                 environment={'python':'3.12.10','spacy':'3.8.11','model':'en_core_web_sm','model_version':'3.8.0'},
                 pdf_quality_gate='not_applicable',input_fingerprint=fingerprint,source_directory=str((ROOT/group).relative_to(ROOT)),
                 adapter='scripts/build_markdown_baselines.py',max_papers_override=25)
 baseline['limitations'][:0]=['마크다운 변환본으로 만든 예비 기준선입니다. PDF 인용 회수율/좌표 품질 검사는 적용하지 않았습니다.','원문 열 순서 혼합과 문장 잘림 가능성이 있으며 사람 검토 완료 기준선이 아닙니다.']
 save(folder/'baseline.json',baseline)
 app=ROOT/'data'/'baselines';app.mkdir(exist_ok=True,parents=True);save(app/(identifier+'.json'),baseline)
 audit=['# '+name+' 마크다운 섹션 점검','','| 논문 | 상태 | 섹션별 단어 수(전처리 근사) | 제외 사유 |','|---|---|---|---|']
 for a in gate:
  audit.append(f"| [{a['document_id']}](../../{a['source']}) | {a['result']} | "+', '.join(f'{k}:{v}' for k,v in a['section_words'].items())+' | '+'; '.join(a['reasons'])+' |')
 audit+=['','표/그림/인용 목록/러닝 헤더로 식별된 블록은 제외했습니다. HTML 위·아래첨자를 정리하고 인용 번호를 [n]으로 전달했습니다. 숫자 역방향 범위(예: 결정축 [10-1])는 인용으로 세지 않도록 괄호 표기를 바꾸고 기록했습니다. 분모는 본문 분석 시 spaCy의 is_alpha로 다시 계산합니다.']
 (folder/'section_audit.md').write_text('\n'.join(audit)+'\n',encoding='utf-8')
 report=result/'baseline_report.md';text=report.read_text();note=f"\n## 마크다운 입력 및 품질 범위\n\n- 입력 25편 중 {len(passed)}편 포함, {len(excluded)}편 제외. 상세: ../markdown_gate.json 및 ../section_audit.md\n- PDF를 재추출하지 않았으며 PDF 인용 회수율 검사는 적용하지 않았습니다.\n- 마크다운의 열 순서 혼합·표로 오인된 본문·문장 잘림 가능성이 있어 연구자 검토 전 예비값입니다.\n"
 if '## 마크다운 입력 및 품질 범위' in text:text=text.split('## 마크다운 입력 및 품질 범위')[0].rstrip()+'\n'
 report.write_text(text+note,encoding='utf-8')
 def describe(sec):
  d=baseline['metrics'].get(sec,{}).get('hedge_per1000')
  return f"{d['median']} ({d['min']}–{d['max']}), n={d['n']}" if d else '확인 불가'
 index.append(f'| [{name}](./{group}/2_baseline/baseline_report.md) | 25 | {len(passed)} | {len(excluded)} | {describe("INT")} | {describe("RD")} |')
 summary.append(dict(group=group,name=name,id=identifier,included=len(passed),excluded=len(excluded),source_sha256=fingerprint))
index+=['','## 파일 구성','','분야별 폴더의 `2_baseline/`에 보고서, baseline.csv, per_paper.csv, common_verbs.csv, evidence.csv, checks.json이 있습니다. `baseline.json`은 앱에 등록한 JSON과 동일합니다. `1_markdown_input/`은 스킬에 전달한 표준 문장 TXT·구조 TSV입니다.','','JPC_C 일부 논문은 결과(RES)와 논의(DIS)가 분리되어 있어 별도 행으로 집계됩니다. RD 행은 해당 통합 섹션이 있는 논문만 포함하므로 분야 전체 편수와 n이 다를 수 있습니다.','','마크다운 구조가 불명확한 제외 논문을 PDF로 보완하거나 임의로 본문을 추정해 포함하지 않았습니다.']
(OUT/'README.md').write_text('\n'.join(index)+'\n',encoding='utf-8')
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
for entry in summary:
 folder=OUT/entry['group'];baseline=json.loads((folder/'baseline.json').read_text())
 baseline['source_hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((folder/'2_baseline').iterdir()) if p.is_file()}
 save(folder/'baseline.json',baseline);save(ROOT/'data'/'baselines'/(entry['id']+'.json'),baseline)
manifest={str(p.relative_to(OUT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='hashes.json' and p.suffix!='.log'}
(OUT/'hashes.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
assert all(hashlib.sha256((OUT/p).read_bytes()).hexdigest()==digest for p,digest in json.loads((OUT/'hashes.json').read_text()).items())
print(json.dumps(summary,ensure_ascii=False,indent=2))
