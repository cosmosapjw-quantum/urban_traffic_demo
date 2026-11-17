"""Apply the pre-registered release timing comparison (LAUNCH.json) to the run JSONs.

usage: compare.py  ->  writes COMPARISON.json next to this file
"""
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LAUNCH = json.loads((HERE / 'LAUNCH.json').read_text())
PRIMARY_T = 25500.0
SECONDARY_T = 26000.0
BITID_SHA = 'ab73c40f1166c92788aef865bd4f4b644359bf985a66f49182830dccf776d7ff'
PRIOR = ROOT / 'artifacts/v1_refinement_20261117/runs'
LABELS = ('legacy_dt10', 'legacy_dt5', 'interval_dt10', 'interval_dt5')


def load(label):
    path = HERE / 'runs' / f'{label}.json'
    return json.loads(path.read_text()) if path.exists() else None


def sample_at(run, t):
    for s in run['samples']:
        if s['time_s'] == t:
            return s
    return None


def l1(a, b):
    return math.fsum(abs(x - y) for x, y in zip(a, b))


def accuracy(s):
    led, svc, mom, rl = s['ledger'], s['service'], s['released_intent_first_moments'], s['road_ledger']
    dec = s['decomposition']
    return dict(
        A1_released_persons=led['persons']['released'],
        A2_journey_completed_vehicles=led['vehicles']['completed'],
        A3_road_completed_vehicles=svc['road_completed_veh'],
        released_vehicles=led['vehicles']['released'],
        journey_completed_persons=led['persons']['completed'],
        road_released_vehicles=svc['road_released_veh'],
        road_occupancy_vehicles=svc['road_released_veh'] - svc['road_completed_veh'],
        released_birth_moment_persons=mom['persons'],
        released_birth_moment_vehicles=mom['vehicles'],
        road_birth_moment_veh_s=rl['birth_moment_veh_s'],
        road_source_arrival_moment_veh_s=rl['birth_moment_veh_s'] + rl['pre_entry_veh_s'],
        road_source_admission_moment_veh_s=(rl['birth_moment_veh_s'] + rl['pre_entry_veh_s']
                                            + rl['source_wait_veh_s'] - rl['pending_veh'] * s['time_s']),
        road_cell_entry_moment_veh_s=rl['cell_entry_moment_veh_s'],
        road_pre_entry_veh_s=rl['pre_entry_veh_s'],
        road_source_wait_veh_s=rl['source_wait_veh_s'],
    ), dict(dest=dec['vehicles']['dest_completed'], cls=dec['vehicles']['class_completed'])


def conservation(run):
    worst = dict(decomposition=0.0, road_mass=0.0, road_residence=0.0, identity=0.0)
    failures = []
    previous = None
    for s in run['samples']:
        led, dec, mom = s['ledger'], s['decomposition'], s['released_intent_first_moments']
        for unit in ('persons', 'vehicles', 'cargo_kg'):
            u = led[unit]
            scale = max(1.0, abs(u['requested']))
            for a, b in ((dec[unit]['released_total'], u['released']),
                         (dec[unit]['completed_total'], u['completed']),
                         (dec[unit]['moment_total'], mom[unit]),
                         (math.fsum(dec[unit]['class_released']), u['released']),
                         (math.fsum(dec[unit]['class_completed']), u['completed'])):
                rel = abs(a - b) / max(1.0, abs(b))
                worst['decomposition'] = max(worst['decomposition'], rel)
                if rel > 1e-9:
                    failures.append((s['time_s'], unit, 'decomposition', rel))
            ident = max(abs(u['requested'] - u['released'] - u['pending']),
                        abs(u['released'] - u['completed'] - u['active'])) / scale
            worst['identity'] = max(worst['identity'], ident)
            if ident > 1e-9:
                failures.append((s['time_s'], unit, 'ledger identity', ident))
            if min(u['released'], u['completed'], u['requested']) < 0:
                failures.append((s['time_s'], unit, 'negative', None))
            if previous is not None:
                p = previous['ledger'][unit]
                if u['released'] < p['released'] or u['completed'] < p['completed']:
                    failures.append((s['time_s'], unit, 'nonmonotone', None))
        rl = s['road_ledger']
        worst['road_mass'] = max(worst['road_mass'], rl['mass_residual_rel'])
        worst['road_residence'] = max(worst['road_residence'], rl['residence_residual_rel'])
        if rl['mass_residual_rel'] > 1e-9:
            failures.append((s['time_s'], 'road', 'mass', rl['mass_residual_rel']))
        if rl['residence_residual_rel'] > 1e-8:
            failures.append((s['time_s'], 'road', 'residence', rl['residence_residual_rel']))
        if previous is not None:
            ps = previous['service']
            if (s['service']['road_released_veh'] < ps['road_released_veh']
                    or s['service']['road_completed_veh'] < ps['road_completed_veh']):
                failures.append((s['time_s'], 'road', 'nonmonotone', None))
        previous = s
    return dict(passed=not failures, worst_relative=worst, failures=failures[:20],
                samples=len(run['samples']), tolerances=dict(mass=1e-9, residence=1e-8))


def cost(run, t):
    calls = [c for c in run['calls'] if c['end_s'] <= t]
    if not calls or calls[-1]['end_s'] != t:
        return None
    ticks = sum(c['ticks'] for c in calls)
    active = [c for c in calls if c['end_s'] > 25200.0]
    active_ticks = sum(c['ticks'] for c in active)
    phases = {}
    for c in calls:
        for k, v in c['phase_metrics']['phase_wall_s'].items():
            phases[k] = phases.get(k, 0.0) + v
    tick_times_active = [c['tick_p50_s'] for c in active if c['tick_p50_s'] is not None]
    return dict(
        C1_peak_records=max(c['peak_records'] for c in calls),
        C2_peak_rss_bytes=calls[-1]['peak_rss_bytes'],
        C3_cpu_s_per_tick=math.fsum(c['cpu_s'] for c in calls) / ticks,
        ticks=ticks,
        cpu_s=math.fsum(c['cpu_s'] for c in calls),
        wall_s_per_tick=math.fsum(c['wall_s'] for c in calls) / ticks,
        active_window_ticks=active_ticks,
        active_cpu_s_per_tick=(math.fsum(c['cpu_s'] for c in active) / active_ticks) if active_ticks else None,
        active_wall_s_per_tick=(math.fsum(c['wall_s'] for c in active) / active_ticks) if active_ticks else None,
        active_native_tick_s_per_tick=(math.fsum(c['tick_sum_s'] for c in active) / active_ticks) if active_ticks else None,
        active_call_tick_p50_median_s=sorted(tick_times_active)[len(tick_times_active) // 2] if tick_times_active else None,
        native_phase_wall_s=phases,
        construct_wall_s=run['construct_wall_s'],
    )


def gap_table(runs, t):
    out = {}
    for timing in ('legacy', 'interval'):
        a, b = runs[f'{timing}_dt10'], runs[f'{timing}_dt5']
        sa, sb = sample_at(a, t), sample_at(b, t)
        if sa is None or sb is None:
            return None
        (xa, va), (xb, vb) = accuracy(sa), accuracy(sb)
        gaps = {k: xa[k] - xb[k] for k in xa}
        gaps['A4_destination_completed_vehicles_L1'] = l1(va['dest'], vb['dest'])
        gaps['class_completed_vehicles_L1'] = l1(va['cls'], vb['cls'])
        rel = {k: (gaps[k] / xb[k] if k in xb and xb[k] else None) for k in gaps}
        out[timing] = dict(dt10=xa, dt5=xb, gap=gaps, relative_gap=rel)
    ratio = {}
    for k in out['legacy']['gap']:
        g0, g1 = out['legacy']['gap'][k], out['interval']['gap'][k]
        ratio[k] = abs(g1) / abs(g0) if g0 else None
    out['improvement_ratio_r'] = ratio
    return out


def series(runs):
    times = sorted({s['time_s'] for r in runs.values() for s in r['samples'] if s['time_s'] > 25200.0})
    rows = []
    for t in times:
        g = gap_table(runs, t)
        if g is None:
            continue
        rows.append(dict(time_s=t, **{f'{timing}_gap': {k: g[timing]['gap'][k] for k in (
            'A1_released_persons', 'A2_journey_completed_vehicles', 'A3_road_completed_vehicles',
            'A4_destination_completed_vehicles_L1', 'road_occupancy_vehicles')} for timing in ('legacy', 'interval')}))
    return rows


def prior_legacy_identity(runs):
    """Extra observation: legacy samples at 25,500 s versus the prior binary's runs."""
    out = {}
    for label, prior in (('legacy_dt10', 'valley_h1_dt10.json'), ('legacy_dt5', 'valley_h1_dt5.json')):
        path = PRIOR / prior
        if not path.exists() or runs.get(label) is None:
            out[label] = 'NOT_RUN'
            continue
        old = sample_at(json.loads(path.read_text()), PRIMARY_T)
        new = sample_at(runs[label], PRIMARY_T)
        if old is None or new is None:
            out[label] = 'NOT_RUN'
            continue
        keys = ('ledger', 'released_intent_first_moments', 'service', 'decomposition', 'road_records', 'journey_counts')
        out[label] = dict(bitwise_equal={k: old[k] == new[k] for k in keys},
                          prior_binary=json.loads(path.read_text())['native_binary']['sha256'])
    return out


def main():
    runs = {label: load(label) for label in LABELS}
    status = {label: (dict(status=r['status'], simulated_s=r['simulated_s'],
                           reason=r.get('reason'), release_timing=r['release_timing'],
                           step_s=r['step_s'], driver_identity=r['driver_identity'],
                           checkpoint=r['checkpoint']) if r else 'NOT_RUN') for label, r in runs.items()}
    if any(r is None for r in runs.values()):
        verdict = dict(decision='NOT_ADOPT', reasons=['G4: not all runs exist'])
        (HERE / 'COMPARISON.json').write_text(json.dumps(dict(runs=status, verdict=verdict), indent=1) + '\n')
        return
    reached = {label: max((s['time_s'] for s in r['samples']), default=0.0) for label, r in runs.items()}
    bit = json.loads((HERE / 'bitid/legacy_h1_25900.json').read_text())
    g1 = dict(observed=bit['checkpoint']['sha256'], expected=BITID_SHA,
              passed=bit['checkpoint']['sha256'] == BITID_SHA, status=bit['status'], simulated_s=bit['simulated_s'])
    gate = {label: conservation(r) for label, r in runs.items()}
    primary = gap_table(runs, PRIMARY_T) if all(reached[l] >= PRIMARY_T for l in LABELS) else None
    secondary = gap_table(runs, SECONDARY_T) if all(reached[l] >= SECONDARY_T for l in LABELS) else None
    costs = {label: {str(t): cost(r, t) for t in (PRIMARY_T, SECONDARY_T)} for label, r in runs.items()}
    ratios = {}
    for dt in ('dt10', 'dt5'):
        for t in (PRIMARY_T, SECONDARY_T):
            a, b = costs[f'legacy_{dt}'][str(t)], costs[f'interval_{dt}'][str(t)]
            if a is None or b is None:
                ratios[f'{dt}@{int(t)}'] = 'NOT_RUN'
                continue
            ratios[f'{dt}@{int(t)}'] = {k: b[k] / a[k] for k in ('C1_peak_records', 'C2_peak_rss_bytes', 'C3_cpu_s_per_tick',
                                                               'wall_s_per_tick', 'active_cpu_s_per_tick',
                                                               'active_wall_s_per_tick', 'active_native_tick_s_per_tick')
                                        if a.get(k) and b.get(k) is not None}
    reasons = []
    if not g1['passed']:
        reasons.append('G1 legacy bit identity failed')
    if not all(g['passed'] for g in gate.values()):
        reasons.append('G3 conservation gate failed')
    if primary is None:
        reasons.append('G4 not all runs reached 25,500 s')
    primary_keys = ('A1_released_persons', 'A2_journey_completed_vehicles', 'A3_road_completed_vehicles',
                    'A4_destination_completed_vehicles_L1')
    clause_a = clause_a2 = None
    if primary is not None:
        r = primary['improvement_ratio_r']
        clause_a = {k: (r[k] is not None and r[k] <= 0.9) for k in primary_keys}
        if not all(clause_a.values()):
            reasons.append('(a) accuracy at 25,500 s: ' + ', '.join(f'{k} r={r[k]:.4g}' for k in primary_keys if not clause_a[k]))
    if secondary is not None:
        r = secondary['improvement_ratio_r']
        clause_a2 = {k: (r[k] is not None and r[k] <= 1.0) for k in primary_keys}
        if not all(clause_a2.values()):
            reasons.append("(a') accuracy at 26,000 s: " + ', '.join(f'{k} r={r[k]:.4g}' for k in primary_keys if not clause_a2[k]))
    thresholds = dict(C1_peak_records=1.05, C2_peak_rss_bytes=1.05, C3_cpu_s_per_tick=1.10)
    clause_b = {}
    for key, value in ratios.items():
        if value == 'NOT_RUN':
            clause_b[key] = 'NOT_RUN'
            continue
        clause_b[key] = {k: value[k] <= thr for k, thr in thresholds.items()}
        bad = [f'{k}={value[k]:.4f}>{thr}' for k, thr in thresholds.items() if value[k] > thr]
        if bad:
            reasons.append(f'(b) cost {key}: ' + ', '.join(bad))
    verdict = dict(decision='ADOPT' if not reasons else 'NOT_ADOPT', reasons=reasons,
                   G1_bit_identity=g1, G3_conservation={k: v['passed'] for k, v in gate.items()},
                   G4_reached_s=reached, clause_a_25500=clause_a, clause_a_26000=clause_a2,
                   clause_b=clause_b, G2_regressions='see RECEIPT.json')
    out = dict(schema='metroflow.v1.release_timing.comparison/1', launch_sha_note='rule from LAUNCH.json (commit 4669f72)',
               runs=status, verdict=verdict, primary_25500=primary, secondary_26000=secondary,
               cost=costs, cost_ratio_policy_over_legacy=ratios, conservation=gate,
               gap_series_60s=series(runs), prior_legacy_observation=prior_legacy_identity(runs))
    (HERE / 'COMPARISON.json').write_text(json.dumps(out, indent=1) + '\n')
    print(json.dumps(verdict, indent=1))


if __name__ == '__main__':
    main()
