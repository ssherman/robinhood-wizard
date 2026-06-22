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


def test_filter_scrubs_tuple_args(caplog):
    logger = logging.getLogger("rh_wizard.test.tuple_args")
    logger.addFilter(RedactingFilter())
    with caplog.at_level(logging.INFO, logger="rh_wizard.test.tuple_args"):
        logger.info("header: %s done", "Bearer abcdef1234567890")
    assert "abcdef1234567890" not in caplog.text
    # Verify the record formats without error
    msg = caplog.records[-1].getMessage()
    assert "[REDACTED]" in msg


def test_filter_scrubs_dict_args(caplog):
    logger = logging.getLogger("rh_wizard.test.dict_args")
    logger.addFilter(RedactingFilter())
    with caplog.at_level(logging.INFO, logger="rh_wizard.test.dict_args"):
        logger.info("token %(tok)s", {"tok": "Bearer abcdef1234567890"})
    assert "abcdef1234567890" not in caplog.text
    # This call would raise TypeError if dict args were iterated as keys
    msg = caplog.records[-1].getMessage()
    assert "[REDACTED]" in msg


def test_redacts_base64_bearer():
    out = redact("Authorization: Bearer ab+cd/ef==gh12")
    assert "ab+cd/ef==gh12" not in out
    assert "[REDACTED]" in out
