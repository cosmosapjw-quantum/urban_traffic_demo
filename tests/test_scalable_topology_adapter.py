from __future__ import annotations

import inspect


def test_scalable_topology_adapter_public_api_is_exact() -> None:
    import metroflow.city.scalable_topology_adapter as adapter
    from metroflow.city.scalable_blocks import ScalableBlockAuthority
    from metroflow.city.scalable_topology import ScalableStreetNetwork

    assert adapter.__all__ == (
        "ScalableCompiledTopology",
        "ScalableGroupCrosswalk",
        "ScalableNumericProfile",
        "ScalableRoadCrosswalk",
        "compile_scalable_topology",
        "require_valid_scalable_compiled_topology",
    )

    for name in adapter.__all__[:4]:
        value = getattr(adapter, name)
        assert inspect.isclass(value)
        assert value.__module__ == adapter.__name__

    compile_signature = inspect.signature(adapter.compile_scalable_topology)
    assert tuple(compile_signature.parameters) == ("network", "block_authority")
    assert compile_signature.parameters["network"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert compile_signature.parameters["block_authority"].kind is inspect.Parameter.KEYWORD_ONLY
    assert compile_signature.parameters["block_authority"].default is inspect.Parameter.empty
    assert inspect.get_annotations(
        adapter.compile_scalable_topology,
        eval_str=True,
    ) == {
        "network": ScalableStreetNetwork,
        "block_authority": ScalableBlockAuthority,
        "return": adapter.ScalableCompiledTopology,
    }

    validator_signature = inspect.signature(
        adapter.require_valid_scalable_compiled_topology
    )
    assert tuple(validator_signature.parameters) == (
        "compiled",
        "network",
        "block_authority",
    )
    assert validator_signature.parameters["compiled"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert validator_signature.parameters["network"].kind is inspect.Parameter.KEYWORD_ONLY
    assert validator_signature.parameters["block_authority"].kind is inspect.Parameter.KEYWORD_ONLY
    assert inspect.get_annotations(
        adapter.require_valid_scalable_compiled_topology,
        eval_str=True,
    ) == {
        "compiled": adapter.ScalableCompiledTopology,
        "network": ScalableStreetNetwork,
        "block_authority": ScalableBlockAuthority,
        "return": type(None),
    }
