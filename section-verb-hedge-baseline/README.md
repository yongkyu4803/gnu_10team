# section-verb-hedge-baseline

화학 등 이공계 연구논문 PDF 2~10편에서 서론·실험·결과·논의·결론 절마다 동사, 헷지(완곡 표현), 강조 표현, 선행연구 보고동사가 1,000단어당 몇 번 나오는지 세어 **중간값과 범위의 기준선**을 만드는 Claude Code 스킬입니다. 모든 숫자에는 근거 문장이 함께 저장됩니다.

*A Claude Code skill that builds section-level baselines (median and range per 1,000 words) of verbs, hedges, boosters and reporting verbs from a small bundle of research-article PDFs, with an evidence sentence for every count.*

## 무엇을 세나
| 지표 | 예 |
|---|---|
| 헷지 | may, could, suggest that, appear to, probably, in general |
| 강조(booster) | demonstrate, prove, clearly, indeed, it is evident that, in fact |
| 보고동사 | "He et al. **reported** …"처럼 선행연구를 전하는 동사 |
| 동사 분포 | 절마다 품사가 VERB인 낱말의 기본형 |

헷지·강조 목록은 Hyland (2005) *Metadiscourse* 부록(pp. 218-223)을 따릅니다. 화학 논문에서 문자 그대로 쓰이는 표현(show·find, 숫자 앞 about, "could be detected", "It should be noted that", "a clear shell" 등)은 합계에서 빼고 확인 후보로 따로 둡니다. 목록과 판정 규칙은 [references/hedge_lexicon.md](references/hedge_lexicon.md)에 있습니다.

## 설치
1. **Python 3.12**를 설치합니다(Windows는 `py -3.12`).
2. 패키지를 설치합니다.
   ```
   python -m pip install -r requirements.txt
   ```
3. **poppler**의 pdftotext를 설치하고 PATH 맨 앞에 둡니다(Windows: `winget install oschwartz10612.Poppler`). xpdf의 pdftotext가 먼저 잡히면 참고문헌 수가 틀리므로 실행이 멈추고 알려 줍니다.

Claude Code 스킬로 쓰려면 이 폴더를 프로젝트의 `.claude/skills/section-verb-hedge-baseline/`(또는 전역 `~/.claude/skills/`)에 둡니다. 사용법은 [SKILL.md](SKILL.md)에 있습니다.

## 실행
```
python scripts/run_stage1.py <PDF 폴더> <출력 폴더>
python scripts/render_layout.py <PDF 폴더> <출력 폴더>/1_extract <그림 폴더>
```
- 첫 줄에 `환경: Python 3.12.x, pdftotext version 25.x`가 나옵니다.
- `extract_gate.json`: 추출 품질 검사. 인용 번호 회수 95% 이상, 끝이 열린 문장 5% 이하, 여백 문구 누출 0을 넘지 못한 논문은 기준선에서 빠집니다.
- `2_baseline/`: `baseline_report.md`, `baseline.csv`, `per_paper.csv`, `common_verbs.csv`, `evidence.csv`(근거 문장)
- 검증 그림: 쪽 그림 위에 초록·절 제목·절별로 센 줄을 색 상자로 그립니다(`index.html`).

## 시험한 범위
| 묶음 | 편수 | 추출 품질 검사 |
|---|---|---|
| Inorganic Chemistry (2010~2015) | 5 | 5편 통과 |
| Chemistry of Materials (2010~2015) | 5 | 5편 통과 |
| Journal of Organic Chemistry (2009~2015) | 6 | 6편 통과 |

- 세 묶음의 헷지·강조 448건을 원문 문맥과 대조했습니다. 오판 61건(약 14%)을 찾아 규칙으로 만들었고, 지금 규칙은 그중 59건을 거릅니다.
- `examples/IC_2010-2015_5편/`은 IC 5편으로 돌린 결과입니다. 저작권 때문에 `evidence.csv`의 문장 열은 비워 두었습니다(문장 번호는 남김).

## 알려진 한계
- **판정 규칙은 위 448건을 보고 만들었습니다.** 따로 남겨 둔 시험 자료가 없으므로, 새 묶음에서는 `evidence.csv`에서 낱말별로 20~30건을 읽어 오판률을 먼저 확인하세요. 이전 판 규칙은 새 묶음에서 오판의 절반만 걸렀습니다.
- 원문 대조의 오판 판정은 사람이 아니라 Claude가 내린 것이며, 사람과의 일치도는 재지 않았습니다.
- 보고동사 판정과 동사 분포(일반 영어 spaCy 모델)는 원문과 대조하지 않았습니다.
- 분야당 5~6편이라 1건 차이로 중간값이 크게 움직입니다. 평균·검정은 쓰지 않고 중간값과 범위만 보고합니다.
- 추출 규칙은 ACS 저널 조판을 기준으로 다듬었습니다. 다른 출판사·연도에서는 절 제목·본문 크기·초록 위치를 검증 그림으로 먼저 확인하세요.
- 저자-연도식 인용(Smith, 2012)은 다루지 못합니다.

## 버전
pdf-extract-0.4.7, hedge-baseline-0.4.4

## 논문 자료
이 저장소에는 논문 PDF나 논문 문장을 넣지 않았습니다. 분석할 PDF는 각자 정당한 경로로 구해 쓰세요.
