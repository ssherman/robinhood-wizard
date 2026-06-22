from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DISCLAIMER = (
    "DISCLAIMER: Not financial advice. No warranty. Use at your own risk. "
    "The authors are not liable for any financial loss."
)


def test_mit_license_present():
    text = (ROOT / "LICENSE").read_text()
    assert "MIT License" in text
    assert "Permission is hereby granted, free of charge" in text


def test_readme_has_disclaimer():
    assert DISCLAIMER in (ROOT / "README.md").read_text()


def test_example_files_have_no_real_secrets():
    import re

    for name in (".env.example", "config.example.yaml"):
        text = (ROOT / name).read_text()
        # Placeholders only: no bearer tokens, and no real-looking value (16+ chars)
        # assigned to a secret field. The public MCP URL is fine to include.
        assert "Bearer " not in text
        assert not re.search(
            r"(access_token|refresh_token|api_key|client_secret)\s*[:=]\s*[\"']?[A-Za-z0-9]{16,}",
            text,
            re.IGNORECASE,
        )


def test_security_and_contributing_present():
    assert (ROOT / "SECURITY.md").exists()
    assert (ROOT / "CONTRIBUTING.md").exists()
