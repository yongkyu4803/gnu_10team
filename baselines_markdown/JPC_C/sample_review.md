# JPC_C 근거 문장 표본 점검

원본 엔진의 hedge/booster 근거 중 may, could, should, suggest, indicate, appear, probably, clearly, demonstrate, possible에 대해 각각 첫 2건, 총 20건을 읽은 편의 표본 점검입니다. 무작위 검증이나 사람 간 일치도 검사, 전체 오판률 추정이 아닙니다. 엔진 집계값은 임의로 수정하지 않았습니다.

- `jp1050047 / 3-050 / could`: “Graphene nanosheets themselves could store Li and act as electronic conductor.”는 불확실성보다 능력 서술일 가능성이 있어 문맥 검토가 필요합니다.
- `jp105923a / 4-013 / should`: “both adsorption and desorption isotherms should be considered”는 권고 용법일 가능성이 높아 헷지 예비판정에 주의해야 합니다.
- `jp105923a / 3-019 / suggest`: “slope ... The decreased ... samples ... samples ...”처럼 두 단의 문장이 섞인 흔적이 있습니다. 마크다운 입력의 읽기 순서 문제로, 구문·문장 단위 판정에 영향을 줄 수 있습니다.
- `jp105923a / 3-017 / indicate`: 문장 안의 “pressures T ...” 등 잘린 수식·열 혼합 흔적이 있어 원문 대조가 필요합니다.
- `jp1050047 / 3-049 / should`: 결과의 원인을 추정·귀속하는 용법으로 해석할 여지가 있습니다. 권고 용법과 구분해야 합니다.
- `jp204242q / 3-154 / probably`, `jp205910b / 3-022 / probably`: 가능 원인·입자 귀속을 유보하는 문맥으로 읽힙니다.
- `jp1050047 / 3-007 / clearly`, `jp1050047 / 3-046, 3-047 / demonstrate`: 관측·결과 주장을 강화하는 문맥입니다. 원본 스킬의 booster 판정과 부합합니다.
- `possible`, `appear` 일부 근거 CSV는 문장이 300자로 잘려 있습니다. 전체 문장은 `1_markdown_input/<논문>_input.txt`의 문장 ID로 확인해야 합니다.

위 사례 때문에 이 기준선은 `needs_review=true`로 등록했습니다. 20건 표본의 관찰을 전체 빈도의 정확도 또는 분야 차이의 근거로 일반화하지 않습니다. 나머지 분야도 자동 기준선이며, 완료된 수동 판정 기준선은 아닙니다.
