"""Keep the test suite off the GPU unless a test explicitly asks for one.

Nothing in this suite needs a device. The only test that reads `jax.devices()`
passes `require_gpu=False`, and `torch_cuda` appears solely as a backend name
`SimulationConfig` is asserted to reject. Despite that, a plain `pytest` run
reserved 9,194 MiB of a 12,288 MiB card for its whole duration: JAX preallocates
`XLA_PYTHON_CLIENT_MEM_FRACTION` (default 0.75) of VRAM the first time a device
initializes, and a few tests exercise the optional JAX flow backend. Measured on
an RTX 3080 Ti; 12288 * 0.75 = 9216 against 9194 observed.

Two independent defences, because either alone leaves a gap:

- `JAX_PLATFORMS=cpu` stops a device from being created at all. This is the one
  that matters, and it only works if set before JAX is imported -- hence a
  module-level assignment in conftest rather than a fixture.
- `XLA_PYTHON_CLIENT_PREALLOCATE=false` bounds the damage if something forces a
  GPU platform anyway.

Neither changes dtypes, execution order or results, so backend-parity and drift
assertions still mean what they meant. An explicit setting in the environment
always wins, so a deliberate benchmark configuration is never overridden.

GPU work is opt-in via `--run-gpu`, which clears the CPU pin and selects tests
marked `@pytest.mark.gpu`. Without it those tests are deselected, so "default to
CPU" does not quietly mean "GPU is untestable".
"""

from __future__ import annotations

import os

import pytest

def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-gpu",
        action="store_true",
        default=False,
        help="run tests marked @pytest.mark.gpu on a real device (off by default)",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "gpu: needs a real GPU device; requires --run-gpu")
    if config.getoption("--run-gpu"):
        # Lift ONLY the platform pin. Deleting the preallocation guard as well
        # would hand back the 9,194 MiB grab this file exists to prevent -- the
        # flag means "let a test reach the device", not "let JAX take three
        # quarters of the card". And delete it only if it still holds the value
        # we set, so an explicit export by the caller survives.
        if os.environ.get("JAX_PLATFORMS") == _DEFAULTS["JAX_PLATFORMS"]:
            del os.environ["JAX_PLATFORMS"]


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--run-gpu"):
        return
    skip = pytest.mark.skip(reason="needs a real GPU; pass --run-gpu to run it")
    for item in items:
        if "gpu" in item.keywords:
            item.add_marker(skip)


_DEFAULTS = {"JAX_PLATFORMS": "cpu", "XLA_PYTHON_CLIENT_PREALLOCATE": "false"}

for _name, _value in _DEFAULTS.items():
    os.environ.setdefault(_name, _value)
