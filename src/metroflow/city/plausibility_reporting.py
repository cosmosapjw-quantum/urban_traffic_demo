"""Artifact rendering for the realistic-city plausibility audit."""

from __future__ import annotations

import hashlib
from html import escape
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .plausibility_audit import RealisticCityPlausibilityAudit

__all__ = ["write_plausibility_artifacts"]


def write_plausibility_artifacts(
    artifact_prefix: str | Path,
    *,
    report: RealisticCityPlausibilityAudit,
    preserve_existing_html: bool = False,
) -> dict[str, Path]:
    """Write deterministic JSON, Markdown, HTML, and manifest artifacts."""

    prefix = Path(artifact_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    paths = {
        "json": Path(f"{prefix}.json"),
        "markdown": Path(f"{prefix}.md"),
        "html": Path(f"{prefix}.html"),
        "manifest": Path(f"{prefix}.manifest.json"),
    }
    paths["json"].write_text(
        json.dumps(
            report.as_dict(include_previews=False),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    paths["markdown"].write_text(_render_markdown(report), encoding="utf-8")
    if preserve_existing_html:
        if not paths["html"].is_file():
            raise FileNotFoundError(
                "preserve_existing_html requires an existing HTML artifact"
            )
    else:
        paths["html"].write_text(_render_html(report), encoding="utf-8")
    manifest = {
        "artifact_format_version": report.schema_version,
        "evidence_status": report.evidence_status,
        "report_fingerprint": report.fingerprint,
        "reference_corpus_fingerprint": report.reference_corpus_fingerprint,
        "map_count": report.map_count,
        "overall_pass": report.overall_pass,
        "raw_osm_data_included": False,
        "external_data_learning_used": False,
        "files": {
            key: {"path": path.name, "sha256": _file_sha256(path)}
            for key, path in paths.items()
            if key != "manifest"
        },
    }
    paths["manifest"].write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return paths


def _render_markdown(report: RealisticCityPlausibilityAudit) -> str:
    lines = [
        "# Metroflow Realistic City Plausibility Audit",
        "",
        "> DIAGNOSTIC ONLY: broad synthetic plausibility audit; not named-city validation.",
        "",
        f"- report fingerprint: `{report.fingerprint}`",
        f"- maps: `{report.map_count}`",
        f"- passed maps: `{report.passed_map_count}`",
        f"- overall: `{'PASS' if report.overall_pass else 'FAIL-CLOSED'}`",
        "- raw OSM included: `false`",
        "- external-data learning: `false`",
        "",
        "## Fixed Empirical Envelopes",
        "",
        "| metric | reference min | reference max | accepted lower | accepted upper |",
        "|---|---:|---:|---:|---:|",
    ]
    lines.extend(
        f"| {item.metric} | {item.reference_min:.6g} | {item.reference_max:.6g} | "
        f"{item.lower:.6g} | {item.upper:.6g} |"
        for item in report.envelopes
    )
    lines.extend(
        [
            "",
            "## Style Results",
            "",
            "| style | maps passed | empirical failures | structural failures |",
            "|---|---:|---:|---:|",
        ]
    )
    for style in report.style_ids:
        summary = report.style_summaries[style]
        lines.append(
            f"| {style} | {int(summary['passed_map_count'])}/{int(summary['map_count'])} | "
            f"{int(summary['empirical_failure_count'])} | "
            f"{int(summary['structural_failure_count'])} |"
        )
    lines.extend(
        [
            "",
            "## Diagnostic Counterevidence",
            "",
            "These fields are not admission gates. They expose repeated motifs and hierarchy imbalance for review.",
            "",
            "| style | dominant 10m length bin | dominant 2500m2 block bin | local length share | collector length share | max branch-free corridor m |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for style in report.style_ids:
        summary = report.style_summaries[style]
        lines.append(
            f"| {style} | {float(summary['dominant_length_bin_share_median']):.3f} | "
            f"{float(summary['dominant_block_area_bin_share_median']):.3f} | "
            f"{float(summary['road_class_local_length_share_median']):.3f} | "
            f"{float(summary['road_class_collector_length_share_median']):.3f} | "
            f"{float(summary['maximum_branch_free_corridor_m_max']):.1f} |"
        )
    failed = tuple(record for record in report.records if not record.passed)
    lines.extend(["", "## Failed Maps", ""])
    if not failed:
        lines.append("None.")
    else:
        lines.extend(
            [
                "| style | seed | empirical | structural |",
                "|---|---:|---|---|",
            ]
        )
        lines.extend(
            f"| {record.style_id} | {record.seed} | "
            f"{', '.join(record.empirical_failures) or '-'} | "
            f"{', '.join(record.structural_failures) or '-'} |"
            for record in failed
        )
    lines.extend(
        [
            "",
            "## Measurement Limits",
            "",
            "- Circuity is measured on compiled straight fragments and is therefore 1.0 by construction in the current compiler; it is not evidence of realistic street curvature.",
            "- The pinned eight-city corpus defines a broad envelope, not a representative global-city sample or named-city calibration.",
            "- Motif, hierarchy, terrain, and land-use counters are diagnostic and do not introduce new admission thresholds.",
            "",
            "## Compact CCoT",
            "",
            "- Question: do all fixed maps satisfy empirical and structural gates?",
            "- Evidence: per-map metrics plus diagnostic motif and hierarchy counters.",
            "- Inference: aggregate averages cannot override any failed map.",
            "- Counterevidence checked: repeated motifs, hierarchy imbalance, block repetition, and single-seed success.",
            f"- Decision: `{'pass' if report.overall_pass else 'fail_closed'}`.",
            "- Falsifier: any failure in the fixed matrix.",
            "- Next action: run PR63 scale evidence without changing these thresholds.",
            "",
        ]
    )
    return "\n".join(lines)


def _render_html(report: RealisticCityPlausibilityAudit) -> str:
    panels = []
    for record in report.records:
        if record.preview is None:
            continue
        layers = record.preview["layers"]
        panels.append(
            f'<section class="style"><h2>{escape(record.style_id)} / seed {record.seed}</h2>'
            '<div class="layer-grid">'
            + _render_preview_svg(record.preview, "terrain", layers["terrain"])
            + _render_preview_svg(record.preview, "roads", layers["roads"])
            + _render_preview_svg(record.preview, "blocks", layers["blocks"])
            + _render_preview_svg(record.preview, "land_use", layers["land_use"])
            + _render_preview_svg(record.preview, "runtime", layers["runtime"])
            + "</div></section>"
        )
    status = "PASS" if report.overall_pass else "FAIL-CLOSED"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Metroflow realistic city plausibility audit</title>
<style>
body{{margin:0;background:#f1f3f5;color:#1d2733;font:13px system-ui,sans-serif}}header{{padding:18px 24px;background:#fff;border-bottom:1px solid #c7cdd4}}main{{padding:16px}}.status{{font-weight:700}}.warning{{color:#8b2f23}}.style{{margin:0 0 16px;background:#fff;border:1px solid #c7cdd4;border-radius:6px;padding:12px}}h1,h2,p{{margin:4px 0 10px}}.layer-grid{{display:grid;grid-template-columns:repeat(5,minmax(220px,1fr));gap:8px;overflow:auto}}figure{{margin:0;border:1px solid #d5dae0;background:#f8f9fa}}figcaption{{padding:6px 8px;font-weight:600}}svg{{display:block;width:100%;aspect-ratio:1/1;background:#eef1f3}}.road-local{{stroke:#8d969f}}.road-collector{{stroke:#4f8f7b}}.road-arterial{{stroke:#d28b37}}.road-expressway{{stroke:#315f9f}}.road-bridge{{stroke:#2f7783}}.block{{fill:none;stroke:#65717d;stroke-width:4}}.runtime-road{{fill:none;stroke:#4f5964;stroke-width:3}}.runtime-node{{fill:#b85f4c}}.residential{{fill:#4f8f7b}}.commercial{{fill:#315f9f}}.mixed_use{{fill:#7d67ad}}.industrial{{fill:#9a6d43}}.open_space{{fill:#85a66f}}
</style></head><body><header><h1>Realistic synthetic city audit</h1>
<p class="warning">DIAGNOSTIC ONLY. Not named-city, traffic, demand, or land-use evolution validation.</p>
<p class="status">{status}: {report.passed_map_count}/{report.map_count} maps passed</p>
<p>Fingerprint <code>{report.fingerprint}</code></p></header><main>{''.join(panels)}</main></body></html>"""


def _render_preview_svg(
    preview: Mapping[str, Any],
    layer_name: str,
    layer: Mapping[str, Any],
) -> str:
    width = float(preview["width_m"])
    height = float(preview["height_m"])
    min_x = -width * 0.5
    min_y = -height * 0.5
    elements: list[str] = []
    if layer_name == "terrain":
        for cell in layer["cells"]:
            if cell["water"]:
                fill = "#7fb7c9"
            elif not cell["buildable"]:
                fill = "#9ca69a"
            else:
                shade = int(
                    225
                    - min(
                        75,
                        max(0, float(cell["elevation"]) - 18.0) * 0.7,
                    )
                )
                fill = f"rgb({shade},{shade + 5},{max(0, shade - 8)})"
            elements.append(
                f'<rect x="{float(cell["x"]):.2f}" y="{float(cell["y"]):.2f}" '
                f'width="{float(cell["width"]):.2f}" '
                f'height="{float(cell["height"]):.2f}" fill="{fill}" />'
            )
    elif layer_name == "roads":
        elements.extend(
            _svg_polyline(
                item["points"],
                css_class=f'road-{escape(str(item["road_class"]))}',
                width=10.0,
            )
            for item in layer["roads"]
        )
    elif layer_name == "blocks":
        elements.extend(
            _svg_polygon(item["polygon"], css_class="block")
            for item in layer["blocks"]
        )
    elif layer_name == "land_use":
        elements.extend(
            _svg_polygon(
                item["polygon"],
                css_class=escape(str(item["land_use_type"])),
            )
            for item in layer["blocks"]
        )
    elif layer_name == "runtime":
        elements.extend(
            _svg_polyline(item["points"], css_class="runtime-road", width=4.0)
            for item in layer["roads"]
        )
        node_step = max(1, len(layer["nodes"]) // 800)
        elements.extend(
            f'<circle class="runtime-node" cx="{float(x):.2f}" '
            f'cy="{float(y):.2f}" r="8" />'
            for x, y in layer["nodes"][::node_step]
        )
    return (
        f'<figure><figcaption>{escape(layer_name.replace("_", " "))}</figcaption>'
        f'<svg data-layer="{escape(layer_name)}" '
        f'viewBox="{min_x:.2f} {min_y:.2f} {width:.2f} {height:.2f}">'
        f'<g transform="scale(1 -1)">{"".join(elements)}</g></svg></figure>'
    )


def _svg_polyline(
    points: Iterable[tuple[float, float]],
    *,
    css_class: str,
    width: float,
) -> str:
    value = " ".join(f"{float(x):.2f},{float(y):.2f}" for x, y in points)
    return (
        f'<polyline class="{css_class}" points="{value}" fill="none" '
        f'stroke-width="{float(width):.2f}" stroke-linecap="round" />'
    )


def _svg_polygon(
    points: Iterable[tuple[float, float]],
    *,
    css_class: str,
) -> str:
    value = " ".join(f"{float(x):.2f},{float(y):.2f}" for x, y in points)
    return f'<polygon class="{css_class}" points="{value}" opacity="0.68" />'


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
