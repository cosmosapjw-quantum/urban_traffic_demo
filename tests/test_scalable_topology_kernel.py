import subprocess
import sys

from metroflow.city.scale import CityScaleSpec


def test_scalable_topology_import_isolated() -> None:
    """Importing the S2 kernel must not admit downstream or simulator modules."""
    import metroflow.city.scalable_topology as topology

    assert CityScaleSpec(100_000, 40.0).target_population == 100_000
    assert topology.__doc__

    code = """
import sys
import metroflow.city.scalable_topology
for name in (
    "metroflow.sim.config",
    "metroflow.city.growth_fabric",
    "metroflow.city.growth_topology",
    "metroflow.city.scalable_blocks",
    "metroflow.city.scalable_topology_adapter",
    "metroflow.city.scalable_authority",
):
    assert name not in sys.modules, name
"""
    subprocess.run([sys.executable, "-c", code], check=True)
