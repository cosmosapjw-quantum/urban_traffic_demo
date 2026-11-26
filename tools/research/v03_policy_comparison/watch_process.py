"""Sample a child process's Linux high-water marks, including abnormal exits."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new JSON result path")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="command and arguments")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if not args.command:
        parser.error("specify a child executable and any arguments")
    start = time.monotonic()
    peaks = dict(VmPeak=0, VmHWM=0)
    expired = False
    child = subprocess.Popen(args.command, env=os.environ.copy())
    while child.poll() is None:
        try:
            for row in Path(f"/proc/{child.pid}/status").read_text().splitlines():
                key, _, val = row.partition(":")
                if key in peaks:
                    peaks[key] = max(peaks[key], int(val.split()[0])*1024)
        except OSError:
            pass
        if time.monotonic() - start > 1800:
            child.kill()
            expired = True
            break
        time.sleep(.2)
    args.output.write_text(json.dumps(dict(child_exit=child.wait(), wall_s=time.monotonic()-start,
                              wall_limit_hit=expired, observed_bytes=peaks, argv=args.command), indent=2)+"\n")


if __name__ == "__main__":
    main()
