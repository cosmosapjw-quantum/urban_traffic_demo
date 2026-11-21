"""Constructive traffic node weighted FIFO feasibility and source sensitivity."""
from fractions import Fraction as F
from pathlib import Path
import json
from tools.research.v03_weighted_fifo_junction_exact_20261121 import solve,example,validate_maxmin_exact,stress
ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/"artifacts/v03_weighted_fifo_20261121/R5_EXACT_WEIGHTED_JUNCTION_THEORY.json"
def read():return json.loads(REPORT.read_bytes())
def test_source_traffic_throughput_and_supply_relief_exact():
    row=read()
    assert row["finite_exact_assertions_checked"]==24696
    assert row["example"]==example()
    x=row["example"]
    assert x["base_flow"]==["3/2","3","7/2"]
    assert x["base_downstream"]==["3","5"]
    assert x["relieved_flow"]==["2","4","3"]
    assert x["relieved_downstream"]==["4","5"]
    assert x["physical_total_flow_gain"]=="1"
def test_constructive_zero_receiving_capacity_avoids_all_illegal_turns():
    b=[[F(1),F(0)],[F(1,2),F(1,2)],[F(0),F(1)]]
    x=solve([F(1),F(2),F(1)],[F(10),F(10),F(4)],b,[F(0),F(5)])
    assert x["flow"]==[F(0),F(0),F(4)]
    assert x["destinations"]==[F(0),F(4)]
    validate_maxmin_exact([F(1),F(2),F(1)],[F(10),F(10),F(4)],b,[F(0),F(5)],x)
def test_single_input_exact_termination_tie_and_sink_conservation():
    for cap in [F(0),F(1,5),F(1),F(10)]:
        x=solve([F(2)],[F(5)],[[F(1)]],[cap])
        assert x["flow"]==[min(F(5),cap)]
        assert x["destinations"]==x["flow"]
        assert len(x["rounds"])<=1
