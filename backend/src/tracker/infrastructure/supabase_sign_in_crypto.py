"""The key pair and the seal of Supabase's browser sign-in.

Supabase's own command-line tool signs in this way (``supabase login``), and
Threadline does the same so that the access token never passes through a
server of ours and never travels in the clear:

1. A one-off P-256 key pair is made here; its public half, as an uncompressed
   point in hex, goes into the sign-in page's address.
2. Once the person clicks Authorize, Supabase makes the access token, makes its
   own one-off key pair, and seals the token with AES-256-GCM under the shared
   secret of the two keys (ECDH).
3. This module derives the same shared secret from the private key it kept and
   Supabase's public key, and opens the seal.

The private key lives in memory for one sign-in and is never written anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from pydantic import SecretStr

from tracker.domain.supabase import SealedAccessToken
from tracker.shared.errors import SupabaseSignInError

#: What is said, and logged, when a sealed token cannot be opened.
_UNOPENABLE = "Supabase's sign-in answer could not be opened"


@dataclass(frozen=True, slots=True)
class SignInKeys:
    """One sign-in's key pair.

    Attributes:
        private_key: Kept in memory to open the sealed token; never shown or saved.
        public_key_hex: The public half as an uncompressed point, in hex, for the page.
    """

    private_key: ec.EllipticCurvePrivateKey
    public_key_hex: str


def new_sign_in_keys() -> SignInKeys:
    """Make a fresh P-256 key pair for one browser sign-in.

    Returns:
        The private key and its public half in the form the sign-in page takes.
    """
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_point = private_key.public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint
    )
    return SignInKeys(private_key=private_key, public_key_hex=public_point.hex())


def open_sealed_token(keys: SignInKeys, sealed: SealedAccessToken) -> SecretStr:
    """Open the access token Supabase sealed for this sign-in's key.

    Args:
        keys: The key pair whose public half went into the sign-in page.
        sealed: Supabase's answer.

    Returns:
        The access token.

    Raises:
        SupabaseSignInError: If the answer is not valid hex, Supabase's key is
            not a P-256 point, the seal does not open with this key, or what is
            inside is not text.
    """
    try:
        their_key = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), bytes.fromhex(sealed.public_key_hex)
        )
        shared_secret = keys.private_key.exchange(ec.ECDH(), their_key)
        opened = AESGCM(shared_secret).decrypt(
            bytes.fromhex(sealed.nonce_hex), bytes.fromhex(sealed.ciphertext_hex), None
        )
        token = opened.decode("utf-8").strip()
    except (ValueError, InvalidTag, UnicodeDecodeError) as error:
        raise SupabaseSignInError(_UNOPENABLE) from error
    if not token:
        raise SupabaseSignInError(_UNOPENABLE)
    return SecretStr(token)
