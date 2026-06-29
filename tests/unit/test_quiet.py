import logging

import pytest

from rh_wizard.logging.quiet import _NOISY, quiet_dependency_logs


@pytest.fixture(autouse=True)
def _restore_levels():
    saved = {name: logging.getLogger(name).level for name in _NOISY}
    yield
    for name, level in saved.items():
        logging.getLogger(name).setLevel(level)


def test_clamps_noisy_libraries_to_warning():
    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.INFO)
    quiet_dependency_logs()
    for name in _NOISY:
        assert logging.getLogger(name).level == logging.WARNING


def test_leaves_unrelated_loggers_untouched():
    other = logging.getLogger("rh_wizard.somewhere")
    other.setLevel(logging.INFO)
    quiet_dependency_logs()
    assert other.level == logging.INFO
    other.setLevel(logging.NOTSET)


def test_accepts_a_custom_level():
    quiet_dependency_logs(logging.ERROR)
    for name in _NOISY:
        assert logging.getLogger(name).level == logging.ERROR
