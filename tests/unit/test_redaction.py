import logging

from rh_wizard.logging.redaction import RedactingFilter, install_redaction, redact


def test_redacts_bearer_token():
    out = redact("Authorization: Bearer abc123.def456.ghi789")
    assert "abc123" not in out
    assert "[REDACTED]" in out


def test_redacts_token_fields():
    out = redact('{"refresh_token": "super-secret-value-1234567890"}')
    assert "super-secret-value-1234567890" not in out
    assert "[REDACTED]" in out


def test_redacts_long_digit_runs():
    out = redact("account 1234567890123 balance")
    assert "1234567890123" not in out


def test_keeps_ordinary_text():
    assert redact("bought 3 shares of AAPL") == "bought 3 shares of AAPL"


def test_filter_scrubs_log_record(caplog):
    logger = logging.getLogger("rh_wizard.test")
    logger.addFilter(RedactingFilter())
    with caplog.at_level(logging.INFO, logger="rh_wizard.test"):
        logger.info("token Bearer abcdef12345 done")
    assert "abcdef12345" not in caplog.text


def test_install_redaction_is_idempotent():
    logger = logging.getLogger("rh_wizard.test.install")
    install_redaction(logger)
    install_redaction(logger)
    assert sum(isinstance(f, RedactingFilter) for f in logger.filters) == 1
