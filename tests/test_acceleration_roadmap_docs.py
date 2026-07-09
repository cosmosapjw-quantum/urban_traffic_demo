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

    assert "Status: complete in `52e7aec`." in pr09
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
    assert "PR09 (`52e7aec`) is complete" in normalized
    assert "PR10 Zero-Copy/Rayon RFC is accepted" in normalized
    assert "Open PR11 as the C++/CUDA Admission RFC" in normalized
    assert "Open PR11 as the C++/CUDA Admission RFC" in prompt_normalized
    assert "PR09 is complete" in prompt_normalized
    assert "state layout implementation remains deferred" in prompt_normalized
    assert "Open a narrow dynamic-potential recompute/cache-amortization slice" not in next_prompt


def test_pr10_zero_copy_rayon_rfc_is_admission_only():
    pr_list = Path("docs/harness/ACCELERATION_PR_LIST.md").read_text()
    project_state = Path("docs/harness/PROJECT_STATE.md").read_text()
    admission = Path("docs/rust/ZERO_COPY_RAYON_ADMISSION.md").read_text()
    cargo = Path("crates/metroflow-rust/Cargo.toml").read_text()
    pr10 = _section(pr_list, "PR10 — Zero-Copy/Rayon Feasibility RFC")
    normalized_admission = _normalized(admission)
    normalized_state = _normalized(project_state)

    assert "Status: complete in `52e7aec`" in _section(
        pr_list,
        "PR09 — Active-Agent State Layout Recheck",
    )
    assert "Status: RFC accepted; implementation not authorized." in pr10
    assert "No zero-copy NumPy FFI, Rayon, or new Rust build surface" in pr10
    assert "docs/rust/ZERO_COPY_RAYON_ADMISSION.md" in pr10
    assert "Open PR11 as the C++/CUDA Admission RFC" in normalized_state
    assert "Status: RFC only" in admission
    assert "No implementation is authorized by this document" in normalized_admission
    assert "PyReadonlyArray" in admission
    assert "rayon" not in cargo.lower()
    assert "numpy" not in cargo.lower()
