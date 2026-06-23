import logging

import pytest

from rh_wizard.logging.mcp_noise import (
    _LOGGER_NAME,
    _SessionTerminationFilter,
    silence_session_termination_warning,
)


def test_drops_session_termination_warning(caplog):
    silence_session_termination_warning()
    logger = logging.getLogger(_LOGGER_NAME)
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        logger.warning("Session termination failed: 400")
    assert "Session termination failed" not in caplog.text


def test_keeps_other_warnings(caplog):
    silence_session_termination_warning()
    logger = logging.getLogger(_LOGGER_NAME)
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        logger.warning("A real problem happened")
    assert "A real problem happened" in caplog.text


@pytest.fixture(autouse=True)
def _cleanup_session_termination_filter():
    yield
    logger = logging.getLogger(_LOGGER_NAME)
    logger.filters = [f for f in logger.filters if not isinstance(f, _SessionTerminationFilter)]


def test_is_idempotent():
    silence_session_termination_warning()
    silence_session_termination_warning()
    logger = logging.getLogger(_LOGGER_NAME)

    assert sum(isinstance(f, _SessionTerminationFilter) for f in logger.filters) == 1
