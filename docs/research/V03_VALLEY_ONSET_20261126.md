# Original-clock, finite-response car onset

This optional arm tests which part of the 25,720 s outlet bias survives when the car source law and route transit use the original native conventions. Source, route graph, demand and three reference snapshots are fixed in advance. No parameter is fitted to the snapshots.

## Exact source phase

The native joint step from t to t+h calls journey prepare at t, then advances the road. Prepare admits the previously unreleased rank interval of the source CDF through t, replaces its birth times by its exact first-moment centroid and retires access atoms with birth plus delay no later than t. At the early outward work peak the uniform source starts at S=25,200 s, ends at E=32,400 s, and has no predecessor restrictions. Let n=(E−S)/h. At the observation time T the last processed prepare time is t=T−h. For each original access atom of delay a, its completed rank-bin count is

    N(t,a) = max(0, min(n, (t−S)/h, floor((t−S−a+1e−10)/h+1/2))).

Indeed the kth midpoint is S+(k−1/2)h, its mass m/n, and it cannot be emitted before the end of its own rank bin. Therefore the class-wide cumulative native offer is Σ_i m_i Σ_a p_i(a) N(t,a)/n. Every original residence–purpose–route cohort stays identifiable. The formula depends on atom delays even when two laws have the same mean. The script joins the compiler's original cohort sequence to all 304,368 staged calendar legs, verifies the masses, means, purpose and projected-network hash, and retains the original law keyed by activity identity. It independently checks the identity against native car road entries at all three clocks.

## Route passage

For a single dilute car, the original local equation is dv/dt=clip((V−v)/τ,−b,a₊), where V=min(road cap,preferred speed). The source velocity and class parameters come directly from the original static preparation. Integrating the saturated segment and then the exponential relaxation gives the original project characteristic. We invert its displacement for each original directed group and carry its exit velocity into the next group. A sample at every route depth is compared numerically with the repository's independent scalar first-passage function. The stable comparison is against three historic native receipts at T=25,700, 25,710 and 25,720 s. They have a common city and calendar and a single bus segment per run, four buses completed, zero bus mass on-road, and no released freight at these clocks.

The four arms give the following comparisons.

- **Original point queue** uses its measured 10 s C++ projection with mean access, finite exit capacity and instantaneous free-speed entry.
- **Phased source + free flow** uses the exact native birth/access law, the same physical routes, and free-speed travel without a queue. All three revised route arms compute a dilute-limit passage estimate conditional on the selected route clock.
- **Phased source + kinetic motion** replaces only free-speed transit by finite response from zero entry speed. It carries speed through each turn.
- **Phased source + kinetic motion + tick transfers** also places source and intergroup packet insertion at the native tick-end boundary. New source mass enters the cell after the current step's propagation. Each intergroup transfer is available for motion on the next step. The observed effective route delay on the original grid is h + Σ_e h ceil(p_e/h), where p_e is the integrated link passage time. Rounding the final link produces the same cumulative outlet observed at aligned T. The inferred closure retains carried speed across the unused part of the transfer tick. Native mixture speeds, queues, finite receiving and latent/gap dynamics remain unresolved at this level.

See `v1_journey.rs` (prepare, advance_owned_joint), `v1_road.rs` (characteristic, incoming packet assembly after transfer), and `src/metroflow/foundation_kinetics.py` (characteristic and passage). A car output match at neighboring observations would validate just this onset window. The original calendar still needs native multimodal and congestion validation.

To reproduce, prepare the C07 network with its own driver and use its C++ binary. Run from a directory containing the two Python files:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python physical_onset.py "$REPO" "$PREPARED" "$PREPARED/point_queue" PHYSICAL_ONSET.json
```

## Measured outcomes

| t (s) | Native car exits (veh) | C07 10 s queue | Exact source + free flow | + finite response | + tick transfers | Transfer arm relative error |
|---:|---:|---:|---:|---:|---:|---:|
| 25700 | 139.5983 | 208.1669 | 210.5489 | 207.1417 | 144.7251 | +3.67% |
| 25710 | 147.9677 | 221.1605 | 223.4801 | 219.9397 | 153.6346 | +3.83% |
| 25720 | 156.6618 | 234.6221 | 236.8980 | 233.2355 | 162.8985 | +3.98% |

The 25,720 s absolute outlet error fell from 77.9603 to 6.2367 veh, a 92.00% reduction. It stayed positive at every tested clock. The historical native stock includes mass pending at the road subsystem boundary. With exact offers and the revised transit at 25,720 s, the projected road-subsystem stock is 807.7674 veh against 814.0041 native (−0.77%). The native cumulative car offers at all three clocks are reproduced to within 1.82e−11 veh. Entry from rest alone had a small effect. Stepwise downstream availability accounts for most of this correction in this ordered ablation. The three snapshots are adjacent observations of the same city and peak, so transferability to later, congested times and other cities remains open.

The full computation took 59.18 wall s and 320,668 KiB peak RSS, including three C07 onset replays. Source parameters were 10 m/s preferred speed, 0 m/s injection speed, 2 s relaxation, 2 m/s² acceleration and 4 m/s² braking. The vectorized passage outputs sampled over route depths agreed with the original scalar kinetic reference to 1.02e−11 in their respective SI units.
