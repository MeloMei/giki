def test_version_exposed():
    import giki
    assert isinstance(giki.__version__, str)
    assert giki.__version__.count(".") == 2
