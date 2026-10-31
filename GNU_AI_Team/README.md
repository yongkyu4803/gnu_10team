# GNU AI Team — 학술 글쓰기 분석 스킬 (1차, 2026-10-26)

출판 논문을 섹션별로 분석해 분야 기준선(평균·범위)을 만드는 Claude 스킬 두 개입니다.

| 스킬 | 하는 일 |
|---|---|
| [hedge-verb-sections](hedge-verb-sections/SKILL.md) | 섹션별(서론·방법·결과·논의·결론) lexical verb와 헷지 동사(suggest, indicate, appear 등)를 세고, 원빈도·10,000단어당·동사 100개당 비율과 논문 간 평균·범위를 엑셀로 정리 |
| [litreview-structure](litreview-structure/SKILL.md) | 서론의 선행연구 토픽 수·토픽당 문헌 수·토픽 조직, 결과·논의에서 선행연구를 인용하는 기능(비교·해석 근거·방법 출처·배경)을 분석 |

두 스킬 모두 자동 예비판정 → Claude 검토판정 → 연구자 최종판정 순서로 판정하고, 판정 기준은 각 폴더의 `references/`에 있습니다.

## 설치

- Claude Code: 두 폴더를 프로젝트의 `.claude/skills/` 또는 `~/.claude/skills/` 아래에 둡니다.
- 필요 환경: Python 3, `pip install spacy openpyxl pymupdf`, `python -m spacy download en_core_web_sm`

## 지금까지 만든 기준선

J. Org. Chem. 6편, Inorganic Chemistry 5편, Chemistry of Materials 5편(2010–2015). 세 분야 16편 모두 방법 절에서 헷지 동사가 0회였습니다.
