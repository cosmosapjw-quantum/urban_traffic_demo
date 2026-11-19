# V03-FIFO-SERVICE-STREAM: bounded implementation research (2026-11-20)

Source parent b94670d03407a4fd2626884f58a1a293f57fd7cc; isolated branch research/v03-fifo-service-stream-20261120. Original native V03 traffic model, 100k resident city inputs, 24h full-day campaign (9 runs), original process limits and physics parameters remain unchanged.

## C1. Test-first exact served Part iterator

New function served_parts(parts, fraction) in crates/metroflow-rust/src/v1_road.rs yields original Part rows in input order without materializing an intermediate served Vec. It repeats EXACTLY the original binary64 operations from portion: let m=p.mass * fraction; keep only m>0; copy the original tag/offset/endpoint bits, set q.mass=m and q.birth *= fraction. No rate, hazard, source fitting, receiver or cumulative scheduling code changed. Original portion still exists unchanged for separate pending/remainder uses.

Independent tests are placed in the existing shadow-only v1_lineage_shadow.rs test module and use the original eager portion as the **separate reference**, comparing complete Part tag/offset, mass/birth and endpoint bits and the original expansion sum over served values. Tested both Uniform and Mixed packet storage, signed zero endpoints, subnormal mass, fractions 0/1/0.3/0.7/min-subnormal/-0 and 4 independent seed-fixed random input sizes (1,17,128,1024) ×23 fractions, with direct source API equality. RED first produced E0432 unresolved import served_parts; after the implementation the same two tests both passed.

SES-1/2 source derivation: original portion and the lazy iterator apply identical deterministic per-row transformation and filter, preserving subsequence order. Original expansion sum is a deterministic fold, so equal term sequence yields bit-equal summation. The result requires the actual service loop to consume the stream without changing its original receiver/free/space update and source queue mutation semantics. It does not yet prove full-day network FIFO or a memory/runtime reduction.

Status after C1: IMPLEMENTATION_VERIFIED_SCOPED_ORDERED_PART_OPERATION, production V03 path NOT_YET_SWITCHED. Execute full Rust regression and keep source code diff isolated before C2 service-loop integration. This milestone is a meaningful material source/test slice and pushed separately with remote SHA readback. Project plan remains 19/21 scoped, V03 BLOCKED and full-day 0/9.
