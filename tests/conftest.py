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

_GPU_ENV = ("JAX_PLATFORMS", "XLA_PYTHON_CLIENT_PREALLOCATE")


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
        # Undo the pin so the device is reachable, but only the pin: anything the
        # caller set explicitly is left alone.
        for name in _GPU_ENV:
            if os.environ.get(name) == _DEFAULTS[name]:
                del os.environ[name]


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
