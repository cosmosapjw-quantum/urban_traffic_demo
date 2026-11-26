# Valley staged finite-capacity road arm

The paired experiment propagates the full original routed-car projection through a finite-capacity point queue. It uses the staged kinetic timing identified in the earlier, transport-unconstrained source-convolution experiment. Both arms in this comparison operate finite-capacity servers.

## Governing rule

A C07 cohort of mass $m$ has its usual rank-midpoint release $r$, deterministic mean origin access time $a$, and physical road step $h=10$ s. The first road admission occurs at $h+h\lceil(r+a)/h\rceil$. This enforces preparation before the observed road interval. The measured native source uses the full access distribution; its atomwise CDF convolution and the mean-access closure in this queue can differ. Destination walk uses its inherited continuous mean. The return again requires the forward completion, dwell, and its paired schedule rank.

Starting from rest on the first link, integrate the original speed-response characteristic up to each distance. Carry the resulting physical exit speed into the next link in each path. For an entry at road boundary $s$, elapsed characteristic time $\tau$, capacity $c$ (veh/s), batch mass $m$ (veh), and previous service finish $F$, define
$$u=s+\tau,\quad w=\max(0,F-u),\quad F'=u+w+m/c,\quad s'=h\lceil F'/h\rceil.$$
The continuous busy clock becomes $F'$ and the next link is available at $s'$. Event ties use the inherited deterministic order. The finite queue charges $m w$ vehicle-seconds; the report counts that charge when the link reservation is made. Mid-bin injection, point-queue storage and serve-in-entry-order are assumptions of this reduced model. The implementation includes a $10^{-12}$-tick tie tolerance. Waiting and observation lag do not cause a second acceleration from rest. Finite receiving, individual movement conflicts, congestion feedback to speed, multimodal transfers and building-level access dispersion remain outside this run.

The sidecar comprises 762,716 link passages for 38,916 routes, generated from the original city and native car law. Link-level free travel in C07 is checked against the corresponding original road distance/target. Selected original scalar passage times and exit speeds across the route depths agree with the vector result within 1.95e-13 in the respective SI units. The two-unit-batch test gives continuous finishes of 69 and 71 s, staged exits at 70 and 80 s, and 2 veh·s waiting.

## Real projected Valley runs

Each pair of values below is C07 / staged finite-capacity queue. The demand quadrature varies, while the road clock of the revised arm stays at 10 s. The final two columns refer to the revised arm. The native 25,720 s routed-car reference was 156.66178 veh exited, 970.66585 admitted, and 814.00407 inside the road subsystem.

| Release mesh (s) | Horizon (s) | Exited at 25,720 s (veh) | Road stock at 25,720 s (veh) | Cumulative service waiting at horizon (veh·s) | Events | Wall (s) |
|---:|---:|---:|---:|---:|---:|---:|
| 600 | 86400 | 123.6165 / 65.2835 | 1250.0019 / 1297.5225 | 765,157.5 / 2,421,859.0 | 54,153,024 | 20.61 |
| 300 | 86400 | 210.6340 / 139.4804 | 597.6738 / 645.3564 | 352,962.2 / 1,889,094.1 | 108,306,048 | 48.57 |
| 150 | 86400 | 226.6878 / 145.5992 | 793.3259 / 852.5814 | 180,798.4 / 1,595,576.4 | 216,612,096 | 124.93 |
| 10 | 25720 | 234.6221 / 146.9605 | 761.6663 / 822.8946 | 135.2 / 11,641.9 | 17,189,950 | 7.38 |

On the 10 s injection mesh, the staged finite-capacity arm admitted 969.85511 veh and exited 146.96046 veh. Its exit discrepancy is -9.70132 veh, and the point-queue change reduced absolute error by 87.56%. The independent full-source-distribution, unconstrained-transport arm had 162.89848 exited. The source laws differ, so subtracting these two outputs does not isolate congestion. The 150 s full-day arm completed 57,095.94033 vehicle trips at 86,400 s with zero pending active/road inventory, permitting evaluation of an entire projected day under this clock. Delay and onset statistics still depend on demand quadrature size. These are conditional predictions from one fixed-route car model, with timing chosen using this onset. Native V03 execution counts are unchanged by this projection.

The same fixed executable was evaluated at 25,730 and 25,740 s without any receipt input. The projected admitted/exited/stock triples in vehicles are 25730 s = 996.2884/155.6362/840.6522; 25740 s = 1022.7217/164.6006/858.1211. These two output predictions use the mean-access finite-capacity closure.

## Reproducibility

Run the commands from the checkout on an environment with its native Python binding, NumPy, C++17, POSIX patch and GNU time. The canonical C07 runner reconstructs the source network and its original matched baselines. REPO is the absolute checkout path and OUT is a new directory. PREP and RUN are introduced below. PHASE_SOURCE contains the companion native_phase_boundary.py. The regenerated sidecar SHA-256 is `a310ee706ae3eb64ba35eef2c9275da38141dbd32eb89f86bcb6a90c89bd73c1`. PHASE_QUEUE_RESULTS.json records the matched raw stdout and source identities, inventories and wall measurements.

```sh
REPO=$(git rev-parse --show-toplevel)
OUT=$(mktemp -d)
PREP="$OUT/c07"
RUN="$OUT/phase"
C07="$REPO/tools/research/valley_point_queue"
PHASE_SOURCE="$C07/onset"
STAGED="$C07/staged_queue"
REFERENCE="$REPO/artifacts/v03_structural_reset_20261126/valley_point_queue/PHYSICAL_ONSET.json"
mkdir -p "$RUN"
python3 "$C07/run_point_queue.py" "$REPO" "$PREP"
cd "$RUN"
python3 "$STAGED/prepare_phase_passages.py" "$REPO" "$PREP" "$PHASE_SOURCE" passages.txt > preparation.json
patch -o point_queue_phase.cpp "$C07/point_queue.cpp" "$STAGED/phase_queue.diff"
g++ -std=c++17 -O3 -Wall -Wextra point_queue_phase.cpp -o phase_queue
for b in 600 300 10 150; do
    h=86400
    if [ "$b" = 10 ]; then h=25720; fi
    /usr/bin/time -f '%e %M' -o "phase_${b}.time" ./phase_queue "$PREP/network.txt" "$b" -1 1 passages.txt "$h" > "phase_${b}.out"
done
for h in 25730 25740; do
    ./phase_queue "$PREP/network.txt" 10 -1 1 passages.txt "$h" > "forward_${h}.out"
done
python3 "$STAGED/summarize_phase_queue.py" "$PREP" . ./phase_queue "$REFERENCE" PHASE_QUEUE_RESULTS.json
```

The summary cross-checks the two-batch fixture, road and door ledgers at every snapshot, per-day accepted totals, the inherited 10 s baseline and the historical native onset receipt.
