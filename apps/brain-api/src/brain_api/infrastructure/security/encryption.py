"""Encryption helpers for team-scoped secrets."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class SecretCipher:
    def __init__(self, key: str) -> None:
        if not key:
            raise ValueError("Encryption key is required")
        material = key.encode("utf-8")
        if len(material) == 44:
            fernet_key = material
        else:
            fernet_key = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
        self._fernet = Fernet(fernet_key)

    def encrypt_text(self, value: str) -> bytes:
        return self._fernet.encrypt(value.encode("utf-8"))

    def decrypt_text(self, value: bytes | None) -> str | None:
        if value is None:
            return None
        try:
            return self._fernet.decrypt(value).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Encrypted value cannot be decrypted") from exc
