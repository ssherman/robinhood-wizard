"""Persist OAuth tokens to disk with strict permissions.

``TokenFile`` is the storage core (fully unit-tested). ``DiskTokenStorage`` adapts it
to the ``mcp`` SDK's ``TokenStorage`` protocol so ``OAuthClientProvider`` can persist and
refresh tokens across headless runs. The exact protocol surface (method names, sync vs
async) is confirmed against the installed ``mcp`` version in Task 9 — keep the adapter
thin so only it changes if the protocol differs.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


class TokenFile:
    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> dict | None:
        if not self._path.exists():
            return None
        return json.loads(self._path.read_text())

    def save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self._path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(data, fh)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self._path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


class DiskTokenStorage:
    """Adapter to the mcp SDK TokenStorage protocol (verified live in Task 9).

    Stores the OAuth token bundle and dynamic-client-registration info as two keys in a
    single JSON file. Serialization uses the pydantic models' ``model_dump``/
    ``model_validate`` so we never hand-roll the schemas.
    """

    def __init__(self, path: Path) -> None:
        self._file = TokenFile(path)

    def _read(self) -> dict:
        return self._file.load() or {}

    async def get_tokens(self):  # -> OAuthToken | None
        from mcp.shared.auth import OAuthToken

        blob = self._read().get("tokens")
        return OAuthToken.model_validate(blob) if blob else None

    async def set_tokens(self, tokens) -> None:
        data = self._read()
        data["tokens"] = tokens.model_dump(mode="json")
        self._file.save(data)

    async def get_client_info(self):  # -> OAuthClientInformationFull | None
        from mcp.shared.auth import OAuthClientInformationFull

        blob = self._read().get("client_info")
        return OAuthClientInformationFull.model_validate(blob) if blob else None

    async def set_client_info(self, client_info) -> None:
        data = self._read()
        data["client_info"] = client_info.model_dump(mode="json")
        self._file.save(data)
