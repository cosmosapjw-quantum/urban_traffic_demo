"""Summarize paired observations from the regular 6 GiB and rebound 7.5 GiB runners."""
import argparse
import json
from pathlib import Path


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("control", "control-monitor", "wide", "wide-monitor", "output"):
        p.add_argument("--"+name, type=Path, required=True)
    args = p.parse_args()
    low, high = rows(args.control), rows(args.wide)
    lo_mon, hi_mon = (json.loads(f.read_text()) for f in [args.control_monitor, args.wide_monitor])
    binding = next(r for r in low if r["phase"] == "binding")
    reb = next(r for r in high if r["phase"] == "rebound")
    low_state = next(r for r in low if r["phase"] == "restored")
    high_state = next(r for r in high if r["phase"] == "restored")
    assert low_state["original_ledger_exact"] and low_state["time_s"] == high_state["time_s"]
    assert high[0]["native"]["sha256"] == binding["binary"]
    assert high[0]["outer_bytes"] == binding["address_cap"] == 8*1024**3
    assert high[0]["reference_sha256"] == binding["reference_sha"]
    assert high[0]["matrix_sha256"] == binding["matrix_sha"]
    assert reb["original_sha256"] == binding["raw_sha"]
    assert reb["new_native_identity"] == high_state["runtime_identity"]
    assert high_state["construction_byte_budget"] == high[0]["budget"]
    def arm(events, budget, peak, exit_code):
        validated = [r for r in events if r["phase"] == "validated"]
        attempts = [r for r in events if r["phase"] == "attempt"]
        failure = next((r for r in events if r["phase"] == "rejected"), {})
        return dict(internal_bytes=budget, outer_bytes=8*1024**3, child_exit=exit_code,
                    max_validated_time_s=validated[-1]["time_s"] if validated else low_state["time_s"],
                    validated_s=[r["time_s"] for r in validated],
                    tick_wall_s=[r.get("wall_s",r.get("tick_wall_s")) for r in validated],
                    last_attempt_s=attempts[-1].get("target", attempts[-1].get("time_s")),
                    rejection=failure.get("message", failure.get("error")), high_water_bytes=peak)
    result = dict(schema="metroflow.research.conditional-budget-comparison.v1",
        same_matrix_sha256=binding["matrix_sha"], common_native_sha256=binding["binary"],
        reference_sha256=binding["reference_sha"], starting_time_s=low_state["time_s"],
        restoration_physics=high_state["matched_keys"], identity_rebind=reb,
        control=arm(low, 6*1024**3, lo_mon["sampled_process_high_water_bytes"], lo_mon["child_exit"]),
        experimental=arm(high, high[0]["budget"], hi_mon["observed_bytes"], hi_mon["child_exit"]),
        release_eligible=False)
    args.output.write_text(json.dumps(result,indent=2)+"\n")


if __name__ == "__main__":
    main()
