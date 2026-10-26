"""C01 real queue/event/info/cache restoration and phase contracts."""
from dataclasses import replace
import json
import pytest
from metroflow.v1.runtime import toy_runtime, Runtime
from metroflow.v1.checkpoint import save_checkpoint, load_checkpoint
from metroflow.v1.city import CityContractError
from metroflow.active_suffix.common import BudgetExceeded


def test_actual_queued_state_json_resume_equals_continuous(tmp_path):
    m = toy_runtime()
    half = m.advance(m.initial(), 10)
    assert half.traffic.road.released > half.traffic.road.completed
    assert half.traffic.road.cells[0].packets
    assert half.routing.cache
    path = tmp_path / 'world.json'
    save_checkpoint(path, m, half)
    restored = load_checkpoint(path, m)
    assert restored == half
    assert m.advance(restored, 60) == m.advance(m.initial(), 60)
    assert m.advance(restored, 60).traffic.events


def test_slow_phase_uses_previous_snapshot_when_clocks_coincide():
    m = toy_runtime()
    s = m.advance(m.initial(), 10)
    assert s.accessibility.stamp_s == 10
    assert s.slow_input.stamp_s == 5
    assert [e.phase for e in s.journal if e.time_s == 10] == ['medium', 'slow']


def test_failed_transaction_preserves_complete_input_world():
    m = toy_runtime()
    m = Runtime(m.transport, m.information, m.routing, m.preference,
                city_identity=m.city_identity, demand_identity=m.demand_identity,
                origin=m.origin, destination=m.destination, record_budget=1)
    state = m.initial()
    with pytest.raises(BudgetExceeded) as error:
        m.advance(state, 30)
    assert error.value.checkpoint is state
    assert not state.journal and state.traffic.road.time_s == 0


def test_graph_deletion_requires_drain_and_is_not_hot_swap():
    m = toy_runtime()
    s = m.advance(m.initial(), 10)
    assert m.graph_edit(s, ('0',))['status'] == 'DRAIN_REQUIRED'
    final = m.advance(s, 60)
    transaction = m.graph_edit(final, ('0',))
    assert transaction['status'] == 'READY_TRANSACTION'
    assert transaction['checkpoint'] is final
    with pytest.raises(CityContractError):
        m.graph_edit(s, ('missing',))


def test_checkpoint_unknown_type_rejected_without_import(tmp_path):
    path = tmp_path / 'bad.json'
    path.write_text(json.dumps(dict(schema='C01_world_v1', state={'type':'os.system','fields':{}})))
    with pytest.raises(CityContractError):
        load_checkpoint(path, toy_runtime())


def test_identity_and_clock_mismatch_rejected(tmp_path):
    m = toy_runtime()
    with pytest.raises(CityContractError):
        m.advance(replace(m.initial(), demand_identity='wrong'), 10)
    with pytest.raises(CityContractError):
        m.advance(replace(m.initial(), next_medium_s=0), 10)


def test_run_writes_checkpoint_and_resumes(tmp_path):
    m = toy_runtime()
    path = tmp_path / 'durable.json'
    final = m.run(m.initial(), 60, path)
    assert load_checkpoint(path, m) == final
    assert not path.with_name(path.name + '.tmp').exists()


def test_actual_frozen_city_and_schedule_retained_in_checkpoint(tmp_path):
    from metroflow.v1.access_audit import fixture_city
    from metroflow.v1.demand import TripSchedule
    city = fixture_city()
    schedule = TripSchedule(city.identity, 'weekday', 0, (), (), 0, 0, 'empty-fixture')
    base = toy_runtime()
    m = Runtime(base.transport, base.information, base.routing, base.preference,
                city_identity=city.identity, demand_identity=schedule.identity,
                origin=base.origin, destination=base.destination,
                city_snapshot=city, trip_schedule=schedule)
    path = tmp_path / 'inputs.json'
    state = m.advance(m.initial(), 5)
    save_checkpoint(path, m, state)
    assert load_checkpoint(path, m).trip_schedule == schedule
    assert json.loads(load_checkpoint(path, m).city_snapshot_json)['identity'] == city.identity


def test_long_run_persists_at_most_900_seconds_between_checkpoints(tmp_path, monkeypatch):
    import metroflow.v1.checkpoint as checkpoint
    m = toy_runtime()
    saved = []
    original = checkpoint.save_checkpoint
    def record(path, model, state):
        saved.append(state.traffic.road.time_s)
        original(path, model, state)
    monkeypatch.setattr(checkpoint, 'save_checkpoint', record)
    m.run(m.initial(), 901, tmp_path / 'long.json')
    assert saved == [900.0, 901.0]


def test_malformed_json_classified(tmp_path):
    path = tmp_path / 'broken.json'
    path.write_text('{broken')
    with pytest.raises(CityContractError) as error:
        load_checkpoint(path, toy_runtime())
    assert error.value.status == 'CONTRACT_ERROR'
