# 헷지·비헷지 목록과 판정 조건 (hedge-baseline-0.4.4)

헷지(hedge)와 비헷지(booster, 강조)의 낱말은 Hyland (2005), *Metadiscourse: Exploring Interaction in Writing* (London: Continuum)의 부록 "Metadiscourse items investigated"(pp. 218-223)의 Hedges·Boosters 항목을 따른다. Hyland는 이 부록을 문맥에서 확인해야 할 **잠재적** 표현 목록으로 소개하므로, 아래 판정 조건(품사, that절 등)으로 문맥을 거른다.

Hyland 목록 가운데 화학 논문에서 문자 그대로 쓰이는 경우가 많은 항목은 합계에 넣지 않고 **확인 후보**로 돌렸다(아래 "Hyland와 다르게 다룬 항목"). Hyland 부록에 없는 낱말은 합계에 넣지 않는다.

## 헷지 (합계에 넣음, 실험 절 제외)
| 범주 | 낱말 | 판정 조건 |
|---|---|---|
| 조동사 | may, might, could, would, should, ought | 품사 태그 MD |
| 동사 | suggest, indicate, assume, suspect, suppose, postulate, argue, claim, doubt, feel, guess | that절(ccomp)을 거느릴 때만. 형용사적 분사는 제외 |
| 동사 | appear, seem, tend | to부정사·that절 보어가 있거나 주어가 it일 때만("appearing at 390 nm" 제외) |
| 부사 | possibly, probably, presumably, perhaps, apparently, plausibly, likely, maybe, uncertainly, unclearly | 품사 ADV |
| 형용사 | possible, probable, likely, unlikely, plausible | 명사 수식이거나 that절이 있을 때. "it is possible to + 동사"는 제외(능력) |
| 형용사 | presumable, doubtful, uncertain, unclear | 품사 ADJ |
| 여러 낱말 | certain amount/extent/level, from my/our/this perspective, in general, in most cases, in most instances, in my opinion, in my view, in this view, in our opinion, in our view, on the whole, to my knowledge | 문장에서 낱말 경계로 일치 |

## 비헷지·강조 (합계에 넣음, 실험 절 제외)
| 범주 | 낱말 | 판정 조건 |
|---|---|---|
| 동사 | demonstrate, prove, establish | 품사 VERB |
| 동사 | know, realize, think, believe | that절을 거느릴 때만("known as", "the known complex" 제외) |
| 부사 | actually, certainly, clearly, conclusively, decidedly, definitely, doubtless, evidently, incontestably, incontrovertibly, indeed, indisputably, obviously, really, surely, truly, undeniably, undisputedly, undoubtedly | 품사 ADV |
| 형용사 | clear, evident, obvious, definite, incontestable, incontrovertible, indisputable, undeniable | 품사 ADJ |
| 형용사 | certain, sure, true | that절이 있을 때만("certain compounds", "true value" 제외) |
| 여러 낱말 | beyond doubt, in fact, no doubt, of course, without doubt | 문장에서 낱말 경계로 일치 |

## Hyland와 다르게 다룬 항목 (확인 후보, 합계에 넣지 않음)
| 범주 | 낱말 | Hyland | 이유 |
|---|---|---|---|
| show_find | show, find, estimate | show·find는 강조, estimate는 헷지 | 화학 논문에서 결과 제시·그림 지시("as shown in Figure 3")·연구 행위("To estimate the emission energy")로 너무 흔하다 |
| rounder | about, approximately, roughly, around, almost (+ nearly, ca.) | 헷지 | 숫자 앞의 어림은 측정값의 표기이지 인식적 헷지와 성격이 다르다. 숫자 앞일 때만 센다 |
| degree | relatively, somewhat, generally, largely, essentially, mostly, mainly, fairly, quite, rather, broadly (+ partially, partly, slightly) | 헷지 | 화학에서는 문자 그대로 쓰이는 경우가 많다(partially blocking ligands) |
| frequency | often, usually, sometimes, frequently, typically, always, never | often 등은 헷지, always·never는 강조 | 관측 빈도("always observed at 77 K")인 경우가 많다 |
| literal | apparent, typical | 헷지 | apparent rate constant, typical procedure 같은 용어로 쓰인다 |
| must | must | 가능성의 must만 강조 | 의무의 must와 자동으로 가르지 못한다 |
| can | can | 목록에 없음 | 가능성과 능력이 섞인다 |

괄호 안 낱말(nearly, ca., partially, partly, slightly)은 Hyland 부록에 없지만 같은 이유로 확인 후보에 둔다.

## 팀 추가 낱말 (확인 후보, 합계에 넣지 않음)
v0.3.0까지 합계에 넣었으나 Hyland 부록에 없는 낱말이다. 근거 문장을 보려고 확인 후보로 남긴다.
| 범주 | 낱말 | v0.3.0에서의 분류 |
|---|---|---|
| team | imply, propose, speculate, presume | 헷지 |
| team | confirm | 강조 |
| team_adv | conceivably | 헷지 |
| team_adv | unambiguously, unequivocally | 강조 |
| team_adj | tentative | 헷지 |
| team_adj | unambiguous | 강조 |

## 문맥 오판 규칙 (hedge-baseline-0.4.2)
CM 5편·JOC 6편의 헷지·강조 315건을 원문 문맥과 대조해 나온 오판 41건(13%)을 규칙으로 만들었다. 걸린 표현은 합계에서 빼고 `review:rule_*` 확인 후보로 남긴다(evidence.csv, per_paper.csv의 `rule_excluded`).
| 규칙 | 조건 | 사례 |
|---|---|---|
| rule_could_ability | could의 본동사가 실험 행위 동사(detect, observe, obtain, isolate, recover, prepare, separate, identify, refine, position, resolve, locate, run, record, measure, purify, synthesize, grow, crystallize) | "no emission could be detected", "could be recovered" |
| rule_should_discourse | should의 본동사가 담화 동사(note, emphasize, mention, recall, stress, point, remember, bear)이거나 주어가 we | "It should be noted that", "we should take into account" |
| rule_should_conditional | should가 문장 첫 낱말(가정 도치) | "Should the copper be incorporated …" |
| rule_booster_literal | prove + to be·형용사 보어, establish의 형용사적 쓰임이나 목적어가 bond·class 등, demonstrate의 목적어가 issue·problem이거나 "in the artwork/figure" | "proved to be unsuccessful", "establish hydrogen bonds", "well-established protocols" |
| rule_adj_attributive | clear·obvious·evident·definite가 명사를 꾸밈. 단 evidence·proof·indication 등은 강조로 남김 | "a clear shell", "no obvious diffraction feature"(남김: "clear evidence") |
| rule_adj_negated | 주어에 no가 붙은 "… was evident" | "no luminophore aggregation was evident" |
| rule_could_ability (0.4.4 추가) | 실험 행위 동사에 repeat·exploit 추가. could 본동사에 not이 붙으면(could not improve) 능력으로 봄. 단 rule out·exclude·explain·account·attribute는 추측이라 남김 | "too much Zn2+ could not improve", "The cycle could be repeated"(남김: "could not be ruled out") |
| rule_should_deontic (0.4.4) | should의 본동사가 avoid·prevent·minimize·eliminate, 또는 문장이 "For an efficient/effective/… "로 시작(요건) | "CO gas should be avoided", "For an efficient injection, … should be transferred" |
| rule_appear_literal (0.4.4) | appear·seem에 in·at·around·near·below·above 전치사구가 붙고 to부정사·that절이 없음 | "The first one appears in the UV region", "it appears at lower energy" |
| rule_reporting (0.4.4) | It + 완료·과거 수동(has been / was suggested·proposed·claimed·argued) | "It has been suggested that …"(남김: 현재형 "It is suggested that") |
| rule_booster_literal (0.4.4 추가) | obviously가 동사 뒤에 옴(정도) | "k decreases obviously" |
| rule_booster_negated (0.4.3) | 강조 형용사·부사에 less·hardly·barely·scarcely·not·never가 붙거나, 그 술어(is, shown 등)에 not이 붙음 | "is less clear", "It is not clear whether", "was not clearly resolved"(남김: "entirely clear", "Clearly, …") |
| rule_possible_ability | it is possible to + 동사(0.4.1까지 일부 빠져나감) | "it was not possible to isolate" |
| rule_possible_literal | possible이 method·approach·route·alternative·bond·option·form을 꾸밈 | "possible alternative methods" |

- 규칙을 만든 뒤 CM·JOC 오판 43건(원문 전체로 다시 본 2건 포함) 가운데 40건을 잡았고, 정상 판정을 잘못 뺀 것은 0건이다. 경계 2건(CM "a clearer face-on ordering", "possible crystalline form")도 빠졌다.
- 못 잡은 3건: "could be found"(가능성 쓰임과 구분하지 못해 find는 규칙에서 뺌), "It was suggested that"(선행연구 보고), "polymers should exhibit"(요건).
- IC 5편에서는 9건이 빠졌고, 문맥을 보면 모두 오판이었다("it is possible to distinguish", "It should be mentioned that" 등).
- IC 133건을 따로 대조하니 오판 18건 가운데 0.4.2 규칙이 잡은 것은 9건이었다. 규칙을 만든 묶음(CM·JOC) 밖에서는 절반만 잡힌다(원문대조_v0.4.6/IC_판정_오판과경계.csv).
- rule_booster_negated(0.4.3)는 16편에서 1건만 바꿨다("is less clear", ic1020862). 부정·정도 수식은 대부분 명사 수식("no obvious feature")이라 rule_adj_attributive가 먼저 거른다. 부정된 강조를 헷지로 옮기지는 않는다(팀 판단 필요). 부정된 강조 동사("do not clearly demonstrate"의 demonstrate)는 아직 강조로 센다.
- 0.4.4는 IC 대조에서 못 잡은 9건의 유형으로 규칙을 넓혔다. 16편에서 10건(IC 9, CM 1)이 바뀌었고 모두 오판이었다. 정상 판정을 잘못 뺀 것은 0건이다. 이제 448건 기준 오판 61건 가운데 59건을 잡는다(못 잡음: CM "could be found", "polymers should exhibit").
- 주의: 0.4.4 규칙은 448건 전부를 보고 만들었으므로, 규칙을 시험할 따로 남겨 둔 자료가 없다. 새 묶음에서는 다시 표본 대조로 오판률을 확인해야 한다.
- 주의: 편수가 5~6편이라 1건만 빠져도 중간값이 크게 움직인다(CM 서론 헷지 4.26→2.18은 1건 차이).

## v0.3.0에서 바뀐 점
- **believe**: 헷지에서 **강조**로 옮김(Hyland 부록의 Boosters).
- Hyland 부록에 있으나 빠져 있던 헷지·강조 낱말과 여러 낱말 표현을 더함(위 표).
- Hyland 부록에 없는 낱말을 합계에서 빼고 확인 후보로 돌림(위 "팀 추가 낱말").
- 확인 후보에 frequency, literal, must, show_find 범주를 더함.

## 제외 판단의 근거가 된 실제 문장 (IC 5편)
- "the red-shifted absorption appearing at 390 nm" (ic1020862): 관측 위치, 헷지 아님
- "calculated triplet energies, indicated as ET" (ic1020862): 기호 지시, 헷지 아님
- "the presence of the proposed complex" (ic1020862): 형용사적 분사, 헷지 아님
- "it is possible to distinguish four basic types" (ic1020862): 능력, 헷지 아님
- "To estimate the emission energy" (ic400600d): 연구 행위, estimate를 확인 후보로 돌린 이유
- "the partially blocking tetradentate ligands" (ic901600v): 문자 그대로, 정도 부사를 확인 후보로 돌린 이유
