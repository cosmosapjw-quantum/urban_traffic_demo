"""Legacy scientific Python execution is an explicitly opted-in test oracle."""
import os


def require_python_oracle():
    if os.environ.get("METROFLOW_ENABLE_PYTHON_ORACLE") != "1":
        raise RuntimeError(
            "Historical Python scientific calculation is an opt-in test oracle only; "
            "use the Rust backend. Set METROFLOW_ENABLE_PYTHON_ORACLE=1 for comparison tests."
        )
