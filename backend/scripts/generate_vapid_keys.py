"""Generate a VAPID key pair for Web Push (RFC 8292). Run once, then paste the output into backend/.env.

    python scripts/generate_vapid_keys.py

These are not a paid credential and are not secret in the way an API key is -- the public key is sent to every
browser that subscribes -- but the private key must stay server-side, since it proves messages came from us.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def main() -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    private_raw = key.private_numbers().private_value.to_bytes(32, "big")
    public_raw = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    print("Add these to backend/.env:\n")
    print(f"VAPID_PUBLIC_KEY={b64u(public_raw)}")
    print(f"VAPID_PRIVATE_KEY={b64u(private_raw)}")
    print("VAPID_SUBJECT=mailto:you@example.com   # change to a real contact address; required by the push services")


if __name__ == "__main__":
    main()
