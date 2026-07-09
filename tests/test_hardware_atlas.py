from __future__ import annotations

import json
import sys
from pathlib import Path


def _write_fixture_source(root: Path) -> Path:
    source_root = root / "src" / "metroflow"
    (source_root / "routing").mkdir(parents=True)
    (source_root / "flow").mkdir(parents=True)
    (source_root / "sim").mkdir(parents=True)
    (source_root / "ui").mkdir(parents=True)
    (source_root / "routing" / "demo.py").write_text(
        """
import heapq


def compute_dynamic_potential_state(graph):
    frontier = []
    heapq.heappush(frontier, (0.0, 0))
    while frontier:
        cost, node = heapq.heappop(frontier)
        for edge in graph[node]:
            heapq.heappush(frontier, (cost + edge.cost, edge.to_node))
    return frontier
""",
        encoding="utf-8",
    )
    (source_root / "flow" / "demo.py").write_text(
        """
import numpy as np


def compute_flow_batch(queue, capacity):
    feasible = np.minimum(np.asarray(queue, dtype=np.float32), capacity)
    return np.asarray(feasible, dtype=np.float32)
""",
        encoding="utf-8",
    )
    (source_root / "sim" / "demo.py").write_text(
        """
def apply_agent_pool_write(pool):
    plugin_memory = {}
    for slot in pool:
        plugin_memory.setdefault(slot, {})["current_link_id"] = slot
    return plugin_memory
""",
        encoding="utf-8",
    )
    (source_root / "ui" / "demo.py").write_text(
        """
import json


def render_snapshot(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
""",
        encoding="utf-8",
    )
    return source_root


def test_hardware_atlas_classifies_fixture_symbols(tmp_path) -> None:
    from metroflow.benchmarks.hardware_atlas import build_hardware_atlas

    source_root = _write_fixture_source(tmp_path)
    report = build_hardware_atlas(source_root=source_root)

    assert report["report_type"] == "hardware_fit_atlas_v1"
    assert report["entry_count"] >= 4

    entries = {entry["symbol"]: entry for entry in report["entries"]}
    potential = entries["routing.demo.compute_dynamic_potential_state"]
    flow = entries["flow.demo.compute_flow_batch"]
    pool_write = entries["sim.demo.apply_agent_pool_write"]
    ui_render = entries["ui.demo.render_snapshot"]

    required_fields = {
        "module",
        "symbol",
        "path",
        "line",
        "role_tags",
        "data_surface",
        "hotspot_signals",
        "hardware_fit",
        "reason",
        "falsifier",
        "recommended_probe",
        "decision_state",
    }
    assert required_fields <= potential.keys()
    assert "graph_search" in potential["role_tags"]
    assert "cpu_parallel_rust" in potential["hardware_fit"]
    assert "array_numeric_core" in flow["role_tags"]
    assert "cpu_simd_numpy" in flow["hardware_fit"]
    assert "deterministic_mutation" in pool_write["role_tags"]
    assert "cpu_parallel_rust" in pool_write["hardware_fit"]
    assert "io_ui_reporting" in ui_render["role_tags"]
    assert "keep_python" in ui_render["hardware_fit"]


def test_hardware_atlas_links_runtime_stage_timings_to_symbol_groups(tmp_path) -> None:
    from metroflow.benchmarks.hardware_atlas import (
        build_hardware_atlas,
        link_runtime_stage_timings_to_atlas,
    )

    source_root = _write_fixture_source(tmp_path)
    report = build_hardware_atlas(
        source_root=source_root,
        runtime_stage_timings=(
            {
                "stage_name": "dynamic_potential_recompute",
                "wall_clock_ns": 1000,
                "wall_time_share": 0.55,
                "gpu_candidate": True,
            },
            {
                "stage_name": "flow_update",
                "wall_clock_ns": 500,
                "wall_time_share": 0.25,
                "gpu_candidate": False,
            },
        ),
    )
    links = {link["stage_name"]: link for link in report["stage_links"]}

    assert links["dynamic_potential_recompute"]["symbol_count"] >= 1
    assert "routing.demo.compute_dynamic_potential_state" in links["dynamic_potential_recompute"]["symbols"]
    assert "cpu_parallel_rust" in links["dynamic_potential_recompute"]["hardware_fit"]
    assert "flow.demo.compute_flow_batch" in links["flow_update"]["symbols"]
    assert link_runtime_stage_timings_to_atlas(
        report["entries"],
        [{"stage_name": "active_agent_pool_write", "wall_clock_ns": 10}],
    )[0]["stage_name"] == "active_agent_pool_write"


def test_hardware_atlas_aggregates_runtime_suite_stage_timings(tmp_path) -> None:
    from metroflow.benchmarks.hardware_atlas import build_hardware_atlas

    report = build_hardware_atlas(
        source_root=_write_fixture_source(tmp_path),
        runtime_suite_payload={
            "per_seed_results": [
                {
                    "seed": 41,
                    "runtime_stage_timings": [
                        {
                            "stage_name": "flow_update",
                            "wall_clock_ns": 100,
                            "wall_time_share": 0.20,
                            "gpu_candidate": False,
                        },
                        {
                            "stage_name": "dynamic_potential_recompute",
                            "wall_clock_ns": 400,
                            "wall_time_share": 0.50,
                            "gpu_candidate": True,
                        },
                    ],
                },
                {
                    "seed": 42,
                    "runtime_stage_timings": [
                        {
                            "stage_name": "flow_update",
                            "wall_clock_ns": 300,
                            "wall_time_share": 0.40,
                            "gpu_candidate": True,
                        },
                        {
                            "stage_name": "dynamic_potential_recompute",
                            "wall_clock_ns": 600,
                            "wall_time_share": 0.60,
                            "gpu_candidate": True,
                        },
                    ],
                },
            ],
        },
    )

    links = {link["stage_name"]: link for link in report["stage_links"]}

    assert [link["stage_name"] for link in report["stage_links"]] == [
        "flow_update",
        "dynamic_potential_recompute",
    ]
    assert links["flow_update"]["measurement"] == {
        "run_count": 2,
        "wall_clock_ns_total": 400,
        "mean_wall_clock_ns": 200.0,
        "max_wall_clock_ns": 300,
        "mean_wall_time_share": 0.3,
        "max_wall_time_share": 0.4,
        "gpu_candidate_run_count": 1,
    }
    assert [card["target"] for card in report["decision_cards"]] == [
        "flow_update",
        "dynamic_potential_recompute",
    ]


def test_hardware_atlas_does_not_import_accelerator_modules(tmp_path) -> None:
    accelerator_prefixes = ("jax", "torch", "_metroflow_rust")
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in accelerator_prefixes)
    }
    for module_name in tuple(saved_modules):
        sys.modules.pop(module_name, None)
    try:
        from metroflow.benchmarks.hardware_atlas import build_hardware_atlas

        build_hardware_atlas(source_root=_write_fixture_source(tmp_path))

        assert "jax" not in sys.modules
        assert "torch" not in sys.modules
        assert "_metroflow_rust" not in sys.modules
    finally:
        for module_name in tuple(sys.modules):
            if any(
                module_name == prefix or module_name.startswith(f"{prefix}.")
                for prefix in accelerator_prefixes
            ):
                sys.modules.pop(module_name, None)
        sys.modules.update(saved_modules)


def test_hardware_atlas_artifact_bundle_writes_json_markdown_html_and_manifest(tmp_path) -> None:
    from metroflow.benchmarks.hardware_atlas import (
        build_hardware_atlas,
        write_hardware_atlas_artifact_bundle,
    )

    report = build_hardware_atlas(
        source_root=_write_fixture_source(tmp_path),
        runtime_stage_timings=(
            {
                "stage_name": "dynamic_potential_recompute",
                "wall_clock_ns": 1000,
                "wall_time_share": 0.55,
                "gpu_candidate": True,
            },
        ),
    )
    paths = write_hardware_atlas_artifact_bundle(
        report,
        output_prefix=tmp_path / "hardware-fit-atlas",
    )

    payload = json.loads(paths["json"].read_text(encoding="utf-8"))
    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    markdown = paths["markdown"].read_text(encoding="utf-8")
    html = paths["html"].read_text(encoding="utf-8")

    assert paths["markdown"] == tmp_path / "hardware-fit-atlas.md"
    assert paths["json"] == tmp_path / "hardware-fit-atlas.json"
    assert paths["html"] == tmp_path / "hardware-fit-atlas.html"
    assert paths["manifest"] == tmp_path / "hardware-fit-atlas.manifest.json"
    assert payload["compact_ccot"]["Question"]
    assert "Hardware Fit Atlas" in markdown
    assert "Decision Cards" in markdown
    assert "dynamic_potential_recompute" in markdown
    assert "<main data-hardware-fit-atlas=" in html
    assert manifest["artifact_format_version"] == "hardware_fit_atlas_bundle_v1"
    assert manifest["report_type"] == "hardware_fit_atlas_v1"
    assert manifest["entry_count"] == payload["entry_count"]
    assert manifest["stage_link_count"] == 1


def test_hardware_atlas_cli_writes_artifact_bundle(tmp_path) -> None:
    from metroflow.benchmarks import run as benchmark_run_module

    prefix = tmp_path / "hardware-fit-atlas"
    exit_code = benchmark_run_module.main(
        [
            "--hardware-atlas",
            "--hardware-atlas-source-root",
            str(_write_fixture_source(tmp_path)),
            "--hardware-atlas-artifact-prefix",
            str(prefix),
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "hardware-fit-atlas.md").exists()
    assert (tmp_path / "hardware-fit-atlas.json").exists()
    assert (tmp_path / "hardware-fit-atlas.html").exists()
    assert (tmp_path / "hardware-fit-atlas.manifest.json").exists()
