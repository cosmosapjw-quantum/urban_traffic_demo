from metroflow.core.journal import InterventionJournal, InterventionRecord
from metroflow.core.state import make_empty_world_state
from metroflow.metrics.benchmarks import record_input_signature_smoke_benchmark
from metroflow.sim.replay import journal_fingerprint, make_replay_input_signature, replay_input_fingerprint


def test_make_replay_input_signature_record():
    world = make_empty_world_state(seed=7)
    journal = InterventionJournal(records=(InterventionRecord(step=3, kind="incident", payload="edge:1"),))
    rec = make_replay_input_signature(world, num_steps=100, input_fingerprint=1.23, journal=journal)
    assert rec.seed == 7
    assert rec.num_steps == 100
    assert rec.journal_fingerprint
    assert rec.input_fingerprint == "1.23"


def test_replay_input_fingerprint_is_deterministic_for_equivalent_inputs():
    journal = InterventionJournal(records=(InterventionRecord(step=8, kind="policy", payload="toll:on"),))
    signature_a = replay_input_fingerprint(11, 20, journal, "obs=a")
    signature_b = replay_input_fingerprint(11, 20, journal, "obs=a")

    assert signature_a == signature_b


def test_replay_input_fingerprint_changes_when_declared_observation_changes():
    journal = InterventionJournal(records=(InterventionRecord(step=8, kind="policy", payload="toll:on"),))
    signature_a = replay_input_fingerprint(11, 20, journal, "obs=a")
    signature_b = replay_input_fingerprint(11, 20, journal, "obs=b")

    assert signature_a != signature_b


def test_journal_fingerprint_rejects_delimiter_collisions():
    journal_a = InterventionJournal(records=(InterventionRecord(step=3, kind="a:b", payload="c"),))
    journal_b = InterventionJournal(records=(InterventionRecord(step=3, kind="a", payload="b:c"),))

    assert journal_fingerprint(journal_a) != journal_fingerprint(journal_b)


def test_replay_input_fingerprint_is_order_sensitive():
    journal_a = InterventionJournal(
        records=(
            InterventionRecord(step=1, kind="policy", payload="a"),
            InterventionRecord(step=2, kind="incident", payload="b"),
        )
    )
    journal_b = InterventionJournal(
        records=(
            InterventionRecord(step=2, kind="incident", payload="b"),
            InterventionRecord(step=1, kind="policy", payload="a"),
        )
    )

    assert replay_input_fingerprint(11, 20, journal_a, "obs=a") != replay_input_fingerprint(11, 20, journal_b, "obs=a")


def test_replay_input_fingerprint_treats_delimiter_collision_cases_as_distinct():
    journal_a = InterventionJournal(records=(InterventionRecord(step=3, kind="a:b", payload="c"),))
    journal_b = InterventionJournal(records=(InterventionRecord(step=3, kind="a", payload="b:c"),))

    assert replay_input_fingerprint(11, 20, journal_a, "obs=a") != replay_input_fingerprint(11, 20, journal_b, "obs=a")


def test_record_input_signature_smoke_benchmark_populates_proxy_fields():
    world = make_empty_world_state(seed=13)
    record = make_replay_input_signature(world, num_steps=12, input_fingerprint="abc")
    bench = record_input_signature_smoke_benchmark(record, step_proxy_score=2.5, state_proxy_score=64.0)

    assert bench.step_proxy_score == 2.5
    assert bench.state_proxy_score == 64.0
    assert bench.signature == "abc"
