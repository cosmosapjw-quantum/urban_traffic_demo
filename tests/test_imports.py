import os
import subprocess
import sys


def test_import_metroflow():
    import metroflow  # noqa: F401


def test_core_runtime_imports_do_not_load_jax():
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    script = (
        "import sys\n"
        "import metroflow\n"
        "import metroflow.city\n"
        "import metroflow.flow\n"
        "import metroflow.learning\n"
        "import metroflow.routing\n"
        "import metroflow.sim\n"
        "import metroflow.sim.init\n"
        "print('jax' in sys.modules)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        cwd=".",
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.stdout.strip() == "False"


def test_city_zones_imports_without_sim_runtime_cycle():
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    script = "from metroflow.city.zones import POI, POIType\nprint(POIType.HOME.value)\n"
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        cwd=".",
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.stdout.strip() == "home"
