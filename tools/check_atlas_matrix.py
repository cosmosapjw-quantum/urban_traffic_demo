"""Small crossed terrain/type matrix; preserve errors rather than selecting seeds."""

from pathlib import Path
import sys
import json
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from metroflow.terrain_city.network import generate, STYLES
from metroflow.terrain_city.audit import geometry_audit

out = Path(sys.argv[1] if len(sys.argv) > 1 else "artifacts/terrain_atlas_20261025/matrix.json")
results = []
for style in STYLES:
    for terrain in ("flat", "river", "coast", "valley", "lake"):
        t = time.perf_counter()
        try:
            a = generate(style, terrain, 4000.0, 20, 17, 20000)
            audit = geometry_audit(a)
            if audit["illegal_projected_contacts"]:
                raise ArithmeticError(str(audit["illegal_projected_contacts"][:2]))
            if len(audit["component_sizes"]) != 1:
                raise ArithmeticError("disconnected published network")
            results.append(
                dict(
                    style=style,
                    terrain=terrain,
                    status="PASS_SCOPED",
                    nodes=a.summary["nodes"],
                    bridges=a.summary["bridges"],
                    placed=a.summary["resident_stock"],
                    pending=a.summary["unplaced_residents"],
                    seconds=time.perf_counter() - t,
                )
            )
        except Exception as e:
            results.append(
                dict(
                    style=style,
                    terrain=terrain,
                    status="FAIL",
                    exception=type(e).__name__,
                    message=str(e),
                )
            )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, indent=2))
        print(results[-1], flush=True)
if any(x["status"] == "FAIL" for x in results):
    sys.exit(1)
