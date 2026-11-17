"""Synthetic check of the release-lag coefficient (journey owner only).

One top-level road leg, uniform births on [0, 1000] s, fractional access delay
atoms. With an uncongested road every offer made in step [t, t+dt) is admitted
at t+dt (legacy and policy share this end-of-step source admission). The mean
lag between each individual's ready time (birth + delay) and its admission is

    legacy: (sum_offers m*(t+dt) - sum_offers (birth moment + m*delay)) / mass
    policy: the same with the policy's offers.

Prediction (LAUNCH.json): legacy 1.5*dt, policy 0.5*dt for delays whose
fractional parts are spread over the step. Writes LAG_ORDER.json.
"""
import json
import math
from pathlib import Path

from _metroflow_rust import NativeJourneyCore

DELAYS = ((37.3, .2), (81.9, .25), (123.4, .15), (160.2, .3), (211.7, .1))
HORIZON = 1500.0


def run(step, timing):
    legs = [(f"atom{k}", 1.0, None, 0., [(0., 1000., 1.)], 1, [(d, 1.)], [(0., 1.)])
            for k, (d, _) in enumerate(DELAYS)]
    core = NativeJourneyCore(legs, [], [], 10**7, release_timing=timing)
    admitted = [[0.0, 0.0, 0.0] for _ in DELAYS]  # mass, admission moment, ready moment
    early = 0.0
    t = 0.0
    while t < HORIZON - 1e-9:
        if timing == 'legacy':
            offers, _ = core.prepare()
        else:
            offers, _, _ = core.prepare_interval(step)
        end = t + step
        for tag, mass, birth in offers:
            k = int(tag[4:])
            d = DELAYS[k][0]
            admitted[k][0] += mass
            admitted[k][1] += mass * end
            admitted[k][2] += birth + mass * d
        core.finish(end, [], [], [], [], [], [], [])
        # Causality: admitted mass by `end` never exceeds the mass ready by `end`.
        for k, (d, _) in enumerate(DELAYS):
            ready = min(1., max(0., (end - d) / 1000.))
            early = max(early, admitted[k][0] - ready)
        t = end
    lag = math.fsum(w * (a[1] - a[2]) / a[0] for (_, w), a in zip(DELAYS, admitted))
    return dict(mean_lag_s=lag, lag_over_dt=lag / step, max_admitted_before_ready=early,
                admitted_fraction=[a[0] for a in admitted])


def main():
    rows = []
    for step in (20., 10., 5., 2.5):
        rows.append(dict(step_s=step, legacy=run(step, 'legacy'), release_interval_v1=run(step, 'release_interval_v1')))
    out = dict(scope='journey-owner synthetic check; uncongested end-of-step admission assumed; not a city result',
               delays=DELAYS, rows=rows)
    Path(__file__).with_name('LAG_ORDER.json').write_text(json.dumps(out, indent=1) + '\n')
    for r in rows:
        print(r['step_s'], round(r['legacy']['lag_over_dt'], 4), round(r['release_interval_v1']['lag_over_dt'], 4),
              r['legacy']['max_admitted_before_ready'], r['release_interval_v1']['max_admitted_before_ready'])


if __name__ == '__main__':
    main()
