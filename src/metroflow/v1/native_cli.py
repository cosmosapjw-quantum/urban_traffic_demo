"""Thin, fail-closed dispatch to standalone Rust executables.

The frontend forwards configuration and process status. It neither constructs
traffic/calendar state nor substitutes Python calculations on backend failure.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

NATIVE_COMMANDS = {
    "city": "metroflow-native-city",
    "atlas": "metroflow-atlas-generate",
    "prepare-frozen": "metroflow-frozen-prepare",
    "run": "metroflow-native-run",
    "akm": "metroflow-akm-native",
    "d07": "metroflow-akm-d07",
    "d08": "metroflow-akm-d08",
    "support": "metroflow-akm-support",
    "feedback": "metroflow-feedback-audit",
    "next-epoch": "metroflow-next-epoch",
    "restored": "metroflow-restored-generate",
    "campaign": "metroflow-v03-campaign",
}


def launch(command, arguments, *, bin_dir=None):
    name = NATIVE_COMMANDS[command]
    directory = bin_dir or os.environ.get("METROFLOW_NATIVE_BIN_DIR")
    if directory:
        candidate = Path(directory).expanduser() / name
        executable = str(candidate.resolve()) if candidate.is_file() else None
    else:
        executable = shutil.which(name)
    if not executable:
        print(f"Rust backend {name} unavailable; no Python fallback.", file=sys.stderr)
        return 127
    try:
        return subprocess.run([executable, *map(str, arguments)], check=False).returncode
    except OSError as exc:
        print(f"Rust backend {name} could not execute: {exc}; no Python fallback.", file=sys.stderr)
        return 126


def native_main(argv):
    parser = argparse.ArgumentParser(prog="metroflow-v1 native")
    parser.add_argument("--bin-dir", type=Path)
    parser.add_argument("backend", choices=NATIVE_COMMANDS)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    return launch(args.backend, args.arguments, bin_dir=args.bin_dir)


def manifest_main(argv):
    parser = argparse.ArgumentParser(prog="metroflow-v1 run", description="Rust native manifest execution")
    parser.add_argument("--bin-dir", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--until", type=float, required=True)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--engine", choices=["exact", "akm", "hybrid", "interface", "pilot"], default="exact")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--prior-receipt", type=Path)
    parser.add_argument("--source-sha256")
    args = parser.parse_args(argv)
    if args.engine == "exact":
        if bool(args.resume) != bool(args.prior_receipt) or args.source_sha256:
            parser.error("exact resume requires both --resume and --prior-receipt")
        command = [args.manifest, args.until, args.threads, args.out, args.checkpoint]
        if args.resume:
            command += [args.prior_receipt, args.resume]
        return launch("run", command, bin_dir=args.bin_dir)
    if args.prior_receipt or bool(args.resume) != bool(args.source_sha256):
        parser.error("AKM resume requires --resume and --source-sha256")
    prefix = "" if args.engine == "akm" else args.engine + "-"
    mode = prefix + ("resume" if args.resume else "fresh")
    return launch("akm", [mode, args.manifest, args.resume or "-", args.source_sha256 or "-",
                          args.until, args.threads, args.checkpoint, args.out], bin_dir=args.bin_dir)
