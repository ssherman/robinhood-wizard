import logging

from rh_wizard.logging.mcp_noise import silence_session_termination_warning

LOGGER_NAME = "mcp.client.streamable_http"


def test_drops_session_termination_warning(caplog):
    silence_session_termination_warning()
    logger = logging.getLogger(LOGGER_NAME)
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        logger.warning("Session termination failed: 400")
    assert "Session termination failed" not in caplog.text


def test_keeps_other_warnings(caplog):
    silence_session_termination_warning()
    logger = logging.getLogger(LOGGER_NAME)
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        logger.warning("A real problem happened")
    assert "A real problem happened" in caplog.text


def test_is_idempotent():
    silence_session_termination_warning()
    silence_session_termination_warning()
    logger = logging.getLogger(LOGGER_NAME)
    from rh_wizard.logging.mcp_noise import _SessionTerminationFilter

    assert sum(isinstance(f, _SessionTerminationFilter) for f in logger.filters) == 1
