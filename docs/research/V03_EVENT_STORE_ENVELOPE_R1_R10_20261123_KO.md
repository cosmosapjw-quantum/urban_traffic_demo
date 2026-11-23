# MetroFlow V03 · Persistent events and moment envelopes · R1/C1–R10/C10

## R1/C1 · 재개 기준과 실제 목표 (2026-11-23 KST)

기준 commit은 3c8650abc8b556387e7f24ce84b1e676e6e8b141이며 원격 branch와 일치를 확인했다. 새 branch는 research/v03-event-store-moment-envelope-20261123이다. 기존 브랜치와 4.68GB checkpoint를 보존한다.

원본 Valley weekday seed7, 주민100000, dt10s, 8GiB RLIMIT_AS, 7200s/run, 86400s×3cities×3repeats의 수용 조건을 유지한다. PLAN.json v1.1.26은 19/21 scoped, 5/21 accepted, V03 직접 선행3/3, 원본 하루0/9다. 연구단계 커밋은 DAG 완료수에 더하지 않는다. 전체 저장소 CI와 main merge는 기존 사용자 정책에 따라 보류한다.

직전 결과는 t25720 원본 물리 상태의 저장·현재 native 전진재현·full-wire 독립복원·질량 장부 일치다. checkpoint bytes4677350066, SHA256447570b8721b17fa19edf159bc4c474cfd6ad41dc936ab0b0114d902e36f0bf9. 실제 파일은 이전 worktree의 artifacts/v03_age_loss_checkpoint_20261122/R6_original_100k_25710_off_requested_20s.final.bin이다. 다음t25730에서 transfer header reservation 요구4867627464B, allowance4867625327B로2137B 초과했다. 작은 초과는 이후tick 전체의 필요여유를 뜻하지 않으며 실제OOM/no-go 증거가 아니다.

### 이번 이론 목표

미세birth측도가 없어 기존 K(u)=sum m(w−u)+ 관측을 원도시에 그대로 적용할 수 없다는 의무를 구성적으로 다룬다. 실제 사용 가능한 질량m, birth 1차moment B, 명시적 age support[L,H]로 sharp stop-loss 하한·상한을 도출한다. 추가분포를 적합하지 않고 관측 가능한 정보로 지연/age envelope를 계산하며, support partition refinement에서의 단조성·수렴오차와 유한창검열을 연결한다. 내부passage/event 질량과 최종journey완료를 구분하고 전역적신규성은 주장하지 않는다.

### 이번 코드 목표

현재 road의 48B compact event pages를 whole-engine service.last_events까지 영속 전달하여 64B EventRow flatten allocation과 그 공존 peak를 제거한다. standalone/Python flat API와 MFWHOLE1 wire, 원래 f64 bits/order/None sentinel, registry wide fallback을 유지한다. 원본20,270,113행에서16B/row 차이는324321808B인 설계치며 descriptor·padding·live owner는 별도 계상한다. 임의credit이나 cap완화 없이 실제 원본t25730 완주와 저장/독립복원으로 판정한다.

### 10단계 실행 연결

| 단계 | 이론 산출 | 코드·실험 산출 |
|---|---|---|
| R1/C1 | 질문·원래계약 고정 | 기준source/checkpoint/worktree |
| R2/C2 | 원전·기존결과 대응 | 실제flatten/decoder 호출경로 |
| R3/C3 | sharp envelope 명제·가정 | 영속page API·bytepool 설계 |
| R4/C4 | 대표extremizer·판별계산 | 행동회귀·실행자원 준비 |
| R5/C5 | 증명·계산식 완결 | 관측기·compact service 구현 |
| R6/C6 | 독립 exact 검산 | Rust/Python·원본10s 실행 |
| R7/C7 | 실제관측 연결 | 유효checkpoint 기반20/40s 확장 |
| R8/C8 | 결과범위·실패재평가 | 새실제blocker에 대한 선택적수술 |
| R9/C9 | 재사용정리·계산계약 | 현재native3도시준비·정량준비도 |
| R10/C10 | 검토교정·다음의무 | 최종실험/ledger/원격게시 |

각 단계마다 별도 commit과 push 후 원격 SHA를 확인한다. 성공한 물리구간만 누적하고, 실패상태의 시계를 전진으로 세지 않는다. 장시간확장은10→20→40→80s 순서로 이전구간의 저장가능한 실제성공에 의존한다. 데이터·계산산출물은 해당 git branch에, 대용량bin/so는 로컬에 보존한다.
