"""Artifact rendering for the realistic synthetic city scale audit."""

from __future__ import annotations

import hashlib
import json
from html import escape
from pathlib import Path

from .realistic_city_scale import RealisticCityScaleReport

__all__ = ["write_realistic_city_scale_artifacts"]


def write_realistic_city_scale_artifacts(
    artifact_prefix: str | Path,
    report: RealisticCityScaleReport,
) -> dict[str, Path]:
    prefix = Path(artifact_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": Path(f"{prefix}.json"),
        "markdown": Path(f"{prefix}.md"),
        "html": Path(f"{prefix}.html"),
        "manifest": Path(f"{prefix}.manifest.json"),
    }
    paths["json"].write_text(
        json.dumps(report.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    paths["markdown"].write_text(_render_markdown(report), encoding="utf-8")
    paths["html"].write_text(_render_html(report), encoding="utf-8")
    manifest = {
        "schema_version": "realistic_city_scale_manifest_v1",
        "claim_status": "diagnostic_scale_gate",
        "report_fingerprint": report.fingerprint,
        "default_promotion_eligible": report.default_promotion_eligible,
        "files": {
            key: {
                "path": str(path),
                "sha256": _file_sha256(path),
                "bytes": path.stat().st_size,
            }
            for key, path in paths.items()
            if key != "manifest"
        },
        "visual_audit_dependency": (
            "artifacts/runtime_spine_review/realistic-city-pr62-plausibility.png"
        ),
        "visual_claim_status": "reused_diagnostic_only_no_generator_change",
    }
    paths["manifest"].write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return paths


def _render_markdown(report: RealisticCityScaleReport) -> str:
    lines = [
        "# Realistic Synthetic City Scale Gate",
        "",
        f"- Claim status: `{report.claim_status}`",
        f"- Report fingerprint: `{report.fingerprint}`",
        f"- Populations: `{', '.join(str(value) for value in report.populations)}`",
        f"- Seeds: `{', '.join(str(value) for value in report.seeds)}`",
        f"- Fixed runtime ticks: `{report.num_steps}`",
        f"- Performance gate: `{'PASS' if report.performance_gate_pass else 'FAIL'}`",
        f"- Prior PR62 plausibility gate: `{report.prior_plausibility_gate_status}`",
        f"- Default promotion eligible: `{str(report.default_promotion_eligible).lower()}`",
        "",
        "This artifact is a host-local diagnostic. Performance cannot override the",
        "independent PR62 morphology/plausibility failure.",
        "",
        "## 100k Performance Pairs",
        "",
        f"| Seed | Generation ratio | RSS ratio | {report.num_steps}-tick ratio | Legacy budget ticks | Realistic budget ticks | Citizens L/R | Trips L/R | Pass |",
        "|---:|---:|---:|---:|---:|---:|:---:|---:|:---:|",
    ]
    for item in report.performance_pairs:
        lines.append(
            "| "
            f"{item.seed} | {item.generation_ratio:.3f} | "
            f"{item.peak_rss_ratio:.3f} | {item.runtime_ratio:.3f} | "
            f"{item.legacy_budget_ticks} | {item.realistic_budget_ticks} | "
            f"{item.legacy_citizen_count}/{item.realistic_citizen_count} | "
            f"{item.legacy_trip_request_count}/{item.realistic_trip_request_count} | "
            f"{'PASS' if item.all_pass else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "Thresholds: generation <=2.0x, peak RSS <=1.5x, parent runtime",
            "<=1.25x, and realistic paired-budget tick count >= legacy.",
            "",
            "## Realistic Generation Stage Shares",
            "",
            "| Stage | Minimum | Mean | Maximum | Rust probe gate |",
            "|---|---:|---:|---:|:---:|",
        ]
    )
    for item in report.stage_shares:
        lines.append(
            f"| `{item.stage_name}` | {item.minimum_share:.3f} | "
            f"{item.mean_share:.3f} | {item.maximum_share:.3f} | "
            f"{'OPEN' if item.rust_probe_eligible else 'CLOSED'} |"
        )
    lines.extend(
        [
            "",
            f"Rust generation probe admitted: `{str(report.rust_generation_probe_admitted).lower()}`",
            f"Candidate stage: `{report.rust_candidate_stage or 'none'}`",
            "",
            "A stage must be one of the A*/planarization/face-extraction groups and",
            "reach at least 30 percent of city-authority time on every fixed seed.",
            "PR63 records admission only and adds no Rust implementation.",
            "",
            "`unattributed_pipeline_overhead` contains blueprint construction, CSR",
            "assembly/validation, final generated-map assembly, and wrapper overhead.",
            "It is visible counterevidence and is never Rust-admission eligible.",
            "",
            "## City-Authority Runs",
            "",
            "| Population | Seed | Mode | Scenario | Style | City ms | Peak RSS MiB | Nodes | Links |",
            "|---:|---:|---|---|---|---:|---:|---:|---:|",
        ]
    )
    for item in report.generation_runs:
        lines.append(
            f"| {item.population_target} | {item.seed} | `{item.topology_mode}` | "
            f"`{item.scenario_id}` | `{item.morphology_style_id}` | "
            f"{item.city_authority_wall_ns / 1e6:.3f} | "
            f"{item.peak_rss_kib / 1024.0:.2f} | {item.node_count} | "
            f"{item.link_count} |"
        )
    lines.extend(
        [
            "",
            "The 1k and 10k rows both use `synthetic_smoke`; 100k switches to",
            "`synthetic_100k`. This is two map extents plus three population/init",
            "workloads, not a continuous three-size city-generation curve.",
            "",
            "## Fixed-Step Runs",
            "",
            "| Population | Seed | Mode | Scenario/style | Init ms | Runtime ms | Init RSS MiB | Citizens | Trips |",
            "|---:|---:|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for item in report.fixed_runs:
        lines.append(
            f"| {item.population_target} | {item.seed} | `{item.topology_mode}` | "
            f"`{item.scenario_id}/{item.morphology_style_id}` | "
            f"{item.initialization_wall_ns / 1e6:.3f} | "
            f"{item.runtime_wall_ns / 1e6:.3f} | "
            f"{item.peak_rss_kib / 1024.0:.2f} | "
            f"{item.citizen_count} | {item.trip_request_count} |"
        )
    lines.extend(
        [
            "",
            "## Compact CCoT",
            "",
            "Question: Does scale evidence authorize promotion or one narrow generation-core probe?",
            "",
            f"Evidence: Fresh subprocess runs compare paired legacy and realistic workloads at {len(report.populations)} population target(s) and {len(report.seeds)} seed(s).",
            "",
            "Inference: The performance and Rust-admission booleans above follow fixed thresholds; they do not assess morphology.",
            "",
            "Counterevidence checked: cumulative RSS, seed mismatch, unpaired wall budgets, nested-stage denominator drift, empty routing workload, and PR62 gate status.",
            "",
            "Decision: Default promotion requires both performance and independent plausibility; a Rust follow-up requires the all-seed stage-share gate.",
            "",
            "Falsifier: Any worker not isolated, any workload mismatch, any threshold change after observation, or use of this smoke artifact as empirical validation.",
            "",
            "Next action: PR64 consumes this report together with PR62 and either promotes or records BLOCKED without changing the default.",
            "",
            "## Visual Dependency",
            "",
            "No generator code changed in PR63. The PR62 five-layer contact sheet is",
            "reused as diagnostic-only visual evidence and is not validation.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_html(report: RealisticCityScaleReport) -> str:
    pair_rows = "".join(
        "<tr>"
        f"<td>{item.seed}</td>"
        f"<td>{item.generation_ratio:.3f}</td>"
        f"<td>{item.peak_rss_ratio:.3f}</td>"
        f"<td>{item.runtime_ratio:.3f}</td>"
        f"<td>{item.legacy_budget_ticks}</td>"
        f"<td>{item.realistic_budget_ticks}</td>"
        f"<td>{'PASS' if item.all_pass else 'FAIL'}</td>"
        "</tr>"
        for item in report.performance_pairs
    )
    stage_rows = "".join(
        "<tr>"
        f"<td>{escape(item.stage_name)}</td>"
        f"<td>{item.minimum_share:.3f}</td>"
        f"<td>{item.mean_share:.3f}</td>"
        f"<td>{item.maximum_share:.3f}</td>"
        f"<td>{'OPEN' if item.rust_probe_eligible else 'CLOSED'}</td>"
        "</tr>"
        for item in report.stage_shares
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Metroflow realistic city scale gate</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 0; color: #1b1d20; background: #f4f5f6; }}
main {{ max-width: 1180px; margin: 0 auto; padding: 32px; }}
h1, h2 {{ letter-spacing: 0; }}
.band {{ border-left: 5px solid #a6382d; background: white; padding: 16px 20px; margin: 18px 0; }}
.metrics {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
.metric {{ background: white; border: 1px solid #d8dadd; padding: 14px; }}
.metric strong {{ display: block; font-size: 1.3rem; margin-top: 6px; }}
table {{ width: 100%; border-collapse: collapse; background: white; margin-bottom: 24px; }}
th, td {{ border: 1px solid #d8dadd; padding: 8px; text-align: right; }}
th:first-child, td:first-child {{ text-align: left; }}
code {{ overflow-wrap: anywhere; }}
@media (max-width: 760px) {{ .metrics {{ grid-template-columns: 1fr; }} main {{ padding: 16px; }} }}
</style>
</head>
<body><main>
<h1>Realistic synthetic city scale gate</h1>
<div class="band"><strong>Diagnostic only.</strong> PR62 plausibility remains
independent and performance cannot promote a morphologically failing generator.</div>
<div class="metrics">
<div class="metric">Performance gate<strong>{'PASS' if report.performance_gate_pass else 'FAIL'}</strong></div>
<div class="metric">PR62 plausibility<strong>{escape(report.prior_plausibility_gate_status)}</strong></div>
<div class="metric">Default promotion<strong>{'ELIGIBLE' if report.default_promotion_eligible else 'BLOCKED'}</strong></div>
</div>
<h2>100k paired performance</h2>
<table><thead><tr><th>Seed</th><th>Generation</th><th>RSS</th><th>Runtime</th><th>Legacy ticks</th><th>Realistic ticks</th><th>Gate</th></tr></thead><tbody>{pair_rows}</tbody></table>
<h2>Generation stage shares</h2>
<table><thead><tr><th>Stage</th><th>Minimum</th><th>Mean</th><th>Maximum</th><th>Rust probe</th></tr></thead><tbody>{stage_rows}</tbody></table>
<p>Report fingerprint: <code>{escape(report.fingerprint)}</code></p>
<p>The unchanged PR62 contact sheet remains the visual smoke dependency; no
image in this report is empirical validation.</p>
</main></body></html>
"""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
