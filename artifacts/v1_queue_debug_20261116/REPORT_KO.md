# Stage·queue 증가 디버깅과 결정적 Rayon 병렬화

2026-11-16 UTC. 기준 commit `92d13be4df91c15962898f3e6d4b881002998296`.
요청 범위는 이력·queue 관리 디버깅과 병렬화다. 새 DAG 노드나 24시간 수용시험을
진행하지 않았고, **19/21 (90.5%)**, V03 BLOCKED를 유지한다.

## 1. 관측한 원인

실제 Valley 전체 918,450-leg 달력의 기존 checkpoint를 재사용했다.
모든 시각은 시뮬레이션 시각이다. 마지막 유효 상태 25,380초(07:03:00)의
journey 기록 수는 다음과 같다.

| 구성 | 행 수 | 전체 journey 기록 중 비율 |
|---|---:|---:|
| 도로 진입 전 접근 지연 `entering` | 1,833,556 | 92.72% |
| 도착 후 접근 지연 `egress` | 33,033 | 1.67% |
| 내부 이동 지연 `internal` | 55,921 | 2.83% |
| 완료 시각 이력 `receipts` | 55,053 | 2.78% |
| 합계 | 1,977,563 | 100% |

따라서 이 구간의 주요 원인은 **완료 이력 누수로 확인되지 않았다**. 많은 OD leg의
각 출발 시간 조각이 접근 지연 법칙의 원자별 대기 행을 만든다. 접근 지연이 끝나기
전 source가 계속 공급되므로 entering population이 채워진다. 행 수는 인구·차량량과
다르며, 작은 유체 질량도 하나의 기록을 차지한다.

다음 tick 25,380→25,390초의 정확한 수명 장부는 아래와 같다.

| stage | 기존 | 생성 | 퇴장 | 후보 상태 |
|---|---:|---:|---:|---:|
| entering | 1,833,556 | 158,000 | 114,964 | 1,876,592 |
| egress | 33,033 | 11,215 | 969 | 43,279 |
| internal | 55,921 | 6,424 | 4,938 | 57,407 |
| receipts | 55,053 | 5,907 | 0 | 60,960 |

각 stage에서 `기존 + 생성 − 퇴장 = 후보`이며, 새 receipt 5,907개는
egress 퇴장 969개와 internal 퇴장 4,938개의 합이다. 추적한 **15개 시도 모두**
이 등식이 성립했다. 후보 총 2,038,238개에서 기존 2,000,000개 journey 예산을
초과하고 원자적으로 거절된다. Road의 packet/part 예산은 별도로 적용된다.

이 범위에서 미퇴장·이중 완료는 발견되지 않았다. 모든 가능한 queue 오류의 부재를
증명한 것은 아니다. `entering.ready_now > 0`은 tick 끝에 준비됐지만 다음 tick의
admission을 기다리는 정상 상태일 수 있다. 이를 곧바로 stale record로 분류하지 않는다.

## 2. 수정한 저장·transaction 관리

기존 한 tick에서 Journey가 rollback, prepare, finish를 위해 반복 복제됐다.
finish는 이미 별도로 보유한 pending candidate를 다시 clone했다. 이를 이동시켜
사용하고, 실패하면 candidate를 즉시 폐기한다. 기존 committed state는 유지된다.
Journey의 큰 복사 두 번과 road rollback용 전체 복사를 제거했다.

Road는 기존 상태로부터 candidate를 계산·검증하되 즉시 설치하지 않는다.
Service와 Journey가 모두 성공한 뒤 road candidate를 설치한다. 이 순서의 마지막
설치는 실패하지 않는 연산이다. 실제 실패 후 checkpoint는 기존 버전과 byte-identical이다.

추가로 사용되지 않던 cell queue/latent 복사, junction head packet 복사,
survivor packet 재복사를 제거했다. 비워진 stage의 allocation은 해제하고,
큰 allocation이 상당히 희소해진 경우 여유 capacity를 회수한다. 완료 이력 수는
commit 때만 갱신하는 cache로 계측한다. restore/load에서는 실제 이력으로 재계산한다.

**행 삭제·시간 binning·질량 합치기·수요 축소·기본 예산 확대는 하지 않았다.**
원래 raw record 수와 순서, 완료 시각, MFWHOLE1 checkpoint 형식을 보존했다.
`parent == len(legs)`는 누락된 outward parent를 pending으로 두는 기존 sentinel이다.
독립 검토 중 의심했으나 frontend와 eligibility 코드를 대조하여 결함으로 분류하지
않았고, 이 의미를 보호하는 테스트를 추가했다.

## 3. 병렬화의 범위

기존 lockfile의 **Rayon 1.12.0 / rayon-core 1.13.0**을 사용했다.
Cargo.toml의 `rayon = "1.10"`은 버전 범위이며 실제 lock 버전이 아니다.
새 의존성은 추가하지 않았다.

- runtime별 private pool을 사용한다. 기본은 1 thread이고 1..256을 명시할 수 있다.
- 독립 cell의 운동·queue 준비, 1,024-leg chunk의 release 계산·검증을 병렬화했다.
- 결과는 원래 index 순서로 모은다. FIFO, 교차로 배분, 부동소수점 합산,
  장부 누적과 receipt 삽입은 기존 직렬 순서로 유지한다.
- 오류도 순서대로 검사한다. 여러 오류 중 임의의 오류를 반환하는 parallel
  short-circuit reduction을 사용하지 않았다.
- thread 수는 물리 identity나 checkpoint bytes에 들어가지 않는다. 전용 pool 밖의
  legacy native 호출은 자동으로 global Rayon pool을 사용하지 않는다.

faer는 선형대수 라이브러리다. 이번 경로는 scalar 운동법칙·FIFO packet·시간별
stage 관리이며 행렬 분해나 선형계 풀이 병목이 없어서 faer를 추가하지 않았다.
이는 코드의 작업 구조에 따른 선택이다.

공식 API 근거:
[ThreadPool::install](https://docs.rs/rayon/1.12.0/rayon/struct.ThreadPool.html#method.install),
[indexed collect](https://docs.rs/rayon/1.12.0/rayon/iter/trait.IndexedParallelIterator.html#method.collect_into_vec),
[parallel sum의 결합 순서](https://docs.rs/rayon/1.12.0/rayon/iter/trait.ParallelIterator.html#method.sum),
[faer](https://faer.veganb.tw/).

## 4. 동일 입력 성능 대조

실제 Valley의 **25,240→25,340초** 동일 입력 checkpoint에서 각각 3회 실행했다.
원래 checkpoint는 매번 그대로 재사용했다. wall은 `driver.advance` 구간만 측정하며
report/debug/save/hash는 제외한다. Peak RSS는 구성·load·실행·checkpoint 검증을
포함한 **process 전체** 값이다. 공유 호스트의 다른 작업과 CPU 배치 영향까지
격리한 성능 인증은 아니다.

| 코드·worker 수 | advance 중앙값(s) | 3회 범위(s) | process peak RSS(bytes) |
|---|---:|---:|---:|
| 기존 serial | 2.430732 | 2.333719–2.472877 | 860,340,224 |
| 최종 serial 1 | 1.792937 | 1.769835–1.800294 | 676,192,256 |
| 최종 Rayon 2 | 2.877136 | 1.909349–3.037027 | 820,449,280 |
| 최종 Rayon 4 | 1.731215 | 1.701168–1.855752 | 822,259,712 |
| 최종 Rayon 8 | 1.749126 | 1.634398–3.783731 | 779,333,632 |

최종 serial은 기존 대비 이 측정에서 시간 **26.24%**, process peak RSS **21.40%**
감소했다. 단계 계측 추가 전 첫 대조도 2.430732→1.933890초, RSS 860,340,224→
678,391,808바이트로 각각 20.44%, 21.15% 감소했다. 해당 원본도 보존했다.

병렬 성능은 일정하지 않다. 최종 4-worker 중앙값 개선은 최적화 serial 대비
3.44%이며 2-worker는 느렸고, 앞선 4-worker 측정도 serial보다 느렸다.
따라서 일반적인 병렬 가속이나 worker 수에 비례하는 확장을 주장하지 않고
**기본 1 thread를 유지**한다. 병렬 실행 가능성과 정확성은 별도로 검증됐다.

단계별 중앙값에서 serial road step은 약 0.755초, journey prepare는 0.365초,
journey finish는 0.243초였다. 4-worker journey finish는 약 0.159초로 줄었지만
prepare는 약 0.404초였고 road 전체는 약 0.749초였다. 전체 road step에는
직렬 FIFO·교차로 처리도 포함되므로, cell prediction의 병렬화만으로 전체 시간이
크게 줄어들지 않는다. 이 계측은 원인을 좁히는 근거이며 각 phase의 세부 원인을
모두 분리한 profiler는 아니다.

## 5. 검증과 재현

실제 로컬 Rust release build와 관련 **68개 테스트**가 통과했다.
테스트는 32개 cell·2,560개 leg로 실제 병렬 경로를 지나며, 혼합 교통·분기·새
runtime 재시작·오류 rollback·stage 퇴장·빈 queue 해제·orphan sentinel을 포함한다.
1/2/4-worker 단위 대조에서는 worker 수·분할 실행·재시작에 따른 byte identity를
확인했다. 실제 1/2/4/8-worker 각 3회 대조의 최종 보고서 및 checkpoint는
**기존 kernel과 정확히 동일**하다. 최초 snapshot도 유지됐다.

최종 4-worker 증가 추적에서도 동일한 25,380초에서 중단됐고 기존 실패 checkpoint
SHA `0886dc78f39ecd404fcea8b11a87de651e1d20447af2f7132ef954911eed2cd8`과 일치한다.
`last_attempt`는 물리 checkpoint와 별개인 최근 호출 진단이다. save/load 전에
수집해야 한다. `debug_state`의 capacity는 전달한 불변 snapshot의 Vec 저장량이며
실행 owner·allocator·전체 RSS와 같지 않다.

실행 설정은 Python frontend에서 `NativeReleaseDriver(..., native_threads=4)`로
지정하거나 기존 CLI의 `METROFLOW_V1_NATIVE_THREADS=4`로 전달한다.

```bash
PYTHONPATH=src OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python tools/debug_v1_native_queues.py \
  --receipt artifacts/v1_queue_debug_20261116/baseline_seed25240.json \
  --end-s 25340 --threads 4 --repeat 3 \
  --out artifacts/v1_queue_debug_20261116/profile_t4.json
```

실측 원본, phase 시간, trace, 비교 결과, 소스 SHA, build/test 로그를 이 디렉터리에
보존했다. 대용량 이진 checkpoint와 기존 binary는 실제 전용 worktree에 남아 있다.
`BASELINE_REPLAY_TOOL.py`는 이전 계측 도구의 byte identity를 위한 역사적 소스 사본이며
실행 entrypoint는 `tools/debug_v1_native_queues.py`다.

## 6. 결정

독립 검토는 디버깅·저장 수명 수정과 결정적 병렬 실행을 한정 수용했다.
초기 접근 지연 stage의 논리적 행 수 제한 자체는 남는다. 이번 수정은 실제 중복
복사와 allocation 관리 비용을 줄였으며 기록의 표현이나 수용 기준은 바꾸지 않았다.
24시간 수용시험, 전체 CI, 통합·merge는 실행하지 않았다.
