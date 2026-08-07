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


def test_the_suite_leaves_the_gpu_alone() -> None:
    """Measured, because this is the property the user actually cares about."""

    probe = subprocess.run(
        ["nvidia-smi", "--query-compute-apps=pid,used_gpu_memory", "--format=csv,noheader"],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        pytest.skip("no NVIDIA GPU on this machine")

    ours = [
        line for line in probe.stdout.splitlines() if line.startswith(f"{os.getpid()},")
    ]
    assert not ours, f"this pytest process is holding VRAM: {ours}"


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
