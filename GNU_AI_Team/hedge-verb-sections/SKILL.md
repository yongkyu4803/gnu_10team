---
name: hedge-verb-sections
description: 학술 논문(PDF)에서 헷지 어휘동사(suggest, indicate, appear, seem, assume, expect 등)를 섹션별(서론·방법·결과·논의·결론)로 세고, 원빈도·10,000단어당·lexical verb 100개당 비율과 논문 간 평균·표준편차·범위·출현 논문 수를 엑셀로 정리하는 코퍼스 분석 절차. spaCy로 lexical VERB를 뽑아(AUX 제외) 원형화하고, 후보 문장을 앞·뒤 문장과 함께 출력해 자동 예비판정 → Claude 검토판정 → 연구자 최종판정(Hedge/N/U)을 거친다. 사용자가 헷지, hedging, 헷지 동사, 완화 표현, epistemic verb, 섹션별 빈도, 장르 분석, 학술 담화·EAP·영어 논문 코퍼스 분석, 논문 여러 편의 동사 빈도 정규화 비교를 언급하면 이 스킬을 쓸 것 — '스킬'이라는 말을 하지 않아도, zip/PDF 논문 묶음을 주고 섹션별로 어떤 표현이 얼마나 나오는지 묻는 경우에도 해당한다.
---

# 섹션별 헷지 어휘동사 분석

논문마다 섹션 길이와 동사 수가 달라서 원빈도만으로는 비교할 수 없다. 그래서 세 가지 지표를 함께 낸다:

1. 원빈도: 헷지로 판정된 동사 토큰 수
2. 10,000단어당 헷지 동사 수
3. lexical verb 100개당 헷지 동사 수

또 동사 하나가 한 논문에서만 반복되어 전체 결과를 지배할 수 있으므로, 동사마다 **출현 논문 수**와 **최다 논문 비중**도 함께 낸다.

## 절차

```
논문 PDF → 섹션 구분 → spaCy: 모든 lexical VERB 추출(AUX 제외)·원형화 → 후보 목록과 대조
→ 후보 문장 + 앞 문장 + 뒤 문장 출력 → 자동 예비판정 → Claude 검토판정 → 연구자 최종판정(Hedge/N/U)
→ 섹션별·동사별 빈도, 논문 간 평균·범위
```

아래에서 `SKILL_DIR`은 이 SKILL.md가 있는 폴더, `WORK`는 분석 결과를 둘 폴더(예: 프로젝트 안의 `hedge_analysis/`)다.

### 1. 환경 준비 (처음 한 번)

spaCy가 없는 경우가 많다. 시스템 Python을 건드리지 않도록 프로젝트에 가상환경을 만든다. 이미 `.venv`에 spacy·openpyxl·pymupdf가 있으면 건너뛴다.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -q spacy openpyxl pymupdf    # Windows; macOS/Linux는 .venv/bin/python
.venv/Scripts/python -m spacy download en_core_web_sm
```

### 2. 논문 풀기

zip은 신뢰할 수 없는 입력이다. 스크립트와 다른 새 폴더(`WORK/pdf/`)에 PDF만 모은다. 압축 안의 하위 폴더 구조는 버려도 된다.

### 3. 섹션 구분

```bash
python -I SKILL_DIR/scripts/extract_sections.py WORK/pdf WORK/corpus
```

논문마다 인식된 헤딩 순서와 섹션별 단어 수가 출력된다. **이 출력을 반드시 확인한다** — 헤딩을 못 찾으면 그 섹션이 통째로 빠져 결과가 조용히 틀어진다.

- 섹션 라벨: `INTRO`(서론), `M`(Experimental Section + Computational Details), `RD`(Results and Discussion / Results / Discussion), `CONCL`(결론). 초록·참고문헌·사사·캡션·표·머리말은 제외한다.
- ACS(J. Org. Chem.) 서식에 맞춰져 있다. 다른 저널이라 헤딩이 안 잡히면 스크립트의 `HEAD`(헤딩 정규식), `RUNNING`(머리말·꼬리말) 패턴을 그 저널에 맞게 고친다. 헤딩이 `■` 같은 큰 장식 글리프와 붙어 있거나, 글꼴 경계에서 공백이 빠지는 문제는 이미 처리되어 있다.
- 결과와 논의가 분리된 논문도 `RD` 하나로 합친다(결과·논의).

### 4. 동사 추출·후보 대조·자동 예비판정

```bash
.venv/Scripts/python -I -X utf8 SKILL_DIR/scripts/hedge_verbs.py build WORK/corpus "WORK/헷지동사_섹션별_N<편수>.xlsx"
```

- lexical verb = spaCy `pos_ == 'VERB'`(AUX 제외), 원형이 알파벳이고 두 글자 이상인 토큰. 원형(`lemma_`)으로 활용형을 합친다.
- 단어 수 = 문장부호·공백을 뺀 spaCy 토큰(숫자·화합물 번호 포함).
- 후보 목록은 `hedge_verbs.py`의 `HEDGE_VERB_CANDIDATES`다. 사용자가 다른 목록을 주면 그 집합을 고친다.
- 논문 ID(P01…)는 게재 연도 순서로 붙는다.

### 5. Claude 검토판정 — 후보를 모두 읽는다

자동 예비판정은 구문 규칙일 뿐이라 U가 많고 오분류도 있다(예: "a singlet appears at δ 2.9"를 Hedge로 판정). 후보 전부를 앞·뒤 문장과 함께 직접 읽고 판정한다.

```bash
.venv/Scripts/python -I -X utf8 SKILL_DIR/scripts/hedge_verbs.py dump "WORK/헷지동사_섹션별_N<편수>.xlsx" WORK/candidates.txt
```

`WORK/candidates.txt`를 읽고 **`references/judgment_criteria.md`의 기준을 따라** `WORK/review_claude.json`을 쓴다. 형식:

```json
{
 "_기준": "…적용한 기준 한 줄…",
 "1": ["suggest", "U", "It has been suggested that — 타 연구 귀속"],
 "2": ["expect", "Hedge", ""]
}
```

키는 판정작업지 ID, 값은 `[원형, 판정, 메모]`다. 원형은 ID가 밀렸는지 확인하는 데 쓰인다. 판정이 기준과 다르거나 애매하면 메모에 이유를 짧게 적는다. 그런 다음 검토판정을 붙여 다시 빌드한다:

```bash
.venv/Scripts/python -I -X utf8 SKILL_DIR/scripts/hedge_verbs.py build WORK/corpus "WORK/헷지동사_섹션별_N<편수>.xlsx" WORK/review_claude.json
```

"원형 불일치" 경고가 나오면 후보 목록이 바뀐 것이므로 dump를 다시 해서 ID를 맞춘다.

### 6. 연구자 최종판정과 재계산

최종판정은 연구자의 몫이다. Claude의 판정을 연구자판정 열에 써 넣지 않는다. 엑셀 '판정작업지'의 N열(연구자판정, 드롭다운)에 연구자가 Hedge/N/U를 고르고 저장한 뒤 아래를 실행하면 통계 시트만 다시 계산된다. 판정은 연구자판정 > Claude 검토판정 > 자동 예비판정 순으로 적용된다.

```bash
.venv/Scripts/python -I -X utf8 SKILL_DIR/scripts/hedge_verbs.py stats "WORK/헷지동사_섹션별_N<편수>.xlsx"
```

## 엑셀 구성

| 시트 | 내용 |
|---|---|
| 안내 | 절차·정의·판정 방법 |
| 판정작업지 | 후보별 앞 문장 / 【동사】 문장 / 뒤 문장, 자동 예비판정·근거, Claude 검토판정·메모, 연구자판정, 메모 |
| 섹션크기 | 논문×섹션의 단어 수, lexical verb 수 |
| 동사분포(전체) | 논문×섹션별 모든 lexical verb 원형 빈도 |
| 논문×섹션 | 원빈도, 10,000단어당, 동사 100개당 (300단어 미만이면 경고) |
| 섹션요약 | 섹션별 세 지표의 논문 간 평균·표준편차·중앙값·최소·최대·범위, 출현 논문 수, 합산(풀링) 비율 |
| 동사×섹션 | 토큰 수, 출현 논문 수, 논문별 토큰, 최다 논문 비중, 지배 경고 |
| 논문×동사 | 논문별 헷지 동사 행렬 |
| 후보동사 점검 | 후보 26개 각각의 VERB 토큰 수와 Hedge/N/U 분포 |

U는 헷지 수에서 뺀다. 평균·표준편차·범위는 논문당 값 하나씩(거시 평균)으로 계산한다.

## 사용자에게 보고할 때

- 섹션요약을 표로 보여준다: 섹션별 원빈도, 10,000단어당, 동사 100개당의 평균(최소–최대)과 출현 논문 수.
- 해석상 주의점을 짚는다:
  - 짧은 섹션(특히 결론, 300단어 미만)은 1–2건만으로도 비율이 크게 튄다.
  - 한 편이 범위의 끝을 혼자 끌고 가면 그 논문이 어느 것인지 말한다.
  - 지배 경고가 붙은 동사(과반 차지, 1편만 출현)를 언급한다.
  - 한 번도 VERB로 나오지 않은 후보 동사를 언급한다.
- 판정 기준 중 결과를 크게 바꾸는 것을 짚는다(부스터와 함께 쓰인 경우, 타 연구 귀속을 U로 둔 것). 연구자가 바꿀 수 있다고 알린다.
- 연구자판정을 넣는 방법과 stats 재계산 명령을 알려준다.
