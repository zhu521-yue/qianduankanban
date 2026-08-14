from app.security import hash_password, token_digest, verify_password


def test_password_hash_roundtrip() -> None:
    encoded = hash_password("Daren@2026", salt=b"0123456789abcdef")
    assert verify_password("Daren@2026", encoded)
    assert not verify_password("wrong", encoded)
    assert "Daren@2026" not in encoded


def test_token_digest_is_stable_and_not_plaintext() -> None:
    assert token_digest("session-token") == token_digest("session-token")
    assert token_digest("session-token") != "session-token"

