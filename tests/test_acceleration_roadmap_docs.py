from __future__ import annotations

from pathlib import Path


DOC_FUTURE_NAME_ALLOWLIST = {
    Path("docs/cuda/CPP_CUDA_ADMISSION.md"),
    Path("docs/CODING_STANDARDS.md"),
    Path("docs/VALIDATION_BENCHMARK_PLAN.md"),
    Path("docs/harness/DECISION_LOG.md"),
    Path("docs/harness/ACCELERATION_PR_LIST.md"),
    Path("docs/harness/NEXT_SESSION_PROMPT.md"),
}
REPO_SCAN_EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "target",
    "build",
    "dist",
}


def _section(markdown: str, heading: str) -> str:
    marker = f"## {heading}"
    start = markdown.index(marker)
    next_start = markdown.find("\n## ", start + len(marker))
    if next_start == -1:
        return markdown[start:]
    return markdown[start:next_start]


def _normalized(markdown: str) -> str:
    return " ".join(markdown.split())


def _repo_files(pattern: str) -> set[Path]:
    return {
        path
        for path in Path(".").glob(pattern)
        if not (set(path.parts) & REPO_SCAN_EXCLUDED_PARTS)
    }


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


def test_project_state_advances_to_prd_state_closure_after_pr11():
    project_state = Path("docs/harness/PROJECT_STATE.md").read_text()
    next_prompt = Path("docs/harness/NEXT_SESSION_PROMPT.md").read_text()
    normalized = _normalized(project_state)
    prompt_normalized = _normalized(next_prompt)

    assert "PR08 (`29daebe`) is complete" in normalized
    assert "PR09 (`52e7aec`) and PR10 (`04554ca`) are complete" in normalized
    assert "PR11 (`55af343`) and PR12 are complete" in normalized
    assert "Open a new spec only after refreshing" in normalized
    assert "Open a new spec only after refreshing" in prompt_normalized
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
    assert "Status: complete in `04554ca`." in pr10
    assert "No zero-copy NumPy FFI, Rayon, or new Rust build surface" in pr10
    assert "docs/rust/ZERO_COPY_RAYON_ADMISSION.md" in pr10
    assert "Open a new spec only after refreshing" in normalized_state
    assert "Status: RFC only" in admission
    assert "No implementation is authorized by this document" in normalized_admission
    assert "PyReadonlyArray" in admission
    assert "rayon" not in cargo.lower()
    assert "numpy" not in cargo.lower()


def test_pr11_cpp_cuda_admission_rfc_is_docs_only():
    pr_list = Path("docs/harness/ACCELERATION_PR_LIST.md").read_text()
    project_state = Path("docs/harness/PROJECT_STATE.md").read_text()
    next_prompt = Path("docs/harness/NEXT_SESSION_PROMPT.md").read_text()
    admission = Path("docs/cuda/CPP_CUDA_ADMISSION.md").read_text()
    pr11 = _section(pr_list, "PR11 — C++/CUDA Admission RFC")
    normalized_admission = _normalized(admission)
    normalized_state = _normalized(project_state)
    prompt_normalized = _normalized(next_prompt)
    forbidden_source_files = (
        _repo_files("**/CMakeLists.txt")
        | _repo_files("**/*.cu")
        | _repo_files("**/*.cuh")
        | _repo_files("**/*.cpp")
        | _repo_files("**/*.cc")
        | _repo_files("**/*.cxx")
        | _repo_files("**/*.hpp")
    )

    assert "Status: complete in `04554ca`" in _section(
        pr_list,
        "PR10 — Zero-Copy/Rayon Feasibility RFC",
    )
    assert "Status: complete in `55af343`." in pr11
    assert "No C++/CUDA, libtorch, CMake, or new runtime backend values" in pr11
    assert "docs/cuda/CPP_CUDA_ADMISSION.md" in pr11
    assert "Open a new spec only after refreshing" in normalized_state
    assert "Open a new spec only after refreshing" in prompt_normalized
    assert "Status: RFC only" in admission
    assert "No implementation is authorized by this document" in normalized_admission
    assert "dense flow" in admission
    assert "route-score batch" in admission
    assert "OD/policy batch" in admission
    assert forbidden_source_files == set()

    build_manifest_text = "\n".join(
        path.read_text()
        for pattern in ("**/pyproject.toml", "**/Cargo.toml")
        for path in _repo_files(pattern)
    ).lower()
    assert "torch_cuda" not in build_manifest_text
    assert "custom_cuda" not in build_manifest_text
    assert "libtorch" not in build_manifest_text
    assert "cudart" not in build_manifest_text
    assert "torch.utils.cpp_extension" not in build_manifest_text

    runtime_text = "\n".join(path.read_text() for path in Path("src").glob("**/*.py"))
    assert '"torch_cuda"' not in runtime_text
    assert '"custom_cuda"' not in runtime_text
    assert "'torch_cuda'" not in runtime_text
    assert "'custom_cuda'" not in runtime_text
    assert "torch.utils.cpp_extension" not in runtime_text

    allowed_doc_mentions = set()
    for path in Path("docs").glob("**/*.md"):
        text = path.read_text()
        if "torch_cuda" in text or "custom_cuda" in text:
            allowed_doc_mentions.add(path)
    assert allowed_doc_mentions <= DOC_FUTURE_NAME_ALLOWLIST


def test_pr12_closure_records_current_roadmap_state_and_next_handoff():
    pr_list = Path("docs/harness/ACCELERATION_PR_LIST.md").read_text()
    project_state = Path("docs/harness/PROJECT_STATE.md").read_text()
    next_prompt = Path("docs/harness/NEXT_SESSION_PROMPT.md").read_text()
    decision_log = Path("docs/harness/DECISION_LOG.md").read_text()
    deprecated = Path("docs/harness/DEPRECATED_IDEAS.md").read_text()
    validation = Path("docs/VALIDATION_BENCHMARK_PLAN.md").read_text()
    pr12 = _section(pr_list, "PR12 — PRD/State Closure")
    normalized_state = _normalized(project_state)
    normalized_prompt = _normalized(next_prompt)

    assert "Status: complete; roadmap state consolidated." in pr12
    assert "PR11 (`55af343`) and PR12" in normalized_state
    assert "Next Implementation Decision" in project_state
    assert "Open a new spec only after refreshing" in normalized_prompt
    assert "C++/CUDA Requires One Narrow Evidence-Gated Kernel" in decision_log
    assert "Immediate Rust Pool-Array Write Backend" in deprecated
    assert "CPP_CUDA_ADMISSION.md" in validation
    assert "ZERO_COPY_RAYON_ADMISSION.md" in validation
