from pathlib import Path
import tomllib


def test_project_targets_ubuntu_2404_python312_with_numpy_baseline():
    project = tomllib.loads(Path("pyproject.toml").read_text())

    assert project["project"]["requires-python"] == ">=3.12"
    assert project["project"]["dependencies"] == ["numpy"]


def test_jax_cuda13_is_optional_extra_not_baseline_dependency():
    project = tomllib.loads(Path("pyproject.toml").read_text())

    optional_deps = project["project"]["optional-dependencies"]
    assert optional_deps["jax"] == ["jax[cuda13]"]
    assert "jax[cuda13]" not in project["project"]["dependencies"]
    assert "jaxlib" not in project["project"]["dependencies"]


def test_maturin_is_dev_only_for_rust_extension_builds():
    project = tomllib.loads(Path("pyproject.toml").read_text())

    optional_deps = project["project"]["optional-dependencies"]
    assert "maturin" in optional_deps["dev"]
    assert "maturin" not in project["project"]["dependencies"]
