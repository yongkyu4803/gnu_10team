# 논문 글쓰기 진단

FastAPI + 프로젝트 루트의 JSON 파일로 동작하는 로컬 웹앱입니다. `GNU_AI_Team`의 `hedge-verb-sections`와 `litreview-structure` 분석 코드를 함께 사용합니다.

## 문서

앱 상단 **문서** 메뉴(`/guide`)에서 같은 문서를 읽을 수 있습니다. 개발자용 API 문서(`/docs`)는 별도로 유지합니다.

[전체 문서 목차](docs/README.md)에서 프로젝트 구조·화면 사용, 두 원본 저장소의 분석 방법, 현재 네 분야 기준선, 기준 업데이트·복원 절차, API·배포·데이터 보관을 확인할 수 있습니다.

## 실행

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m spacy download en_core_web_sm
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

화면: http://127.0.0.1:8001 · API 문서: http://127.0.0.1:8001/docs

## 사용 순서

1. 원고를 섹션별로 입력하거나 전체 원고를 헤딩으로 나눕니다. TXT·DOCX·텍스트 PDF를 불러올 수 있습니다.
2. 출판 논문과 비교하려면 아래 PDF 분석에서 같은 분야 논문을 업로드합니다.
3. 추출된 섹션·참고문헌 상태를 확인하고 동사·헷지 및 선행연구 후보를 검토합니다. 연구자 판정은 JSON에 저장됩니다.
4. 완료된 작업의 체크박스를 고르고 분야 기준선 이름을 입력해 기준선을 생성합니다. 같은 PDF는 SHA-256으로 중복 제거됩니다.
5. 위쪽 분야 메뉴에서 기준선을 선택하고 원고를 진단합니다. 분야별 동사 상위 10개, 겹침·희귀 동사, 헷지 평균·범위, 선행연구 토픽·문헌·인용 기능을 비교합니다.
6. PDF 작업의 엑셀 다운로드는 현재 JSON 판정을 반영해 통계를 재계산합니다. 동사·선행연구 엑셀을 각각 제공합니다.

원고 자체 진단에서도 헷지 판정, 서론 토픽, 토픽 조직, 결과·논의 인용 기능을 수정·저장할 수 있습니다.

## 계산과 범위

- spaCy `en_core_web_sm`으로 lexical VERB를 추출합니다. AUX는 제외하고 원형으로 합칩니다. 브라우저와 기준선에 같은 분석기를 적용합니다.
- 분야 동사 순서는 출현 논문 수 → 논문별 /10k 빈도 평균 → 동사 이름 순입니다. 평균·범위는 논문별 값 기준입니다.
- 누락되거나 텍스트가 없는 섹션은 분야 동사·헷지 비교에서 제외합니다. PDF 작업에 추출 섹션과 미인식 섹션을 표시합니다.
- 헷지는 연구자 > 검토 > 자동 순으로 집계하며 U는 제외합니다. 자동 판정은 문맥 검토 전 예비판정입니다.
- 선행연구는 번호식 인용 `[1–3]`, `[3a,b]`, `⟦c:1–3⟧`와 ACS PDF 위첨자를 지원합니다. 저자-연도 인용은 자동 집계하지 않습니다.
- 자동 토픽은 문단 단위입니다. 의미 토픽과 조직 유형은 연구자가 수정해야 합니다. `(제외)`로 시작하는 토픽은 토픽 통계에서 제외합니다.
- 기준선은 생성 시점 판정의 스냅샷입니다. 판정을 수정하면 기준선을 다시 생성해야 합니다. 미검토 헷지 후보 수와 출처 작업 ID도 JSON에 보존합니다.
- 원본 레포에는 README에 언급된 16편의 PDF·엑셀·완성 기준 데이터가 없습니다. 앱에 그 수치를 임의로 넣지 않았습니다. 출판 논문을 업로드해 기준선을 생성해야 비교값이 표시됩니다.
- OCR은 지원하지 않습니다. PDF 자동 섹션 추출은 ACS 서식 중심이며 다른 서식에서는 반드시 추출 결과를 확인하세요.

## 저장 위치

서버 실행 디렉터리와 관계없이 이 README가 있는 프로젝트 루트의 `data/`를 사용합니다. 외부 DB는 사용하지 않습니다.

```
data/
  jobs/<UUID>/
    job.json              # 상태·원본 파일명·추출 점검
    candidates.json       # 헷지 후보·연구자 판정
    literature.json       # 인용 문장·토픽·조직·인용 기능 판정
    pdf/                  # 업로드 PDF
    corpus/               # 동사용 본문 JSON
    citation_corpus/      # 인용 표지를 보존한 본문 JSON
    result.xlsx           # 최초 동사 분석
    literature.xlsx       # 최초 선행연구 분석
    baseline_lit.json     # 원본 litreview baseline 명령 결과
  manuscripts/<UUID>.json # 원고 입력·분석·수정 판정
  baselines/<UUID>.json   # 분야 기준선·출처·논문별 지표
```

JSON은 임시 파일과 원자적 교체로 저장합니다. PDF 분석은 별도 프로세스에서 한 작업씩 처리합니다. 단일 서버 프로세스 전용이므로 `--workers`를 늘리지 마세요. 재시작 시 중단 작업은 failed로 표시되며 다시 업로드할 수 있습니다.

## 검증

```sh
.venv/bin/python -m unittest discover -s tests -v
node --check frontend/app.js
```

통합 검증은 임시 디렉터리와 합성 PDF를 사용합니다. 원고 분석, 인용 범위 확장, 토픽 병합·조직 판정, 인용 기능 수정, 헷지 수정·재집계, TXT/DOCX/PDF 불러오기, PDF 작업, 판정의 엑셀 반영, 기준선 생성·비교를 확인합니다. 실제 논문의 추출 정확도를 보증하는 테스트는 아닙니다.

## Stage 1 기준선 엔진 추가

`section-verb-hedge-baseline/` 레포를 통합했습니다. 서버 시작 시 포함된 `examples/IC_2010-2015_5편` CSV를 프로젝트 루트 `data/baselines/`의 JSON으로 등록합니다. 파일별 SHA-256, 원본 출처, 엔진 버전, 모델, 단위, 추출 품질 검사 결과를 보존합니다. JSON 저장 후 다시 읽어 SHA-256을 검증합니다.

분야 메뉴의 **무기화학 · IC 2010–2015 · Stage 1**을 선택하면 즉시 비교할 수 있습니다.

- 원고는 표준 문장 TXT·구조 TSV로 변환한 뒤 원본 `hedge_baseline.py` CLI로 분석합니다. 임의의 유사 규칙으로 다시 구현하지 않습니다.
- 기준선과 원고 모두 `spaCy 3.8.11`·`en_core_web_sm 3.8.0`, 알파벳 토큰 분모, 1,000단어당 빈도를 사용합니다. 대표값은 중간값과 범위이며 섹션별 n을 표시합니다.
- 헷지뿐 아니라 강조 표현, 선행연구 보고동사, review 범주와 문장별 근거를 표시합니다. 실험·방법은 헷지와 강조 비율에서 제외합니다. 1쪽 PDF와 본문 텍스트 없는 PDF는 원본 추출기의 적용 범위 밖이므로 명확한 오류로 안내합니다.
- 공통 동사 CSV는 절반 이상 논문에 출현한 동사만 담습니다. 미수록 동사는 출현 0건으로 표시하지 않으며, 정확한 희귀도도 추정하지 않습니다.
- 입력 원고에도 원본 추출기의 문장 분리와 NONPROSE 규칙을 적용합니다. NMR·원소분석 데이터로 판별된 문장은 집계에서 제외합니다. 공유를 위해 원본 `extract_pdf.py`의 중첩 `split_sents` 함수만 모듈 함수로 이동했으며 규칙 본문은 바꾸지 않았습니다.
- 예시 `evidence.csv`는 원저작자가 문장 본문을 비워 공개했습니다. 새로 입력한 원고의 근거 문장은 실제 엔진 출력으로 제공합니다.
- Stage 1 기준선에는 선행연구 토픽 기준값이 없습니다. 세 번째 탭은 기존 선행연구 엔진으로 원고 자체를 분석하며 비교값은 비워 둡니다.

새 기준선은 PDF 영역에서 **Stage 1 기준선 생성**을 선택하고 이름과 PDF 2~10편을 입력하면 됩니다. 원본 `run_stage1.py`를 별도 프로세스에서 실행해 인용 회수 95% 이상·열린 문장 5% 이하·여백 누출 0 기준으로 검사합니다. 통과 논문이 2편 미만이면 등록하지 않습니다. 추출 보고·근거 CSV·검사 결과와 `render_layout.py`로 만든 절 경계 검증 그림(`layout/index.html`)은 작업의 ZIP 다운로드에 포함됩니다. Fail 논문은 기준선에 섞지 않습니다.

새 PDF 생성은 ACS 중심 자동 추출이므로 원문·추출 보고를 확인해야 합니다. Poppler `pdftotext`가 없으면 원본 스킬의 pdfplumber 경로를 사용합니다. xpdf가 먼저 검색되면 원본 스킬이 중단합니다. 원본은 Python 3.12를 권장하며 현재 프로젝트의 Python 3.13 환경에서는 포함 기준선과 원고 CLI 분석을 검증했습니다.

기존 평균·/10k 기준선은 별도 모드로 유지합니다. 서로 다른 방법의 지표를 섞어 비교하지 않습니다.

## 포함된 마크다운 기준선

CM·IC·JOC·JPC_C 각 25편의 마크다운과 기준선 생성 결과를 포함합니다. 앱은 첫 실행 시 `baselines_markdown/*/baseline.json`을 로컬 JSON 저장소에 등록하며, 기본 비교는 JOC 마크다운 기준선입니다. 입력 100편 중 82편이 포함되었고 18편은 구조 문제로 제외되었습니다. [전체 기준선 보고서](baselines_markdown/README.md)를 확인하세요. 이 기준선은 원문 읽기 순서 등의 검토가 남은 예비값입니다.

ZIP·원본 PDF·가상환경·런타임 데이터는 Git에 포함하지 않습니다. 기준선은 기존 마크다운으로 다시 생성할 수 있습니다.

```sh
python3.12 -m venv .venv-baseline
.venv-baseline/bin/pip install -r requirements.txt
.venv-baseline/bin/python -m spacy download en_core_web_sm
.venv-baseline/bin/python scripts/build_markdown_baselines.py
# 분야별 CM, IC, JOC, JPC_C에 반복
.venv-baseline/bin/python section-verb-hedge-baseline/scripts/hedge_baseline.py baselines_markdown/CM/1_markdown_input baselines_markdown/CM/2_baseline --max-papers 25
.venv-baseline/bin/python scripts/finalize_markdown_baselines.py
```

분석 코드 출처:
- GNU_AI_Team: https://github.com/jyoon0319/GNU_AI_Team (기반 커밋 `5ff9e9b`, 프로젝트 통합을 위한 수정 포함)
- section-verb-hedge-baseline: https://github.com/angela0420/section-verb-hedge-baseline (기반 커밋 `b5e8a68`, 문장 분리 함수 공유와 입력 편수 옵션 수정 포함)

## 관리자 페이지

주소: http://127.0.0.1:8001/admin (진단 화면의 **기준 관리** 링크)

첫 실행 시 `data/admin/initial_password.txt`에 생성되는 비밀번호로 로그인합니다. 비밀번호 해시와 세션 서명 키는 `data/admin/credentials.json`에 보관되며 두 파일은 현재 사용자만 읽을 수 있습니다. 로그인은 8시간 동안 유지됩니다. 이름은 변경 이력에 남길 작업자 이름입니다. 단일 로컬 관리자용 비밀번호 방식입니다.

- **현재 기준 · 버전:** 네 분야의 적용 버전, 포함·제외 논문 수, 섹션별 중간값·범위를 확인합니다.
- **자료 선택 · 재계산:** 프로젝트의 분야별 마크다운에서 분석할 문서를 고르고 이름·변경 사유·최소 본문 길이(1,000단어 이상)를 지정합니다. 현재 엔진의 단위·통계·헷지 규칙은 유지합니다.
- 재계산은 선택한 마크다운과 분석 코드의 사본 및 SHA-256을 보존한 뒤 별도 프로세스로 실행합니다. 결과의 n·중간값·최소·최대를 다시 계산해 검증하고 새 버전을 만듭니다. 현재 적용 기준은 자동으로 바뀌지 않습니다.
- 버전 **미리보기**에서 포함 논문 변화와 구조 검사 결과를 확인하고 **이 버전 적용**을 누릅니다. 적용 사유를 입력하면 현재 기준과 이력이 하나의 JSON 저장으로 함께 갱신됩니다.
- 이전에 적용했던 버전은 **이 버전으로 복원**할 수 있습니다. 누가 언제 어떤 사유로 어느 버전에서 변경했는지 남습니다. 동시에 다른 관리자가 기준을 바꾸면 적용 요청을 거절하고 새로고침을 요구합니다.
- 실패한 작업도 사유와 로그를 남기며 현재 기준을 바꾸지 않습니다. 작업 ZIP에는 입력 마크다운·규칙 사본·문장 입력·CSV·검사 결과·로그가 포함됩니다.
- 진단 화면은 현재 적용된 버전만 기본 선택 목록에 표시합니다. 이미 열려 있던 화면이 이전 기준으로 새 진단을 요청하면 새로고침하도록 안내합니다. 저장된 과거 진단 결과와 이전 버전은 보존됩니다.
- 재계산한 기준의 규칙 해시와 원고 분석기의 규칙 해시가 달라지면 비교를 중단하고 새 규칙으로 기준선을 재계산하도록 안내합니다.

관리자 상태는 프로젝트 루트 아래에 저장합니다.

```
data/admin/
  credentials.json       # 비밀번호 해시·서명 키 (Git 제외)
  initial_password.txt   # 최초 로그인 비밀번호 (Git 제외)
  registry.json          # 분야별 적용 버전·버전 목록·변경 이력
  versions/<UUID>.json   # 보관된 기준값 스냅샷
  jobs/<UUID>/           # 작업 상태·입력·규칙 사본·분석 결과·로그
```

관리자 API는 로그인 쿠키(HttpOnly·SameSite=Strict), 동일 출처 검사, 로그인 시도 제한을 사용합니다. `data/`는 기존처럼 Git에서 제외됩니다. 같은 `data/` 파일이 남아 있는 로컬 환경이나 영구 디스크 환경에서는 재시작 후에도 적용 기준·이력·버전이 유지되며, 중단된 재계산은 실패로 기록됩니다. Render의 임시 파일시스템에서는 이 보존을 보장하지 않습니다.

## Render 배포

프로젝트 루트에 `.python-version`(Python 3.12)과 `render.yaml`을 포함했습니다. 기존 Web Service의 설정은 파일 추가만으로 자동 변경되지 않으므로 Render의 Settings에서 다음을 지정하세요.

- Root Directory: 비워 둠(저장소 루트)
- Build Command: `bash scripts/render-build.sh`
- Start Command: `python -m uvicorn backend.main:app --host 0.0.0.0 --port $PORT --workers 1`
- Health Check Path: `/api/health`
- `PYTHON_VERSION` 환경변수가 3.14로 지정되어 있다면 삭제하여 `.python-version`을 사용하거나, 사용 가능한 Python 3.12 패치 버전으로 지정합니다.

`gunicorn app:app`은 이 프로젝트의 시작 명령이 아닙니다. 앱 진입점은 `backend.main:app`이며, 빌드 단계에서 분석 모델 `en_core_web_sm 3.8.0`을 설치합니다.

관리자 최초 비밀번호는 Render Shell에서 `cat data/admin/initial_password.txt`로 확인할 수 있습니다. 기준 변경 이력·버전·업로드는 `data/`에 기록하므로 재배포 후에도 유지하려면 이 경로에 영구 디스크를 연결해야 합니다. 기본 로컬 저장 경로는 변경하지 않았습니다.

배포 설정, 무료 플랜의 데이터 소실 범위, 영구 저장 전환과 백업 방법은 [Render 배포 및 데이터 보관 안내](docs/render-deployment.md)를 참고하세요.
