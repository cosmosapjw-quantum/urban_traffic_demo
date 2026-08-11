from __future__ import annotations


def test_scalable_blocks_module_import_exists() -> None:
    import metroflow.city as city

    assert city.__name__ == "metroflow.city"

    import metroflow.city.scalable_blocks as blocks

    assert blocks.__name__ == "metroflow.city.scalable_blocks"
