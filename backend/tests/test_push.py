"""Web Push: message encryption (RFC 8291), VAPID (RFC 8292), subscriptions, and the connect.py triggers
that fire it. No network -- push.send's actual POST is mocked wherever it matters; the encryption itself is
checked by independently decrypting our own output the way a real browser would."""
import base64
import hashlib
import hmac
import json
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric import utils as ec_utils
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDFExpand

from app.partners import db
from app.social import push
from tests.test_partners import fresh_limits  # noqa: F401
from tests.test_people import two_people


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


_FAKE_PRIV = ec.generate_private_key(ec.SECP256R1())
FAKE_PRIV_B64 = b64u(_FAKE_PRIV.private_numbers().private_value.to_bytes(32, "big"))
FAKE_PUB_B64 = b64u(_FAKE_PRIV.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint))
FAKE_VAPID = (FAKE_PUB_B64, FAKE_PRIV_B64, "mailto:test@example.com")


def make_subscription():
    """A fake browser subscription: its own EC keypair (p256dh) and a random auth secret -- exactly what a
    real PushSubscription carries, and all push._encrypt needs to address a message to it."""
    ua_private = ec.generate_private_key(ec.SECP256R1())
    ua_public_raw = ua_private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return ua_private, b64u(ua_public_raw), b64u(os.urandom(16))


def decrypt(body: bytes, ua_private, auth_secret_b64: str) -> bytes:
    """The receiver side of RFC 8291/8188, written independently of push._encrypt so this test actually
    checks it against the spec -- the way a real browser's push service worker would decrypt it."""
    salt, idlen = body[:16], body[20]
    as_public_raw, ciphertext = body[21:21 + idlen], body[21 + idlen:]
    as_public = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public_raw)
    ua_public_raw = ua_private.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)

    shared_secret = ua_private.exchange(ec.ECDH(), as_public)
    auth_secret = push._unb64u(auth_secret_b64)
    key_info = b"WebPush: info\x00" + ua_public_raw + as_public_raw
    prk_key = hmac.new(auth_secret, shared_secret, hashlib.sha256).digest()
    ikm = HKDFExpand(algorithm=hashes.SHA256(), length=32, info=key_info).derive(prk_key)

    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    cek = HKDFExpand(algorithm=hashes.SHA256(), length=16, info=b"Content-Encoding: aes128gcm\x00").derive(prk)
    nonce = HKDFExpand(algorithm=hashes.SHA256(), length=12, info=b"Content-Encoding: nonce\x00").derive(prk)

    record = AESGCM(cek).decrypt(nonce, ciphertext, None)
    assert record[-1:] == b"\x02"  # the padding delimiter octet for the one (and so "last") record
    return record[:-1]


# ---------------------------------------------------------------- message encryption (RFC 8291)

def test_encrypted_payload_round_trips_the_way_a_real_browser_would_decrypt_it():
    ua_private, p256dh, auth = make_subscription()
    plaintext = json.dumps({"title": "New message from Ana", "body": "Hey! Coffee tomorrow?", "url": "/people?tab=inbox"}).encode()
    body = push._encrypt(plaintext, p256dh, auth)
    assert decrypt(body, ua_private, auth) == plaintext


def test_each_message_uses_a_fresh_salt_and_ephemeral_key_even_for_identical_plaintext():
    _, p256dh, auth = make_subscription()
    assert push._encrypt(b"{}", p256dh, auth) != push._encrypt(b"{}", p256dh, auth)


def test_decryption_fails_with_the_wrong_auth_secret():
    ua_private, p256dh, _ = make_subscription()
    wrong_auth = b64u(os.urandom(16))
    body = push._encrypt(b'{"a":1}', p256dh, wrong_auth)
    try:
        decrypt(body, ua_private, b64u(os.urandom(16)))
        assert False, "should not decrypt with the wrong auth secret"
    except Exception:
        pass


# ---------------------------------------------------------------- VAPID (RFC 8292)

def test_enabled_and_public_key_reflect_configured_keys(monkeypatch):
    monkeypatch.setattr(push, "vapid_keys", lambda: None)
    assert push.enabled() is False and push.public_key() is None
    monkeypatch.setattr(push, "vapid_keys", lambda: FAKE_VAPID)
    assert push.enabled() is True and push.public_key() == FAKE_PUB_B64


def test_vapid_jwt_has_the_right_claims_and_a_genuine_es256_signature(monkeypatch):
    monkeypatch.setattr(push, "vapid_keys", lambda: FAKE_VAPID)
    token = push._vapid_jwt("https://fcm.googleapis.com/fcm/send/abc123")
    header_b64, claims_b64, sig_b64 = token.split(".")
    assert json.loads(push._unb64u(header_b64)) == {"typ": "JWT", "alg": "ES256"}
    claims = json.loads(push._unb64u(claims_b64))
    assert claims["aud"] == "https://fcm.googleapis.com" and claims["sub"] == "mailto:test@example.com"

    raw_sig = push._unb64u(sig_b64)
    r, s = int.from_bytes(raw_sig[:32], "big"), int.from_bytes(raw_sig[32:], "big")
    der_sig = ec_utils.encode_dss_signature(r, s)
    pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), push._unb64u(FAKE_PUB_B64))
    pub.verify(der_sig, f"{header_b64}.{claims_b64}".encode(), ec.ECDSA(hashes.SHA256()))  # raises if invalid

    other_key = ec.generate_private_key(ec.SECP256R1()).public_key()
    try:
        other_key.verify(der_sig, f"{header_b64}.{claims_b64}".encode(), ec.ECDSA(hashes.SHA256()))
        assert False, "should not verify against a different key"
    except InvalidSignature:
        pass


# ---------------------------------------------------------------- subscriptions and notify_user

def register(client, email):
    r = client.post("/api/people/register", json={"email": email, "password": "correct-horse-battery", "display_name": "Pusher", "birth_year": 1995, "agreed": True})
    assert r.status_code == 200, r.text
    return r.json()["me"]["id"], {"Authorization": f"Bearer {r.json()['token']}"}


def test_subscribing_twice_on_the_same_endpoint_updates_rather_than_duplicates(client):
    uid, _ = register(client, "push-sub@example.com")
    push.subscribe(uid, "https://example.com/ep1", "p256dh-1", "auth-1")
    push.subscribe(uid, "https://example.com/ep1", "p256dh-2", "auth-2")
    with db.tx() as c:
        rows = c.execute("SELECT * FROM push_subscriptions WHERE user_id = ?", (uid,)).fetchall()
    assert len(rows) == 1 and rows[0]["p256dh"] == "p256dh-2"
    push.unsubscribe(uid, "https://example.com/ep1")
    with db.tx() as c:
        assert c.execute("SELECT COUNT(*) FROM push_subscriptions WHERE user_id = ?", (uid,)).fetchone()[0] == 0


def test_notify_user_does_nothing_when_push_is_not_configured():
    push.notify_user(999_999_999, "Title", "Body")  # must not raise; enabled() is False (offline) by default


def test_notify_user_sends_to_every_subscription_and_forgets_stale_ones(client, monkeypatch):
    monkeypatch.setattr(push, "vapid_keys", lambda: FAKE_VAPID)
    uid, _ = register(client, "push-notify@example.com")
    push.subscribe(uid, "https://example.com/ep-a", "p256dh-a", "auth-a")
    push.subscribe(uid, "https://example.com/ep-b", "p256dh-b", "auth-b")

    calls = []

    def fake_send(endpoint, p256dh, auth, title, body, url, ttl=push.TTL_SECONDS):
        calls.append(endpoint)
        return 410 if endpoint.endswith("ep-a") else 201

    monkeypatch.setattr(push, "send", fake_send)
    push.notify_user(uid, "Hi", "there")
    assert sorted(calls) == ["https://example.com/ep-a", "https://example.com/ep-b"]
    with db.tx() as c:
        left = {r["endpoint"] for r in c.execute("SELECT endpoint FROM push_subscriptions WHERE user_id = ?", (uid,)).fetchall()}
    assert left == {"https://example.com/ep-b"}  # the 410 (gone) subscription was forgotten


# ---------------------------------------------------------------- routes

def test_push_public_key_route_reports_disabled_by_default(client):
    r = client.get("/api/push/public-key")
    assert r.status_code == 200 and r.json() == {"enabled": False, "public_key": None}


def test_push_subscribe_and_unsubscribe_routes_require_auth(client):
    uid, h = register(client, "push-route@example.com")
    body = {"endpoint": "https://example.com/route-1", "p256dh": "x", "auth": "y"}
    assert client.post("/api/push/subscribe", json=body).status_code == 401
    assert client.post("/api/push/subscribe", json=body, headers=h).status_code == 200
    with db.tx() as c:
        assert c.execute("SELECT COUNT(*) FROM push_subscriptions WHERE user_id = ?", (uid,)).fetchone()[0] == 1
    assert client.post("/api/push/unsubscribe", json={"endpoint": body["endpoint"]}, headers=h).status_code == 200
    with db.tx() as c:
        assert c.execute("SELECT COUNT(*) FROM push_subscriptions WHERE user_id = ?", (uid,)).fetchone()[0] == 0


# ---------------------------------------------------------------- triggers (connect.py)

def test_push_fires_on_a_new_request_an_acceptance_and_a_message(client, monkeypatch):
    calls = []
    monkeypatch.setattr(push, "notify_user", lambda uid, title, body, url="/people": calls.append((uid, title, url)))
    a, a_id, b, b_id = two_people(client)

    r = client.post("/api/people/connect", json={"to_user": b_id, "message": "hi"}, headers=a)
    assert r.json()["status"] == "pending"
    assert calls[-1] == (b_id, "New connection request", "/people?tab=inbox")

    cid = r.json()["id"]
    client.post(f"/api/people/connections/{cid}/respond", json={"accept": True}, headers=b)
    assert calls[-1] == (a_id, "Request accepted", "/people?tab=inbox")

    client.post(f"/api/people/chats/{cid}/messages", json={"body": "yo"}, headers=a)
    assert calls[-1] == (b_id, "Message from Zed", f"/people?tab=inbox&chat={cid}")


def test_push_does_not_fire_for_a_demo_profiles_auto_accept_or_reply(client, monkeypatch):
    """Demo profiles have no push subscription of their own to notify, and the human who messaged them sees
    the reply immediately in the UI -- no push should fire in either direction."""
    calls = []
    monkeypatch.setattr(push, "notify_user", lambda *a, **k: calls.append((a, k)))
    with db.tx() as c:
        c.execute(
            "INSERT INTO users (email, display_name, password_hash, birth_year, visible, demo, created_at) "
            "VALUES ('demo1@wayfinder.invalid', 'Demo Person', 'x', 1995, 1, 1, '2024-01-01T00:00:00+00:00')")
        demo_id = c.execute("SELECT id FROM users WHERE email = 'demo1@wayfinder.invalid'").fetchone()["id"]
    a, a_id, _, _ = two_people(client)
    r = client.post("/api/people/connect", json={"to_user": demo_id, "message": "hi"}, headers=a)
    assert r.json()["status"] == "accepted"  # demo profiles auto-accept
    cid = r.json()["id"]
    client.post(f"/api/people/chats/{cid}/messages", json={"body": "hello"}, headers=a)
    assert calls == []
