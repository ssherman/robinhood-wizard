import threading
import urllib.request

from rh_wizard.auth.callback import OAuthCallbackServer


def test_redirect_uri_format():
    srv = OAuthCallbackServer("localhost", 3030)
    assert srv.redirect_uri == "http://localhost:3030/callback"


def test_captures_code_and_state():
    srv = OAuthCallbackServer("localhost", 0)  # port 0 -> OS-assigned
    result_box = {}

    def run():
        result_box["r"] = srv.wait_for_code(timeout=5)

    t = threading.Thread(target=run)
    t.start()
    # the server binds before wait returns; poll the resolved port
    port = srv.wait_until_listening(timeout=5)
    urllib.request.urlopen(
        f"http://localhost:{port}/callback?code=THECODE&state=xyz", timeout=5
    ).read()
    t.join(timeout=5)

    assert result_box["r"].code == "THECODE"
    assert result_box["r"].state == "xyz"


def test_captures_error():
    srv = OAuthCallbackServer("localhost", 0)
    result_box = {}

    def run():
        result_box["r"] = srv.wait_for_code(timeout=5)

    t = threading.Thread(target=run)
    t.start()
    port = srv.wait_until_listening(timeout=5)
    urllib.request.urlopen(
        f"http://localhost:{port}/callback?error=access_denied", timeout=5
    ).read()
    t.join(timeout=5)

    assert result_box["r"].error == "access_denied"
    assert result_box["r"].code is None
