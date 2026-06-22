import rh_wizard


def test_package_exposes_version():
    assert rh_wizard.__version__ == "0.1.0"
