# V02 동결 도시 지도 검수

이 감사는 8km synthetic 도시 6유형×고정 seed7/17/41의18개와,
4도로형태×5지형의20개(고정 seed순환)를 같은 resolution42에서 실행한다.
seed 교체나 좋은 지도만 선택하는 절차는 없다. 각 케이스의 실행 CitySnapshot JSON을
lossless xz(preset6)으로 동결하고 다시 load_city에 넣어 권위 geometry 검사를 거친다.
SVG는 동결 JSON에서만 생성하며 각 SVG metadata는 원본 압축 파일 SHA256을 포함한다.

지표는 resident/requested/unplaced 장부, 블록 면적 범위·compactness,
노드 차수 분포, section 길이/직선거리 detour, 교량 폐쇄 전후 합법 방향 도달성이다.
이것은 중심선·polygon mask·층간 clearance 검증이며 pavement envelope나
역사적 도시 복원·미학적 realism 인증을 뜻하지 않는다.

## 접근성 결함을 숨기지 않는 구분

현재 generated atlas를 V1으로 load한 결과에는 등록된 PortalRef가 없다.
registered portalcoverage=0, 해당 주민 전원이 registered unserved이며,
실제 등록 서비스 기반 access CDF는 null(미지원)이다. 인구를 삭제하거나
임의의 문을 등록해서 통과시키지 않는다.

별도로 모든 block boundary node를 가상 문으로 선언한 uniform-area depth0 quadrature
조건부 CDF를 측정한다. 이는 geometry의 접근 잠재력 진단이며 실제 등록 서비스가 아니다.
CDF threshold는30/60/120/300/600초, 보행속도1.4m/s다. quadrature mass를
주민 stock과 대조하지만 p95나 gate share의 인증은 아니다.

감사 결과가 AUDIT_COMPLETE_WITH_FINDINGS여도 geometry_status PASS는 독립적이다.
등록 gate 부족은 제품 연결의 미해결 항목으로 유지하며 전체 release 수용으로 확대하지 않는다.

## 실행과 시각 검수

`python tools/audit_v1_maps.py --frozen-seeds 7,17,41`

PNG contact sheet는 Pillow가 설치된 진단 환경에서 `--png`를 추가한다.
Pillow는 선택적 시각화 의존성이며 core geometry 감사에는 필요하지 않다.

각 케이스는 독립적으로 동결·행 결과를 저장하므로 중단 후 재실행은 SHA가 맞는
완료 케이스를 재사용한다. 원본 파일이 달라졌으면 자동 덮어쓰지 않고 오류를 낸다.
동결의 byte identity와 실제 물리 identity를 별개로 기록한다.
38회 전체 실행 후에는6개 유형 seed7의 Pillow contact sheet를 실제 JSON으로 만든다.
SVG/PNG와 숫자의 대조 결과는 VISUAL_REVIEW.json에 별도로 기록한다.
표현의 선 두께/축소/교량 붉은색은 진단용이며 교차 위반 판정은 load_city가 담당한다.

최대 수정회차는3이다. 이번 기본 감사에서 코드·지도 변경이 없으면 correction_rounds=0이며,
새 실제 geometry defect가 발견되면 입력과 결과를 보존하고 core owner에게 전달한다.
전체 CI·통합·교통 성능·실제 도시 보정은 실행하지 않는다.
