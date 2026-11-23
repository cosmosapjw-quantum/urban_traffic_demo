"""Preserve selected MetroFlow recovery data before authorized worktree cleanup.

This script only creates and verifies archives; it never removes worktrees.
Historical checkpoints retain their original binary/source bindings and are not
claimed compatible with the current native model.
"""
from __future__ import annotations

import collections
import datetime
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time

LATEST = Path('/home/cosmosapjw/urban_traffic_v03_bottleneck_theory_20261123')
PRIMARY = Path('/home/cosmosapjw/urban_traffic_v03_20261116')
OLD_CURRENT = Path('/home/cosmosapjw/urban_traffic_v03_causal_rank_20261123')
RUST = Path('/home/cosmosapjw/urban_traffic_rust_20261116')
META = LATEST / 'artifacts/cleanup_20261123'
OUT = LATEST / 'artifacts/retained_recovery_20261123'
CHUNK = 8 * 1024 * 1024
SKIP = {'.venv', 'venv', '__pycache__', '.pytest_cache', '.mypy_cache',
        '.ruff_cache', 'build', 'dist'}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(CHUNK), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def disk():
    s = os.statvfs(LATEST)
    return {'capacity': s.f_blocks*s.f_frsize,
            'used': (s.f_blocks-s.f_bfree)*s.f_frsize,
            'available': s.f_bavail*s.f_frsize}


def announce(message):
    print(now(), message, flush=True)


def validate_source(path):
    assert path.is_file() and not path.is_symlink(), str(path)
    assert path.resolve().is_relative_to(Path('/home/cosmosapjw'))


def checkpoint(source, name, expected_raw, expected_compressed=None):
    validate_source(source)
    target = OUT / name
    partial = target.with_name(target.name + '.partial')
    assert not target.exists() and not partial.exists(), str(target)
    before = source.stat()
    started = time.monotonic()
    h = hashlib.sha256()
    source_bytes = 0
    with source.open('rb') as inp, partial.open('xb') as out:
        if expected_compressed:
            for block in iter(lambda: inp.read(CHUNK), b''):
                h.update(block)
                source_bytes += len(block)
                out.write(block)
        else:
            with gzip.GzipFile(filename='', mode='wb', fileobj=out,
                               compresslevel=1, mtime=0) as zipped:
                for block in iter(lambda: inp.read(CHUNK), b''):
                    h.update(block)
                    source_bytes += len(block)
                    zipped.write(block)
        out.flush()
        os.fsync(out.fileno())
    assert h.hexdigest() == (expected_compressed or expected_raw), str(source)
    after = source.stat()
    assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    compressed_hash = digest(partial)
    if expected_compressed:
        assert compressed_hash == expected_compressed
    raw_hash = hashlib.sha256()
    raw_bytes = 0
    with gzip.open(partial, 'rb') as inp:
        for block in iter(lambda: inp.read(CHUNK), b''):
            raw_hash.update(block)
            raw_bytes += len(block)
    assert raw_hash.hexdigest() == expected_raw, str(partial)
    partial.rename(target)
    result = {'source': str(source), 'archive': str(target),
              'source_bytes': source_bytes, 'raw_bytes': raw_bytes,
              'raw_sha256': expected_raw, 'compressed_bytes': target.stat().st_size,
              'compressed_sha256': compressed_hash, 'gzip_full_decode_verified': True,
              'elapsed_seconds': time.monotonic()-started}
    announce('VERIFIED checkpoint ' + name + ' ' + str(target.stat().st_size) + ' bytes')
    return result


def main():
    inventory = json.loads((META / 'INVENTORY.json').read_text())
    OUT.mkdir(exist_ok=True)
    assert not (META / 'RECOVERY_VERIFIED.json').exists(), 'already completed'
    initial_disk = disk()
    refs = git(LATEST, 'for-each-ref', '--format=%(refname) %(objectname)').decode().splitlines()
    latest_head = git(LATEST, 'rev-parse', 'HEAD').decode().strip()
    source_roots = [Path(w['path']) for w in inventory['worktrees'] if Path(w['path']) != LATEST]
    assert len(source_roots) == 24 and PRIMARY in source_roots
    for w in inventory['worktrees']:
        root = Path(w['path'])
        if root == LATEST:
            continue
        assert git(root, 'rev-parse', 'HEAD').decode().strip() == w['head']
        changes = git(root, 'diff', '--name-only', 'HEAD').decode().splitlines()
        assert set(changes) == {f['path'] for f in w.get('changed_tracked', [])}, str(root)
        if root != PRIMARY:
            assert not changes

    plans = []
    selected = []
    for w in inventory['worktrees']:
        root = Path(w['path'])
        if root == LATEST:
            continue
        for record in w.get('untracked', []):
            rel = Path(record['path'])
            assert not rel.is_absolute() and '..' not in rel.parts
            source = root / rel
            assert source.exists() or source.is_symlink(), str(source)
            if any(t in SKIP or t.startswith('target') for t in rel.parts):
                disposition = 'discard_rebuildable_output'
            elif '.so' in rel.suffixes:
                disposition = 'discard_superseded_native_except_two_pinned_binaries'
            elif (rel.name.endswith('.bin') or rel.name.endswith('.bin.gz')) and record['bytes'] > 1048576:
                disposition = 'discard_superseded_checkpoint_except_three_selected_cases'
            elif rel.as_posix() == 'handoff_delivery/urban_traffic_projection.bundle.b64':
                disposition = 'discard_base64_duplicate_of_verified_preserved_handoff_bundle'
            else:
                disposition = 'preserve_unpublished_evidence_or_input'
                selected.append((source, root.name + '/' + rel.as_posix()))
            plans.append({'worktree': str(root), **record, 'disposition': disposition})
        for record in w.get('changed_tracked', []):
            selected.append((root / record['path'], root.name + '/' + record['path']))

    # Only non-cache ignored file under a removal candidate found by the bounded
    # inventory; the primary .remember directory remains in the kept primary.
    handoff = Path('/home/cosmosapjw/urban_traffic_projection_20261117/handoff_delivery/urban_traffic_projection.bundle')
    selected.append((handoff, 'urban_traffic_projection_20261117/handoff_delivery/urban_traffic_projection.bundle'))
    delivery = handoff.with_name('DELIVERY.json')
    if all(source != delivery for source, _ in selected):
        selected.append((delivery, 'urban_traffic_projection_20261117/handoff_delivery/DELIVERY.json'))

    pinned = [
        (OLD_CURRENT / 'native_binding/_metroflow_rust.so', 'native/current/_metroflow_rust.so',
         '22a7cebc751b575521a8360ab7e235aa7fa6fa9e4d54c8ac8904b35e708ae57a'),
        (RUST / 'artifacts/v1_rust_completion_20261116/budget_final_binary/_metroflow_rust.cpython-312-x86_64-linux-gnu.so',
         'native/historical_budget_final/_metroflow_rust.cpython-312-x86_64-linux-gnu.so',
         '3e06969385dffdb9834c56d2cf0831e67e07e618df4f1f2169cff974aa9a3972')]
    for source, arcname, expected in pinned:
        validate_source(source)
        assert digest(source) == expected, str(source)
        selected.append((source, arcname))

    selected_checkpoints = {
        str(OLD_CURRENT / 'artifacts/v03_causal_rank_20261123/S08_time_zero_prefix.final.bin.gz'),
        str(RUST / 'artifacts/v1_rust_completion_20261116/runtime_budget_campaign/coastal_weekend_s41.run1.last_valid.bin'),
        str(RUST / 'artifacts/v1_rust_completion_20261116/runtime_budget_campaign/river_weekday_s17.run1.last_valid.bin')}
    for row in plans:
        source = str(Path(row['worktree']) / row['path'])
        if source in selected_checkpoints:
            row['disposition'] = 'preserve_selected_checkpoint_compressed'
        elif source in {str(item[0]) for item in pinned}:
            row['disposition'] = 'preserve_pinned_native_binary_compressed'

    patches = {}
    for name, args in [('primary_HEAD_to_worktree.patch', ('diff', '--binary', 'HEAD')),
                       ('primary_index.patch', ('diff', '--cached', '--binary')),
                       ('primary_worktree.patch', ('diff', '--binary'))]:
        patches[name] = git(PRIMARY, *args)
    environment = []
    for root in source_roots:
        venv = root / '.venv'
        cfg = venv / 'pyvenv.cfg'
        if cfg.is_file():
            packages = []
            for metadata in sorted(venv.glob('lib/python*/site-packages/*.dist-info/METADATA')):
                name = version = None
                with metadata.open(errors='replace') as stream:
                    for line in stream:
                        if line.startswith('Name: '): name = line[6:].strip()
                        if line.startswith('Version: '): version = line[9:].strip()
                        if name and version: break
                packages.append({'name': name, 'version': version})
            environment.append({'worktree': str(root), 'pyvenv_cfg': cfg.read_text(), 'packages': packages})

    write_json(META / 'DISPOSITIONS.json', plans)
    write_json(META / 'ENVIRONMENTS.json', environment)
    write_json(META / 'REFS_BEFORE_REMOVAL.json', refs)
    dirty = []
    archive_entries = []
    seen = {}
    archive = OUT / 'unpublished_evidence_and_native.tar.gz'
    partial = archive.with_name(archive.name + '.partial')
    assert not archive.exists() and not partial.exists()
    with tarfile.open(partial, 'w:gz', compresslevel=1, dereference=False) as tar:
        for source, arcname in selected:
            assert source.is_file() or source.is_symlink(), str(source)
            stat = source.lstat()
            info = tar.gettarinfo(str(source), arcname=arcname)
            if source.is_symlink():
                hashvalue = hashlib.sha256(os.readlink(source).encode()).hexdigest()
                tar.addfile(info)
                entry = {'source': str(source), 'member': arcname, 'kind': 'symlink',
                         'target': os.readlink(source), 'sha256': hashvalue, 'bytes': stat.st_size}
            else:
                hashvalue = digest(source)
                key = (hashvalue, stat.st_size, info.mode)
                entry = {'source': str(source), 'member': arcname, 'kind': 'file',
                         'sha256': hashvalue, 'bytes': stat.st_size}
                if key in seen:
                    info.type = tarfile.LNKTYPE
                    info.linkname = seen[key]
                    info.size = 0
                    entry['hardlink_to'] = seen[key]
                    tar.addfile(info)
                else:
                    with source.open('rb') as stream:
                        tar.addfile(info, stream)
                    seen[key] = arcname
                after = source.stat()
                assert (stat.st_size, stat.st_mtime_ns) == (after.st_size, after.st_mtime_ns), str(source)
            archive_entries.append(entry)
            if source.is_relative_to(PRIMARY) and str(source.relative_to(PRIMARY)) in {
                f['path'] for f in inventory['worktrees'][0]['changed_tracked']}:
                dirty.append(entry)
        metadata_payloads = {**patches,
            'source_bindings.json': json.dumps({'latest_head': latest_head, 'primary_head':
                git(PRIMARY, 'rev-parse', 'HEAD').decode().strip(), 'refs': refs,
                'selected_files': archive_entries, 'environments': environment}, indent=2).encode()}
        for name, data in metadata_payloads.items():
            arcname = 'metadata/' + name
            info = tarfile.TarInfo(arcname)
            info.size = len(data)
            info.mode = 0o600
            tar.addfile(info, io.BytesIO(data))
            archive_entries.append({'member': arcname, 'kind': 'file', 'bytes': len(data),
                                    'sha256': hashlib.sha256(data).hexdigest()})
    expected = {entry['member']: entry for entry in archive_entries}
    verified = {}
    with tarfile.open(partial, 'r|gz') as tar:
        for member in tar:
            entry = expected[member.name]
            if member.islnk():
                assert member.linkname in verified
                result = verified[member.linkname]
            elif member.issym():
                assert member.linkname == entry['target']
                result = (hashlib.sha256(member.linkname.encode()).hexdigest(), entry['bytes'])
            else:
                h = hashlib.sha256()
                size = 0
                stream = tar.extractfile(member)
                for block in iter(lambda: stream.read(CHUNK), b''):
                    h.update(block)
                    size += len(block)
                result = (h.hexdigest(), size)
            assert result == (entry['sha256'], entry['bytes']), member.name
            verified[member.name] = result
    assert set(verified) == set(expected)
    partial.rename(archive)
    evidence = {'archive': str(archive), 'bytes': archive.stat().st_size,
                'sha256': digest(archive), 'members': archive_entries,
                'all_members_stream_verified': True, 'dirty_tracked_snapshots': dirty}
    write_json(META / 'EVIDENCE_ARCHIVE_MANIFEST.json', evidence)
    announce('VERIFIED evidence archive, members=' + str(len(archive_entries)))

    bundle = OUT / 'all_project_refs.bundle'
    partial_bundle = OUT / 'all_project_refs.bundle.partial'
    assert not bundle.exists() and not partial_bundle.exists()
    result = subprocess.run(['git', '-C', str(LATEST), 'bundle', 'create', str(partial_bundle), '--all'],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert result.returncode == 0, result.stdout.decode(errors='replace')
    checked = subprocess.run(['git', '-C', str(LATEST), 'bundle', 'verify', str(partial_bundle)],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (META / 'GIT_BUNDLE_VERIFY.txt').write_bytes(checked.stdout)
    assert checked.returncode == 0
    partial_bundle.rename(bundle)
    bundle_record = {'archive': str(bundle), 'bytes': bundle.stat().st_size,
                     'sha256': digest(bundle), 'git_bundle_verify_exit': checked.returncode,
                     'refs': refs}
    announce('VERIFIED all-refs Git bundle ' + str(bundle.stat().st_size) + ' bytes')

    checkpoints = []
    checkpoints.append(checkpoint(
        OLD_CURRENT / 'artifacts/v03_causal_rank_20261123/S08_time_zero_prefix.final.bin.gz',
        'valley_s7_t25700.current.bin.gz',
        'ac7a209c6adfd594c791d1ac4b5b33c6e013ae73b7b594e42121115c89bd8369',
        '191f64eb23b1cd68e95f09fc1c18c6888dfa21b77ec1a4f24d576a36272ae3f3'))
    checkpoints.append(checkpoint(
        RUST / 'artifacts/v1_rust_completion_20261116/runtime_budget_campaign/coastal_weekend_s41.run1.last_valid.bin',
        'coastal_s41_t32660.historical.bin.gz',
        'f92cc99f87e30fe6fafc37674eb58ad4855fe83a61e32f659596d9cfcaa1aa1e'))
    checkpoints.append(checkpoint(
        RUST / 'artifacts/v1_rust_completion_20261116/runtime_budget_campaign/river_weekday_s17.run1.last_valid.bin',
        'river_s17_t25350.historical.bin.gz',
        'e179f3b9b5b9081a8adb121e51761514654743a8e8bbe4166691dd04cc46425e'))
    record = {'schema': 'metroflow-recovery-preservation-v1', 'verified_at': now(),
              'latest_head_before_cleanup': latest_head, 'disk_before_preservation': initial_disk,
              'disk_after_preservation': disk(), 'kept_worktrees': [str(PRIMARY), str(LATEST)],
              'removal_candidates': [str(root) for root in source_roots if root != PRIMARY],
              'evidence_archive': evidence, 'git_bundle': bundle_record, 'checkpoints': checkpoints,
              'total_retained_bytes': evidence['bytes'] + bundle_record['bytes'] +
                  sum(x['compressed_bytes'] for x in checkpoints),
              'scope_note': 'Retain current Valley plus two explicitly historical other-city checkpoints; '
                  'not a claim of current-binary compatibility or a full-day run.'}
    write_json(META / 'RECOVERY_VERIFIED.json', record)
    write_json(OUT / 'RECOVERY_MANIFEST.json', record)
    announce('ALL SELECTED RECOVERY VERIFIED; total bytes=' + str(record['total_retained_bytes']))


if __name__ == '__main__':
    main()
