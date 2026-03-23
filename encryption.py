"""
AES-256-GCM encryption for user personal data.
Each field is independently encrypted with a random nonce.
"""
import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class EncryptionService:
    def __init__(self, key_b64: str):
        raw = base64.b64decode(key_b64)
        if len(raw) != 32:
            raise ValueError("Encryption key must be 32 bytes (base64-encoded)")
        self._aesgcm = AESGCM(raw)

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(12)
        ct = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ct).decode("utf-8")

    def decrypt(self, data) -> str:
        if isinstance(data, str):
            raw = base64.b64decode(data.encode("utf-8"))
        else:
            raw = data
        nonce, ct = raw[:12], raw[12:]
        return self._aesgcm.decrypt(nonce, ct, None).decode("utf-8")
