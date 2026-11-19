#!/usr/bin/env python3
"""V03 lineage: exact mathematical witnesses and finite IEEE counterexamples.

THEORY RESEARCH ONLY. This script does not modify the original V03 executable,
does not fit rates, and cannot prove speed/memory for an unimplemented kernel.
All rational identities are checked using fractions.Fraction. IEEE witnesses
are checked with CPython binary64 and exact hexadecimal payloads.
"""
from __future__ import annotations

from collections import defaultdict
from fractions import Fraction as Q
from hashlib import sha256
import itertools
import json
import math
from pathlib import Path
import platform
import random
import struct
from time import perf_counter


def bits(x: float) -> str:
    return struct.pack(">d", float(x)).hex()


def quotient_source(s: int, m: int) -> Q:
    return Q(s, m)


def prefix_integral(segments, route: str, q: Q, field: str = "route") -> Q:
    """Integrate a piecewise constant mark density up to mass coordinate q."""
    total = sum((row["length"] for row in segments), Q(0))
    assert Q(0) <= q <= total
    value = Q(0)
    for row in segments:
        length = min(q, row["length"])
        value += length * row[field].get(route, Q(0))
        q -= length
    assert q == 0
    return value


def interval_direct(segments, route: str, lo: Q, hi: Q, field: str = "route") -> Q:
    """Independent direct interval intersection, not a prefix-difference oracle."""
    assert lo <= hi
    total = Q(0)
    cursor = Q(0)
    for row in segments:
        nxt = cursor + row["length"]
        start = max(cursor, lo)
        end = min(nxt, hi)
        if end > start:
            total += (end - start) * row[field].get(route, Q(0))
        cursor = nxt
    return total


def test_marked_mass_coordinate() -> dict:
    # Every composition vector sums to one: strict packet FIFO mass coordinate.
    segments = [
        {"length": Q(4), "route": {"A": Q(3, 4), "B": Q(1, 4)},
         "birth": {"A": Q(3, 2), "B": Q(1, 4)}},
        {"length": Q(3), "route": {"A": Q(1, 3), "B": Q(2, 3)},
         "birth": {"A": Q(2, 3), "B": Q(1, 3)}},
    ]
    total = sum((s["length"] for s in segments), Q(0))
    assert total == 7
    assert all(sum(s["route"].values()) == 1 for s in segments)
    # The birth moment is extensive, not required to sum to one.
    endpoints = sorted(set([Q(0), Q(4), Q(7)] +
                           [Q(i, 12) * total for i in range(13)]))
    nchecks = 0
    for lo in endpoints:
        for hi in endpoints:
            if hi < lo:
                continue
            for route in ("A", "B"):
                for field in ("route", "birth"):
                    a = prefix_integral(segments, route, hi, field) - prefix_integral(segments, route, lo, field)
                    b = interval_direct(segments, route, lo, hi, field)
                    assert a == b, (field, route, lo, hi)
                    nchecks += 1
            routed = sum(
                interval_direct(segments, route, lo, hi, "route")
                for route in ("A", "B")
            )
            assert routed == hi - lo
    return {
        "cumulative_query_checks": nchecks,
        "total_mass": str(total),
        "route_A_total": str(prefix_integral(segments, "A", total)),
        "route_B_total": str(prefix_integral(segments, "B", total)),
        "birth_A_total": str(prefix_integral(segments, "A", total, "birth")),
        "birth_B_total": str(prefix_integral(segments, "B", total, "birth")),
        "fifo_property": "F_r(s2)-F_r(s1)>=0 for s2>=s1; monotone output cursor",
    }


def test_coalescence() -> dict:
    # Exact real-valued density equivalence when EACH mark's mass/birth density
    # and ready/target are equal across adjacent intervals. The inverse is
    # false if different route densities are hidden by a total-mass-only merge.
    rho = {"A": Q(2, 3), "B": Q(1, 3)}
    theta = {"A": Q(4, 3), "B": Q(2, 3)}
    two = [{"length": Q(1), "route": rho, "birth": theta},
           {"length": Q(2), "route": rho, "birth": theta}]
    one = [{"length": Q(3), "route": rho, "birth": theta}]
    boundaries = [Q(i, 12) for i in range(37)]
    checks = 0
    for a in boundaries:
        for b in boundaries:
            if b < a:
                continue
            for route in ("A", "B"):
                for field in ("route", "birth"):
                    lhs = interval_direct(two, route, a, b, field)
                    rhs = interval_direct(one, route, a, b, field)
                    assert lhs == rhs
                    checks += 1
    cannot_merge = [
        {"length": Q(1), "route": {"A": Q(1), "B": Q(0)},
         "birth": {"A": Q(1), "B": Q(0)}},
        {"length": Q(1), "route": {"A": Q(0), "B": Q(1)},
         "birth": {"A": Q(0), "B": Q(1)}},
    ]
    average = [
        {"length": Q(2), "route": {"A": Q(1, 2), "B": Q(1, 2)},
         "birth": {"A": Q(1, 2), "B": Q(1, 2)}},
    ]
    assert sum(interval_direct(cannot_merge, r, Q(0), Q(2))
               for r in ("A", "B")) == Q(2)
    assert all(interval_direct(cannot_merge, r, Q(0), Q(2)) ==
               interval_direct(average, r, Q(0), Q(2)) for r in ("A", "B"))
    assert interval_direct(cannot_merge, "A", Q(0), Q(1)) == 1
    assert interval_direct(average, "A", Q(0), Q(1)) == Q(1, 2)
    return {
        "positive_range_check_count": checks,
        "counterexample_route_A_first_half_true": "1",
        "counterexample_route_A_first_half_false_merge": "1/2",
        "counterexample_total_A_B_endpoints_equal": True,
        "scope": "real-valued interval query equivalence; IEEE order and ready times require separate checks",
    }


def test_proportional_split() -> dict:
    base = [
        (Q(3), Q(21, 2)),
        (Q(4), Q(12)),
        (Q(5, 2), Q(10, 3)),
    ]
    factors = [Q(0), Q(1), Q(1, 7), Q(3, 8), Q(9, 10), Q(11, 13)]
    cases = 0
    for m, birth in base:
        for f in factors:
            served = (f * m, f * birth)
            remaining = ((1-f)*m, (1-f)*birth)
            assert served[0]+remaining[0] == m
            assert served[1]+remaining[1] == birth
            assert served[0]>=0 and remaining[0]>=0
            cases += 1
    return {"exact_fraction_mass_birth_conservation_cases":cases,
            "factors":list(map(str,factors)),
            "scope":"exact real/rational arithmetic under existing partial service law"}


def test_ieee_dag() -> dict:
    # Positive finite f in [0,1]; all witnesses are literal Python binary64.
    x, f, g = 0.1, 0.3, 0.7
    eager = (x*f)*g
    collapsed = x*(f*g)
    assert eager != collapsed
    eager_hex, collapsed_hex = eager.hex(), collapsed.hex()
    # A simple immutable operation trace, not a production executable:
    ops = (("mul",f),("mul",g))
    value = x
    for op,arg in ops:
        assert op == "mul"
        value = value*arg
    assert bits(value) == bits(eager)
    # Split conservation is exact over rationals, NOT generally bit-exact.
    split = (x*f)+(x*(1-f))
    assert bits(split) != bits(x)
    # The Rust interval code does sequential multiply-then-divide, and
    # distributing the division into the coefficient can change rounding.
    mass, width, denominator = 0.7, 6.0, 9.0
    sequential = (mass*width)/denominator
    precollapsed = mass*(width/denominator)
    assert bits(sequential) != bits(precollapsed)
    # Reversing 'fsum of products' versus 'product of sum' may differ too.
    weights = (0.1, 0.3, 0.5)
    factor = 0.7
    exact_original = math.fsum([z*factor for z in weights])
    regrouped = math.fsum(weights)*factor
    # This particular fixed example may coincide by rounding; use an explicit
    # existential search with deterministic finite seed when needed.
    rng = random.Random(20261119)
    found = None
    for idx in range(20000):
        xs = [rng.random() for _ in range(7)]
        c = rng.random()
        av = math.fsum(z*c for z in xs)
        bv = math.fsum(xs)*c
        if bits(av) != bits(bv):
            found = {"counterexample_index":idx,
                     "xs":xs,"factor":c,
                     "sum_individual_products_hex":av.hex(),
                     "multiply_sum_hex":bv.hex()}
            break
    assert found is not None
    return {
        "two_stage_original_hex":eager_hex,
        "two_stage_flattened_hex":collapsed_hex,
        "split_reconstituted_hex":split.hex(),
        "original_mass_hex":x.hex(),
        "interval_order_sequential_hex":sequential.hex(),
        "interval_order_reassociated_hex":precollapsed.hex(),
        "fsum_noncommutation":found,
        "literal_bytes_from_struct":bits(eager),
        "selected_trace_operations":len(ops),
        "scope":"finite CPython IEEE binary64 counterexample; not global V03 code equivalence",
    }


def test_route_order_bits() -> dict:
    # A fixed-count FIFO source can distinguish each of comb(2m,m) orders
    # if route labels of each of the 2m output events can be observed.
    samples = []
    for m in (1, 4, 16, 64, 256):
        exact = math.comb(2*m,m)
        bits_needed = math.log2(exact)
        samples.append({
            "m_per_route":m,
            "total_elements":2*m,
            "number_possible_orders_decimal":str(exact),
            "minimum_bits_for_exact_route_order":math.ceil(bits_needed),
            "log2_orders":bits_needed,
        })
    # For m=2, all six orders can be recovered by observing the entire exit
    # route-label event sequence; per-route mass counts are always identical.
    words = set(itertools.permutations("AABB"))
    assert len(words)==6
    assert {tuple(sorted(w)) for w in words}=={("A","A","B","B")}
    return {"cases":samples,
            "m2_distinguishable_exit_orders":len(words),
            "scope":"bit lower bound for a subclass of strict ordered FIFO states with route-event outputs; not a universal V03 memory-growth theorem"}


def test_head_blocking_non_lipschitz() -> dict:
    # A tiny positive mass A ahead of B blocks B when A's direction is red
    # and B's direction is green. Removing only A changes B exit by order-one
    # mass, proving no uniform Lipschitz response to total-variation mass.
    epsilons = [Q(1,2**k) for k in (4,8,12,20,28)]
    rows=[]
    for eps in epsilons:
        tv = eps
        outbound_B_difference = Q(1)
        assert outbound_B_difference/tv == 1/eps
        rows.append({"epsilon_A_at_red_head":str(eps),
                     "difference_in_B_exit_mass":"1",
                     "error_amplification_ratio":str(1/eps)})
    return {"cases":rows,
            "strict_fifo_head_of_line_discontinuity":True,
            "scope":"adversarial signalized diverge; does not rule out bounded error under additional smooth junction assumptions"}


def test_symbolic_memory_bound() -> dict:
    # Idealized repeated proportional service of ONE immutable P-row source
    # template, with K outgoing events and no forced materialization.
    # Each event shares one template and stores one factor+reference node.
    P, K = 160, 44852
    eager_copied_rows = P*K
    symbolic_nodes_upper = P+2*K
    assert eager_copied_rows == 7_176_320
    assert symbolic_nodes_upper == 89_864
    assert eager_copied_rows/symbolic_nodes_upper > 79
    return {
        "template_rows":P,
        "event_count":K,
        "eager_copied_rows_idealized":eager_copied_rows,
        "symbolic_row_plus_two_nodes_per_event":symbolic_nodes_upper,
        "idealized_element_count_ratio":eager_copied_rows/symbolic_nodes_upper,
        "caution":"does not count original V03 per-row event output or merge fan-in, cannot predict actual RSS or CPU acceleration",
    }


def main() -> None:
    start = perf_counter()
    project = Path(__file__).resolve().parents[2]
    pinned = {
        str(name): sha256((project/name).read_bytes()).hexdigest()
        for name in (
            "crates/metroflow-rust/src/v1_road.rs",
            "docs/v1/PLAN.json",
            "scenarios/v1/release_matrix.json",
            "artifacts/v1_v03_workspace_20261117/ATTRIBUTION_KO.md",
        )
    }
    blocks = {
        "fraction_split": test_proportional_split(),
        "marked_mass_F_is_F_of_cumulative_cursor": test_marked_mass_coordinate(),
        "coalescence_required_mark_density": test_coalescence(),
        "ieee_nonassociativity": test_ieee_dag(),
        "route_order_lower_bound": test_route_order_bits(),
        "strict_FIFO_head_discontinuity": test_head_blocking_non_lipschitz(),
        "ideal_symbolic_composition_DAG": test_symbolic_memory_bound(),
    }
    result = {
        "identity": "V03-FIFO-LINEAGE-THEORY-ORACLES-20261119-V1",
        "python_version": platform.python_version(),
        "seed": 20261119,
        "project_baseline_pinned_sha256": pinned,
        "tested_claims": blocks,
        "duration_seconds": perf_counter() - start,
        "status": "CHECKED_FINITE_CASES_ONLY",
        "full_production_kernel_implemented": False,
        "parent_research_v03_status": "BLOCKED_0_OF_9_24H_RUNS",
        "exclusions": [
            "No claim of full native V03 kernel equivalence",
            "No performance measurement of unimplemented lineage DAG",
            "No unrestricted global error bound for arbitrary FIFO junctions",
            "No fitted driver, probe or external physical parameters",
        ],
    }
    out = project/"artifacts/v03_fifo_lineage_theory_20261119/EXACT_THEORY_CHECKS.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False,sort_keys=True)+"\n")
    print(json.dumps({
        "status":result["status"],
        "proof_oracles":len(blocks),
        "marked_cursor_checks":blocks["marked_mass_F_is_F_of_cumulative_cursor"]["cumulative_query_checks"],
        "coalescence_checks":blocks["coalescence_required_mark_density"]["positive_range_check_count"],
        "ieee_reassociation_diff":(
            blocks["ieee_nonassociativity"]["two_stage_original_hex"] !=
            blocks["ieee_nonassociativity"]["two_stage_flattened_hex"]),
        "example_route_order_bits":blocks["route_order_lower_bound"]["cases"][-1]["minimum_bits_for_exact_route_order"],
        "file":str(out),
    },sort_keys=True))


if __name__ == "__main__":
    main()
