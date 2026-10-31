# 유기화학 마크다운 섹션 점검

| 논문 | 상태 | 섹션별 단어 수(전처리 근사) | 제외 사유 |
|---|---|---|---|
| [jo1002714](../../JOC/jo1002714.md) | Fail | INT:1652, MET:5817 | 결과·논의 헤딩/본문 미인식 |
| [jo100315j](../../JOC/jo100315j.md) | Pass | INT:331, RD:1315, MET:6439 |  |
| [jo100420x](../../JOC/jo100420x.md) | Pass | INT:532, RD:1233, MET:2087 |  |
| [jo100742e](../../JOC/jo100742e.md) | Fail | INT:2368, MET:659 | 결과·논의 헤딩/본문 미인식 |
| [jo1011653](../../JOC/jo1011653.md) | Pass | INT:274, RD:1354, CON:101, MET:1371 |  |
| [jo101346t](../../JOC/jo101346t.md) | Pass | INT:949, MET:281, RD:2707, CON:126 |  |
| [jo101439h](../../JOC/jo101439h.md) | Pass | INT:930, RD:3866, CON:140, MET:3150 |  |
| [jo101763t](../../JOC/jo101763t.md) | Fail | INT:2281, CON:141, MET:4287 | 결과·논의 헤딩/본문 미인식 |
| [jo102133m](../../JOC/jo102133m.md) | Pass | INT:433, RD:1993, CON:104, MET:359 |  |
| [jo102334c](../../JOC/jo102334c.md) | Pass | INT:383, RD:2177, CON:89, MET:1740 |  |
| [jo200095e](../../JOC/jo200095e.md) | Pass | INT:498, RD:624, MET:4198 |  |
| [jo4021562](../../JOC/jo4021562.md) | Fail | INT:2110, CON:106, MET:1637 | 결과·논의 헤딩/본문 미인식 |
| [jo402365s](../../JOC/jo402365s.md) | Fail | INT:3818, CON:152, MET:3947 | 결과·논의 헤딩/본문 미인식 |
| [jo402386k](../../JOC/jo402386k.md) | Pass | INT:360, RD:1577, CON:118, MET:5575 |  |
| [jo4024057](../../JOC/jo4024057.md) | Pass | INT:582, RD:1545, CON:157, MET:5436 |  |
| [jo4024107](../../JOC/jo4024107.md) | Pass | INT:376, RD:2417, CON:171, MET:8306 |  |
| [jo402429q](../../JOC/jo402429q.md) | Pass | INT:272, RD:1124, CON:304, MET:2020 |  |
| [jo4024304](../../JOC/jo4024304.md) | Pass | INT:377, RD:1561, CON:61, MET:2624 |  |
| [jo402437z](../../JOC/jo402437z.md) | Pass | INT:481, RD:1743, CON:149, MET:5412 |  |
| [jo402526z](../../JOC/jo402526z.md) | Pass | INT:651, RD:1524, CON:81, MET:6411 |  |
| [jo402527w](../../JOC/jo402527w.md) | Pass | INT:747, RD:10367 |  |
| [jo901581w](../../JOC/jo901581w.md) | Pass | INT:255, RD:2116, CON:271, MET:733 |  |
| [jo902046g](../../JOC/jo902046g.md) | Pass | INT:341, RD:3208, CON:345, MET:3033 |  |
| [jo902300e](../../JOC/jo902300e.md) | Pass | INT:606, RD:2527, CON:360, MET:1377 |  |
| [jo902313g](../../JOC/jo902313g.md) | Pass | INT:420, RD:1870, MET:3247 |  |

표/그림/인용 목록/러닝 헤더로 식별된 블록은 제외했습니다. HTML 위·아래첨자를 정리하고 인용 번호를 [n]으로 전달했습니다. 숫자 역방향 범위(예: 결정축 [10-1])는 인용으로 세지 않도록 괄호 표기를 바꾸고 기록했습니다. 분모는 본문 분석 시 spaCy의 is_alpha로 다시 계산합니다.
