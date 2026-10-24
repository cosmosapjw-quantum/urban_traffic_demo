# 다음 연구 단위 인계

Repo cosmosapjw-quantum/urban_traffic_demo, branch research/restored-morphology-layered-traffic-20261024. 부모 e093ecd35e0af1bc940d3fa36ae09bd0a4a3978a, 지도 a92bd461a98262963fdb87092878da9b39cf3c7c, 교통 d8077c8fafc1e87746b57b55069b3fa0cca119bf. 이후 감사commit은 실제HEAD와PUBLICATION.json으로확인한다.

AGENTS.md와 docs/research/frontage_interval_20261024/REPORT_KO.md, artifacts/frontage_interval_20261024/STAGE_RESULTS.json을먼저읽는다. 관련코드만읽고과거전체archive감사를다시시작하지않는다. 새지도접근로는구역의일부선언site에대해서만실제도로를생성했다. 전체구역OD/미해상intrazonal을자동완료처리하지않는다.

원래 active matter gain-loss + mesoscopic committed suffix + collision-informed legal-link Dijkstra를보존한다. Pure stdlib scientific core,개별차량/차로위치루프·GPU·JAX·main변경없음. 기존Model의기본숫자는유지된다. PackedModel은입력수요/신호/incident경계가dt에정렬돼야하는opt-in후보다. IntervalModel은작은연속시간oracle용이며도시성능부적합결과를숨기지않는다. 도로단위국소이벤트/비동기스케줄을검토할때전역스캔의고비용을다시도입하지않는다.

다음첫경계는고정격자의소량queue-depletion오차와frozen-entrydelay의추월/FIFO문제를작은반례로정량화하는것이다. Exact10초freeflow,source부분구간,closure재개,신호경계,질량/저장량을별도oracles로유지한다. Variable-ratecalendar의압축은질량삭제나이동중경로변경이아닌누적유량/시간moment의명시오차계약으로다룬다. 그후모든구역의local/access/egress를집계수요와연결한다.

Evidence: 번들102시험=원격범위90+parentreference12; 두배치79/23exit0. 기본Model부모대조630ticks상태/fingerprint일치. 동일시계압축7200→2853records,완료량동일. packed300s도시probe는주민stock100k중480.9634veh만release,mean=null이다. 작은walltime을전일성능으로외삽하지않는다. Native subagent/전체repoCI/Python3.12/로컬전일/calibration은미실행이다.

각실행가능행동단위가끝나면expectedSHA로연구branch에fast-forward게시하고readback한다. 실패한event후보와validcheckpoint는보존하며budget확대나수요축소로성공을연출하지않는다. staticBraess65→80은재사용검사이며모든동적악화의설명이아니다.
