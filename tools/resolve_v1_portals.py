"""Checkpointed construction audit on immutable V02 map inputs."""
import argparse
from dataclasses import asdict
import hashlib
import json
import lzma
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT))
from metroflow.v1.city import load_city  # noqa: E402
from metroflow.v1.generated_entries import generate_entries  # noqa: E402


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(index, out):
    source_dir = ROOT / 'artifacts/v1/map_audit'
    original = json.loads((source_dir / 'MATRIX.json').read_text())['cases'][index]
    source = source_dir / original['source']
    assert sha(source) == original['source_sha256']
    start = time.monotonic()
    city = load_city(json.loads(lzma.decompress(source.read_bytes())))
    constructed, report = generate_entries(city)
    out.mkdir(parents=True, exist_ok=True)
    patch = out / f'{index:02d}.patch.json.xz'
    payload = dict(base_source=original['source'], base_sha256=sha(source),
                   parent_identity=city.identity, identity=constructed.identity,
                   portals=[asdict(p) for p in constructed.portals], construction=report)
    patch.write_bytes(lzma.compress(json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()))
    summary = {k: v for k, v in report.items() if k not in ('entries', 'candidate_failures')}
    summary.update(index=index, case=original['case'], seed=original['seed'],
                   family=original['family'], identity=constructed.identity,
                   parent_identity=city.identity, source=original['source'], source_sha256=sha(source),
                   patch=patch.name, patch_sha256=sha(patch), wall_s=time.monotonic()-start)
    (out / f'{index:02d}.audit.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    print(json.dumps(summary, allow_nan=False), flush=True)


def replay(index, out):
    row = json.loads((out / f'{index:02d}.audit.json').read_text())
    patch = out / row['patch']
    assert sha(patch) == row['patch_sha256']
    payload = json.loads(lzma.decompress(patch.read_bytes()))
    base = ROOT / 'artifacts/v1/map_audit' / payload['base_source']
    assert sha(base) == payload['base_sha256']
    data = json.loads(lzma.decompress(base.read_bytes()))
    assert data['identity'] == payload['parent_identity']
    data.update(portals=payload['portals'], identity=payload['identity'])
    city = load_city(data)
    from metroflow.v1.activity import compile_activity
    from metroflow.v1.development import compile_entry
    blocks = {b.id: b for b in city.face_graph.blocks}
    for entry in payload['construction']['entries']:
        b = blocks[entry['block_id']]
        m = compile_activity(city, b.id, 'residential' if b.residents else 'job')
        actual = compile_entry(city, m, entry['id'], capacity_veh_s=entry['capacity_veh_s'],
                               corridor=entry['corridor'], existing=False)
        assert json.loads(json.dumps(asdict(actual))) == {k: entry[k] for k in asdict(actual)}
    print(json.dumps(dict(status='REPLAY_PASS', index=index, identity=city.identity,
                          entries=len(city.portals))))


def aggregate(out):
    originals = json.loads((ROOT/'artifacts/v1/map_audit/MATRIX.json').read_text())['cases']
    rows = []
    for i, original in enumerate(originals):
        row = json.loads((out/f'{i:02d}.audit.json').read_text())
        assert row['source_sha256'] == original['source_sha256']
        assert row['parent_identity'] == original['identity']
        assert sha(out/row['patch']) == row['patch_sha256']
        rows.append(row)
    from tools.audit_v1_physics import unsupported_registered_access
    result = dict(status='PASS' if not any(map(unsupported_registered_access, rows)) else 'BLOCKED',
                  cases=rows, original_matrix_sha256=sha(ROOT/'artifacts/v1/map_audit/MATRIX.json'),
                  scope='synthetic new entries on original frozen roads and population; legal-turn connectivity and registered area access')
    (out/'MATRIX.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps(dict(status=result['status'], maps=len(rows),
                         unserved=sum(r['registered_unserved_residents'] for r in rows))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=int, choices=range(38))
    parser.add_argument('--replay', action='store_true')
    parser.add_argument('--aggregate', action='store_true')
    parser.add_argument('--out', type=Path, default=ROOT/'artifacts/v1_portal_resolution_20261027')
    args = parser.parse_args()
    if args.aggregate:
        aggregate(args.out)
    elif args.index is None:
        parser.error('--index is required unless --aggregate is selected')
    else:
        (replay if args.replay else run)(args.index, args.out)
