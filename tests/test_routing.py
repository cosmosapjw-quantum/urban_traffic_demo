from metroflow.traffic.routing import path_size_factor, should_reroute, ReroutePolicy


def test_path_size_factor_positive():
    ps = path_size_factor((2.0, 3.0), (1, 2))
    assert ps > 0.0


def test_should_reroute_hard_event():
    pol = ReroutePolicy()
    assert should_reroute(True, 10.0, 10.0, 0, pol) is True


def test_should_reroute_refractory():
    pol = ReroutePolicy(eta_degradation_threshold=0.2, refractory_steps=5)
    assert should_reroute(False, 13.0, 10.0, 5, pol) is True
    assert should_reroute(False, 13.0, 10.0, 4, pol) is False
