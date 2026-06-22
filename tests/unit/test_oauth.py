from rh_wizard.auth.oauth import build_client_metadata
from rh_wizard.config.settings import Settings


def test_metadata_has_required_oauth21_fields():
    md = build_client_metadata(Settings(), "http://localhost:3030/callback")
    assert md["client_name"] == "Robinhood Wizard"
    assert md["redirect_uris"] == ["http://localhost:3030/callback"]
    assert set(md["grant_types"]) == {"authorization_code", "refresh_token"}
    assert md["response_types"] == ["code"]


def test_metadata_uses_configured_client_name():
    s = Settings(oauth_client_name="My Agent")
    md = build_client_metadata(s, "http://localhost:3030/callback")
    assert md["client_name"] == "My Agent"
