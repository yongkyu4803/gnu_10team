---
name: section-verb-hedge-baseline
description: 이공계(화학 등) 연구논문 PDF 2~10편 묶음에서 본문을 문장 단위로 추출하고, 서론·실험·결과·논의·결론 절마다 동사 분포, 헷지(완곡 표현), 비헷지(강조 표현), 선행연구 보고동사의 1,000단어당 빈도를 세어 중간값과 범위의 기준선(Stage 1)을 만든다. "논문 묶음에서 섹션별 동사·헷지 기준선 만들어 줘", "이 논문들 헷지 비율 비교해 줘", "Stage 1 기준선" 같은 요청에 사용한다. Use for section-level hedge, booster and reporting-verb baselines from a small bundle of research-article PDFs.
argument-hint: [PDF 폴더 경로] [출력 폴더 경로]
---

# 섹션별 동사·헷지 기준선 (Stage 1)

값은 스크립트가 센다. 모델은 근거 문장을 보고 해석만 한다. 모든 숫자에는 근거 문장(evidence.csv)이 있어야 한다.
이 스킬의 규칙은 무기화학(Inorganic Chemistry 2010~2015) 5편을 실제로 처리하며 난 오류에서 나왔다.

## 준비 (처음 한 번)
- **Python 3.12**를 쓴다. Python 3.14에서는 spaCy 3.8이 동작하지 않는다(pydantic v1 호환 문제). Windows는 `py -3.12`로 부른다.
- 패키지: `python -m pip install -r requirements.txt` 뒤 `python -m spacy download en_core_web_sm`
- **pdftotext는 poppler**를 쓴다(Windows: `winget install oschwartz10612.Poppler`). xpdf의 pdftotext가 PATH에서 먼저 잡히면 참고문헌 수가 틀리므로, `run_stage1.py`가 첫머리에서 멈추고 알려 준다. pdftotext가 없으면 pdfplumber로 대신 센다.
- 한국어 Windows(cp949) 인코딩은 스크립트가 UTF-8로 고정한다(pdf-extract-0.4.7). `python -X utf8`을 따로 붙이지 않아도 된다.
- 실행 첫머리에 `환경: Python 3.12.x, pdftotext version 25.x` 한 줄이 나오는지 본다.

## 실행 순서
1. **입력 확인**: PDF 폴더에 연구논문 2~10편이 있는지 본다. 원본은 수정하지 않는다. 읽지 못한 파일은 목록으로 남긴다.
2. **한 번에 실행**: `python scripts/run_stage1.py <PDF 폴더> <출력 폴더>`
   - `1_extract/`: 논문마다 문장 TXT, 구조 TSV(절·문단·쪽·prose), 확인 목록(`_review.csv`), 보고서(`_report.json`), 줄 위치(`_layout.json`, 검증 그림용)
   - `extract_gate.json`: 추출 품질 검사. 기준을 넘지 못한 논문은 기준선에서 자동으로 빠진다.
   - `2_baseline/`: `baseline_report.md`, `baseline.csv`, `per_paper.csv`, `common_verbs.csv`, `evidence.csv`, `checks.json`
3. **추출 품질 확인**: `extract_gate.json`에서 Fail인 논문이 있으면 그 논문의 `_review.csv`와 원문 PDF를 대조한 뒤 사용자에게 알린다. 기준은 다음과 같다.
   - 인용 번호 회수(참고문헌 번호 중 본문에서 인용으로 복원된 비율) 95% 이상
   - 끝이 열린 문장 5% 이하
   - 여백 문구(Downloaded from … 기관명) 누출 0
   - **검증 그림**: `python scripts/render_layout.py <PDF 폴더> <출력 폴더>/1_extract <그림 폴더>`로 쪽 그림 위에 초록(노랑 테두리), 절 제목(빨강 테두리), 절별로 센 본문 줄(서론 파랑, 실험 초록, 결과·논의 주황, 결론 보라)을 그린다. `index.html`로 모아 본다. 새 저널·연도에서는 Pass여도 한 번은 그림으로 절 경계를 확인한다.
4. **기준선 읽기**: `baseline_report.md`의 표를 그대로 옮기고, 눈에 띄는 값은 `evidence.csv`에서 문장 2~3개를 찾아 함께 제시한다.
5. **보고**: 관찰과 가설을 나누어 쓴다(아래 금지 규칙). 사용자가 Stage 2(내 논문 대조)를 원하면 이 기준선 파일을 그대로 넘긴다.

## 지표
| 지표 | 세는 것 | 분모 |
|---|---|---|
| 헷지 | 조동사 may·might·could·would·should, that절을 거느린 suggest·indicate·assume·claim 등, appear·seem + to/that, possibly·probably 등, possible·likely 등, in general·to my knowledge 같은 여러 낱말 표현 | 절의 단어 수(실험 절 제외) |
| 비헷지(강조) | demonstrate·prove·establish, that절을 거느린 know·believe·think·realize, clearly·indeed·obviously 등, clear·evident, in fact·of course 같은 여러 낱말 표현 | 같음 |
| 보고동사 | 분석 엔진(engine_local)이 '선행연구 보고'로 판정한 표현 | 절의 단어 수 |
| 동사 분포 | 품사가 VERB인 낱말의 기본형 | 절의 단어 수 |
| 확인 후보(합계 제외) | can, 어림말(about·approximately + 숫자), 정도·빈도 부사(relatively·often 등), must, show·find·estimate, apparent·typical, Hyland 부록에 없는 팀 추가 낱말(confirm·propose 등), 문맥 오판 규칙에 걸린 표현(could = 실험으로 해냄, "It should be noted", "proved to be", "a clear shell" 등, `review:rule_*`) | — |

헷지·비헷지 낱말은 Hyland (2005) *Metadiscourse* 부록(pp. 218-223)을 따른다. 목록과 판정 조건, Hyland와 다르게 다룬 항목과 그 이유는 `references/hedge_lexicon.md`에 있다. 목록을 바꾸면 그 파일과 스크립트를 같이 고치고 버전을 올린다.

## 금지 규칙
1. **prose=false 문장(NMR·원소분석 데이터)은 세지 않는다.** 구조 TSV의 `prose` 열을 따른다.
2. **헷지·비헷지는 실험 절을 분모에서 뺀다.** 실험 절의 동사 분포와 보고동사는 따로 보고한다.
3. **낱말만 보고 헷지로 세지 않는다.** 화학 논문에서는 문자 그대로 쓰이는 경우가 많다. (사례: "absorption appearing at 390 nm", "triplet energies, indicated as ET", "the proposed structures", "it is possible to distinguish", "partially blocking ligands" — 모두 헷지가 아님)
4. **선행연구 보고와 겹치면 헷지로 세지 않는다.** (사례: "He et al. proposed that …"은 보고동사로만 센다)
5. **can, 어림말, 정도 부사는 합계에 넣지 않는다.** 확인 후보로 따로 둔다.
6. **기준선은 중간값과 범위(최솟값~최댓값)로만 쓴다.** 평균, 표준편차, 통계 검정을 쓰지 않는다. 표본이 10편 이하이기 때문이다.
7. **경향을 단정하지 않는다.** "결과·논의의 헷지는 1,000단어당 중간값 3.1(2.34~10.95)"처럼 관찰로 쓰고, 이유는 가설로 표시한다.
8. **편수가 다른 절을 같은 무게로 비교하지 않는다.** 절마다 편수(n)를 함께 적는다. 결론이 짧은 논문(100단어 안팎)의 값은 크게 흔들린다는 점을 적는다.
9. **추출 품질 검사에서 Fail인 논문을 말없이 섞지 않는다.** 뺐는지, 넣고 경고했는지 보고서에 적는다.
10. **확인하지 못한 값은 "확인 불가"로 적는다.** 채우지 않는다.
11. 수정한 파일은 저장 후 다시 열어 확인하고, 해시를 대조하기 전에는 "저장했다"고 보고하지 않는다.

## 다른 저널·분야로 넓힐 때
- 첫 실행에서 `1_extract/*_report.json`의 `body_size`(본문 글자 크기), `main_font`, `by_section`(절별 문장 수)이 그 저널에 맞는지 먼저 본다.
- ACS는 실험 절을 본문보다 한 단계 작은 글자(9 pt)로 조판한다. 다른 출판사도 실험 절이 빠지면 이 점을 의심한다.
- 절 제목이 다른 이름(예: "Materials and Methods", "Results")이면 `scripts/extract_pdf.py`의 `HEAD_RE`와 `TYPE`에 더한다.
- 저자-연도식 인용(Smith, 2012)은 지금 보고동사 판정과 인용 회수 검사가 다루지 못한다.
- 번호가 붙은 절 제목("1. INTRODUCTION", CM 일부)과 ■ 표시가 붙은 제목을 모두 알아본다(pdf-extract-0.4.4).
- DISCUSSION 절이 따로 없고 RESULTS 절만 있는 논문은 RESULTS에서 해석도 함께 하므로 결과·논의(RD)로 묶어 센다. 묶은 논문은 `checks.json`과 보고서의 처리 검사에 적힌다(hedge-baseline-0.4.1).
- 인용 회수가 낮으면 `_report.json`의 `never_cited`를 본다. 범위 인용(13−15)의 가운데 번호만 빠져 있으면 줄표 글리프가 `(cid:n)`으로 나오는 경우다. 그 글꼴을 `FONT_MAP`에 더한다(cm1031656의 AdvP4C4E74 `(cid:1)` 사례).
- 실험 절이 긴 논문은 실험 절의 작은 글자(9 pt)가 본문 글자(10 pt)보다 많을 수 있다. 가장 많은 두 크기가 비슷하게 많고 0.5~1.5 pt 차이 나면 큰 쪽을 본문으로 본다(jo2012384, pdf-extract-0.4.5). 본문 크기는 `_report.json`의 `body_size`로 확인한다.
- 계산화학 논문의 "COMPUTATIONAL DETAILS/METHODS" 절은 실험·방법(MET)으로 센다.
- 2010년 무렵 JOC처럼 "ABSTRACT:" 표시 없이 Received 줄 아래에 초록이 있고 초록 글자가 본문과 크기가 다르면, 그 영역에서 가장 많은 글꼴로 초록을 잡는다(jo902004n).
- 실험 절에서 굵은 화합물 이름으로 시작하는 줄("2-Hydroxy-…adamantane (10a):39 2.29 g")은 본문 글꼴의 굵은체도 본문으로 쳐서 살린다. 줄 첫 글자가 굵은체일 때만이다(pdf-extract-0.4.6). 이 줄에 붙은 인용 번호가 빠지면 인용 회수가 떨어진다(jo902004n 93%→100%).
- 2010년 무렵 ACS 쪽 머리글("Inorganic Chemistry, Vol. 49, No. 5, 2010", "2048 Yang et al.")은 본문에서 뺀다. 굵은 쪽 번호로 시작해 본문으로 섞이면 쪽 경계에서 문장이 끊기고 끝이 열린 문장이 늘어난다(ic901600v).

## 알려진 한계 (pdf-extract-0.4.7, hedge-baseline-0.4.4)
- 문맥 오판 규칙은 IC·CM·JOC 448건 전부를 보고 만들었다(0.4.4). 따로 남겨 둔 시험 자료가 없으므로, 새 묶음에서는 규칙을 믿기 전에 표본 대조로 오판률을 확인한다. 편수가 5~6편이라 1건 차이로 중간값이 크게 움직일 수 있다.
- 부정·정도 수식이 붙은 강조 형용사·부사("is less clear", "It is not clear whether")는 강조에서 빼 확인 후보로 둔다(0.4.3). 헷지로 옮기지는 않는다. 부정된 강조 동사("do not clearly demonstrate"의 demonstrate)는 아직 강조로 센다.
- 문맥 오판 규칙(0.4.2, `references/hedge_lexicon.md`)은 CM·JOC 315건 대조에서 나온 유형만 다룬다. "could be found", 선행연구를 전하는 "It was suggested that", 요건을 말하는 should("polymers should exhibit")는 아직 헷지로 센다. 새 분야에서는 `evidence.csv`에서 낱말별로 20~30건을 읽어 오판률을 먼저 본다.
- 2010·2011년 PDF에는 원래 기호를 알 수 없는 글리프(`(cid:n)`)가 일부 남는다. 같은 `(cid:1)`도 글꼴에 따라 줄표일 때와 도(°) 기호일 때가 있어, 글꼴별로만 바꾼다.
- 대괄호 안에 0으로 시작하는 번호([047−1748], ICDD 번호)는 인용으로 보지 않는다.
- 두 줄에 걸친 끼움 소제목 일부가 잘린다. 실험 절의 화합물 이름 소제목은 문장 하나로 남는 경우가 있다(실험 절은 헷지 분모에서 빠지므로 헷지 값에는 영향 없음).
- 추출 결과는 사람이 원문과 대조하지 않은 자동 결과다(needs_review: true).
- 영어 모델(en_core_web_sm)은 일반 영어로 학습되어 화학 문장의 구문 분석이 틀릴 수 있다. 헷지 판정의 구조 조건도 이 분석에 기댄다.

## 예시 결과
`examples/IC_2010-2015_5편/`에 무기화학 5편으로 돌린 결과가 있다.
