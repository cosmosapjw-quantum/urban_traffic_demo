"""The suite must not touch the GPU unless a test explicitly asks for it.

Nothing here needs a device. The only test that reads `jax.devices()` passes
`require_gpu=False`, and `torch_cuda` appears solely as a backend name that
`SimulationConfig` is asserted to reject. Yet a plain `pytest` run used to
reserve 9,194 MiB of a 12,288 MiB card, because JAX preallocates 75% of VRAM the
first time a device initializes and a handful of tests exercise the optional JAX
flow backend.

So the default is CPU, and GPU is opt-in. A machine whose GPU also drives the
display should be able to run the tests without losing it, and CI on a GPU-less
runner should exercise the same code path everyone else does.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest


@pytest.fixture(autouse=True)
def _default_mode_only(request: pytest.FixtureRequest) -> None:
    """These assertions describe the DEFAULT run, so skip them under --run-gpu.

    Without this the opt-in flag makes the very tests that guard the CPU pin
    fail, which would train the reader to ignore them.
    """

    if request.config.getoption("--run-gpu") and "gpu" not in request.keywords:
        pytest.skip("--run-gpu deliberately lifts the CPU pin these tests assert")


def test_jax_is_pinned_to_cpu_for_the_test_session() -> None:
    """Set in conftest before any JAX import, which is the only time it works."""

    assert os.environ.get("JAX_PLATFORMS") == "cpu"


def test_preallocation_is_disabled_as_a_second_line_of_defence() -> None:
    """Belt and braces: if something forces a GPU platform, it still must not
    seize three quarters of the card."""

    assert os.environ.get("XLA_PYTHON_CLIENT_PREALLOCATE") == "false"


def test_jax_actually_runs_on_cpu_here() -> None:
    """Assert the effect, not just the environment variable."""

    jax = pytest.importorskip("jax")

    assert jax.default_backend() == "cpu"
    assert all(device.platform == "cpu" for device in jax.devices())


def test_a_jax_touching_run_holds_no_vram() -> None:
    """Runs the JAX files in a SUBPROCESS and measures it, not ourselves.

    Asserting on this process was close to worthless: it collects at position
    304 while the first JAX-touching file starts at 356, so it ran before
    anything could have allocated. The measurement has to bracket the code that
    would do the allocating.
    """

    # Two distinct absences, and reading the returncode only covers one of them:
    # with no NVIDIA driver installed there is no `nvidia-smi` to run, and
    # `subprocess.run` raises before producing a returncode to check. That is
    # every GitHub runner, which is precisely where this module claims to work.
    try:
        probe = subprocess.run(["nvidia-smi", "-L"], capture_output=True)
    except OSError:
        pytest.skip("nvidia-smi is not installed; VRAM cannot be measured here")
    if probe.returncode != 0:
        pytest.skip("no NVIDIA GPU on this machine")

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # DEVNULL, not PIPE: nothing reads the pipe until wait(), so a child that
    # produces more than the buffer holds blocks forever -- which is exactly what
    # happens when the bracketed tests fail and print tracebacks.
    run = subprocess.Popen(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_meso_core.py", "tests/test_jax_dense_flow_bakeoff.py"],
        cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    peak = 0
    while run.poll() is None:
        probe = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,used_gpu_memory",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True,
        )
        for line in probe.stdout.splitlines():
            pid, _, used = line.partition(",")
            if pid.strip() == str(run.pid):
                peak = max(peak, int(used.strip() or 0))
    # Without this the assertion passes when the child never ran at all -- a
    # missing file or an import error gives peak == 0 just as convincingly as a
    # clean run does.
    assert run.wait() == 0, "the bracketed JAX test files did not pass"

    assert peak == 0, f"the JAX test files reserved {peak} MiB of VRAM"


def test_the_vram_probe_skips_where_nvidia_smi_is_absent(tmp_path) -> None:
    """A host without the tool cannot measure VRAM, and must say so.

    This module's own docstring promises that "CI on a GPU-less runner should
    exercise the same code path everyone else does". It did not: the guard above
    reads `nvidia-smi`'s returncode, and when the binary is absent entirely
    `subprocess.run` raises `FileNotFoundError` before there is a returncode to
    read. GitHub's runners have no NVIDIA driver, so the guard against a missing
    GPU was itself the thing that failed there.

    Skip, not pass. There is no VRAM to hold on such a host, so the assertion
    would be vacuously true -- a green that measured nothing, which is the same
    defect the oracle check was just repaired for.

    Driven as a real subprocess with an empty PATH, because asserting on a
    mocked `subprocess.run` would test the mock.
    """

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_gpu_is_not_used_by_default.py::test_a_jax_touching_run_holds_no_vram"],
        cwd=root,
        env={**os.environ, "PATH": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    combined = result.stdout + result.stderr

    assert "FileNotFoundError" not in combined, (
        "the missing-GPU guard raises instead of skipping when nvidia-smi is absent"
    )
    assert result.returncode == 0, combined[-2000:]
    assert "1 skipped" in result.stdout, combined[-2000:]


def test_a_gpu_opt_in_exists_and_is_off_by_default() -> None:
    """Otherwise "default to CPU" would mean "GPU is untestable"."""

    config = subprocess.run(
        [sys.executable, "-m", "pytest", "--help"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )

    assert "--run-gpu" in config.stdout


@pytest.mark.gpu
def test_the_opt_in_lifts_the_pin_without_handing_back_the_whole_card(
    request: pytest.FixtureRequest,
) -> None:
    """--run-gpu means "reach the device", not "take three quarters of it".

    An earlier version of the hook deleted both variables, so opting into a
    single GPU test restored the 9,194 MiB preallocation the file exists to
    prevent.
    """

    assert request.config.getoption("--run-gpu")
    assert "JAX_PLATFORMS" not in os.environ, "the platform pin must be lifted"
    assert os.environ.get("XLA_PYTHON_CLIENT_PREALLOCATE") == "false", (
        "the preallocation guard must survive --run-gpu"
    )


@pytest.mark.gpu
def test_a_real_device_is_reachable_under_the_opt_in(request: pytest.FixtureRequest) -> None:
    """Runs only with --run-gpu, which is the point.

    In a default run this body must never execute; if the deselection hook broke,
    this test would appear in the report as a pass rather than a skip, and the
    CPU pin would be the only thing between the suite and the display GPU.
    """

    assert request.config.getoption("--run-gpu"), "a gpu-marked test ran without --run-gpu"

    jax = pytest.importorskip("jax")
    assert jax.default_backend() == "gpu"


def test_torch_also_cannot_reach_the_gpu_by_default() -> None:
    """JAX_PLATFORMS pins JAX only; torch reads none of it.

    Torch does not preallocate the way JAX does, so it is a smaller hazard, but
    "the suite must not use the GPU unless a test asks" is not satisfied by
    covering one framework. Hiding the device covers every consumer, including
    ones added later that nobody remembers to pin.
    """

    assert os.environ.get("CUDA_VISIBLE_DEVICES") == ""

    torch = pytest.importorskip("torch", reason="torch not installed")
    assert not torch.cuda.is_available(), "torch can still reach the device"


@pytest.mark.gpu
def test_a_caller_exported_device_mask_survives_the_opt_in() -> None:
    """The lift must remove only what conftest itself set.

    Runs under --run-gpu, which is the only mode in which the code under test
    executes. The previous version of this test never passed the flag, imported a
    SECOND copy of conftest (tests/ has no __init__.py, so `from tests import
    conftest` is not the module pytest loaded), and was skipped by this file's own
    autouse fixture anyway. Restoring the original bug verbatim left it green --
    verified by mutation -- so it locked nothing.

    Driven by `_run_pytest_with_run_gpu` below, which exports the mask and checks
    this assertion actually ran.
    """

    expected = os.environ.get("METROFLOW_EXPECT_MASK")
    if expected is None:
        pytest.skip("driven by test_the_opt_in_does_not_delete_a_caller_export")
    assert os.environ.get("CUDA_VISIBLE_DEVICES") == expected, (
        "--run-gpu removed a mask the caller exported explicitly"
    )


def test_the_opt_in_does_not_delete_a_caller_export() -> None:
    """Drive the gpu-marked probe above in a real --run-gpu session."""

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="", METROFLOW_EXPECT_MASK="")
    probe = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--run-gpu",
         "tests/test_gpu_is_not_used_by_default.py::"
         "test_a_caller_exported_device_mask_survives_the_opt_in"],
        cwd=root, env=env, capture_output=True, text=True,
    )

    assert probe.returncode == 0, (
        f"the probe did not pass under --run-gpu:\n{probe.stdout}\n{probe.stderr}"
    )
    assert "1 passed" in probe.stdout, (
        f"the probe did not actually run; it must not be skipped:\n{probe.stdout}"
    )


def test_conftest_only_claims_variables_it_actually_set() -> None:
    """`_APPLIED_BY_US` must reflect reality, in the module pytest loaded.

    Asserted against the LIVE conftest module, not a re-import: with no
    __init__.py in tests/, `from tests import conftest` mints a second module
    whose _apply_defaults sees everything already set and records nothing, so the
    old assertion was `set() <= {...}` and could not fail.
    """

    import conftest  # the module pytest itself loaded

    for name in conftest._APPLIED_BY_US:
        assert name in conftest._DEFAULTS
        assert os.environ.get(name) == conftest._DEFAULTS[name]
