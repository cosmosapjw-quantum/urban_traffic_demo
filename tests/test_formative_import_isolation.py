"""Integration regression: the pure map lane must not eagerly load legacy GIS."""
from pathlib import Path
import os
import subprocess
import sys


def test_formative_lane_import_and_run_without_optional_city_modules():
    root = Path(__file__).resolve().parents[1]
    code = '''
import importlib.abc, sys
class ForbidOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'numpy','jax','cupy','torch'} or (
            fullname.startswith('metroflow.city.') and not
            fullname.split('.')[-1].startswith('formative_growth')
        ):
            raise ImportError('eager optional dependency: ' + fullname)
sys.meta_path.insert(0, ForbidOptional())
from metroflow.city.formative_growth import FormationConfig, generate_formative_city
city = generate_formative_city(FormationConfig(seed=3,node_count=24,epochs=3,urbanized_area_km2=12.))
assert len(city.nodes) == 24
assert city.metrics['connected_components'] == 1
print('PURE_IMPORT_AND_EXECUTION_OK')
'''
    result = subprocess.run([sys.executable,'-c',code],cwd=root,
                            env=dict(os.environ,PYTHONPATH=str(root/'src')),
                            text=True,capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PURE_IMPORT_AND_EXECUTION_OK' in result.stdout
