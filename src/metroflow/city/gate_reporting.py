from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from metroflow.city.graph import NodeKind, RoadClass


def _required_mapping(report: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    if key not in report or not isinstance(report[key], Mapping):
        raise ValueError(f"missing or invalid mapping: {key}")
    return report[key]


def serialize_ci_report(report: Mapping[str, Any]) -> dict[str, Any]:
    metrics = dict(_required_mapping(report, "metrics"))
    thresholds = dict(_required_mapping(report, "thresholds"))
    versions = dict(_required_mapping(report, "versions"))

    for key in ("hard_fail_rate_max", "ring_radial_connectivity_min", "incident_seed_pass_rate_min"):
        if key not in thresholds:
            raise ValueError(f"missing threshold key: {key}")

    for key in ("oracle_version", "corpus_version", "budget_version", "generator_version"):
        if key not in versions:
            raise ValueError(f"missing version key: {key}")

    return {
        "metrics": metrics,
        "thresholds": thresholds,
        "versions": versions,
        "hard_fail_reasons": list(report.get("hard_fail_reasons", [])),
        "reason_codes": list(report.get("reason_codes", [])),
    }


def build_active_sidecar_hierarchy_report(*, topology: Any) -> dict[str, Any]:
    metadata = dict(getattr(topology, "metadata", {}) or {})
    links = tuple(getattr(topology, "links", ()) or ())
    nodes = tuple(getattr(topology, "nodes", ()) or ())
    road_class_counts: dict[str, int] = {}
    for link in links:
        key = str(getattr(getattr(link, "road_class", None), "value", getattr(link, "road_class", "")))
        road_class_counts[key] = road_class_counts.get(key, 0) + 1
    interchange_like_node_count = sum(
        1
        for node in nodes
        if getattr(node, "kind", None)
        in {NodeKind.INTERCHANGE, NodeKind.BRIDGE_ENDPOINT, NodeKind.RAMP_SPLIT, NodeKind.RAMP_MERGE}
    )
    hierarchy_module_counts = dict(metadata.get("hierarchy_module_counts", {}) or {})
    return {
        "engine": str(metadata.get("engine", "")),
        "call_path": str(metadata.get("active_call_path", "")),
        "road_class_counts": dict(sorted(road_class_counts.items())),
        "expressway_link_count": int(road_class_counts.get(RoadClass.EXPRESSWAY.value, 0)),
        "ramp_link_count": int(road_class_counts.get(RoadClass.RAMP.value, 0)),
        "bridge_link_count": int(road_class_counts.get(RoadClass.BRIDGE.value, 0)),
        "bridge_crossing_count": int(len(tuple(getattr(topology, "bridge_crossings", ()) or ()))),
        "collector_spine_segment_count": int(metadata.get("collector_spine_segment_count", 0)),
        "same_district_stitch_segment_count": int(metadata.get("same_district_stitch_segment_count", 0)),
        "inter_district_connector_count": int(metadata.get("inter_district_connector_count", 0)),
        "core_fan_segment_count": int(metadata.get("core_fan_segment_count", 0)),
        "interchange_like_node_count": int(metadata.get("interchange_like_node_count", interchange_like_node_count)),
        "hierarchy_legibility_score": float(metadata.get("hierarchy_legibility_score", 0.0)),
        "hierarchy_module_counts": hierarchy_module_counts,
        "road_hierarchy_module_signature": tuple(
            metadata.get("road_hierarchy_module_signature", ()) or ()
        ),
        "road_hierarchy_module_alignment_ok": bool(
            metadata.get("road_hierarchy_module_alignment_ok", False)
        ),
    }


def build_sidecar_shadow_comparison_report(
    *,
    scenario_id: str,
    seed: int,
    legacy_engine: str,
    sidecar_engine: str,
    sidecar_call_path: str,
    legacy_image_path: str | Path,
    sidecar_image_path: str | Path,
    sidecar_history_path: str | Path,
) -> dict[str, Any]:
    from metroflow.tools.analyze_city_map_image import analyze_city_map_image

    legacy = analyze_city_map_image(legacy_image_path)
    sidecar = analyze_city_map_image(sidecar_image_path)
    history_status = _load_history_status(sidecar_history_path)

    metrics = {
        "legacy_active_pixel_ratio": legacy.active_pixel_ratio,
        "legacy_active_bbox_fill_ratio": legacy.active_bbox_fill_ratio,
        "legacy_center_core_fill_ratio": legacy.center_core_fill_ratio,
        "legacy_outer_ring_fill_ratio": legacy.outer_ring_fill_ratio,
        "legacy_strip_signature_detected": int(legacy.strip_signature_detected),
        "legacy_shell_heavy_signature_detected": int(legacy.shell_heavy_signature_detected),
        "sidecar_active_pixel_ratio": sidecar.active_pixel_ratio,
        "sidecar_active_bbox_fill_ratio": sidecar.active_bbox_fill_ratio,
        "sidecar_center_core_fill_ratio": sidecar.center_core_fill_ratio,
        "sidecar_outer_ring_fill_ratio": sidecar.outer_ring_fill_ratio,
        "sidecar_strip_signature_detected": int(sidecar.strip_signature_detected),
        "sidecar_shell_heavy_signature_detected": int(sidecar.shell_heavy_signature_detected),
        "center_core_fill_delta": sidecar.center_core_fill_ratio - legacy.center_core_fill_ratio,
        "outer_ring_fill_delta": sidecar.outer_ring_fill_ratio - legacy.outer_ring_fill_ratio,
        "active_pixel_ratio_delta": sidecar.active_pixel_ratio - legacy.active_pixel_ratio,
        "active_bbox_fill_ratio_delta": sidecar.active_bbox_fill_ratio - legacy.active_bbox_fill_ratio,
        "sidecar_history_window_size": len(history_status.recent_entries),
        "sidecar_local_minimum_suspected": int(history_status.local_minimum_suspected),
    }

    reasons: list[str] = []
    if sidecar.strip_signature_detected:
        reasons.append("sidecar_strip_detected")
    if sidecar.shell_heavy_signature_detected:
        reasons.append("sidecar_shell_heavy_detected")
    if len(history_status.recent_entries) < 5:
        reasons.append("insufficient_sidecar_history")
    if history_status.local_minimum_suspected:
        reasons.append("sidecar_local_minimum_suspected")
    if metrics["center_core_fill_delta"] <= 0.0:
        reasons.append("sidecar_center_core_not_improved")
    if metrics["outer_ring_fill_delta"] >= 0.0:
        reasons.append("sidecar_outer_ring_not_softened")
    if not (legacy.strip_signature_detected or legacy.shell_heavy_signature_detected):
        reasons.append("legacy_failure_not_explicit")

    recommend_cutover = len(reasons) == 0

    return {
        "scenario_id": str(scenario_id),
        "seed": int(seed),
        "legacy_engine": str(legacy_engine),
        "sidecar_engine": str(sidecar_engine),
        "sidecar_call_path": str(sidecar_call_path),
        "metrics": metrics,
        "recommendation": {
            "recommend_cutover": bool(recommend_cutover),
            "reasons": reasons or ["sidecar_ready_for_cutover"],
        },
    }


def write_sidecar_shadow_comparison_markdown(
    *,
    output_path: str | Path,
    report: Mapping[str, Any],
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    metrics = dict(_required_mapping(report, "metrics"))
    recommendation = dict(_required_mapping(report, "recommendation"))
    lines = [
        "# Sidecar Shadow Comparison",
        "",
        f"- Scenario ID: `{report['scenario_id']}`",
        f"- Seed: `{int(report['seed'])}`",
        f"- Legacy engine: `{report['legacy_engine']}`",
        f"- Sidecar engine: `{report['sidecar_engine']}`",
        f"- Sidecar call path: `{report['sidecar_call_path']}`",
        f"- Recommend cutover: `{int(bool(recommendation['recommend_cutover']))}`",
        "",
        "## Metrics",
        "",
    ]
    for key in sorted(metrics):
        value = metrics[key]
        if isinstance(value, float):
            lines.append(f"- {key}: `{value:.4f}`")
        else:
            lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Recommendation Reasons", ""])
    for reason in recommendation.get("reasons", ()):
        lines.append(f"- {reason}")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def _load_history_status(history_path: str | Path):
    from metroflow.tools.track_city_map_history import CityMapHistoryEntry, evaluate_city_map_history

    path = Path(history_path)
    if not path.exists():
        return evaluate_city_map_history(())
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = [CityMapHistoryEntry(**entry) for entry in raw.get("entries", [])]
    return evaluate_city_map_history(entries)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build sidecar vs scaffold shadow comparison report.")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--legacy-engine", required=True)
    parser.add_argument("--sidecar-engine", required=True)
    parser.add_argument("--sidecar-call-path", required=True)
    parser.add_argument("--legacy-image", required=True)
    parser.add_argument("--sidecar-image", required=True)
    parser.add_argument("--sidecar-history", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    report = build_sidecar_shadow_comparison_report(
        scenario_id=args.scenario,
        seed=int(args.seed),
        legacy_engine=args.legacy_engine,
        sidecar_engine=args.sidecar_engine,
        sidecar_call_path=args.sidecar_call_path,
        legacy_image_path=args.legacy_image,
        sidecar_image_path=args.sidecar_image,
        sidecar_history_path=args.sidecar_history,
    )
    write_sidecar_shadow_comparison_markdown(output_path=args.output, report=report)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
