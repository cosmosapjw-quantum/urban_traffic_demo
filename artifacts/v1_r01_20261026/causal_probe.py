"""Reproduce R01 observable channels and T04 same-cost measurement."""
import json
import math
from metroflow.v1 import (
    CostKey, CostObservation, PriorCost, Channel, Report, InformationModel,
    completed_route_observations,
)
from metroflow.v1.timing_oracles import timing_fixture

k = CostKey('route', 'trip', 'car')
o = CostObservation(k, 90, 10, 0, 10, 1, (1000., 0.), 'sensor', 'probe', 'sample')
p = PriorCost(k, 21, 'static', o.measure)
m = InformationModel((p,), (Channel('server', 'server', (k,), float('inf'), 2, 100, 100),))
s = m.advance(m.initial(), 21.999, (Report('server', o),))
before = m.observe(s, (0, 0)).costs[0]
after = m.observe(m.advance(s, 22), (0, 0)).costs[0]
physical = timing_fixture(.1, window=0)
state = physical.advance(physical.initial(), 30)
obs, = completed_route_observations(physical, state, since_s=0,
                                   sensor_xy={'trip': (0., 0.)}, version='T04')
actual = physical.report(state)['whole_population_mean_s']
assert before.seconds == 21 and after.seconds == 90 and math.isclose(obs.seconds, actual, rel_tol=1e-12)
print(json.dumps(dict(status='PASS', server_before_delivery_s=before.seconds,
                      server_at_delivery_s=after.seconds, delivered_at_s=after.delivered_s,
                      observed_completed_mean_s=obs.seconds, physical_mean_s=actual,
                      cost_extra_queue_or_signal_s=obs.seconds-actual), indent=2))
