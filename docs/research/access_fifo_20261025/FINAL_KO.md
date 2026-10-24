# 접근·개발과 순서 보존 수송: 최종 한정 결산

2026-10-25. 감사 부모 eed80ea54378281bf79994caf7348ce0b3009bbb. 지도 f3ba16d306ecff4a560a3d21dd1236bd6c9a0960, 교통 25f887a8d8abc2ba3d1b5a46badcabfd5f877e71. 기존 부모 소스와 production default는 변경하지 않았다. 상세 가정은 MAP_STAGE_KO.md와 TRAFFIC_STAGE_KO.md에 있다. 전체 직접 유도·반례·실행 JSON·그림은 이번 납품 번들의 SUMMARY_KO.md/REPORT_KO.md와 artifacts/access_fifo_20261025에 보존한다.

## 지도
물리적 지상 접근이 확보된 고정 주거용량에만 신규 인구를 배치한다. 기존 빈 용량을 먼저 채우고 대기가 남을 때만 접근로를 건설한다. 합법 방향/층/회전에서 구한 free-flow 기회접근성 A=sum J exp(-T/tau)와 새 중심선 길이로 후보를 선택하고, 매 채택마다 망 비용을 재계산한다. 같은 평지·예산에서 일자리 anchor를 바꾸면 개발 위치도 바뀐다. 기존 주민을 재배치하지 않는다.

네 형태에서 120명씩 3epoch, 총360명 신규 점유와4개 접근로를 얻었다. epoch마다450m예산이며 총길이는 grid800.009484m,organic361.433371m,superblock800.010719m,ring128.111754m다. 부모 길이 장부와 cycle rank를 보존하고 검사 대상 중심선 불법교차0을 확인했다. 배경100k주민은 동결돼 있으며 신규360명의 별도 장부다. 8개의80m정방 빈 개발지는 외생 입력이고, 실제 필지분할/주택시장/혼잡 기반 개발 최적화가 아니다. 그림에서 반복 격자와 빈 원형 중심부는 남는다.

## 교통의 두 기준모형
ordered_lane: 동종 이동질량의 공통 clock Z(t)=integral U p dt를 사용한다. 진입마다 미래 지연을 고정하지 않고 Z_target=Z(entry)+L을 저장한다. Z(A(s))=Z(s)+L에서 A'(s)=v(s)/v(A(s))>=0이므로 이동구간의 순서가 보존된다. 출구 서버도 FIFO이며 막힌 head를 같은 차로의 뒤집단이 넘지 않는다. 독립 차로는 별도 instance다. Source는 tick 시작의 batch, 입구 용량/저장량은 경계 분할, 출구 서비스는 구간 내 연속 rate다. Spatial queue/shock나 finite-gap 안전모형은 아니다.

옛 Packed 반례는 early40초/late23초를 다시 재현했다. 새 reference는 early14.239134–14.339134초,late20.534951–20.634951초다. source가 원래 rate-bin에서 boundarybatch로 달라졌으므로 이를 matched speed benchmark로 부르지 않는다. 원 도시 코어 자체의 반례도 그대로 남아 있다.

103m/10mps,2veh batch,exit1veh/s의 최초/최종/평균은10.3/12.3/11.3초이며 quote와 실제 수송이 일치했다. Road residence22.6veh*s와 이동206veh*m도 닫힌다. Quote는 fixed rate/supply,즉시진입,미래경쟁없음의 조건부 값이다. 밀도변화의 dt1/.5/.25/.125초 결과는19.261029/19.214473/19.191858/19.180721초로 별도 기록했고 일반 수렴을 선언하지 않았다.

periodic_gap:K상태를r회 반복하고 각 선두차도 같은 법칙으로 진화시킨다. 모든 제어를 OLDstate에서 계산한 뒤 h_i_new=h_i+dx_(i+1)-dx_i로 동시 갱신한다. L=r sum(h+vehicle_length)와 앞/뒤 marked velocity 주변분포가 보존된다. 주기적 초기조건·환경·관측·제어와 결정론적 평행이동 공변성 아래 반복연산 R과 update F가 RF_K=F_(rK)R를 만족하는 정확한 대칭축약이다. 일반적인 pair분포 closure가 아니며 비주기 사건은 더 많은 대표상태를 요구한다.

4상태×7반복과28상태 직접확장을240단계 비교해 gap/speed/displacement 차이0,길이1540m 잔차-6.82e-13m,주변분포L1차이0이었다. 4상태×25000은100000차량이지만 물리길이5500km가 필요하다. 고정된10만주민 도시의 계산을 네상태로 해결한 것은 아니다.

32상태의 작은 Fourier모드에서 안전필터가 비활성일 때 이산선형행렬의 예측과 실제 성장률이 일치했다. dt=.5/.25/.1초에서.041192463/.038750457/.037246451 per s,최대복소모드 오차7.27e-15m,필터개입0. 안전성과 안정성은 다르며 정체를 없애기 위해 감쇠를 추가하지 않았다. Wolfram의 연속극한 분산식 잔차0과 경고 원문을 기록했다.

실제로 새로 건설한98.100223m 접근로 한 방향을 연결해 평균12.4174073061초를 예측/수송 양쪽에서 얻었다. 전체 도시OD/교차로의 새 물리 통합은 아직 하지 않았다. Static Braess65→80분도 유지했다.

## 검증과 미완료
납품격리workspace177passed(부모152+지도7+lane9+ring9),부모reference12개포함. 새 공개 seam RED와 추가 regression을 구분했다. 정지출발 dt1e-16의 소거오차,NaNledger통과는 실제 두 RED 뒤 수정했다. 3개 새 scientific core의 원격 blob과 실행본을 대조했고 부모 추적source diff0,Python3.13.5,stdlib-only다. 첫 plot 권한오류는 생성그림폴더만 교정해 해결했다.

전체repoCI/Python3.12/native독립subagent/실측보정/로컬전일100k/게임우월성은 NOT_RUN이다. 다음은 lane-group flux와 관측량을 통일하고 비주기 입출구에서 필요한 순서·상관 memory를 결정하는 단위다. 신규 주민을 실제 집계 여정수요로 바꾸는 adapter도 별도로 필요하다. 이 세 모듈을 그대로 붙여 완성된 kinetic city라 부르지 않는다.

## 재현
PYTHONPATH=src python -m pytest -q tests/test_access_development.py tests/test_ordered_lane.py tests/test_periodic_gap.py
위 명령은25개다. 전체177개는 부모 reference를 포함한 납품 code/의 tests 전체 범위다.

PYTHONPATH=src python -S tools/run_access_development.py --style organic
PYTHONPATH=src python -S tools/run_access_development.py --style ring_radial
PYTHONPATH=src python -S tools/run_access_fifo_traffic.py
python tools/plot_access_fifo.py

네 형태 전체는 grid_core와superblock_mixed도 같은 지도도구로 실행한다. 공통 outdir의 실제 JSON을 그림도구가 사용한다.

문헌: Waddell et al.2010 DOI10.5198/jtlu.v3i2.124의 접근성/입지 연결,Bar-Gera&Carey2022 DOI10.1016/j.trb.2022.04.002의 FIFO검사 문제,Bando et al.1995 DOI10.1103/PhysRevE.51.1035의 headway불안정성을 참고했다. 확인 범위는 publisher/author abstract와공식서지이며 해당전체알고리즘 재현이나 새로운선행부재 주장은 하지 않는다.
