"""Recompute fixed-window measurements from committed MetroFlow run receipts."""
import argparse
import json
import math
from pathlib import Path
from statistics import mean


def native_tip(run):
    final = run["completed_horizons"][-1]
    last = final["native_tick_wall_s"][-15:]
    assert len(last) == 15 and all(t > 0 for t in last)
    step_s = final["elapsed_physical_s"] - run["completed_horizons"][-2]["elapsed_physical_s"]
    step_s /= len(final["native_tick_wall_s"])
    times = [i * step_s for i in range(len(last))]
    log_wall = [math.log(v) for v in last]
    x_bar, y_bar = mean(times), mean(log_wall)
    slope = sum((x-x_bar)*(y-y_bar) for x,y in zip(times,log_wall)) / sum((x-x_bar)**2 for x in times)
    unexplained = sum((y-y_bar-slope*(x-x_bar))**2 for x,y in zip(times,log_wall))
    total = sum((y-y_bar)**2 for y in log_wall)
    return {
        "physical_tick_s": step_s,
        "first_tick_end_s": final["completed_time_s"] - times[-1],
        "last_tick_end_s": final["completed_time_s"],
        "first_wall_s": last[0], "last_wall_s": last[-1],
        "observed_window_wall_doubling_simulated_s": math.log(2)/slope,
        "log_fit_r_squared_descriptive": 1-unexplained/total,
        "local_last_tick_simulated_seconds_per_wall_second": step_s/last[-1],
        "scope": "one 15-tick morning window; four partial-day timing segments; same-host diagnostics",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("repo", type=Path)
    args = ap.parse_args()
    def from_repo(name):
        return json.loads((args.repo/name).read_bytes())
    base = "artifacts/v03_remainder_rebuild_20261124/"
    old = "artifacts/v1_v03_workspace_20261117/"
    gate = from_repo(old+"gate_final_valley_weekday_s7.json")
    observed = from_repo(old+"diag_observe_valley.json")
    comparison = {name: {key: run.get(key) for key in ("simulated_s","wall_s","peak_rss_bytes","reason","status")}
                  for name,run in (("enforced",gate),("observation",observed))}
    print(json.dumps({"historical_valley":comparison,"bounded_baseline_tip":native_tip(from_repo(base+"L10_fresh0.json"))},indent=2))


if __name__ == "__main__":
    main()
