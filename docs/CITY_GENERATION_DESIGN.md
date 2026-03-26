# City Generation Design

## 생성 파이프라인
1. barrier / terrain field 생성
2. ring / radial / branch / grid skeleton 생성
3. hierarchy 부여:
   - expressway
   - principal arterial
   - collector
   - local
4. zone assignment:
   - bedtown
   - CBD
   - commercial
   - industrial
   - mixed
   - leisure
5. CSUR-inspired cross-section assignment
6. interface synthesis:
   - base
   - shift
   - transition
   - ramp
7. node compilation:
   - through continuity
   - turn-pocket separation
   - conflict suppression
   - symmetric/asymmetric two-way compatibility
   - signal eligibility

## 핵심 원칙
- geometry만이 아니라 demand substrate까지 함께 생성
- static catalog보다 on-demand parametric compile
- UI가 spline/editor 같아도 내부 표현은 typed carriageway graph
