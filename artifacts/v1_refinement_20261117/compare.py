"""Build COMPARISON.json from the per-run JSON of the fixed refinement design.

Differences are candidate minus reference at common sample times. No
acceptance thresholds are derived from these numbers; only the PLAN
numerical_policy tolerances (mass 1e-9, residence 1e-8 relative, floor 1)
are applied, and only to conservation identities.
"""
import json, math
from pathlib import Path

OUT = Path(__file__).resolve().parent
PLAN = json.loads((OUT.parents[1] / 'docs/v1/PLAN.json').read_text())['numerical_policy']
MASS_TOL, RES_TOL, FLOOR = PLAN['mass_relative_tolerance'], PLAN['residence_relative_tolerance'], PLAN['report_absolute_floor']
UNITS = ('persons', 'vehicles', 'cargo_kg')
LABELS = ['h0_dt10', 'h1_dt10', 'h0p5_dt10', 'h0p25_dt10', 'h1_dt5']
SERVICE = ('road_released_veh', 'road_completed_veh', 'bus_road_vehicles', 'completed_bus_vehicles',
           'waiting_persons', 'onboard_persons', 'arrived_persons', 'wait_person_s',
           'freight_completed_vehicles', 'cargo_delivered_kg', 'cargo_unfinished_kg')


def load(label):
    p = OUT / 'runs' / f'valley_{label}.json'
    return json.loads(p.read_text()) if p.exists() else None


def tol(x):
    return max(FLOOR, abs(x))


def scalars(s):
    """Flat scalar observables of one sample (units in key names / report)."""
    out = {}
    for u in UNITS:
        for k in ('requested', 'released', 'completed', 'pending', 'active'):
            out[f'ledger.{u}.{k}'] = s['ledger'][u][k]
        out[f'first_moment.{u}'] = s['released_intent_first_moments'][u]
    for k in SERVICE:
        out[f'service.{k}'] = s['service'][k]
    out['service.road_occupancy_veh'] = s['service']['road_released_veh'] - s['service']['road_completed_veh']
    out['records.road_total'] = s['road_records']['total_records']
    out['records.journey_total'] = s['journey_counts']['total_records']
    return out


def vectors(s):
    out = {}
    for u in UNITS:
        d = s['decomposition'][u]
        for k in ('class_released', 'class_completed', 'dest_released', 'dest_completed'):
            if k in d:
                out[f'{u}.{k}'] = d[k]
    return out


def conservation(run):
    rows, worst = [], {}
    def note(name, resid, scale, kind):
        rel = abs(resid) / tol(scale)
        lim = MASS_TOL if kind == 'mass' else RES_TOL
        w = worst.setdefault(name, dict(max_relative=0.0, tolerance=lim, kind=kind))
        w['max_relative'] = max(w['max_relative'], rel)
    prev = None
    for s in run['samples']:
        L = s['ledger']
        for u in UNITS:
            r = L[u]
            note(f'{u}: requested-released-pending', r['requested'] - r['released'] - r['pending'], r['requested'], 'mass')
            note(f'{u}: released-completed-active', r['released'] - r['completed'] - r['active'], r['requested'], 'mass')
            note(f'{u}: negative part of active/pending/completed', min(0.0, r['active'], r['pending'], r['completed']), r['requested'], 'mass')
            d = s['decomposition'][u]
            note(f'{u}: sum over classes - report released', math.fsum(d['class_released']) - r['released'], r['requested'], 'mass')
            note(f'{u}: sum over classes - report completed', math.fsum(d['class_completed']) - r['completed'], r['requested'], 'mass')
            if 'dest_completed' in d:
                note(f'{u}: sum over destinations - report completed', math.fsum(d['dest_completed']) - r['completed'], r['requested'], 'mass')
                note(f'{u}: sum over destinations - report released', math.fsum(d['dest_released']) - r['released'], r['requested'], 'mass')
            note(f'{u}: decomposed first moment - report', d['moment_total'] - s['released_intent_first_moments'][u],
                 s['released_intent_first_moments'][u], 'mass')
            if prev is not None:
                note(f'{u}: decrease of completed in time', min(0.0, r['completed'] - prev['ledger'][u]['completed']), r['requested'], 'mass')
                note(f'{u}: decrease of released in time', min(0.0, r['released'] - prev['ledger'][u]['released']), r['requested'], 'mass')
        sv = s['service']
        note('road: negative occupancy (released-completed)', min(0.0, sv['road_released_veh'] - sv['road_completed_veh']), sv['road_released_veh'], 'mass')
        assigned_cargo = s['assignment_units']['cargo_kg']['assigned']
        note('cargo: delivered+unfinished - assigned', sv['cargo_delivered_kg'] + sv['cargo_unfinished_kg'] - assigned_cargo, assigned_cargo, 'mass')
        prev = s
    for w in worst.values():
        w['pass'] = w['max_relative'] <= w['tolerance']
    return worst


def diff(cand, ref):
    times = sorted(set(s['time_s'] for s in cand['samples']) & set(s['time_s'] for s in ref['samples']))
    cs = {s['time_s']: s for s in cand['samples']}; rs = {s['time_s']: s for s in ref['samples']}
    out = dict(common_times_s=times, scalars={}, vectors={})
    if not times:
        return out
    for k in scalars(rs[times[0]]):
        series = [scalars(cs[t])[k] - scalars(rs[t])[k] for t in times]
        rv = [scalars(rs[t])[k] for t in times]
        i = max(range(len(times)), key=lambda j: abs(series[j]))
        out['scalars'][k] = dict(endpoint_reference=rv[-1], endpoint_difference=series[-1],
            endpoint_relative=series[-1] / tol(rv[-1]), max_abs_difference=abs(series[i]), at_time_s=times[i],
            curve_difference=series)
    for k in vectors(rs[times[0]]):
        l1, mx, ends = [], [], None
        for t in times:
            a, b = vectors(cs[t])[k], vectors(rs[t])[k]
            d = [x - y for x, y in zip(a, b)]
            l1.append(math.fsum(abs(x) for x in d)); mx.append(max(abs(x) for x in d))
            ends = (d, b)
        d, b = ends
        top = sorted(range(len(d)), key=lambda j: -abs(d[j]))[:5]
        out['vectors'][k] = dict(endpoint_l1=l1[-1], endpoint_max_abs=mx[-1], endpoint_reference_l1=math.fsum(abs(x) for x in b),
            max_l1_over_time=max(l1), curve_l1=l1, endpoint_top_components=[dict(index=j, difference=d[j], reference=b[j]) for j in top if d[j] != 0.0])
    return out


def resources(run):
    calls = run['calls']
    ticks = sum(c['ticks'] for c in calls)
    return dict(status=run['status'], simulated_s=run['simulated_s'], wall_s=run['wall_s'], advance_wall_s=run['advance_wall_s'],
        construct_wall_s=run['construct_wall_s'], peak_rss_bytes=run['peak_rss_bytes'], peak_tracked_records=run['peak_records'],
        ticks=ticks, mean_tick_s=math.fsum(c['tick_sum_s'] for c in calls) / ticks if ticks else None,
        max_tick_s=max(c['tick_max_s'] or 0 for c in calls), alloc_counting=run.get('alloc_counting'),
        sample_overhead_wall_s=math.fsum(s['sample_wall_s'] for s in run['samples']),
        reason=run.get('reason'), resource_limit_kind=run.get('resource_limit_kind'),
        endpoint_projection=run['samples'][-1]['projection'] if run['samples'] else None,
        endpoint_event_resolution=run['samples'][-1]['event_resolution'] if run['samples'] else None)


def order(e_fine, e_mid, e_coarse):
    """Observed ratio/order for differences at h, 2h, 4h vs the h=0 reference."""
    out = dict(e_0p25=e_fine, e_0p5=e_mid, e_1=e_coarse)
    for a, b, name in ((e_mid, e_fine, 'ratio_0p5_over_0p25'), (e_coarse, e_mid, 'ratio_1_over_0p5')):
        out[name] = a / b if b != 0 else None
        out['order_' + name[6:]] = math.log2(abs(a / b)) if b != 0 and a != 0 else None
    return out


runs = {l: load(l) for l in LABELS}
cmp = dict(scope='Valley valley_weekday_s7 full calendar, common prefix 0..25500 s, 1 thread, bounded_bytes_v1; diagnostic, not acceptance',
           plan_numerical_policy=PLAN, design=dict(A='dt=10 s, h in {0,1,0.5,0.25} s, reference h=0', B='h=1 s, dt in {10,5} s, reference dt=5'),
           runs={l: (resources(r) if r else dict(status='NOT_RUN')) for l, r in runs.items()},
           conservation={l: conservation(r) for l, r in runs.items() if r},
           A={}, B={}, h_trend={})
for l in ('h1_dt10', 'h0p5_dt10', 'h0p25_dt10'):
    if runs[l] and runs['h0_dt10']:
        cmp['A'][l + '_minus_h0_dt10'] = diff(runs[l], runs['h0_dt10'])
if runs['h1_dt10'] and runs['h1_dt5']:
    cmp['B']['h1_dt10_minus_h1_dt5'] = diff(runs['h1_dt10'], runs['h1_dt5'])
if all(k + '_minus_h0_dt10' in cmp['A'] for k in ('h1_dt10', 'h0p5_dt10', 'h0p25_dt10')):
    A = cmp['A']
    for k in A['h1_dt10_minus_h0_dt10']['scalars']:
        if k.startswith('records.'):
            continue
        e = [A[f'{h}_minus_h0_dt10']['scalars'][k]['endpoint_difference'] for h in ('h0p25_dt10', 'h0p5_dt10', 'h1_dt10')]
        if any(x != 0.0 for x in e):
            cmp['h_trend'][k] = order(*e)
    for k in A['h1_dt10_minus_h0_dt10']['vectors']:
        e = [A[f'{h}_minus_h0_dt10']['vectors'][k]['endpoint_l1'] for h in ('h0p25_dt10', 'h0p5_dt10', 'h1_dt10')]
        if any(x != 0.0 for x in e):
            cmp['h_trend'][k + '.l1'] = order(*e)
(OUT / 'COMPARISON.json').write_text(json.dumps(cmp, indent=1))
print('written')
