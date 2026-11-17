"""Bounded refinement probe: entry-projection width h and time step dt (diagnostic).

Two modes.

  legs CASE OUT_NPZ
      Compile the case calendar once (separate process, so its transient memory
      never enters a run's peak RSS) and store, per calendar leg in engine order,
      the immutable amounts (persons, vehicles, cargo_kg), the carrier the native
      report divides by, and integer codes for mode, purpose, vehicle_class and
      destination label. Also stores sha256 of the ordered leg-ID sequence so a
      run can verify that native leg index i is calendar leg i.

  run CASE HORIZON_S WIDTH_S STEP_S OUT_PREFIX LEGS_NPZ
      Same driver/limits as probe_v1_event_store.py, but with an explicit step
      and a 300 s report curve after SAMPLE_FROM_S (hourly native calls before).
      Per sample: driver.report(state) (ledger, first moments, service), the
      class/destination decomposition of the journey released/completed
      carrier state read through the existing sample_legs diagnostic and
      weighted exactly as the native report weights it (amount_j / carrier),
      debug_state record counts, projection diagnostics, tick costs, RSS.

The decomposition is a re-aggregation of existing per-leg state; its column
sums are checked against the report ledger. Road-internal class ledgers,
road residence seconds and road birth/exit moments are not exposed by the
native Python API and are not reconstructed here.
"""
import hashlib, json, math, os, resource, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_FROM_S = float(os.environ.get('METROFLOW_REFINE_SMOKE_SAMPLE_FROM_S', '21600'))  # override only for smoke tests
SAMPLE_EVERY_S = 300.0
CHUNK = 1024


def current_rss_bytes():
    try:
        return int(Path('/proc/self/statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')
    except OSError:
        return None


def build_schedule(case, matrix):
    from tools.run_v1_local_acceptance import load_release_city, compile_activity, compile_factorized_demand
    city, _ = load_release_city(case)
    homes = tuple(compile_activity(city, b.id) for b in city.face_graph.blocks if b.residents)
    jobs = tuple(compile_activity(city, b.id, 'job') for b in city.face_graph.blocks if b.jobs)
    services = tuple(compile_activity(city, b.id, 'service', service_stock=b.jobs) for b in city.face_graph.blocks if b.jobs)
    return compile_factorized_demand(homes, jobs, services, day=case['day'], freight_kg=1000,
                                     worker_shortfall=matrix['worker_shortfall'])


def legs_mode(case_id, out):
    import numpy as np
    sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
    from metroflow.v1.native_calendar import compile_native_factorized_calendar
    matrix = json.loads((ROOT / 'scenarios/v1/release_matrix.json').read_text())
    case = next(c for c in matrix['cases'] if c['id'] == case_id)
    t0 = time.perf_counter()
    schedule = build_schedule(case, matrix)
    reg = compile_native_factorized_calendar(schedule, byte_budget=min(6 * 1024**3, matrix['limits']['peak_rss_bytes']))
    n = len(reg)
    ids = hashlib.sha256()
    amounts, carrier, codes = [], [], []
    tables = {k: {} for k in ('mode', 'purpose', 'vehicle_class', 'destination')}
    label_cache = {}
    for i in range(n):
        ident, _cohort, _parent, meta, amt, _dwell = reg.leg(i)
        ids.update(ident.encode()); ids.update(b'\0')
        amounts.append(amt)
        carrier.append(amt[1] if amt[1] != 0.0 else amt[0])
        row = []
        for key, handle in (('destination', meta[1]), ('purpose', meta[2]), ('mode', meta[3]), ('vehicle_class', meta[4])):
            if handle not in label_cache:
                label_cache[handle] = reg.label(handle)
            lab = label_cache[handle]
            row.append(tables[key].setdefault(lab, len(tables[key])))
        codes.append(row)
    i = n
    names = {k: [None] * len(v) for k, v in tables.items()}
    for k, v in tables.items():
        for lab, j in v.items():
            names[k][j] = lab
    np.savez(out, amounts=np.asarray(amounts, dtype=np.float64), carrier=np.asarray(carrier, dtype=np.float64),
             codes=np.asarray(codes, dtype=np.int32), names=np.asarray(json.dumps(names)),
             id_sha256=np.asarray(ids.hexdigest()))
    print(json.dumps(dict(legs=i, id_sha256=ids.hexdigest(), wall_s=time.perf_counter() - t0,
                          distinct={k: len(v) for k, v in tables.items()})))


def run_mode(case_id, horizon, width, step, prefix, legs_npz):
    os.environ.update(METROFLOW_V1_ENGINE_BACKEND='rust_whole', METROFLOW_V1_ROUTING_BACKEND='rust',
        METROFLOW_V1_NATIVE_THREADS='1', METROFLOW_V1_STORAGE_POLICY='bounded_bytes_v1',
        METROFLOW_V1_ENTRY_PROJECTION_WIDTH_S=width, METROFLOW_BUDGET_TRACE='record')
    sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
    import numpy as np
    from tools.run_v1_local_acceptance import (atomic_json, candidate_provenance, file_sha256,
        observed_environment, peak_rss_bytes, prepare, resource_limit_kind)
    from metroflow.v1.native_engine import native_binary_provenance
    from metroflow.active_suffix.common import BudgetExceeded
    import _metroflow_rust as native

    horizon = float(horizon); step_s = float(step)
    leg = np.load(legs_npz)
    amounts, carrier, codes = leg['amounts'], leg['carrier'], leg['codes']
    names = json.loads(str(leg['names']))
    want_ids = str(leg['id_sha256'])
    nlegs = len(carrier)
    ratio = np.where(carrier[:, None] != 0.0, amounts / np.where(carrier[:, None] != 0.0, carrier[:, None], 1.0), 0.0)
    # class = (mode, purpose); destination code separately (columns: dest, purpose, mode, vclass)
    n_purpose, n_mode = len(names['purpose']), len(names['mode'])
    class_code = codes[:, 2] * n_purpose + codes[:, 1]
    dest_code = codes[:, 0]
    n_class, n_dest = n_mode * n_purpose, len(names['destination'])

    matrix = json.loads((ROOT / 'scenarios/v1/release_matrix.json').read_text())
    case = next(c for c in matrix['cases'] if c['id'] == case_id)
    limit = matrix['limits']['peak_rss_bytes']
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    prefix = Path(prefix); prefix.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    result = dict(status='RUNNING', scope='DIAGNOSTIC_REFINEMENT_PREFIX_NOT_CAMPAIGN', case=case_id,
        horizon_s=horizon, entry_projection_width_s=float(width), step_s=step_s,
        sample_from_s=SAMPLE_FROM_S, sample_every_s=SAMPLE_EVERY_S, legs_npz=str(legs_npz),
        legs_npz_sha256=file_sha256(Path(legs_npz)), leg_id_sha256=want_ids,
        class_key='mode x purpose (calendar labels)', class_names=[[m, p] for m in names['mode'] for p in names['purpose']],
        destination_names=[(lambda d: f"{d.get('block_id')}:{d.get('kind')}" if isinstance(d, dict) else str(d))(json.loads(x))
                           for x in names['destination']],
        candidate=candidate_provenance(), native_binary=native_binary_provenance(),
        environment=observed_environment(), rss_before_construct_bytes=current_rss_bytes(), calls=[], samples=[])
    driver, _ = prepare(case, matrix, step_s)
    rt = driver.runtime
    result.update(driver_identity=driver.identity, native_storage=rt.storage_config(),
                  execution_config=rt.execution_config(), construct_wall_s=time.perf_counter() - t0,
                  rss_after_construct_bytes=current_rss_bytes(), peak_rss_after_construct_bytes=peak_rss_bytes())
    first = native.budget_trace_snapshot(True)
    result['alloc_counting'] = first.get('alloc_counting')
    state = driver.initial()
    id_checked = dict(done=False)

    def keep(tr):
        sites = {k: dict(ratio=v['max_ratio'], required=v['max_required'], limit=v['limit_at_max'], terms=v['terms_at_max'])
                 for k, v in tr['sites'].items()
                 if k.split(':')[0] in ('road_work', 'road_actual', 'service_sinks', 'journey_commit', 'engine_admission')}
        out = dict(sites=sites, counters=tr.get('counters', {}))
        for k in ('live_bytes', 'peak_bytes'):
            if k in tr:
                out[k] = tr[k]
        return out

    def decompose(st):
        rel = np.empty(nlegs); com = np.empty(nlegs); mom = np.empty(nlegs)
        h = hashlib.sha256() if not id_checked['done'] else None
        for a in range(0, nlegs, CHUNK):
            rows = rt.sample_legs(st.runtime_state, range(a, min(nlegs, a + CHUNK)))
            for k, (ident, r, c, m) in enumerate(rows):
                rel[a + k] = r; com[a + k] = c; mom[a + k] = m
                if h is not None:
                    h.update(ident.encode()); h.update(b'\0')
        if h is not None:
            if h.hexdigest() != want_ids:
                raise SystemExit('native leg order differs from calendar table; decomposition invalid')
            id_checked['done'] = True
        out = {}
        for j, unit in enumerate(('persons', 'vehicles', 'cargo_kg')):
            r = ratio[:, j] * rel; c = ratio[:, j] * com; m = ratio[:, j] * mom
            out[unit] = dict(
                released_total=float(math.fsum(r)), completed_total=float(math.fsum(c)), moment_total=float(math.fsum(m)),
                class_released=np.bincount(class_code, r, n_class).tolist(),
                class_completed=np.bincount(class_code, c, n_class).tolist())
            if unit != 'cargo_kg':
                out[unit].update(dest_released=np.bincount(dest_code, r, n_dest).tolist(),
                                 dest_completed=np.bincount(dest_code, c, n_dest).tolist())
        return out

    def sample(st, call_wall):
        s0 = time.perf_counter()
        rep = driver.report(st)
        dbg = driver.debug_state(st)
        dec = decompose(st)
        ex = rep['execution']
        road = dbg['road']
        return dict(time_s=st.time_s, ledger=ex['ledger'], released_intent_first_moments=ex['released_intent_first_moments'],
            service=ex['service'], assignment_units=ex['assignment']['units'],
            journey_counts={k: v for k, v in dbg['journey'].items() if k not in ('capacity_scope', 'carrier_sum_units')},
            road_records={k: road[k] for k in ('total_records', 'cell_packets', 'pending_packets', 'cell_parts', 'pending_parts',
                                               'uniform_parts', 'mixed_parts', 'max_cell_parts', 'max_pending_parts',
                                               'vector_capacity_bytes', 'latent_entries')},
            event_resolution=road['event_resolution'], projection=rt.projection_diagnostics(),
            decomposition=dec, rss_bytes=current_rss_bytes(), peak_rss_bytes=peak_rss_bytes(),
            sample_wall_s=time.perf_counter() - s0, preceding_call_wall_s=call_wall)

    advance_wall = 0.0
    try:
        while state.time_s < horizon:
            if state.time_s < SAMPLE_FROM_S:
                target = min(horizon, SAMPLE_FROM_S, (math.floor(state.time_s / 3600) + 1) * 3600)
            else:
                target = min(horizon, state.time_s + SAMPLE_EVERY_S)
            c0 = time.perf_counter()
            state = driver.advance(state, target)
            cw = time.perf_counter() - c0
            advance_wall += cw
            m = rt.last_advance_metrics
            ticks = sorted(m['tick_times_s'])
            tr = keep(native.budget_trace_snapshot(True))
            result['calls'].append(dict(end_s=state.time_s, wall_s=cw, ticks=len(ticks),
                tick_sum_s=math.fsum(ticks), tick_p50_s=ticks[len(ticks) // 2] if ticks else None,
                tick_p95_s=ticks[min(len(ticks) - 1, int(0.95 * len(ticks)))] if ticks else None,
                tick_max_s=ticks[-1] if ticks else None, peak_records=m['peak_records'],
                peak_rss_bytes=peak_rss_bytes(), rss_bytes=current_rss_bytes(), **tr))
            if state.time_s >= SAMPLE_FROM_S:
                result['samples'].append(sample(state, cw))
            print(json.dumps(dict(t=state.time_s, wall=round(time.perf_counter() - t0, 1), rss=peak_rss_bytes())), flush=True)
        result['status'] = 'REACHED_HORIZON'
    except (BudgetExceeded, ArithmeticError, ValueError, RuntimeError, MemoryError) as e:
        cp = getattr(e, 'checkpoint', None)
        if cp is not None:
            state = cp
        result.update(status='BLOCKED', reason=str(e)[:600], exception_type=type(e).__name__,
                      resource_limit_kind=resource_limit_kind(str(e), result['native_storage']),
                      phase_metrics=rt.phase_metrics(), failing_call=keep(native.budget_trace_snapshot(True)))
    checkpoint = Path(str(prefix) + '.last_valid.bin')  # not with_suffix: labels may contain '.'
    driver.save(checkpoint, state)
    result.update(simulated_s=state.time_s, advance_wall_s=advance_wall, wall_s=time.perf_counter() - t0,
                  peak_rss_bytes=peak_rss_bytes(), peak_records=max((c['peak_records'] for c in result['calls']), default=0),
                  report=driver.report(state), debug=driver.debug_state(state),
                  checkpoint=dict(path=str(checkpoint), bytes=checkpoint.stat().st_size, sha256=file_sha256(checkpoint)),
                  script_sha256=file_sha256(Path(__file__)))
    atomic_json(Path(str(prefix) + '.json'), result)
    print(json.dumps({k: result[k] for k in ('status', 'simulated_s', 'wall_s', 'peak_rss_bytes')}))


if __name__ == '__main__':
    if sys.argv[1] == 'legs':
        legs_mode(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == 'run':
        run_mode(*sys.argv[2:8])
    else:
        raise SystemExit(__doc__)
