"""Retained allocation accounting must count sharing and ownership accurately."""
import math

from _metroflow_rust import NativeJourneyCore, NativeReceiptHistory, NativeServiceCore, NativeStageQueue


def journey(*, law_rows=1, profile_rows=1, distinct_second_law=False):
    law = [(float(i), 1. / law_rows) for i in range(law_rows)]
    second = list(law)
    if distinct_second_law:
        second[0] = (second[0][0], .5 / law_rows)
        second[1] = (second[1][0], 1.5 / law_rows)
    profile = [(float(i), float(i + 1), 1. / profile_rows)
               for i in range(profile_rows)]
    legs = [
        ("a", 1., None, 0., profile, 2, law, law),
        ("b", 1., None, 0., list(profile), 2, second, list(law)),
    ]
    return NativeJourneyCore(legs, [], [], 20_000)


def test_one_shared_law_payload_is_counted_once_across_four_references():
    short = journey(law_rows=1).storage_accounting()
    long = journey(law_rows=512).storage_accounting()
    # Python inputs use distinct lists; the native constructor interns equal
    # laws. Only one retained payload grows by 511 pairs of binary64 values.
    assert long[0] - short[0] == 511 * 16
    assert long[1:] == short[1:]
    distinct = journey(law_rows=512, distinct_second_law=True).storage_accounting()
    # A genuinely different allocation adds its complete payload and header.
    assert 512 * 16 < distinct[0] - long[0] < 512 * 16 + 1024


def test_shared_profile_payload_is_counted_once_by_arc_object_identity():
    short = journey(profile_rows=1).storage_accounting()
    long = journey(profile_rows=512).storage_accounting()
    assert long[0] - short[0] == 511 * 24
    assert long[1:] == short[1:]


def test_static_dense_and_dynamic_journey_storage_have_separate_lifetimes():
    core = journey(law_rows=4)
    static, dense, dynamic = core.storage_accounting()
    assert static > 0 and dense > 0 and dynamic == 0
    initial = core.snapshot()
    for end in (1., 2.):
        core.prepare()
        core.finish(end, [], [], [], [], [], [], [])
    later = core.storage_accounting()
    assert later[:2] == (static, dense) and later[2] > 0
    core.restore(initial)
    restored_static, restored_dense, restored_dynamic = core.storage_accounting()
    assert (restored_static, restored_dynamic) == (static, 0)
    assert restored_dense > 0
    assert core.snapshot() == initial
    # Legacy Python row restore may reuse its Vec<Vec<Receipt>> outer buffer
    # for the smaller ReceiptHistory elements. Equal physical rows therefore
    # do not imply equal retained Vec capacities; the getter reports reality.


def test_service_owned_source_strings_are_charged_separately_from_dense_state():
    def service(name):
        return NativeServiceCore([], [], [(name, 0., 1.)], [(name, 0., 1.)])
    short = service("a").storage_accounting()
    long = service("a" * 513).storage_accounting()
    # Freight and car labels are separate owned Strings, unlike journey laws.
    assert long[0] - short[0] == 2 * 512
    assert long[1:] == short[1:]
    assert short[1] > 0 and short[2] == 0


def test_filtered_stage_decode_envelope_covers_each_fresh_append_preflight():
    for length in (1, 3, 255, 256, 257, 2049):
        queue = NativeStageQueue([(i, 1., 0., 0. if i % 4 == 0 else 100.)
                                  for i in range(length)])
        queue.retire_due(1.)
        rows = queue.snapshot()
        upper = queue.decoded_storage_upper_bytes()
        decoded = NativeStageQueue([])
        for row in rows:
            assert decoded.append_upper_bytes(1) <= upper
            decoded.append(row)
        assert decoded.storage_shape()[3] <= upper
        assert decoded.snapshot() == rows


def test_history_decode_envelope_survives_copy_on_write_capacity_changes():
    rows = [(float(i), math.ldexp(1., -(i * 37) % 1000 - 1000))
            for i in range(1025)]
    current = NativeReceiptHistory([])
    for row in rows:
        previous = current.fork()  # force COW of a partial head on every append
        current.append(*row)
    assert previous.snapshot() == rows[:-1]
    upper = current.decoded_storage_upper_bytes()
    decoded = NativeReceiptHistory([])
    for row in rows:
        assert decoded.append_upper_bytes() <= upper
        decoded.append(*row)
    assert decoded.storage_bytes() <= upper
    assert decoded.decoded_storage_upper_bytes() == upper
    assert decoded.snapshot() == current.snapshot() == rows


def test_many_histories_charge_only_one_sequential_decode_workspace():
    count = 128
    legs = [(f"leg-{i}", 1., None, 0., [(0., 1., 1.)], 2,
             [(0., 1.)], [(0., 1.)]) for i in range(count)]
    core = NativeJourneyCore(legs, [], [], 20_000)
    empty = core.snapshot()
    complete = (2., [], [], [], [1.] * count, [1.] * count,
                [[(1., 1.)] for _ in range(count)], [.5] * count)
    core.restore(complete)
    history = NativeReceiptHistory([(1., 1.)])
    final = history.decoded_final_storage_upper_bytes()
    extra = history.decoded_storage_upper_bytes() - final
    assert core.decoded_storage_upper_bytes() == count * final + extra
    core.prepare()
    core.finish(3., [], [], [], [], [], [], [])
    assert core.decoded_storage_upper_bytes() == count * final + extra
    core.restore(empty)
    assert core.decoded_storage_upper_bytes() == 0
    core.restore(complete)
    assert core.decoded_storage_upper_bytes() == count * final + extra
