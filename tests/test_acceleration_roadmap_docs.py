from __future__ import annotations

from pathlib import Path


def _section(markdown: str, heading: str) -> str:
    marker = f"## {heading}"
    start = markdown.index(marker)
    next_start = markdown.find("\n## ", start + len(marker))
    if next_start == -1:
        return markdown[start:]
    return markdown[start:next_start]


def _normalized(markdown: str) -> str:
    return " ".join(markdown.split())


def test_pr09_active_agent_layout_recheck_is_evidence_gated_skip():
    pr_list = Path("docs/harness/ACCELERATION_PR_LIST.md").read_text()
    pr09 = _section(pr_list, "PR09 — Active-Agent State Layout Recheck")
    normalized = _normalized(pr09)

    assert "Status: deferred by evidence." in pr09
    assert "No active-agent state layout implementation is authorized" in normalized
    assert "active_agent_pool_array_write" in pr09
    assert "below the review gate" in pr09
    assert "Commit: `docs(harness): defer active agent layout recheck`" in pr09


def test_pr09_deprecation_records_reopen_gate():
    deprecated = Path("docs/harness/DEPRECATED_IDEAS.md").read_text()
    rust_pool = _section(deprecated, "Immediate Rust Pool-Array Write Backend")

    assert "Status: deferred" in rust_pool
    assert "PR09 rechecked this decision" in rust_pool
    assert "Typed-array pool replacement becomes review-ready" in rust_pool
    assert "route potential work is completed" in rust_pool


def test_project_state_advances_to_zero_copy_rayon_rfc_after_pr09():
    project_state = Path("docs/harness/PROJECT_STATE.md").read_text()
    next_prompt = Path("docs/harness/NEXT_SESSION_PROMPT.md").read_text()
    normalized = _normalized(project_state)
    prompt_normalized = _normalized(next_prompt)

    assert "PR08 (`29daebe`) is complete" in normalized
    assert "PR09 active-agent state layout recheck is deferred by evidence" in normalized
    assert "Open PR10 as the Zero-Copy/Rayon Feasibility RFC" in normalized
    assert "Open PR10 as the Zero-Copy/Rayon Feasibility RFC" in prompt_normalized
    assert "Open a narrow dynamic-potential recompute/cache-amortization slice" not in next_prompt
