"""Keep the test suite off the GPU unless a test explicitly asks for one.

Nothing in this suite needs a device. The only test that reads `jax.devices()`
passes `require_gpu=False`, and `torch_cuda` appears solely as a backend name
`SimulationConfig` is asserted to reject. Despite that, a plain `pytest` run
reserved 9,194 MiB of a 12,288 MiB card for its whole duration: JAX preallocates
`XLA_PYTHON_CLIENT_MEM_FRACTION` (default 0.75) of VRAM the first time a device
initializes, and a few tests exercise the optional JAX flow backend. Measured on
an RTX 3080 Ti; 12288 * 0.75 = 9216 against 9194 observed.

Three defaults, each covering a gap the others leave:

- `JAX_PLATFORMS=cpu` stops a JAX device being created at all. Only works if set
  before JAX is imported, hence a module-level assignment rather than a fixture.
- `XLA_PYTHON_CLIENT_PREALLOCATE=false` bounds the damage if something forces a
  GPU platform anyway.
- `CUDA_VISIBLE_DEVICES=""` hides the device from every consumer, not just JAX.
  torch reads none of JAX's variables and will not be the last accelerator
  library added here; pinning frameworks one at a time works until someone
  forgets.

None of them changes dtypes, execution order or results, so backend-parity and
drift assertions still mean what they meant.

Only values this file actually set are ever removed, and only under `--run-gpu`.
An earlier version compared against the default value instead, so a caller who
exported `CUDA_VISIBLE_DEVICES=""` deliberately had it deleted out from under
them -- "an explicit setting always wins" was written in this docstring while the
code did the opposite.

`CUDA_VISIBLE_DEVICES=""` is also skipped entirely when the caller has pinned
`JAX_PLATFORMS` to something other than cpu, because hiding every device from a
JAX explicitly told to use CUDA produces `CUDA_ERROR_NO_DEVICE` rather than the
fail-closed backend error the claim ledger requires.

GPU work is opt-in via `--run-gpu`, which lifts the platform pin and the device
mask (keeping the preallocation guard) and runs tests marked `@pytest.mark.gpu`.
Without it those tests are SKIPPED -- they appear in the report as skips, not as
pytest "deselected" items, which is a different mechanism.
"""

from __future__ import annotations

import os

import pytest

_DEFAULTS = {
    "JAX_PLATFORMS": "cpu",
    "XLA_PYTHON_CLIENT_PREALLOCATE": "false",
    "CUDA_VISIBLE_DEVICES": "",
}

# Lifted by --run-gpu. The preallocation guard is deliberately absent: the flag
# means "let a test reach the device", not "let JAX take three quarters of it".
_LIFTED_BY_RUN_GPU = ("JAX_PLATFORMS", "CUDA_VISIBLE_DEVICES")

# Populated below with exactly the names this file set, so nothing the caller
# configured is ever removed.
_APPLIED_BY_US: set[str] = set()


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-gpu",
        action="store_true",
        default=False,
        help="run tests marked @pytest.mark.gpu on a real device (off by default)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "gpu: needs a real GPU device; requires --run-gpu")
    if not config.getoption("--run-gpu"):
        return
    for name in _LIFTED_BY_RUN_GPU:
        if name in _APPLIED_BY_US:
            del os.environ[name]
            _APPLIED_BY_US.discard(name)


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--run-gpu"):
        return
    skip = pytest.mark.skip(reason="needs a real GPU; pass --run-gpu to run it")
    for item in items:
        if "gpu" in item.keywords:
            item.add_marker(skip)


def _apply_defaults() -> None:
    caller_pinned_jax = os.environ.get("JAX_PLATFORMS", "cpu") != "cpu"
    for name, value in _DEFAULTS.items():
        if name in os.environ:
            continue  # the caller's configuration wins, always
        if name == "CUDA_VISIBLE_DEVICES" and caller_pinned_jax:
            # Masking every device while JAX is explicitly pointed at CUDA gives
            # CUDA_ERROR_NO_DEVICE, not a clean backend failure.
            continue
        os.environ[name] = value
        _APPLIED_BY_US.add(name)


_apply_defaults()
