# backend/tests/test_kalshi_auth.py
import time
from unittest.mock import patch
from app.kalshi.auth import KalshiAuth


def test_get_headers_contains_required_keys(tmp_path):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "test_key.pem"
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    auth = KalshiAuth(key_id="test_key_id", private_key_path=str(key_path))
    headers = auth.get_headers("GET", "/trade-api/v2/events")

    assert "KALSHI-ACCESS-KEY" in headers
    assert headers["KALSHI-ACCESS-KEY"] == "test_key_id"
    assert "KALSHI-ACCESS-SIGNATURE" in headers
    assert "KALSHI-ACCESS-TIMESTAMP" in headers
    assert "Content-Type" in headers


def test_different_requests_produce_different_signatures(tmp_path):
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_path = tmp_path / "test_key.pem"
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    auth = KalshiAuth(key_id="test_key_id", private_key_path=str(key_path))
    headers1 = auth.get_headers("GET", "/trade-api/v2/events")
    headers2 = auth.get_headers("POST", "/trade-api/v2/orders")

    assert headers1["KALSHI-ACCESS-SIGNATURE"] != headers2["KALSHI-ACCESS-SIGNATURE"]
