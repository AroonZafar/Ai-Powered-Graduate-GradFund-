import jwt
import pytest

from app.security import InvalidToken, decode_token, hash_password, issue_token, verify_password

SECRET = "s" * 40


def test_hash_verifies_and_rejects_wrong_password():
    h = hash_password("a-long-passphrase")
    assert verify_password("a-long-passphrase", h)
    assert not verify_password("a-long-passphrasf", h)


def test_hashes_are_salted_and_never_plaintext():
    a, b = hash_password("same-password-1"), hash_password("same-password-1")
    assert a != b
    assert "same-password-1" not in a


@pytest.mark.parametrize("stored", ["", "garbage", "bcrypt$1$2$3$4$5", "scrypt$x$y$z$!!$!!"])
def test_malformed_stored_hash_is_rejected_not_raised(stored):
    assert verify_password("whatever-pass", stored) is False


def test_token_round_trip():
    assert decode_token(issue_token("user-1", SECRET, 60), SECRET) == "user-1"


def test_expired_token_rejected():
    token = issue_token("user-1", SECRET, 60, now=1_000_000)
    with pytest.raises(InvalidToken):
        decode_token(token, SECRET)


def test_wrong_secret_rejected():
    with pytest.raises(InvalidToken):
        decode_token(issue_token("user-1", SECRET, 60), "t" * 40)


def test_unsigned_alg_none_token_rejected():
    forged = jwt.encode({"sub": "user-1", "iss": "gradfund", "iat": 1, "exp": 9_999_999_999}, key=None, algorithm="none")
    with pytest.raises(InvalidToken):
        decode_token(forged, SECRET)


def test_wrong_issuer_rejected():
    token = jwt.encode({"sub": "u", "iss": "someone-else", "iat": 1, "exp": 9_999_999_999}, SECRET, algorithm="HS256")
    with pytest.raises(InvalidToken):
        decode_token(token, SECRET)


def test_tampered_token_rejected():
    token = issue_token("user-1", SECRET, 60)
    with pytest.raises(InvalidToken):
        decode_token(token[:-2] + ("AA" if not token.endswith("AA") else "BB"), SECRET)
