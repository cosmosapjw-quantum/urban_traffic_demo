from collections import Counter
from metroflow.terrain_city.network import generate


def test_uncommitted_deadend_stubs_are_not_mistaken_for_served_blocks():
    city=generate('corridor','valley',4000.,20,population=20000)
    degree=Counter(v for s in city.roadmap.sections for v in (s.start,s.end))
    unbacked=[s.id for s in city.roadmap.sections if s.hierarchy!='arterial' and
              any(degree[v]==1 and v not in city.centers for v in (s.start,s.end))]
    assert not unbacked, 'Deadend streets have neither development block nor declared destination'


def test_pruning_keeps_stock_and_face_contracts():
    city=generate('polycentric','river',4000.,20,population=10**9)
    assert city.summary['components']==1
    assert sum(b.residents for b in city.blocks)+city.summary['unplaced_residents']==10**9
    assert city.summary['unplaced_residents']>0
    assert city.summary['cycle_rank']==len(city.blocks)
