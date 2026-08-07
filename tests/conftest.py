"""Stop the test suite from reserving most of the GPU it does not use.

JAX preallocates `XLA_PYTHON_CLIENT_MEM_FRACTION` (default 0.75) of total VRAM
the first time a device initializes, whether or not it computes anything. A few
tests exercise the optional JAX flow backend, so running `pytest` on a machine
with a CUDA build of JAX takes ~9.2 GiB of a 12 GiB card hostage for the whole
run -- measured on an RTX 3080 Ti, 12288 MiB * 0.75 = 9216 MiB against 9194 MiB
observed. On a workstation whose GPU also drives the display, that is disruptive
and buys nothing: the authoritative path is NumPy, and city generation touches
no accelerator at all.

Disabling preallocation changes the allocation strategy only. It does not change
dtypes, execution order or results, so backend-parity and drift assertions are
unaffected.

An explicit setting in the environment always wins, so anyone benchmarking with
a deliberate memory configuration keeps it.
"""

from __future__ import annotations

import os

os.environ.setdefault("XLA_PYTHON_CLIENT_PREALLOCATE", "false")
