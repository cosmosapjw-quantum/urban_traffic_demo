"""Remove exactly the obsolete worktrees selected by the user's cleanup request.

Requires the actual verified recovery receipt. Keeps primary Git storage, dirty
primary work, all branch refs, and the latest theory checkout. No branch deletion,
history rewriting, Git garbage collection, or unrelated-directory cleanup.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/home/cosmosapjw/urban_traffic_v03_bottleneck_theory_20261123')
PRIMARY = Path('/home/cosmosapjw/urban_traffic_v03_20261116')
META = ROOT / 'artifacts/cleanup_20261123'
SKIP = {'.venv', 'venv', '__pycache__', '.pytest_cache', '.mypy_cache',
        '.ruff_cache', 'build', 'dist', 'htmlcov'}


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args])


def disk():
    s = os.statvfs(ROOT)
    return {'capacity': s.f_blocks*s.f_frsize, 'used': (s.f_blocks-s.f_bfree)*s.f_frsize,
            'available': s.f_bavail*s.f_frsize}


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def refs():
    return git(ROOT, 'for-each-ref', '--format=%(refname) %(objectname)').decode().splitlines()


def worktrees():
    return [line[9:] for line in git(ROOT, 'worktree', 'list', '--porcelain').decode().splitlines()
            if line.startswith('worktree ')]


def process_references(roots):
    observed, denied = [], []
    own = os.getpid()
    def under(value):
        return any(value == r or value.startswith(r + '/') for r in roots)
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == own:
            continue
        try:
            links = [proc/'cwd']
            try:
                links += list((proc/'fd').iterdir())
            except (FileNotFoundError, PermissionError):
                pass
            for entry in links:
                try:
                    value = os.readlink(entry)
                except (FileNotFoundError, PermissionError):
                    continue
                if under(value):
                    observed.append({'pid': int(proc.name), 'kind': entry.name, 'path': value})
            try:
                maps = (proc/'maps').read_text()
                for line in maps.splitlines():
                    if any(r + '/' in line for r in roots):
                        observed.append({'pid': int(proc.name), 'kind': 'mapped_file', 'record': line})
            except PermissionError:
                denied.append(int(proc.name))
        except (FileNotFoundError, ProcessLookupError):
            continue
    return observed, denied


def main():
    inventory = json.loads((META/'INVENTORY.json').read_text())
    verified = json.loads((META/'RECOVERY_VERIFIED.json').read_text())
    candidates = verified['removal_candidates']
    assert len(candidates) == 23 and len(set(candidates)) == 23
    assert str(ROOT) not in candidates and str(PRIMARY) not in candidates
    assert set(worktrees()) == set(candidates + [str(ROOT), str(PRIMARY)])
    assert git(ROOT, 'rev-parse', '--git-common-dir').decode().strip() == str(PRIMARY/'.git')
    assert refs() == verified['git_bundle']['refs'], 'refs changed since archive'
    archives = [verified['evidence_archive'], verified['git_bundle']]
    for archive in archives:
        assert Path(archive['archive']).stat().st_size == archive['bytes']
        assert digest(archive['archive']) == archive['sha256']
    for archive in verified['checkpoints']:
        assert archive['gzip_full_decode_verified']
        assert Path(archive['archive']).stat().st_size == archive['compressed_bytes']
        assert digest(archive['archive']) == archive['compressed_sha256']
    for entry in verified['evidence_archive']['dirty_tracked_snapshots']:
        assert digest(entry['source']) == entry['sha256'], 'primary dirty file changed'
    evidence_sources = {entry.get('source') for entry in verified['evidence_archive']['members']}
    state_by_root = {w['path']: w for w in inventory['worktrees']}
    for name in candidates:
        root = Path(name)
        assert root.parent == Path('/home/cosmosapjw') and root.name.startswith('urban_traffic_')
        assert root.is_dir() and not root.is_symlink()
        previous = state_by_root[name]
        assert git(root, 'rev-parse', 'HEAD').decode().strip() == previous['head']
        assert not git(root, 'diff', '--name-only', 'HEAD'), name
        untracked = set(filter(None, git(root, 'ls-files', '--others', '--exclude-standard', '-z').decode().split('\0')))
        assert untracked == {f['path'] for f in previous['untracked']}, 'untracked paths changed: '+name
        ignored = filter(None, git(root, 'ls-files', '--others', '--ignored', '--exclude-standard', '-z').decode().split('\0'))
        for relative in ignored:
            p = Path(relative)
            if any(t in SKIP or t.startswith('target') or t.endswith('.egg-info') for t in p.parts):
                continue
            if p.suffix in {'.pyc', '.pyo'}:
                continue
            assert str(root/p) in evidence_sources, 'unpreserved ignored file: '+str(root/p)
    active, denied = process_references(candidates)
    assert not active, json.dumps(active)
    before = disk()
    receipt = {'schema': 'metroflow-worktree-removal-v1', 'started_at': now(),
               'before': before, 'before_preservation': verified['disk_before_preservation'],
               'initial_inventory_filesystem': inventory.get('filesystem_before_inventory'),
               'kept_worktrees': [str(PRIMARY), str(ROOT)],
               'process_references': active, 'process_maps_unreadable_pids': denied,
               'outcomes': [], 'retained_archive_bytes': verified['total_retained_bytes']}
    for name in candidates:
        # The preceding complete preflight protects against newly created work or
        # open project files. Force is needed only for already classified local
        # checkpoints and build output, which Git correctly sees as untracked.
        started = time.monotonic()
        result = subprocess.run(['git', '-C', str(ROOT), 'worktree', 'remove', '--force', name],
                                capture_output=True, text=True)
        row = {'path': name, 'returncode': result.returncode, 'stdout': result.stdout,
               'stderr': result.stderr, 'exists_after': Path(name).exists(),
               'elapsed_seconds': time.monotonic()-started}
        receipt['outcomes'].append(row)
        (META/'REMOVAL_RECEIPT.json').write_text(json.dumps(receipt, indent=2)+'\n')
        print(now(), 'REMOVED' if result.returncode == 0 else 'FAILED', name, flush=True)
        assert result.returncode == 0 and not Path(name).exists(), row
    assert set(worktrees()) == {str(PRIMARY), str(ROOT)}
    assert refs() == verified['git_bundle']['refs'], 'branch/ref change detected'
    for entry in verified['evidence_archive']['dirty_tracked_snapshots']:
        assert digest(entry['source']) == entry['sha256']
    checked = subprocess.run(['git', '-C', str(ROOT), 'fsck', '--connectivity-only', '--no-dangling'],
                             capture_output=True, text=True)
    (META/'GIT_CONNECTIVITY_CHECK.txt').write_text(checked.stdout+checked.stderr)
    assert checked.returncode == 0, checked.stderr
    receipt.update({'completed_at': now(), 'after': disk(), 'remaining_worktrees': worktrees(),
                    'all_branch_refs_preserved': True, 'primary_dirty_snapshots_unchanged': True,
                    'git_connectivity_exit': checked.returncode})
    receipt['reclaimed_since_predelete_bytes'] = receipt['after']['available'] - before['available']
    receipt['net_available_gain_since_preservation_start_bytes'] = receipt['after']['available'] - verified['disk_before_preservation']['available']
    (META/'REMOVAL_RECEIPT.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps({k:receipt[k] for k in ['completed_at','after','remaining_worktrees',
          'reclaimed_since_predelete_bytes','net_available_gain_since_preservation_start_bytes']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
