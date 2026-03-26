# Coding Standards

## units
- time conversion 명시
- length = meter
- speed = m/s 내부 고정
- generalized cost는 시간 [s]로 통일

## state
- mutable global state 금지
- WorldState를 통해서만 상태 이동
- version counter 없는 cache 금지

## JAX
- core loop는 pure function
- explicit PRNG
- scan/vmap/segment ops 우선

## tests
- 새 상태변수/계약 추가 시 테스트 동시 추가
- numerical method 변경 시 benchmark 필수

## learning
- baseline fallback 필수
- reward/cost clipping rule 명시
- update cadence 문서화
