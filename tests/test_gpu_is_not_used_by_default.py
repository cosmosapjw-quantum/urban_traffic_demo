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

    if subprocess.run(["nvidia-smi", "-L"], capture_output=True).returncode != 0:
        pytest.skip("no NVIDIA GPU on this machine")

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    run = subprocess.Popen(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
         "tests/test_meso_core.py", "tests/test_jax_dense_flow_bakeoff.py"],
        cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
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
    run.wait()

    assert peak == 0, f"the JAX test files reserved {peak} MiB of VRAM"


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


def test_an_explicitly_exported_setting_is_never_removed() -> None:
    """The docstring promised this while the code did the opposite.

    --run-gpu compared against the DEFAULT value rather than tracking what it had
    set, so a caller who deliberately exported CUDA_VISIBLE_DEVICES="" had it
    deleted.
    """

    from tests import conftest  # type: ignore[import-not-found]

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="")
    probe = subprocess.run(
        [sys.executable, "-c",
         "import os,sys;sys.path.insert(0,'tests');import conftest;"
         "print('applied', sorted(conftest._APPLIED_BY_US))"],
        cwd=root, env=env, capture_output=True, text=True,
    )

    assert "CUDA_VISIBLE_DEVICES" not in probe.stdout, (
        "conftest claimed a variable it did not set: " + probe.stdout
    )
    assert conftest._APPLIED_BY_US <= set(conftest._DEFAULTS)


def test_pinning_jax_to_cuda_is_not_sabotaged_by_the_device_mask() -> None:
    """Masking every device while JAX is told to use CUDA gives NO_DEVICE.

    That is not the fail-closed backend error the claim ledger requires; it is a
    driver error from a configuration this file created.
    """

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, JAX_PLATFORMS="cuda")
    env.pop("CUDA_VISIBLE_DEVICES", None)
    probe = subprocess.run(
        [sys.executable, "-c",
         "import os,sys;sys.path.insert(0,'tests');import conftest;"
         "print('mask=' + repr(os.environ.get('CUDA_VISIBLE_DEVICES')))"],
        cwd=root, env=env, capture_output=True, text=True,
    )

    assert "mask=None" in probe.stdout, probe.stdout
