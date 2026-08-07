import sys

def test_identity():
    from tests import conftest as tc
    import conftest as pc
    print("SAME:", tc is pc)
    print("tc file:", tc.__file__, "name:", tc.__name__)
    print("pc file:", pc.__file__, "name:", pc.__name__)
    print("tc applied:", tc._APPLIED_BY_US)
    print("pc applied:", pc._APPLIED_BY_US)
    print("subset holds:", tc._APPLIED_BY_US <= set(tc._DEFAULTS))
