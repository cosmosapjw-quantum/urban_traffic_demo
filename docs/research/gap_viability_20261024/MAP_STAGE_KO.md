# 지도 후속 루프: 반응 중 가속과 접근구간 시야

Base b546ba6d096ff1efabc40d44aafffb1c303db2ce. 2026-10-24. Default API는 reaction_accel=0, approach_step_m=None으로 이전 단일관측점 행동을 유지한다. 새 옵션은 별도 연구 경로다. Native subagent NOT_RUN; 실제 Python/CAS/반례 기반 직렬 검증.

정지거리 가정: delta초 동안 순가속도<=a, 이후 보장 순감속 b_eff>0. D=v*delta+a*delta^2/2+(v+a*delta)^2/(2*b_eff)+margin. b_eff=b-g*grade/sqrt(1+grade^2). a는 중력을 포함한 net 반응구간 가속도 상한이다. v10m/s,delta2s,a2m/s²,b4m/s²에서48.5m이며 이전상수가속0 가정의32.5m와 다르다. Wolfram의 정확한값97/2와일치.

원래 한관측점 방식은 가장먼점에서보여도 중간점에서가려지는작은능선을놓친다. 400m도로,관측점부근2.2m완만언덕과접속점앞1.2m능선 반례에서원 gate는통과하지만새2m간격screen은거절한다. 각시선의지형교차는기존bilinear patch 연속검사이나 관측자의위치는표본이다. 그러므로 모든위치의지속시야나교차로안전을인증하지않는다. 표본상한초과는sight_sampling_budget,접근구간부족은sight_extent_unknown으로거절한다. 건물/차량 occlusion은범위밖이다.

동일4형태/seed17/8활동지점/900m예산에서각4개접근로가유지되었고길이800.003655,361.433371,800.003655,186.813959m다. 새기능때문에대표지도가더좋아졌다는주장은하지않는다. 통제반례의부적절한접속만거절하며원지도불변,cycle rank/분할길이/비접속중심선교차0검사를통과했다.

Fresh RED5개 후 기존관련시험포함16passed. 재현: PYTHONPATH=src python -m pytest -q tests/test_robust_approach.py tests/test_sight_frontage.py tests/test_frontage_growth.py; python -S tools/run_gap_map.py.

다음 교통단위는h'=w-v, 유한가감속과선두차정지전과정의최대접근량이다. 안전한최종정지위치만으로중간충돌을판정하지않는다. 지도/교통의제동식은동일한상수가속궤적원리에놓되이map gate를전체안전정리로확대하지않는다.

근거: FHWA Interchange Design Promptlist(https://highways.dot.gov/field-offices/missouri/interchange-design-promptlist)의접근도로시야검토; Sidorenko et al.(2022),doi:10.1109/TIV.2022.3209910의제동전과정의종방향안전문제. 법정설계기준준수/새이론의선행성주장없음.
