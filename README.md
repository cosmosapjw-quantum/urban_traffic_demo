# Urban Traffic Simulator — Developer Documentation + Starter Skeleton Bundle

이 번들은 다음을 포함한다.

1. 개발자 문서 세트(md)
2. spec-kit 입력/타깃 문서
3. 세분화된 작업 티켓 백로그
4. `src/metroflow/` 코드 스켈레톤
5. 최소 테스트/벤치 스켈레톤

## 핵심 구현 순서
- 먼저 S2:
  - WorldState
  - contracts
  - multirate scheduler
  - cache invalidation
  - replay benchmark
- 다음 S1:
  - mesoscopic hybrid core
  - generalized-cost routing
  - candidate path K + path-size correction
  - event-triggered reroute
  - lagged land-use feedback

## 다음 작업
- `docs/TICKET_BACKLOG.md` 와 `specs/001-metroflow/tasks_detailed.md` 를 기준으로
  `src/metroflow/` 구현을 채워가면 된다.
