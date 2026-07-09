"""Static hardware-fit atlas for backend migration planning."""

from __future__ import annotations

import ast
import json
from collections import Counter
from dataclasses import asdict, dataclass
from html import escape
from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = [
    "HardwareAtlasEntry",
    "HardwareDecisionCard",
    "build_next_probe_summaries",
    "build_hardware_atlas",
    "extract_workload_matrix",
    "extract_runtime_stage_timings",
    "format_hardware_atlas_markdown",
    "hardware_atlas_to_dict",
    "link_workload_matrix_to_decision_cards",
    "link_runtime_stage_timings_to_atlas",
    "render_hardware_atlas_html",
    "write_hardware_atlas_artifact_bundle",
]

ROLE_TAGS = {
    "orchestration_state",
    "city_generation_topology",
    "graph_search",
    "array_numeric_core",
    "deterministic_mutation",
    "policy_scoring",
    "learning_label_surrogate",
    "io_ui_reporting",
}

HARDWARE_FIT_VALUES = {
    "keep_python",
    "cpu_scalar",
    "cpu_simd_numpy",
    "cpu_parallel_rust",
    "gpu_tensor_jax",
    "gpu_tensor_torch_future",
    "custom_cuda_future",
    "nn_surrogate_candidate",
    "no_acceleration",
}

STAGE_ROLE_HINTS: dict[str, tuple[str, ...]] = {
    "route_candidate_refresh": ("graph_search", "policy_scoring"),
    "route_candidate_potential": ("graph_search",),
    "dynamic_potential_recompute": ("graph_search",),
    "route_candidate_path_build": ("graph_search",),
    "route_candidate_metadata": ("array_numeric_core", "policy_scoring"),
    "flow_update": ("array_numeric_core",),
    "active_agent_update": ("deterministic_mutation",),
    "active_agent_allocation": ("deterministic_mutation", "policy_scoring"),
    "active_agent_candidate_selection": ("policy_scoring",),
    "active_agent_pool_write": ("deterministic_mutation",),
    "active_agent_pool_array_write": ("deterministic_mutation",),
    "active_agent_plugin_memory_write": ("deterministic_mutation",),
    "active_agent_movement": ("deterministic_mutation",),
    "reroute_decision": ("policy_scoring",),
}


@dataclass(frozen=True)
class HardwareAtlasEntry:
    module: str
    symbol: str
    path: str
    line: int
    role_tags: tuple[str, ...]
    data_surface: tuple[str, ...]
    hotspot_signals: tuple[str, ...]
    hardware_fit: tuple[str, ...]
    reason: str
    falsifier: str
    recommended_probe: str
    decision_state: str


@dataclass(frozen=True)
class HardwareDecisionCard:
    target: str
    hardware_fit: tuple[str, ...]
    expected_bottleneck: str
    measurement_probe: str
    acceptance_threshold: str
    fallback: str
    rollback: str


def build_hardware_atlas(
    *,
    source_root: str | Path | None = None,
    runtime_stage_timings: Sequence[Any] = (),
    runtime_suite_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a static code role and hardware-fit atlas without accelerator imports."""

    root = _resolve_source_root(source_root)
    entries = tuple(_iter_atlas_entries(root))
    extracted_timings = tuple(runtime_stage_timings) or extract_runtime_stage_timings(
        runtime_suite_payload or {}
    )
    stage_links = tuple(link_runtime_stage_timings_to_atlas(entries, extracted_timings))
    decision_cards = tuple(_build_decision_cards(entries, stage_links))
    workload_matrix = extract_workload_matrix(runtime_suite_payload or {})
    decision_workload_links = link_workload_matrix_to_decision_cards(
        decision_cards=decision_cards,
        workload_matrix=workload_matrix,
    )
    next_probe_summaries = build_next_probe_summaries(decision_workload_links)
    compact_ccot = _build_compact_ccot(entries, stage_links, decision_cards)
    report = {
        "report_type": "hardware_fit_atlas_v1",
        "source_root": _display_path(root),
        "entry_count": len(entries),
        "role_tag_counts": dict(_count_field_values(entries, "role_tags")),
        "hardware_fit_counts": dict(_count_field_values(entries, "hardware_fit")),
        "entries": [asdict(entry) for entry in entries],
        "stage_links": list(stage_links),
        "decision_cards": [asdict(card) for card in decision_cards],
        "workload_matrix": list(workload_matrix),
        "decision_workload_links": decision_workload_links,
        "next_probe_summaries": next_probe_summaries,
        "compact_ccot": compact_ccot,
        "notes": [
            "This atlas is a diagnostic planning artifact, not a validation claim.",
            "It does not import JAX, torch, CUDA, or the Rust extension.",
            "GPU and NN candidates require deterministic baseline labels and fallback.",
        ],
    }
    return hardware_atlas_to_dict(report)


def hardware_atlas_to_dict(report: Any) -> dict[str, Any]:
    """Return a JSON-safe hardware atlas payload."""

    payload = _json_ready(report)
    if not isinstance(payload, dict):
        raise TypeError("hardware atlas report must serialize to a mapping")
    return payload


def extract_runtime_stage_timings(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Extract timing rows from a runtime suite or single runtime benchmark payload."""

    if not isinstance(payload, Mapping):
        return ()
    direct = payload.get("runtime_stage_timings")
    if isinstance(direct, Sequence) and not isinstance(direct, str | bytes):
        return tuple(_as_mapping(item) for item in direct)
    rows: list[Mapping[str, Any]] = []
    per_seed = payload.get("per_seed_results")
    if isinstance(per_seed, Sequence) and not isinstance(per_seed, str | bytes):
        for result in per_seed:
            result_map = _as_mapping(result)
            timings = result_map.get("runtime_stage_timings")
            if isinstance(timings, Sequence) and not isinstance(timings, str | bytes):
                rows.extend(_as_mapping(item) for item in timings)
    return _aggregate_stage_timing_rows(rows)


def extract_workload_matrix(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Extract workload matrix entries from a runtime suite payload."""

    if not isinstance(payload, Mapping):
        return ()
    matrix = payload.get("workload_matrix")
    if not isinstance(matrix, Sequence) or isinstance(matrix, str | bytes):
        return ()
    entries: list[Mapping[str, Any]] = []
    for item in matrix:
        item_map = _workload_entry_to_mapping(item)
        workload_class = str(item_map.get("workload_class", "")).strip()
        stage_group = str(item_map.get("stage_group", "")).strip()
        if not workload_class or not stage_group:
            continue
        entries.append(
            {
                "workload_class": workload_class,
                "label": str(item_map.get("label", workload_class)),
                "stage_group": stage_group,
                "hardware_lanes": list(_as_sequence(item_map.get("hardware_lanes"))),
                "enabled": bool(item_map.get("enabled", False)),
                "coverage_state": str(item_map.get("coverage_state", "diagnostic_metadata")),
                "parameters": dict(_as_mapping(item_map.get("parameters"))),
                "decision_state": str(item_map.get("decision_state", "diagnostic")),
            }
        )
    return tuple(entries)


def link_workload_matrix_to_decision_cards(
    *,
    decision_cards: Sequence[HardwareDecisionCard | Mapping[str, Any]],
    workload_matrix: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Join workload coverage entries to existing decision cards by target."""

    workloads_by_stage: dict[str, list[Mapping[str, Any]]] = {}
    for entry in workload_matrix:
        stage_group = str(entry.get("stage_group", "")).strip()
        if not stage_group:
            continue
        workloads_by_stage.setdefault(stage_group, []).append(entry)

    links: list[dict[str, Any]] = []
    seen_targets: set[str] = set()
    for card in decision_cards:
        card_map = _decision_card_to_mapping(card)
        target = str(card_map.get("target", "unknown"))
        if target in seen_targets:
            continue
        seen_targets.add(target)
        workloads = tuple(workloads_by_stage.get(target, ()))
        if not workloads:
            continue
        workload_classes = _ordered_unique(
            entry.get("workload_class", "unknown") for entry in workloads
        )
        coverage_states = _ordered_unique(
            entry.get("coverage_state", "diagnostic_metadata") for entry in workloads
        )
        measured = _ordered_unique(
            entry.get("workload_class", "unknown")
            for entry in workloads
            if _is_measured_workload_entry(entry)
        )
        required = _ordered_unique(
            entry.get("workload_class", "unknown")
            for entry in workloads
            if not _is_measured_workload_entry(entry)
        )
        hardware_lanes = _ordered_unique(
            lane
            for entry in workloads
            for lane in _as_sequence(entry.get("hardware_lanes"))
        )
        decision_class = _decision_class_for_workload_link(
            measured=measured,
            required=required,
        )
        links.append(
            {
                "target": target,
                "workload_classes": workload_classes,
                "coverage_states": coverage_states,
                "hardware_lanes": hardware_lanes,
                "decision_class": decision_class,
                "measured_workload_classes": measured,
                "required_probe_workload_classes": required,
                "measurement_probe": str(card_map.get("measurement_probe", "N/A")),
                "acceptance_threshold": str(card_map.get("acceptance_threshold", "N/A")),
                "fallback": str(card_map.get("fallback", "N/A")),
                "rollback": str(card_map.get("rollback", "N/A")),
            }
        )
    return links


def build_next_probe_summaries(
    decision_workload_links: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Summarize decision-changing probes without inventing new card targets."""

    summaries: list[dict[str, Any]] = []
    seen_targets: set[str] = set()
    for link in decision_workload_links:
        target = str(link.get("target", "unknown"))
        if target in seen_targets:
            continue
        seen_targets.add(target)
        measured = tuple(str(item) for item in _as_sequence(link.get("measured_workload_classes")))
        required = tuple(
            str(item) for item in _as_sequence(link.get("required_probe_workload_classes"))
        )
        summaries.append(
            {
                "target": target,
                "decision_effect": _decision_effect_for_workload_link(
                    measured=measured,
                    required=required,
                    decision_class=str(link.get("decision_class", "")),
                ),
                "measured_workload_classes": list(measured),
                "required_probe_workload_classes": list(required),
                "next_probe": str(link.get("measurement_probe", "N/A")),
                "falsifier": str(link.get("acceptance_threshold", "N/A")),
            }
        )
    return summaries


def link_runtime_stage_timings_to_atlas(
    entries: Sequence[HardwareAtlasEntry | Mapping[str, Any]],
    runtime_stage_timings: Sequence[Any],
) -> list[dict[str, Any]]:
    """Map measured runtime stage names to likely static symbol groups."""

    entry_maps = tuple(_entry_to_mapping(entry) for entry in entries)
    links: list[dict[str, Any]] = []
    for timing in runtime_stage_timings:
        timing_map = _as_mapping(timing)
        stage_name = str(timing_map.get("stage_name", "unknown"))
        role_hints = STAGE_ROLE_HINTS.get(stage_name, ())
        token_hints = _stage_token_hints(stage_name)
        matched = tuple(
            entry
            for entry in entry_maps
            if _entry_matches_stage(entry, role_hints=role_hints, token_hints=token_hints)
        )
        links.append(
            {
                "stage_name": stage_name,
                "role_hints": list(role_hints),
                "symbol_count": len(matched),
                "symbols": [str(entry["symbol"]) for entry in matched[:16]],
                "hardware_fit": _ordered_unique(
                    fit
                    for entry in matched
                    for fit in _as_sequence(entry.get("hardware_fit"))
                ),
                "measurement": {
                    key: timing_map[key]
                    for key in (
                        "wall_clock_ns",
                        "wall_time_share",
                        "gpu_candidate",
                        "run_count",
                        "wall_clock_ns_total",
                        "mean_wall_clock_ns",
                        "max_wall_clock_ns",
                        "mean_wall_time_share",
                        "max_wall_time_share",
                        "gpu_candidate_run_count",
                        "call_count",
                        "input_size",
                        "estimated_copy_bytes",
                    )
                    if key in timing_map
                },
                "recommended_probe": _stage_recommended_probe(stage_name, matched),
            }
        )
    return links


def format_hardware_atlas_markdown(report: Mapping[str, Any]) -> str:
    """Render a reviewer-facing hardware atlas markdown artifact."""

    payload = hardware_atlas_to_dict(report)
    lines = [
        "# Hardware Fit Atlas",
        "",
        "This diagnostic artifact maps code roles to CPU/Rust/GPU/NN fit. It is not a "
        "validation claim or backend authorization.",
        "",
        "## Summary",
        "",
        f"- Report type: {payload.get('report_type', 'unknown')}",
        f"- Source root: {payload.get('source_root', 'unknown')}",
        f"- Entry count: {payload.get('entry_count', 0)}",
        f"- Role tags: {_format_count_mapping(payload.get('role_tag_counts'))}",
        f"- Hardware fit: {_format_count_mapping(payload.get('hardware_fit_counts'))}",
        "",
        "## Compact CCoT",
        "",
    ]
    ccot = _as_mapping(payload.get("compact_ccot"))
    for key in ("Question", "Evidence", "Inference", "Counterevidence checked", "Decision", "Falsifier", "Next action"):
        lines.append(f"- {key}: {ccot.get(key, 'N/A')}")
    lines.extend(["", "## Stage Links", ""])
    stage_links = tuple(_as_mapping(item) for item in _as_sequence(payload.get("stage_links")))
    if stage_links:
        lines.extend(
            [
                "| stage | symbols | hardware fit | next probe |",
                "|---|---:|---|---|",
            ]
        )
        for link in stage_links:
            lines.append(
                "| "
                f"{link.get('stage_name', 'unknown')} | "
                f"{link.get('symbol_count', 0)} | "
                f"{', '.join(str(item) for item in _as_sequence(link.get('hardware_fit'))) or 'none'} | "
                f"{link.get('recommended_probe', 'N/A')} |"
            )
    else:
        lines.append("No runtime stage timings were provided.")
    lines.extend(["", "## Decision Cards", ""])
    cards = tuple(_as_mapping(item) for item in _as_sequence(payload.get("decision_cards")))
    if cards:
        lines.extend(
            [
                "| target | fit | probe | acceptance |",
                "|---|---|---|---|",
            ]
        )
        for card in cards:
            lines.append(
                "| "
                f"{card.get('target', 'unknown')} | "
                f"{', '.join(str(item) for item in _as_sequence(card.get('hardware_fit'))) or 'none'} | "
                f"{card.get('measurement_probe', 'N/A')} | "
                f"{card.get('acceptance_threshold', 'N/A')} |"
            )
    else:
        lines.append("No acceleration decision cards were generated.")
    lines.extend(["", "## Workload Decision Links", ""])
    workload_links = tuple(
        _as_mapping(item) for item in _as_sequence(payload.get("decision_workload_links"))
    )
    if workload_links:
        lines.extend(
            [
                "| target | workloads | measured | required probes |",
                "|---|---|---|---|",
            ]
        )
        for link in workload_links:
            lines.append(
                "| "
                f"{link.get('target', 'unknown')} | "
                f"{', '.join(str(item) for item in _as_sequence(link.get('workload_classes'))) or 'none'} "
                f"({', '.join(str(item) for item in _as_sequence(link.get('hardware_lanes'))) or 'no lanes'}) | "
                f"{', '.join(str(item) for item in _as_sequence(link.get('measured_workload_classes'))) or 'none'} | "
                f"{', '.join(str(item) for item in _as_sequence(link.get('required_probe_workload_classes'))) or 'none'} "
                f"[{link.get('decision_class', 'unknown')}; "
                f"{', '.join(str(item) for item in _as_sequence(link.get('coverage_states'))) or 'no coverage states'}] |"
            )
    else:
        lines.append("No workload matrix entries were linked to decision cards.")
    lines.extend(["", "## Next Probe Summaries", ""])
    next_probe_summaries = tuple(
        _as_mapping(item) for item in _as_sequence(payload.get("next_probe_summaries"))
    )
    if next_probe_summaries:
        lines.extend(
            [
                "| target | decision effect | next probe | falsifier |",
                "|---|---|---|---|",
            ]
        )
        for summary in next_probe_summaries:
            lines.append(
                "| "
                f"{summary.get('target', 'unknown')} | "
                f"{summary.get('decision_effect', 'unknown')} | "
                f"{summary.get('next_probe', 'N/A')} | "
                f"{summary.get('falsifier', 'N/A')} |"
            )
    else:
        lines.append("No workload-linked next probe summaries were generated.")
    lines.extend(["", "## Sample Entries", ""])
    lines.extend(["| symbol | roles | fit | probe |", "|---|---|---|---|"])
    for entry in tuple(_as_mapping(item) for item in _as_sequence(payload.get("entries")))[:40]:
        lines.append(
            "| "
            f"{entry.get('symbol', 'unknown')} | "
            f"{', '.join(str(item) for item in _as_sequence(entry.get('role_tags')))} | "
            f"{', '.join(str(item) for item in _as_sequence(entry.get('hardware_fit')))} | "
            f"{entry.get('recommended_probe', 'N/A')} |"
        )
    return "\n".join(lines) + "\n"


def render_hardware_atlas_html(report: Mapping[str, Any]) -> str:
    """Render a standalone HTML review artifact for a hardware atlas."""

    payload = hardware_atlas_to_dict(report)
    data_json = escape(json.dumps(payload, separators=(",", ":"), sort_keys=True))
    stage_rows = "\n".join(
        _render_stage_link_row(item) for item in _as_sequence(payload.get("stage_links"))
    )
    entry_rows = "\n".join(
        _render_entry_row(item) for item in _as_sequence(payload.get("entries"))[:80]
    )
    card_rows = "\n".join(
        _render_decision_card_row(item) for item in _as_sequence(payload.get("decision_cards"))
    )
    workload_link_rows = "\n".join(
        _render_workload_decision_link_row(item)
        for item in _as_sequence(payload.get("decision_workload_links"))
    )
    next_probe_rows = "\n".join(
        _render_next_probe_summary_row(item)
        for item in _as_sequence(payload.get("next_probe_summaries"))
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Hardware Fit Atlas</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 0; background: #f6f7f9; color: #202833; }}
    main {{ max-width: 1200px; margin: 0 auto; padding: 28px; }}
    h1 {{ font-size: 26px; margin: 0 0 6px; letter-spacing: 0; }}
    h2 {{ font-size: 16px; margin: 24px 0 10px; letter-spacing: 0; }}
    .meta {{ color: #5b6573; margin-bottom: 18px; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }}
    .metric {{ background: #fff; border: 1px solid #d9dfe8; border-radius: 8px; padding: 12px; }}
    .metric strong {{ display: block; margin-top: 4px; font-size: 20px; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #d9dfe8; }}
    th, td {{ border-bottom: 1px solid #e5e9ef; padding: 8px 9px; text-align: left; font-size: 12px; vertical-align: top; }}
    th {{ background: #edf1f5; font-weight: 650; }}
    .note {{ color: #5b6573; font-size: 13px; line-height: 1.45; }}
    code {{ font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }}
  </style>
</head>
<body>
<main data-hardware-fit-atlas="{data_json}">
  <h1>Hardware Fit Atlas</h1>
  <div class="meta">source <code>{escape(str(payload.get("source_root", "unknown")))}</code></div>
  <section class="grid">
    <div class="metric">entries<strong>{escape(str(payload.get("entry_count", 0)))}</strong></div>
    <div class="metric">stage links<strong>{escape(str(len(_as_sequence(payload.get("stage_links")))))}</strong></div>
    <div class="metric">decision cards<strong>{escape(str(len(_as_sequence(payload.get("decision_cards")))))}</strong></div>
  </section>
  <h2>Stage Links</h2>
  <table>
    <thead><tr><th>stage</th><th>symbols</th><th>fit</th><th>probe</th></tr></thead>
    <tbody>{stage_rows}</tbody>
  </table>
  <h2>Decision Cards</h2>
  <table>
    <thead><tr><th>target</th><th>fit</th><th>probe</th><th>acceptance</th></tr></thead>
    <tbody>{card_rows}</tbody>
  </table>
  <h2>Workload Decision Links</h2>
  <table>
    <thead><tr><th>target</th><th>workloads</th><th>measured</th><th>required probes</th></tr></thead>
    <tbody>{workload_link_rows}</tbody>
  </table>
  <h2>Next Probe Summaries</h2>
  <table>
    <thead><tr><th>target</th><th>decision effect</th><th>next probe</th><th>falsifier</th></tr></thead>
    <tbody>{next_probe_rows}</tbody>
  </table>
  <h2>Sample Entries</h2>
  <table>
    <thead><tr><th>symbol</th><th>roles</th><th>fit</th><th>reason</th></tr></thead>
    <tbody>{entry_rows}</tbody>
  </table>
  <p class="note">This static artifact is for backend migration planning and anti-drift review only.</p>
</main>
</body>
</html>
"""


def write_hardware_atlas_artifact_bundle(
    report: Mapping[str, Any],
    *,
    output_prefix: str | Path,
) -> dict[str, Path]:
    """Write markdown, JSON, HTML, and manifest artifacts for a hardware atlas."""

    prefix = Path(output_prefix)
    markdown_path = Path(f"{prefix}.md")
    json_path = Path(f"{prefix}.json")
    html_path = Path(f"{prefix}.html")
    manifest_path = Path(f"{prefix}.manifest.json")
    for path in (markdown_path, json_path, html_path, manifest_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    payload = hardware_atlas_to_dict(report)
    markdown_path.write_text(format_hardware_atlas_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    html_path.write_text(render_hardware_atlas_html(payload), encoding="utf-8")

    manifest = {
        "artifact_format_version": "hardware_fit_atlas_bundle_v1",
        "report_type": str(payload.get("report_type", "unknown")),
        "source_root": str(payload.get("source_root", "unknown")),
        "entry_count": int(payload.get("entry_count", 0) or 0),
        "stage_link_count": len(_as_sequence(payload.get("stage_links"))),
        "decision_card_count": len(_as_sequence(payload.get("decision_cards"))),
        "workload_class_count": len(_as_sequence(payload.get("workload_matrix"))),
        "next_probe_summary_count": len(_as_sequence(payload.get("next_probe_summaries"))),
        "artifact_paths": {
            "markdown": str(markdown_path),
            "json": str(json_path),
            "html": str(html_path),
            "manifest": str(manifest_path),
        },
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "markdown": markdown_path,
        "json": json_path,
        "html": html_path,
        "manifest": manifest_path,
    }


def _iter_atlas_entries(source_root: Path) -> tuple[HardwareAtlasEntry, ...]:
    entries: list[HardwareAtlasEntry] = []
    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        module = _module_name(source_root, path)
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue
        nodes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            and hasattr(node, "lineno")
        ]
        for node in sorted(nodes, key=lambda item: (int(item.lineno), getattr(item, "name", ""))):
            symbol = f"{module}.{node.name}" if module else str(node.name)
            source = _source_for_node(lines, node)
            entries.append(
                _classify_symbol(
                    module=module,
                    symbol=symbol,
                    path=path,
                    line=int(node.lineno),
                    node=node,
                    source=source,
                )
            )
    return tuple(entries)


def _classify_symbol(
    *,
    module: str,
    symbol: str,
    path: Path,
    line: int,
    node: ast.AST,
    source: str,
) -> HardwareAtlasEntry:
    lower = f"{module} {symbol} {source}".lower()
    metrics = _node_metrics(node, source)
    role_tags = _classify_roles(module, symbol, lower, metrics)
    data_surface = _classify_data_surface(lower, metrics)
    hotspot_signals = _classify_hotspot_signals(metrics, lower)
    hardware_fit = _classify_hardware_fit(role_tags, lower)
    return HardwareAtlasEntry(
        module=module,
        symbol=symbol,
        path=_display_path(path),
        line=line,
        role_tags=tuple(role_tags),
        data_surface=tuple(data_surface),
        hotspot_signals=tuple(hotspot_signals),
        hardware_fit=tuple(hardware_fit),
        reason=_reason_for_roles(role_tags, hardware_fit),
        falsifier=_falsifier_for_fit(hardware_fit),
        recommended_probe=_recommended_probe_for_roles(role_tags, hardware_fit),
        decision_state=_decision_state_for_fit(hardware_fit),
    )


def _node_metrics(node: ast.AST, source: str) -> dict[str, int]:
    return {
        "lines": max(len(source.splitlines()), 1),
        "loops": sum(isinstance(item, ast.For | ast.While | ast.comprehension) for item in ast.walk(node)),
        "calls": sum(isinstance(item, ast.Call) for item in ast.walk(node)),
        "assignments": sum(isinstance(item, ast.Assign | ast.AnnAssign | ast.AugAssign) for item in ast.walk(node)),
    }


def _classify_roles(
    module: str,
    symbol: str,
    lower: str,
    metrics: Mapping[str, int],
) -> tuple[str, ...]:
    roles: list[str] = []
    if module.startswith("city") or any(token in lower for token in ("topology", "generate", "builder")):
        roles.append("city_generation_topology")
    graph_signal = any(
        token in lower
        for token in (
            "heapq",
            "heappush",
            "heappop",
            "dijkstra",
            "dynamic_potential",
            "route_candidate",
            "ranked_route",
            "path_build",
        )
    )
    if graph_signal or module.startswith("routing"):
        roles.append("graph_search")
    numpy_signal = any(token in lower for token in ("np.", "numpy", "ndarray", "asarray"))
    if numpy_signal or module.startswith("flow"):
        roles.append("array_numeric_core")
    mutation_signal = any(
        token in lower
        for token in (
            "plugin_memory",
            "setdefault",
            "with_dynamic_updates",
            "from_internal_arrays",
            "queue_vehicles",
            "active_agent",
            "replace(",
        )
    )
    if mutation_signal:
        roles.append("deterministic_mutation")
    policy_signal = any(
        token in lower
        for token in (
            "policy",
            "score",
            "utility",
            "reroute",
            "choice",
            "candidate_selection",
            "path_size",
        )
    )
    if policy_signal or module.startswith(("policy", "learning")):
        roles.append("policy_scoring")
    learning_signal = any(token in lower for token in ("surrogate", "label", "experience", "learning"))
    if learning_signal or module.startswith("learning"):
        roles.append("learning_label_surrogate")
    io_signal = any(
        token in lower
        for token in ("json", "html", "write_text", "read_text", "socket", "http", "render")
    )
    if io_signal or module.startswith(("ui", "viz", "benchmarks")):
        roles.append("io_ui_reporting")
    if module.startswith(("sim", "core")) or "config" in symbol.lower() or "state" in lower:
        roles.append("orchestration_state")
    if not roles:
        roles.append("orchestration_state")
    return tuple(role for role in _ordered_unique(roles) if role in ROLE_TAGS)


def _classify_data_surface(lower: str, metrics: Mapping[str, int]) -> tuple[str, ...]:
    surfaces: list[str] = []
    if any(token in lower for token in ("np.", "numpy", "ndarray", "asarray")):
        surfaces.append("np.ndarray")
    if "jax" in lower:
        surfaces.append("optional JAX array")
    if "torch" in lower:
        surfaces.append("future torch tensor")
    if any(token in lower for token in ("rust_cpu", "_metroflow_rust", "copy-boundary")):
        surfaces.append("Rust FFI copy boundary")
    if any(token in lower for token in ("dict", "plugin_memory", "setdefault")):
        surfaces.append("dict/plugin memory")
    if any(token in lower for token in ("dataclass", "state", "replace(", "with_dynamic_updates")):
        surfaces.append("dataclass/state")
    if any(token in lower for token in ("json", "html", "write_text", "read_text", "socket", "http")):
        surfaces.append("json/html/file IO")
    if metrics.get("loops", 0) > 0:
        surfaces.append("python control flow")
    if not surfaces:
        surfaces.append("python object")
    return tuple(_ordered_unique(surfaces))


def _classify_hotspot_signals(metrics: Mapping[str, int], lower: str) -> tuple[str, ...]:
    signals = [f"lines={metrics.get('lines', 0)}"]
    if metrics.get("loops", 0) > 0:
        signals.append(f"loops={metrics['loops']}")
    if metrics.get("calls", 0) > 0:
        signals.append(f"calls={metrics['calls']}")
    if metrics.get("lines", 0) >= 80:
        signals.append("large_symbol")
    if any(token in lower for token in ("heapq", "heappush", "heappop", "dijkstra")):
        signals.append("heap_graph_signal")
    if any(token in lower for token in ("np.", "numpy", "ndarray")):
        signals.append("numpy_vector_signal")
    if any(token in lower for token in ("plugin_memory", "setdefault", "dict")):
        signals.append("dict_state_mutation_signal")
    if any(token in lower for token in ("rust_cpu", "_metroflow_rust")):
        signals.append("rust_ffi_signal")
    if "jax" in lower:
        signals.append("optional_jax_signal")
    if "torch" in lower:
        signals.append("future_torch_signal")
    if any(token in lower for token in ("json", "html", "write_text", "read_text")):
        signals.append("io_reporting_signal")
    return tuple(_ordered_unique(signals))


def _classify_hardware_fit(role_tags: Sequence[str], lower: str) -> tuple[str, ...]:
    roles = set(role_tags)
    fits: list[str] = []
    if "io_ui_reporting" in roles and roles <= {"io_ui_reporting", "orchestration_state"}:
        fits.extend(("keep_python", "no_acceleration"))
    if "orchestration_state" in roles:
        fits.append("keep_python")
    if "city_generation_topology" in roles:
        fits.append("cpu_scalar")
    if "graph_search" in roles:
        fits.append("cpu_parallel_rust")
        if any(token in lower for token in ("potential", "cost", "candidate", "score")):
            fits.append("nn_surrogate_candidate")
    if "array_numeric_core" in roles:
        fits.append("cpu_simd_numpy")
        if any(token in lower for token in ("batch", "flow", "metadata", "score", "cost")):
            fits.extend(("gpu_tensor_jax", "custom_cuda_future"))
    if "deterministic_mutation" in roles:
        fits.extend(("cpu_scalar", "cpu_parallel_rust"))
    if "policy_scoring" in roles:
        fits.extend(("nn_surrogate_candidate", "gpu_tensor_jax", "gpu_tensor_torch_future"))
    if "learning_label_surrogate" in roles:
        fits.append("nn_surrogate_candidate")
    if not fits:
        fits.append("keep_python")
    return tuple(fit for fit in _ordered_unique(fits) if fit in HARDWARE_FIT_VALUES)


def _reason_for_roles(role_tags: Sequence[str], hardware_fit: Sequence[str]) -> str:
    roles = set(role_tags)
    fits = set(hardware_fit)
    if "graph_search" in roles:
        return "Branch-heavy graph traversal fits Rust CPU first; labels may feed NN surrogates."
    if "array_numeric_core" in roles:
        return "Typed array math can use NumPy/SIMD now and GPU kernels only after scale evidence."
    if "deterministic_mutation" in roles:
        return "Deterministic state mutation is CPU-oriented and should preserve replay order."
    if "policy_scoring" in roles:
        return "Policy scoring can become batched tensor or NN inference with baseline labels."
    if "io_ui_reporting" in roles or "keep_python" in fits:
        return "Control, reporting, and UI surfaces should stay Python unless timing evidence changes."
    return "No accelerator-specific structure is visible in the static scan."


def _falsifier_for_fit(hardware_fit: Sequence[str]) -> str:
    fits = set(hardware_fit)
    if "gpu_tensor_jax" in fits or "custom_cuda_future" in fits:
        return "Reject GPU work if compile/copy cost dominates or batch size stays below the gate."
    if "nn_surrogate_candidate" in fits:
        return "Reject NN work without deterministic labels, model fingerprint, and baseline fallback."
    if "cpu_parallel_rust" in fits:
        return "Reject Rust work if parity fails or Python/Rust copy-boundary cost dominates."
    return "Reopen only if measured wall-time share crosses the review gate across deterministic seeds."


def _recommended_probe_for_roles(role_tags: Sequence[str], hardware_fit: Sequence[str]) -> str:
    roles = set(role_tags)
    fits = set(hardware_fit)
    if "graph_search" in roles:
        return "Measure per-OD graph-search time, cache hit rate, and Rust copy-boundary cost."
    if "array_numeric_core" in roles:
        return "Measure dense batch size, NumPy baseline time, and optional JAX compile vs steady-state."
    if "policy_scoring" in roles or "nn_surrogate_candidate" in fits:
        return "Collect baseline labels and batch scoring latency before opening NN/GPU work."
    if "deterministic_mutation" in roles:
        return "Split pack, action planning, and immutable apply timings before backend work."
    return "Keep in Python and measure only if it appears in runtime stage timings."


def _decision_state_for_fit(hardware_fit: Sequence[str]) -> str:
    fits = set(hardware_fit)
    if fits <= {"keep_python", "no_acceleration"}:
        return "keep_python"
    if {"gpu_tensor_jax", "custom_cuda_future", "gpu_tensor_torch_future", "nn_surrogate_candidate"} & fits:
        return "measure_before_implementation"
    if "cpu_parallel_rust" in fits:
        return "rust_watchlist"
    return "baseline_watchlist"


def _build_decision_cards(
    entries: Sequence[HardwareAtlasEntry],
    stage_links: Sequence[Mapping[str, Any]],
) -> tuple[HardwareDecisionCard, ...]:
    cards: list[HardwareDecisionCard] = []
    if stage_links:
        seen_stage_targets: set[str] = set()
        for link in stage_links:
            stage_name = str(link.get("stage_name", "unknown"))
            if stage_name in seen_stage_targets:
                continue
            seen_stage_targets.add(stage_name)
            fits = tuple(str(item) for item in _as_sequence(link.get("hardware_fit")))
            cards.append(
                HardwareDecisionCard(
                    target=stage_name,
                    hardware_fit=fits or ("keep_python",),
                    expected_bottleneck=_stage_expected_bottleneck(stage_name),
                    measurement_probe=str(link.get("recommended_probe", _stage_recommended_probe(stage_name, ()))),
                    acceptance_threshold=(
                        "Open implementation only if the stage exceeds 30% share across three "
                        "deterministic seeds or a narrow microbench beats baseline including copy/compile."
                    ),
                    fallback="Keep Python/NumPy deterministic baseline authoritative.",
                    rollback="Remove backend activation if replay parity or copy-inclusive timing regresses.",
                )
            )
        return tuple(cards)

    fit_counts = _count_field_values(entries, "hardware_fit")
    for fit, _count in fit_counts.most_common(4):
        if fit in {"keep_python", "no_acceleration"}:
            continue
        cards.append(
            HardwareDecisionCard(
                target=f"static_fit:{fit}",
                hardware_fit=(fit,),
                expected_bottleneck=_fit_expected_bottleneck(fit),
                measurement_probe=_fit_measurement_probe(fit),
                acceptance_threshold=(
                    "Require runtime-stage evidence or copy-inclusive microbench improvement "
                    "before implementing."
                ),
                fallback="Keep existing baseline backend and artifact-only evidence.",
                rollback="Drop the candidate if measurement does not change the next action.",
            )
        )
    return tuple(cards)


def _decision_class_for_workload_link(
    *,
    measured: Sequence[str],
    required: Sequence[str],
) -> str:
    if measured and required:
        return "partial_requires_probe"
    if measured:
        return "supports"
    if required:
        return "blocks"
    return "defers"


def _is_measured_workload_entry(entry: Mapping[str, Any]) -> bool:
    return bool(entry.get("enabled", False)) and str(
        entry.get("coverage_state", "")
    ) in {"measured_in_suite", "measured_in_probe"}


def _decision_effect_for_workload_link(
    *,
    measured: Sequence[str],
    required: Sequence[str],
    decision_class: str,
) -> str:
    if decision_class == "partial_requires_probe" or (measured and required):
        return "supports_partial_review_requires_probe"
    if decision_class == "supports" or measured:
        return "supports_decision_card_review"
    if decision_class == "blocks" or required:
        return "blocks_backend_implementation"
    return "defers_until_workload_matrix_available"


def _build_compact_ccot(
    entries: Sequence[HardwareAtlasEntry],
    stage_links: Sequence[Mapping[str, Any]],
    decision_cards: Sequence[HardwareDecisionCard],
) -> dict[str, str]:
    role_counts = _count_field_values(entries, "role_tags")
    fit_counts = _count_field_values(entries, "hardware_fit")
    leading_roles = ", ".join(f"{role}={count}" for role, count in role_counts.most_common(4)) or "none"
    leading_fits = ", ".join(f"{fit}={count}" for fit, count in fit_counts.most_common(4)) or "none"
    return {
        "Question": "Which code surfaces should move to Rust, stay NumPy/Python, or become GPU/NN candidates?",
        "Evidence": (
            f"Scanned {len(entries)} symbols; linked {len(stage_links)} runtime stages; "
            f"top roles: {leading_roles}; top fits: {leading_fits}."
        ),
        "Inference": "Backend work should follow role/data-shape evidence, not a single repeated hot-path observation.",
        "Counterevidence checked": (
            "Static fit alone is not accepted as performance evidence; smoke benchmark shares remain diagnostic."
        ),
        "Decision": (
            f"Generate {len(decision_cards)} decision cards and require measured probes before implementation."
        ),
        "Falsifier": "If linked stage timing and static fit disagree, run a narrower probe before coding a backend.",
        "Next action": "Use decision cards to pick one Rust, NumPy/SIMD, GPU/JAX, or NN label-collection slice.",
    }


def _stage_recommended_probe(stage_name: str, matched: Sequence[Mapping[str, Any]]) -> str:
    if stage_name in {"dynamic_potential_recompute", "route_candidate_potential"}:
        return "Compare cache-hit, Python Dijkstra, Rust Dijkstra, and label extraction time separately."
    if stage_name == "flow_update":
        return "Run dense flow batches and split NumPy, optional JAX compile, and steady-state timings."
    if "active_agent" in stage_name:
        return "Split candidate scoring, budget lookup, action planning, and immutable apply timings."
    if "metadata" in stage_name or "scoring" in stage_name:
        return "Batch candidate scoring and measure tensor-friendly array shapes at larger K."
    if not matched:
        return "Add a stage-specific symbol mapping before selecting a backend."
    return "Run a copy-inclusive microbench for the linked symbol group."


def _stage_expected_bottleneck(stage_name: str) -> str:
    if stage_name in {"dynamic_potential_recompute", "route_candidate_potential"}:
        return "Irregular reverse graph search and cache recomputation."
    if stage_name == "flow_update":
        return "Dense array math and memory bandwidth at larger link/turn counts."
    if "active_agent" in stage_name:
        return "Deterministic slot-order mutation plus Python state replacement."
    if "reroute" in stage_name or "candidate_selection" in stage_name:
        return "Batched policy scoring and label quality rather than route legality."
    return "Unknown until a stage-specific timing probe is attached."


def _fit_expected_bottleneck(fit: str) -> str:
    if fit == "cpu_parallel_rust":
        return "Branchy CPU control flow or deterministic mutation."
    if fit == "cpu_simd_numpy":
        return "Typed array math and memory bandwidth."
    if fit.startswith("gpu_tensor") or fit == "custom_cuda_future":
        return "Large batch tensor throughput after compile/copy overhead."
    if fit == "nn_surrogate_candidate":
        return "Learned scoring or cost approximation with deterministic labels."
    return "No current backend bottleneck."


def _fit_measurement_probe(fit: str) -> str:
    if fit == "cpu_parallel_rust":
        return "Run parity plus copy-inclusive Rust microbench on deterministic inputs."
    if fit == "cpu_simd_numpy":
        return "Measure vectorized NumPy baseline at scaled array sizes."
    if fit.startswith("gpu_tensor") or fit == "custom_cuda_future":
        return "Measure first-call compile, steady-state, copy bytes, and batch size."
    if fit == "nn_surrogate_candidate":
        return "Collect baseline labels and compare inference latency with fallback."
    return "Keep as report-only until runtime timing crosses a gate."


def _entry_matches_stage(
    entry: Mapping[str, Any],
    *,
    role_hints: Sequence[str],
    token_hints: Sequence[str],
) -> bool:
    roles = {str(item) for item in _as_sequence(entry.get("role_tags"))}
    symbol = str(entry.get("symbol", "")).lower()
    if role_hints and roles.intersection(role_hints):
        if not token_hints:
            return True
        return any(token in symbol for token in token_hints) or any(
            token in " ".join(str(item) for item in _as_sequence(entry.get("hotspot_signals"))).lower()
            for token in token_hints
        )
    return any(token in symbol for token in token_hints)


def _stage_token_hints(stage_name: str) -> tuple[str, ...]:
    explicit = {
        "dynamic_potential_recompute": ("dynamic_potential", "potential"),
        "route_candidate_potential": ("candidate", "potential", "route"),
        "route_candidate_refresh": ("candidate", "route", "refresh"),
        "route_candidate_path_build": ("candidate", "path", "route"),
        "route_candidate_metadata": ("candidate", "metadata", "path_size"),
        "flow_update": ("flow",),
        "active_agent_pool_write": ("agent", "pool", "write"),
        "active_agent_pool_array_write": ("agent", "pool", "array"),
        "active_agent_plugin_memory_write": ("agent", "plugin", "memory"),
        "active_agent_movement": ("agent", "movement", "advance"),
        "active_agent_update": ("agent", "active"),
        "active_agent_allocation": ("agent", "allocation"),
        "active_agent_candidate_selection": ("agent", "candidate", "selection"),
        "reroute_decision": ("reroute", "decision"),
    }
    if stage_name in explicit:
        return explicit[stage_name]
    return tuple(token for token in stage_name.split("_") if token not in {"update", "recompute"})


def _count_field_values(entries: Sequence[HardwareAtlasEntry], field_name: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for entry in entries:
        values = getattr(entry, field_name)
        for value in values:
            counts[str(value)] += 1
    return counts


def _aggregate_stage_timing_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[Mapping[str, Any], ...]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    order: list[str] = []
    for row in rows:
        stage_name = str(row.get("stage_name", "unknown"))
        if stage_name not in grouped:
            grouped[stage_name] = []
            order.append(stage_name)
        grouped[stage_name].append(row)
    aggregated: list[Mapping[str, Any]] = []
    for stage_name in order:
        stage_rows = grouped[stage_name]
        wall_values = [_as_int(row.get("wall_clock_ns")) for row in stage_rows]
        share_values = [_as_float(row.get("wall_time_share")) for row in stage_rows]
        total_wall = int(sum(wall_values))
        run_count = len(stage_rows)
        aggregated.append(
            {
                "stage_name": stage_name,
                "run_count": run_count,
                "wall_clock_ns_total": total_wall,
                "mean_wall_clock_ns": float(total_wall / run_count) if run_count else 0.0,
                "max_wall_clock_ns": int(max(wall_values)) if wall_values else 0,
                "mean_wall_time_share": round(
                    float(sum(share_values) / run_count) if run_count else 0.0,
                    6,
                ),
                "max_wall_time_share": float(max(share_values)) if share_values else 0.0,
                "gpu_candidate_run_count": sum(
                    1 for row in stage_rows if bool(row.get("gpu_candidate", False))
                ),
            }
        )
    return tuple(aggregated)


def _module_name(source_root: Path, path: Path) -> str:
    relative = path.relative_to(source_root).with_suffix("")
    parts = tuple(part for part in relative.parts if part != "__init__")
    return ".".join(parts)


def _source_for_node(lines: Sequence[str], node: ast.AST) -> str:
    start = max(int(getattr(node, "lineno", 1)) - 1, 0)
    end = int(getattr(node, "end_lineno", start + 1))
    return "\n".join(lines[start:end])


def _resolve_source_root(source_root: str | Path | None) -> Path:
    if source_root is None:
        return Path(__file__).resolve().parents[1]
    root = Path(source_root)
    if not root.exists():
        raise ValueError(f"hardware atlas source root does not exist: {root}")
    if not root.is_dir():
        raise ValueError(f"hardware atlas source root must be a directory: {root}")
    return root


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def _entry_to_mapping(entry: HardwareAtlasEntry | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(entry, HardwareAtlasEntry):
        return asdict(entry)
    return entry


def _decision_card_to_mapping(
    card: HardwareDecisionCard | Mapping[str, Any],
) -> Mapping[str, Any]:
    if isinstance(card, HardwareDecisionCard):
        return asdict(card)
    return card


def _workload_entry_to_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "__dataclass_fields__") and not isinstance(value, type):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return {
            key: getattr(value, key)
            for key in (
                "workload_class",
                "label",
                "stage_group",
                "hardware_lanes",
                "enabled",
                "coverage_state",
                "parameters",
                "decision_state",
            )
            if hasattr(value, key)
        }
    return {}


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "__dict__"):
        return {
            key: getattr(value, key)
            for key in (
                "stage_name",
                "wall_clock_ns",
                "wall_time_share",
                "gpu_candidate",
            )
            if hasattr(value, key)
        }
    return {}


def _as_sequence(value: Any) -> tuple[Any, ...]:
    if isinstance(value, tuple | list):
        return tuple(value)
    return ()


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _ordered_unique(values: Any) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        item = str(value)
        if item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered


def _json_ready(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__") and not isinstance(value, type):
        return {str(key): _json_ready(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_ready(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _format_count_mapping(value: Any) -> str:
    mapping = _as_mapping(value)
    if not mapping:
        return "none"
    return ", ".join(f"{key}={mapping[key]}" for key in sorted(mapping))


def _render_stage_link_row(item: Any) -> str:
    link = _as_mapping(item)
    return (
        "<tr>"
        f"<td>{escape(str(link.get('stage_name', 'unknown')))}</td>"
        f"<td>{escape(str(link.get('symbol_count', 0)))}</td>"
        f"<td>{escape(', '.join(str(value) for value in _as_sequence(link.get('hardware_fit'))))}</td>"
        f"<td>{escape(str(link.get('recommended_probe', 'N/A')))}</td>"
        "</tr>"
    )


def _render_entry_row(item: Any) -> str:
    entry = _as_mapping(item)
    return (
        "<tr>"
        f"<td>{escape(str(entry.get('symbol', 'unknown')))}</td>"
        f"<td>{escape(', '.join(str(value) for value in _as_sequence(entry.get('role_tags'))))}</td>"
        f"<td>{escape(', '.join(str(value) for value in _as_sequence(entry.get('hardware_fit'))))}</td>"
        f"<td>{escape(str(entry.get('reason', 'N/A')))}</td>"
        "</tr>"
    )


def _render_decision_card_row(item: Any) -> str:
    card = _as_mapping(item)
    return (
        "<tr>"
        f"<td>{escape(str(card.get('target', 'unknown')))}</td>"
        f"<td>{escape(', '.join(str(value) for value in _as_sequence(card.get('hardware_fit'))))}</td>"
        f"<td>{escape(str(card.get('measurement_probe', 'N/A')))}</td>"
        f"<td>{escape(str(card.get('acceptance_threshold', 'N/A')))}</td>"
        "</tr>"
    )


def _render_workload_decision_link_row(item: Any) -> str:
    link = _as_mapping(item)
    return (
        "<tr>"
        f"<td>{escape(str(link.get('target', 'unknown')))}</td>"
        f"<td>{escape(', '.join(str(value) for value in _as_sequence(link.get('workload_classes'))))}<br><code>{escape(', '.join(str(value) for value in _as_sequence(link.get('hardware_lanes'))))}</code></td>"
        f"<td>{escape(', '.join(str(value) for value in _as_sequence(link.get('measured_workload_classes'))))}</td>"
        f"<td>{escape(', '.join(str(value) for value in _as_sequence(link.get('required_probe_workload_classes'))))}<br><code>{escape(str(link.get('decision_class', 'unknown')))}</code><br><code>{escape(', '.join(str(value) for value in _as_sequence(link.get('coverage_states'))))}</code></td>"
        "</tr>"
    )


def _render_next_probe_summary_row(item: Any) -> str:
    summary = _as_mapping(item)
    return (
        "<tr>"
        f"<td>{escape(str(summary.get('target', 'unknown')))}</td>"
        f"<td>{escape(str(summary.get('decision_effect', 'unknown')))}</td>"
        f"<td>{escape(str(summary.get('next_probe', 'N/A')))}</td>"
        f"<td>{escape(str(summary.get('falsifier', 'N/A')))}</td>"
        "</tr>"
    )
