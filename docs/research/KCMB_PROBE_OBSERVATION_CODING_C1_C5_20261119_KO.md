# KCMB affine probe-selection: coding C1–C5

2026-11-19 KST. Research-only opt-in observable module, separate branch research/kcmb-probe-observation-20261119. Parent physical source 916e5124dfa6f735cf067e596efa2b6c29411c9c. Prior R1–R10 theory on this branch is commit 96e5327c0cbd9e22455f6201747b9a4db0ea6432.

## C1 goal and acceptance
The already constructed six-moment microscopic Markov + conservative transport physically differentiates bulk population mean speed and a hypothetical speed/control weighted probe mean. Deliver one pure source module exposing declared weights, exact finite-dimensional read-only mapping and stationary oracle, without rewriting any V1, KCMB transition, or Chicago source data. Original V03 24h 3-city×3 runs remains BLOCKED 0/9. Actual CTA reporting algorithm not identified.

## C2 formulas, units and code contracts
Existing physical six moments for each class are (m0,m1,j0,j1,z0,z1), all with vehicle-equivalent units; j represents v/U and z represents (v/U)^2. Declare nonnegative w_sigma(u)=a_sigma+b_sigma*u with a_sigma>=0 and a_sigma+b_sigma>=0 for sigma0,1 and 0<=u<=1. Exact probe numerator U Σ(a_sigma j_sigma+b_sigma z_sigma) has [m/s * vehicle-equiv]; denominator Σ(a_sigma m_sigma+b_sigma j_sigma) has [vehicle-equiv]. Mean is their ratio [m/s] if denominator>0, otherwise raise ValueError without inventing zero speed.

Source module src/metroflow/v1/kcmb_probe_observation.py:
- immutable AffineProbeWeights and endpoint positivity validation.
- selected_probe_mean_speed(...) and pooled_probe_mean_speed(...) using support-weighted sum of numerators/denominators, not arithmetic mean over cells.
- stationary_six_moments(p,k,tau,mass=...) from the frozen continuous-time microscopic Markov generator.

The class and road states are immutable inputs; observation readback cannot alter mass, source age, route identity or stored kinetic phase.

## C3 error and closure
No higher-order closure appears for an affine probe weight: j and z suffice, and the formula is exactly determined by the six moments (modulo floating-point). Independent nonlinear selection such as w(u)=u² requires a third moment; two positive measures can have identical first two moments but different third (constructive epsilon perturbation at u={0,1/3,2/3,1}). All input moment arrays are checked against the existing realizability cone; positive weight scaling leaves selected speed unchanged. The observation never infers actual CTA bus GPS selection weights.

Local stationary oracle with alpha=kp, nu=k(1−p), lambda=k tau has j1=p(1+alpha tau)/(1+lambda), j0=p−j1, z1=j1(2+alpha tau)/(2+lambda), z0=j1−z1 and variance p(1−p)/(1+lambda). Even the source speed distribution need not have this full stationary velocity variance: the transport solver will be separately exercised.

## C4 environment and scope
New source and tests in an independent worktree, running Python3.12 with the already installed Rust optional extension. No external network during source execution, no new credentials. Any evaluation of the official Chicago 12+12 records is performed only through existing source-frozen tool and its separate held-out date. Full city simulation not attempted.

## C5 actual red/green implementation
The new public tests were authored before source implementation. Initial placeholder raised NotImplementedError and invalid weight tests failed; 20 tests failed with 1 non-implementation structural test passing. After implementation all 21 test cases pass, including explicit independent microscopic weighted sums, positive/negative bias identity, zero support, invalid weights and moments, support-weighted multi-class pooling, six-element stationary generator RHS and a constructive nonlinear-weight counterexample. No assertions were weakened merely to obtain green.

After current scope-dependent regression verification, commit the new source, tests and report and push this C1–C5 stage with remote SHA readback. Then separately implement C6–C10 actual KCMBCorridor bus-labelled runtime scenarios and numerical receipts. Do not count this stage as empirical validation of any hypothetical η parameter or of the original V1.
