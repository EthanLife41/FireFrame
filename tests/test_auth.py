"""Session-cookie signing: valid round-trips, tampered/forged/expired rejected."""
from itsdangerous import URLSafeTimedSerializer

from backend.auth import create_session_token, verify_session_token


def test_valid_token_round_trips():
    token = create_session_token(True)
    assert verify_session_token(token) is True


def test_garbage_token_is_rejected():
    assert verify_session_token("not-a-real-token") is False
    assert verify_session_token("") is False


def test_tampered_token_is_rejected():
    token = create_session_token(True)
    head, sep, sig = token.rpartition(".")
    # Corrupt the middle of the signature, not the final char: only that last
    # base64url char carries unused trailing bits, so a flip there can decode to
    # the same bytes and verify anyway. Middle chars map to whole bytes, so the
    # decoded signature always changes and can't collide back to the original.
    i = len(sig) // 2
    corrupted = "".join("A" if c != "A" else "B" for c in sig[i:i + 3])
    tampered = head + sep + sig[:i] + corrupted + sig[i + 3:]
    assert tampered != token
    assert verify_session_token(tampered) is False


def test_token_signed_with_a_different_secret_is_rejected():
    forged = URLSafeTimedSerializer("a-different-secret").dumps({"auth": True})
    assert verify_session_token(forged) is False


def test_unauthenticated_payload_is_rejected():
    from backend.auth import serializer

    # signed, but auth=False must not grant access
    not_authed = serializer.dumps({"auth": False})
    assert verify_session_token(not_authed) is False


def test_loads_honors_max_age():
    from itsdangerous import SignatureExpired

    from backend.auth import serializer

    token = serializer.dumps({"auth": True})
    try:
        serializer.loads(token, max_age=-1)   # -1 forces immediate expiry
        raised = False
    except SignatureExpired:
        raised = True
    assert raised
