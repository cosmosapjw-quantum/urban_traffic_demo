"""Validate and render the sole MetroFlow V1 execution plan. No external packages."""

from pathlib import Path
from collections import Counter
import argparse
import json
import hashlib
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "docs/v1/PLAN.json"
STATUSES = {
    "PLANNED",
    "READY",
    "IN_PROGRESS",
    "VERIFIED_SCOPED",
    "MERGED",
    "ACCEPTED",
    "BLOCKED",
    "STOPPED",
}
LABELS = {
    "P00": "Plan authority",
    "M01": "Area access laws",
    "T01": "Whole journey clock",
    "I01": "Repository integration",
    "M02": "Layered city contract",
    "M03": "Activity and portals",
    "D01": "Daily cohort demand",
    "T02": "Finite-response closure",
    "T03": "Lane groups and nodes",
    "T04": "Time and flux transport",
    "R01": "Causal information",
    "R02": "Committed routing",
    "B01": "Bus and freight",
    "C01": "World and scheduler",
    "M04": "Lagged development",
    "C02": "Full-day scenarios",
    "P01": "Measured optimization",
    "V01": "Physics audit",
    "V02": "Map audit",
    "V03": "Local 100k day",
    "RLS01": "Release",
}


def expanded(plan):
    """Materialize shared per-node contracts without a second authority."""
    defaults = plan["node_defaults"]
    return dict(
        plan,
        nodes=[
            dict(
                n,
                evidence_required=n.get("evidence_required", defaults["evidence_required"]),
                rollback=n.get("rollback", defaults["rollback"]),
                pr=dict(
                    n["pr"],
                    review=n["pr"].get("review", defaults["pr_review"]),
                    merge_policy=n["pr"].get("merge_policy", defaults["pr_merge_policy"]),
                ),
            )
            for n in plan["nodes"]
        ],
    )


def validate(plan, release=False):
    if plan.get("plan_id") != "METROFLOW-V1" or plan.get("schema_version") != 1:
        raise ValueError("unknown plan schema")
    nodes = plan["nodes"]
    by = {n["id"]: n for n in nodes}
    if not nodes or len(by) != len(nodes):
        raise ValueError("nonempty unique node identifiers required")
    required = (
        "title",
        "depends_on",
        "files",
        "inputs",
        "outputs",
        "assumptions",
        "invariants",
        "observables",
        "tests",
        "acceptance",
        "failure_classification",
        "positive_next_action",
        "resource_budget",
        "pr",
    )
    for n in nodes:
        for key in required:
            if key not in n or (not n[key] and key != "depends_on"):
                raise ValueError(f"{n['id']}: missing {key}")
        if n["status"] not in STATUSES:
            raise ValueError("invalid node status")
        if any(d not in by for d in n["depends_on"]):
            raise ValueError("unknown dependency")
        if len(set(n["depends_on"])) != len(n["depends_on"]):
            raise ValueError("duplicate dependency")
        if any(c not in plan["contracts"] for c in n["contracts"]):
            raise ValueError("unknown contract")
        if n["pr"]["base"] != plan["integration_branch"]:
            raise ValueError("PR target drift")
    visited = set()
    active = set()
    order = []

    def visit(k):
        if k in active:
            raise ValueError("cycle in execution DAG")
        if k in visited:
            return
        active.add(k)
        for d in by[k]["depends_on"]:
            visit(d)
        active.remove(k)
        visited.add(k)
        order.append(k)

    for k in by:
        visit(k)
    for r in plan["requirements"] + plan["release_gates"]:
        if not r["nodes"] or any(k not in by for k in r["nodes"]):
            raise ValueError("unmapped requirement or gate")
    if len({n["pr"]["key"] for n in nodes}) != len(nodes):
        raise ValueError("duplicate logical PR key")
    next_id = plan.get("next_node")
    if next_id is None:
        if any(n["status"] != "ACCEPTED" for n in nodes):
            raise ValueError("unfinished plan needs a next node")
    elif next_id not in by or by[next_id]["status"] == "ACCEPTED":
        raise ValueError("invalid next node")
    if release:
        if any(n["status"] != "ACCEPTED" for n in nodes):
            raise ValueError("release BLOCKED: all mandatory nodes must be ACCEPTED with evidence")
        proofs = plan.get("release_evidence", {})
        for gate in plan["release_gates"]:
            proof = proofs.get(gate["id"], {})
            if proof.get("status") != "PASS" or not proof.get("path") or not proof.get("sha256"):
                raise ValueError("release BLOCKED: missing receipt for " + gate["id"])
            path = (ROOT / proof["path"]).resolve()
            if not path.is_relative_to(ROOT) or not path.is_file():
                raise ValueError("release BLOCKED: receipt path " + gate["id"])
            if hashlib.sha256(path.read_bytes()).hexdigest() != proof["sha256"]:
                raise ValueError("release BLOCKED: receipt byte mismatch " + gate["id"])
    return order


def md_list(items):
    return "\n".join("- " + str(x) for x in items) + "\n"


def render_master(p):
    p = expanded(p)
    order = validate(p)
    by = {n["id"]: n for n in p["nodes"]}
    text = [
        f"# MetroFlow V1 전체 실행계획\n\n버전 **{p['version']}**, {p['date']}. 규범 원본: `docs/v1/PLAN.json`. 이 문서는 자동 생성된다. 직접 고치지 않는다.\n",
        p["authority"] + "\n",
        "## 1. 1차 완성의 의미\n\n" + p["product"]["definition"] + "\n",
        "**완성 판정:** `"
        + p["product"]["completion_label"]
        + "`. 실측 보정·게임 대비 우월성은 포함하지 않는다.\n",
        "**규모:** " + json.dumps(p["product"]["scale"], ensure_ascii=False) + "\n",
        "### 포함\n" + md_list(p["product"]["mandatory"]),
        "### 제외\n" + md_list(p["product"]["exclusions"]),
        "### 완료로 간주하지 않는 것\n" + md_list(p["product"]["not_completion"]),
        "## 2. 권위·변경·PR 실행 규칙\n",
    ]
    for k, v in p["execution_policy"].items():
        text.append(
            f"**{k}**\n\n"
            + (
                md_list(v)
                if isinstance(v, list)
                else json.dumps(v, ensure_ascii=False)
                if isinstance(v, dict)
                else str(v)
            )
            + "\n"
        )
    text.extend(
        [
            "현재 통합 대상: `"
            + p["integration_branch"]
            + "`; bootstrap: `"
            + p["bootstrap_branch"]
            + "`.\n",
            "최초 PR에서 `I01` 전체 저장소 수용을 완료한 뒤 병합한다. 현재 sandbox 검증은 이 병합·릴리스 검증을 대신하지 않는다.\n",
            "## 3. 원래 프로젝트에서의 선택\n" + md_list(p["original_scope_decisions"]),
            "## 4. 선택한 아키텍처와 계약\n",
        ]
    )
    for k, v in p["selected_architecture"].items():
        text.append(
            "**"
            + k
            + "**: "
            + (json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v)
            + "\n"
        )
    for k, v in p["contracts"].items():
        text.append(f"### {k}\n{v}\n")
    text.append(
        "### 수치 수용 정책\n```json\n"
        + json.dumps(p["numerical_policy"], ensure_ascii=False, indent=2)
        + "\n```\n"
    )
    text.append(
        "## 5. 의존성 DAG와 현재 상태\n\nDAG는 실행 의존성이지 일정 추정이 아니다. `VERIFIED_SCOPED`는 해당 범위의 검증이며 완성 제품의 완료율이 아니다.\n"
    )
    text.append("```mermaid\n" + render_mermaid(p) + "```\n")
    text.append("|노드|작업|의존|상태|\n|---|---|---|---|")
    for k in order:
        n = by[k]
        text.append(f"|{k}|{n['title']}|{', '.join(n['depends_on']) or '없음'}|{n['status']}|")
    text.append("\n## 6. 노드별 상세 작업 패키지\n")
    headings = {
        "inputs": "입력",
        "outputs": "산출물·인터페이스",
        "assumptions": "선택한 가정·범위",
        "invariants": "불변·보존·금지조건",
        "observables": "관측가능량",
        "contracts": "공통 계약",
        "files": "대상 파일 또는 예정 경로",
        "tests": "실행·수용시험 명령",
        "acceptance": "완료조건",
        "failure_classification": "실패 분류",
        "positive_next_action": "통과 후 다음 행동",
        "resource_budget": "예산·종료조건",
        "evidence_required": "증거",
        "rollback": "롤백",
    }
    for k in order:
        n = by[k]
        text.append(
            f"### {k}. {n['title']}\n\n의존: {', '.join(n['depends_on']) or '없음'}; 상태: **{n['status']}**.\n"
        )
        text.append(
            "예정 PR: `"
            + n["pr"]["key"]
            + "`, branch `"
            + n["pr"]["branch"]
            + "` → `"
            + n["pr"]["base"]
            + "`.\n"
        )
        if n["status"] == "PLANNED":
            text.append(
                "아래 파일·명령은 목표 계약이다. 아직 존재하거나 통과했다고 주장하지 않는다.\n"
            )
        for key, title in headings.items():
            value = n[key]
            text.append(
                "**"
                + title
                + "**\n\n"
                + (md_list(value) if isinstance(value, list) else str(value) + "\n")
            )
        text.append("**PR 검토 항목**\n\n" + md_list(n["pr"]["review"]))
    text.append("## 7. 요구사항 추적\n|요구|내용|노드|\n|---|---|---|")
    for r in p["requirements"]:
        text.append(f"|{r['id']}|{r['text']}|{', '.join(r['nodes'])}|")
    text.append("\n## 8. 최종 release gates\n")
    for gate in p["release_gates"]:
        text.append(
            f"### {gate['id']}\n{gate['criterion']}\n\n책임 노드: {', '.join(gate['nodes'])}.\n"
        )
    text.append("## 9. 근거와 현재 실행 경계\n")
    text.append(
        "```json\n" + json.dumps(p["current_execution"], ensure_ascii=False, indent=2) + "\n```\n"
    )
    for s in p["source_pins"]:
        text.append(f"- `{s['path']}` @ `{s['sha']}`: {s['authority']}")
    text.append(
        "\n다음 작업: **"
        + (p["next_node"] or "계획 종료")
        + "**. `python tools/v1_plan.py next`로 같은 결과를 조회한다.\n"
    )
    return "\n".join(text) + "\n"


def render_mermaid(p):
    lines = ["flowchart TD"]
    for n in p["nodes"]:
        lines.append(f'  {n["id"]}["{n["id"]}: {n["title"]}"]')
    for n in p["nodes"]:
        lines.extend(f"  {d} --> {n['id']}" for d in n["depends_on"])
    return "\n".join(lines) + "\n"


def render_dot(p):
    lines = [
        "digraph V1 {",
        'graph [rankdir=TB, nodesep=0.28, ranksep=0.4, labelloc=t, label="MetroFlow V1 dependency DAG | bold: scoped verification, dashed: planned"];',
        'node [shape=box, fontname="DejaVu Sans", fontsize=11, margin="0.12,0.10"];',
        "edge [arrowsize=0.6];",
    ]
    for n in p["nodes"]:
        style = "rounded,bold" if n["status"] == "VERIFIED_SCOPED" else "rounded,dashed"
        lines.append(f'{n["id"]} [label="{n["id"]}\\n{LABELS[n["id"]]}", style="{style}"];')
    for n in p["nodes"]:
        lines.extend(f"{d} -> {n['id']};" for d in n["depends_on"])
    lines.append("}")
    return "\n".join(lines) + "\n"


def render_prs(p):
    p = expanded(p)
    text = [
        "# V1 PR 작업표\n",
        "`PLAN.json`에서 생성. 논리 PR key는 GitHub PR 번호가 아니다. 미래 PR을 실제 생성했다고 표시하지 않는다.\n",
        "초기 P00/M01/T01와 I01 수용은 하나의 bootstrap PR에 들어간다. 그 외는 의존 PR이 통합된 뒤 한 노드씩 실행한다.\n",
        "|키|제목|의존|branch|base|\n|---|---|---|---|---|",
    ]
    for n in p["nodes"]:
        q = n["pr"]
        text.append(
            f"|{q['key']}|{q['title']}|{', '.join(n['depends_on']) or '-'}|{q['branch']}|{q['base']}|"
        )
    text.append("\n## 모든 PR 본문에 포함할 내용\n")
    text.append(md_list(p["nodes"][0]["pr"]["review"]))
    text.append(
        "각 노드의 입력·파일·가정·단위·수용시험·중단조건은 MASTER_PLAN_KO.md의 해당 절을 그대로 참조한다.\n"
    )
    return "\n".join(text) + "\n"


def outputs(p):
    return {
        "MASTER_PLAN_KO.md": render_master(p),
        "DAG.mmd": render_mermaid(p),
        "DAG.dot": render_dot(p),
        "PR_CATALOG_KO.md": render_prs(p),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("validate", "render", "next"))
    ap.add_argument("--plan", type=Path, default=DEFAULT)
    ap.add_argument("--release", action="store_true")
    args = ap.parse_args()
    p = json.loads(args.plan.read_text())
    order = validate(p, args.release)
    if args.command == "render":
        for name, text in outputs(p).items():
            (args.plan.parent / name).write_text(text)
        print("Generated plan views:", ", ".join(outputs(p)))
    elif args.command == "validate":
        for name, text in outputs(p).items():
            path = args.plan.parent / name
            if not path.exists() or path.read_text() != text:
                raise ValueError("generated plan drift: " + name)
        print(
            json.dumps(
                dict(
                    status="VALID_PLAN_NOT_RELEASE",
                    nodes=len(order),
                    status_counts=dict(Counter(n["status"] for n in p["nodes"])),
                    next_node=p["next_node"],
                    full_repository_ci=p["current_execution"]["full_repository_ci"],
                ),
                ensure_ascii=False,
            )
        )
    else:
        if p["next_node"] is None:
            print(
                json.dumps(
                    dict(
                        node=None, instruction="V1 계획 종료. 새 작업은 별도 승인 계획이 필요하다."
                    ),
                    ensure_ascii=False,
                )
            )
            return
        n = next(n for n in p["nodes"] if n["id"] == p["next_node"])
        print(
            json.dumps(
                dict(
                    node=n["id"],
                    title=n["title"],
                    branch=n["pr"]["branch"],
                    instruction=(
                        "같은 bootstrap PR에서 전체 저장소/3.12·3.13 수용을 실행한다. 병합 전 새 기능 PR을 선행하지 않는다."
                        if n["id"] in p["bootstrap_pr_scope"]
                        else "선행 노드의 ACCEPTED 증거를 확인하고 이 노드의 계약·파일·시험만 실행한다."
                    ),
                    tests=n["tests"],
                    acceptance=n["acceptance"],
                ),
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError) as exc:
        print("PLAN_ERROR:", exc, file=sys.stderr)
        raise SystemExit(2)
