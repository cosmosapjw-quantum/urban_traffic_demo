# R6 독립 검토: age moment envelope

- 기록일: 2026-11-23.
- 대상 worktree: `/home/cosmosapjw/worktrees/urban-traffic-v03-event-store-moment-envelope-20261123`.
- 범위: 아래 3개 파일의 읽기 전용 과학 검토, 직접 유도, 별도 정확유리수 검산. Native 코드·문헌 접근 이력·f64 누적 오차 certificate는 검토하지 않았다.
- 결론: 검토 범위에서 필요한 수정 0건. 보편적 명제는 직접 유도로 판정했고, 유한 검사 통과를 증명으로 대체하지 않았다.
- 이후 부모가 전달한 R5 commit/push 기준: `eb544bc639e40e7172e1b14a0fda8dfd3c89211e`. 이 commit/push는 부모가 확인한 상태이며, 본 기록 작성에서 재확인하지 않았다.
- 본 파일은 이미 완료된 1회 독립 검토를 기록한다. 기록 단계에서 검토·실험을 재실행하거나 확장하지 않았다.

## 1. 검토 파일 identity

SHA-256은 독립 검사 실행 당시 각 파일의 bytes를 읽어 계산한 값이다.

| 파일 | SHA-256 |
|---|---|
| `src/metroflow/v1/age_moment_envelope.py` | `b807d2d03e5db04c49feebf3fb2663f82a5e1dddc1c1868afe36aef59997d87f` |
| `tests/research/test_v03_age_moment_envelope_20261123.py` | `f771cbd5e3d48d816588bd951e4255e5d7e00b29f7c4ab0fc14b900ffc3d1d64` |
| `docs/research/V03_AGE_MOMENT_ENVELOPE_THEORY_20261123.md` | `882121941556b58f6cf97eaf5f0b87c0e6115420b7d5b36110f0c3ee82f18031` |

## 2. 직접 유도와 claim status

가정은 유한한 양의 측도, \(m>0\), \(0\le L<H\), \(mL\le A\le mH\), 알려진 support \([L,H]\)다. \(m=0\) 및 \(L=H\)는 별도 정확 극한으로 처리한다. \(\mu=A/m\), \(g_u(a)=(a-u)_+\).

1. **Sharp envelope — derived.** Jensen로 \(K_-(u)=m g_u(\mu)\). Convex chord를 적분하면
   \[
   K_+(u)=\frac{mH-A}{H-L}g_u(L)+\frac{A-mL}{H-L}g_u(H).
   \]
   \(m\delta_\mu\)와 endpoint 질량 \((mH-A)/(H-L),(A-mL)/(H-L)\)이 각각 모든 threshold에서 하계와 상계를 동시에 달성한다. 추가 calendar·원자 수 제약까지 포함한 sharpness는 이 결론에 포함하지 않는다.

2. **Gap와 genuine nested refinement — derived.** Gap은 support 밖에서 0이고, \(L\le u\le\mu\)에서는 \(m(H-\mu)(u-L)/(H-L)\), \(\mu\le u\le H\)에서는 \(m(\mu-L)(H-u)/(H-L)\). 최대는 \(u=\mu\)에서
   \[
   \frac{m(\mu-L)(H-\mu)}{H-L}\le\frac{m(H-L)}4.
   \]
   하계 nesting은 \((\sum_i z_i)_+\le\sum_i(z_i)_+\), \(z_i=A_i-m_i u\)로 성립한다. Parent chord는 각 child endpoint에서 \(g_u\)를 지배하므로 child chord도 지배한다. 실제 동일 측도의 disjoint parts, child support의 포함 관계, 정확한 mass/moment 합이 필요하다. 여러 block 최대 gap의 합은 전체 최대 gap의 상계이며 일반적으로 등호는 아니다.

3. **Strict-tail/CDF secant — derived.** 원자별 forward kernel은 \(\min(1,\max(0,(a-v)/h))\le1_{\{a>v\}}\). Backward kernel은 \(1_{\{a\ge v\}}\) 이상이다. 이를 적분하고 K의 안전한 하·상계를 대입하면 구현의 secant 구간이 나온다. \(a=v\)에서 forward는 0, backward는 1이다. \(L_i>v\), \(H_i\le v\)의 support 추가 판정도 정확하다.

4. **Fixed-source censor — derived.** 관측 질량 O, source \(M^*\), 미관측 \(C=M^*-O\)를 \(+\infty\)에 놓으면 유한 v에서 \(F(v)=(O-\nu((v,\infty)))/M^*\). 또한 \(w\ge u+\delta\Rightarrow(w-u)_+\ge\delta\)이므로
   \[
   P(W_H\ge u+\delta)\le [C+\min(O,K_+(u)/\delta)]/M^*.
   \]
   Source 분모를 유지하는 구현이 맞다. Passage incidence는 이 수식만으로 고유 journey 완료 분포가 되지 않는다.

5. **Birth mapping와 단위 — derived.** 공통 clock t에서 \(a=t-b\), \(A=mt-B\), \([L,H]=[t-b_+,t-b_-]\). \(t,b\mapsto t+s,b+s\), \(B\mapsto B+ms\)에서 불변이다. 질량·moment·support 사실은 평균만으로 복원할 수 없다. m은 관측 질량, A와 K는 질량·시간, secant tail은 질량, 정규화 CDF는 무차원이다.

**Implementation status:** 아래 독립 exact finite 검사 범위에서 implementation-verified. Native support/first-moment 의미와 rounding certificate는 조건부로 남는다.

## 3. 실제 독립 실행과 관측 출력

저자의 pytest를 재실행한 결과가 아니다. Remote Desktop Commander에서 `python3 -B - <<'PY'` 형태의 별도 메모리 내 Python/Fraction 검사를 실행했다. 모듈은 importlib로 직접 로드했고, 원래 파일들을 읽어 SHA-256을 계산했다. 검사 파일·원본 stdout 로그 파일을 생성하지 않았다.

수정된 실행은 당시 도구 출력에서 다음 값과 `ALL_ASSERTIONS_PASSED`를 실제 관측했다. 아래 표는 관측된 결과의 기록이며 원본 로그 파일을 뜻하지 않는다.

| 독립 검사 | 실제 수 |
|---|---:|
| 비영 4원자 분포 | 80 |
| Envelope 직접 원자합 비교 | 1,440 |
| Strict-tail/CDF 직접 원자합 비교 | 8,640 |
| Censor tail 직접 원자합 비교 | 8,640 |
| Nested partition threshold 배치: K 및 CDF 함께 검사 | 720 |
| Birth clock shift | 4 |
| Atom CDF 비수렴 예 | 3 |

Zero mass, 전원 censor, degenerate support, 각 block의 평균 위치에서 최대 gap도 확인했다. 이 항목은 위 count에 별도 수를 부여하지 않았다.

### 검사 입력 오류와 교정

첫 실행은 위 envelope/CDF/censor/nesting 검사를 통과한 뒤 birth fixture에서 중단됐다. 검토자가 \(i=-3,\ldots,3\)에 질량 \((i+1)/2\)를 사용해 음의 질량을 넣은 것이 원인이다. 생산 코드는 `ValueError: age moment is incompatible with mass and support`로 거절했다. 질량을 양수 \((i+4)/2\)로 고친 뒤 전체 검사를 재실행했고 위 성공 출력을 관측했다. 실패 분류는 **검토용 입력 오류**이며 생산 코드 실패가 아니다. 그 뒤의 보고서 작성에서는 재실행하지 않았다.

## 4. 재현 recipe

아래는 당시 메모리 검사의 입력과 assertion을 재구성할 수 있는 절차다. 이 절차 자체를 새로 실행했다는 뜻은 아니다.

1. Python Fraction으로 ages \(=(0,1/3,2,7/2)\), 각 질량 \(c/3\), \(c\in\{0,1,2\}\)의 Cartesian product에서 전부 0인 조합만 제외한다: 80개.
2. Thresholds \(=(-1,0,1,2,3,4,5,1/3,7/2)\). 각 분포마다 support \([0,4]\)와 양의 질량 원자의 실제 min/max 두 가지를 사용한다.
3. \(m=\sum m_j,A=\sum a_jm_j\)로 block을 만들고, 직접합 \(K(u)=\sum_jm_j(a_j-u)_+\)가 envelope 안에 있는지 검사한다. 각 block에서 \(u=A/m\)의 gap이 반환 uniform gap과 같은지, uniform gap이 \(m(H-L)/4\) 이하인지 확인한다.
4. Steps \(=(1/5,3/2,7)\), sources \(=(m,m+7/3)\). 직접합 \(\sum_{a_j\le u}m_j/M^*\)와 \(\sum_{a_j>u}m_j\)를 CDF/strict-tail 구간과 비교한다. Censor 실제 tail \([M^*-m+\sum_{a_j\ge u+h}m_j]/M^*\)가 반환 tail 상계 이하이며 그 상계가 1 이하인지 확인한다.
5. 같은 80개 분포에 coarse \([0,4]\) → 처음 두 원자 support \([0,1/3]\)와 나머지 \([2,7/2]\) → singleton 원자 block의 실제 분할을 사용한다. 9개 threshold마다 K 하계 증가·상계 감소·마지막 exactness를 확인한다. CDF도 step \(3/2\), source \(m+1\)에서 같은 nesting과 마지막 exactness를 확인한다.
6. Birth fixture: \(b_i=i/3\), 질량 \((i+4)/2\), \(i=-3,\ldots,3\), \(t=10/3\), birth support \([-1,1]\). \(A=\sum_i(t-b_i)m_i\)와 mapping을 비교하고 shifts \((-100,0,7/11,100)\)에 대해 \(B\mapsto B+ms\), \(t,b_\pm\mapsto t+s,b_\pm+s\) 결과가 동일한지 확인한다.
7. Zero block \(B(0,0,0,4)\)의 K=0, empty observations/source5의 CDF=0 및 censor tail 상계=1을 확인한다.

### 독립 최소 반례 확인

- **Nonnested bin 증가:** 단위 질량 원자 \(0,1,2,3\), \(u=3/2\). 두 부분 \(\{0,1\},\{2,3\}\)의 envelope는 \([2,2]\). 세 부분 \(\{0\},\{1,2\},\{3\}\)는 \([3/2,2]\). Bin 수만 늘려서는 하계 단조성이 없다.
- **Atom에서 CDF 수렴 제한:** \(n=10,100,1000\), \(m=1,A=2\), support \([2-n^{-2},2+n^{-2}]\), step \(h=1/n\), source2. Gap와 gap/h가 0으로 가더라도 \(v=2\)의 반환 CDF는 \([0,1/2]\)로 남는다. 실제 \(\delta_2\)의 CDF는 \(1/2\). 따라서 문서의 continuity-point 제한이 필요하며 정확하다.
