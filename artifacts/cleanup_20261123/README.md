# MetroFlow worktree·백업 정리 결과 — 2026-11-23

## 완료 결과

사용자의 명시적 정리 요청에 따라, 25개 등록 worktree 중 오래된 23개를 Git의 worktree remove로 제거했다. 필요한 자료를 최신 작업본 안에 압축하고 실제 검증한 뒤 제거했다. 별도 branch 삭제, history rewrite, Git garbage collection은 수행하지 않았다.

| 항목 | 실제 결과 |
|---|---:|
| 등록 worktree | 25 → 2 |
| 제거된 오래된 worktree | 23 / 23 |
| 보존한 Git refs | 30 / 30 |
| 기본 작업본의 미커밋 수정 | 10 / 10 원본 및 압축 snapshot·patch 보존 |
| 선택한 checkpoint | 3 / 3 full gzip decode 및 SHA-256 일치 |
| 보존한 압축 payload | 1,063,453,930 bytes (1.063 GB) |
| 제거 직전 가용 공간 | 97,868,349,440 bytes (97.87 GB) |
| 제거 직후 가용 공간 | 186,581,393,408 bytes (186.58 GB) |
| 제거 구간 가용 공간 증가 | 88,713,043,968 bytes (88.71 GB) |
| 압축 보존 시작부터 제거 완료까지 가용 공간 순증 | 83,900,416,000 bytes (83.90 GB) |
| 최종 추가 측정 가용 공간 | 187,345,342,464 bytes (187.35 GB), df 사용률 80% |

GB는 10^9 bytes이다. 파일시스템은 다른 작업과 공유되고 측정 사이에도 변화했다. 따라서 위 차이는 해당 구간의 **파일시스템 관측치**이며 이 작업의 배타적 기여로 해석하지 않는다. 제거 전 23개 디렉터리의 독립 du 사용량 합계는 87,839,965,184 bytes였으며 hardlink 중복 가능성이 있는 규모 지표다. 가장 초기의 다른 시점 df와 최종 값을 빼서 더 큰 공간을 확보했다고 주장하지 않는다.

남긴 경로:

- 최신 연구 작업본: /home/cosmosapjw/urban_traffic_v03_bottleneck_theory_20261123
- 기본 작업본 및 공통 Git 저장소: /home/cosmosapjw/urban_traffic_v03_20261116
- 압축 복구 자료: /home/cosmosapjw/urban_traffic_v03_bottleneck_theory_20261123/artifacts/retained_recovery_20261123/

기본 작업본은 모든 branch 이력을 담은 공통 .git과 미커밋 수정 10개를 보유하므로 보존했다. 이 디렉터리는 불필요한 백업으로 분류하지 않았다.

## 압축해서 남긴 것

| 파일 | 크기 (bytes) | 내용·binding |
|---|---:|---|
| valley_s7_t25700.current.bin.gz | 736,524,111 | 최신 Valley 유효 prefix t=25700 s. native baseline 492e276의 source/binary binding 유지 |
| coastal_s41_t32660.historical.bin.gz | 143,575,826 | 과거 Coastal 유효 prefix t=32660 s. frozen budget-final binary/source 전용 |
| river_s17_t25350.historical.bin.gz | 81,573,697 | 과거 River 유효 prefix t=25350 s. frozen budget-final binary/source 전용 |
| unpublished_evidence_and_native.tar.gz | 11,919,832 | 185 tar 항목: 미게시 분석·로그·입력, 10 dirty snapshots와 patch, native 2개, 환경 package metadata 및 handoff |
| all_project_refs.bundle | 89,860,464 | 보존 시점 30개 refs 및 도달 가능한 Git history; git bundle verify 성공 |

Coastal/River checkpoint는 현재 native 모델과의 호환성을 주장하지 않는 **역사적 재시작 자료**다. 후속 gate JSON에 더 늦은 시간이 기록되어 있어도 그 시점의 bin을 확인하지 못했으므로 이 두 파일을 최신 gate checkpoint라고 부르지 않는다. 정확한 출처는 HISTORICAL_CHECKPOINT_SELECTION.json과 원래 Git receipts에 남겼다.

중복 valley_legs.npz 두 파일은 SHA-256 ad70081e9502dfcb29871eafbd69634e77442db1b88a133be300d30d45fffa17로 같아 tar 안에 한 payload와 hardlink alias로 보존했다. 오래된 미게시 handoff bundle 및 DELIVERY.json도 남겼으며 byte-identical base64 사본은 생략했다. 다른 소형 base64 전달 자료는 동일성 입증 없이 삭제하지 않고 압축 evidence에 남겼다.

세 checkpoint의 압축본 전체를 실제로 decode하여 raw SHA-256을 원래 검증값과 대조했다. Evidence archive의 185개 항목도 streaming 검증했다. 두 pinned native의 SHA-256은 원래 binding과 일치한다. 압축본은 최신 작업본에 존재하며 용량상 Git에는 올리지 않는다. Git에는 선택 기준, hash manifest, 제거 receipt, 이 문서와 수행 script를 남긴다.

## 제거 범위와 복구 범위

23개 제거 경로의 tracked 내용은 각각 branch refs에 남아 있다. 해당 worktree의 superseded 대형 중간 checkpoint, 오래된 native 산출물, 재생성 가능한 target/venv/cache는 제거했다. 선택하지 않은 중간 binary snapshot 전체가 복구된다고 주장하지 않는다. 삭제된 checkpoint의 경로·크기·disposition은 INVENTORY.json, DISPOSITIONS.json, DISK_AND_BACKUP_INVENTORY.json에 남아 있다.

프로젝트 이름과 기존 문서 참조로 확인한 범위에서는 별도 MetroFlow backup 디렉터리를 발견하지 않았다. 다른 프로젝트 backup은 정리 대상에 포함하지 않았다. 소스에 포함된 docs/archive는 연구 history이므로 Git에 그대로 남았다.

복구할 때는 필요한 branch를 Git에서 새 worktree로 만들고, evidence tar의 해당 작업본 경로에 있는 파일만 골라 복원한다. 세 checkpoint는 필요한 경우에만 압축 해제한다. historical checkpoint에는 evidence tar의 native/historical_budget_final 바이너리와 source commit 532effe32f90c20cf3cbc1de350d0e7267f52584를 사용해야 하며, current Valley와 혼용하지 않는다. 전체 복구의 검증 기준은 RECOVERY_VERIFIED.json의 raw/compressed hash다.

## 검증 및 drift watchdog

- 제거 직전 tracked 변경과 untracked 경로 집합이 inventory와 같은지 확인했다. 의도치 않은 ignored 파일도 검출하도록 검사했다.
- 관측 가능한 cwd, open file descriptor, mapped file에서 제거 경로를 사용하는 process 참조가 없음을 확인했다. 읽을 수 없던 process maps PID는 receipt에 명시했다.
- 23개 경로 소멸, 등록 worktree 2개, refs 불변, 기본 작업본 dirty 파일 10개의 hash 불변을 확인했다.
- git fsck --connectivity-only --no-dangling exit 0.
- 원 PRD 0492364:docs/PRD.md blob f8cc371410ca0e24b0947cda3d6772787efddc7a 보존.
- 원 constitution 6524500:memory/constitution.md blob 7c78e214c9558bcb1023854e55025f1c554aadee 보존.
- baseline 492e276부터 production source/tests/tools/AGENTS/PLAN에 이번 이론·정리 작업으로 생긴 변경은 없다.
- 원 동기인 대규모 mesoscopic traffic → 접근성 → 지연된 개발/수요 feedback과 strict FIFO, 합법 경로, 차량·사람·화물 보존을 변경하지 않았다.

## 앞서 완료한 이론 R1–R10

research/v03-bottleneck-theory-20261123 branch에서 R1–R10 각각 commit 및 push하고 원격 SHA 일치를 확인했다. R10 commit은 e5beb6f5544da60eab6b995e8f5a90492b485817이다. 주요 보고서는 docs/research/V03_BOTTLENECK_RECONSTRUCTION_20261123.md, 결과 receipt는 artifacts/v03_bottleneck_theory_20261123/R10_THEORY_RECEIPT.json이다.

이번 범위는 theory-only였다. 여섯 구성적 경로 O/A/B/C/D/E, 증명·반례·128개 exact-rational 결합 service 검산·flux mark 적분 및 refinement 검산을 완료했다. 새 native city 실행, 실행 준비도 상승, 실측 runtime 최적화는 주장하지 않는다. V03 상태는 19/21 scoped-or-accepted, 5/21 accepted, full-day 0/9, BLOCKED를 유지한다.
