# backend/app/kalshi/auth.py
import base64
import time
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class KalshiAuth:
    def __init__(self, key_id: str, private_key_path: str) -> None:
        self.key_id = key_id
        pem_bytes = Path(private_key_path).read_bytes()
        key = serialization.load_pem_private_key(pem_bytes, password=None)
        if not isinstance(key, rsa.RSAPrivateKey):
            raise ValueError(f"Expected RSA private key, got {type(key)}")
        self.private_key = key

    def get_headers(self, method: str, path: str) -> dict[str, str]:
        timestamp_ms = str(int(time.time() * 1000))
        message = (timestamp_ms + method + path).encode("utf-8")
        signature = self.private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.key_id,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(signature).decode("utf-8"),
            "KALSHI-ACCESS-TIMESTAMP": timestamp_ms,
            "Content-Type": "application/json",
        }
