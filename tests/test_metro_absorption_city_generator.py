from importlib import import_module


def test_generator_v2_contract_modules_import_without_visual_dependencies():
    required_modules = (
        "metroflow.city.generator_v2",
        "metroflow.city.contracts",
        "metroflow.city.realism_contracts",
        "metroflow.city.seed_manifest",
        "metroflow.city.envelope_corpus",
        "metroflow.city.gate_reporting",
    )

    for module_name in required_modules:
        assert import_module(module_name) is not None


def test_generator_v2_preview_topology_is_deterministic_and_2d():
    generator_v2 = import_module("metroflow.city.generator_v2")

    generator = generator_v2.GeneratorV2()
    topology_a = generator.generate_preview_topology(
        {
            "scenario_id": "synthetic_100k",
            "seed": 42,
            "style_id": "ring_radial",
        }
    )
    topology_b = generator.generate_preview_topology(
        {
            "scenario_id": "synthetic_100k",
            "seed": 42,
            "style_id": "ring_radial",
        }
    )

    assert topology_a.nodes == topology_b.nodes
    assert topology_a.links == topology_b.links
    assert len(topology_a.nodes) >= 100
    assert len(topology_a.links) >= 300
    assert topology_a.metadata["engine"] == "generator_v2"
    assert topology_a.metadata["active_call_path"] == "generator_v2.preview_topology"

    xs = [float(node.x) for node in topology_a.nodes]
    ys = [float(node.y) for node in topology_a.nodes]
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    assert width > 0.0
    assert height > 0.0
    assert (width / max(height, 1e-6)) <= 2.25


def test_city_gate_reporting_preserves_threshold_and_version_contract():
    gate_reporting = import_module("metroflow.city.gate_reporting")

    report = gate_reporting.serialize_ci_report(
        {
            "metrics": {"hard_fail_rate": 0.01, "ring_radial_connectivity_pass_rate": 0.97},
            "thresholds": {
                "hard_fail_rate_max": 0.02,
                "ring_radial_connectivity_min": 0.95,
                "incident_seed_pass_rate_min": 0.95,
            },
            "versions": {
                "oracle_version": "v1",
                "corpus_version": "v1",
                "budget_version": "v1",
                "generator_version": "v2",
            },
        }
    )

    assert report["thresholds"]["hard_fail_rate_max"] == 0.02
    assert report["versions"]["generator_version"] == "v2"
