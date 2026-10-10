"""The seal of Supabase's browser sign-in: ECDH on P-256, then AES-256-GCM.

The tests play Supabase with their own key, as its sign-in session would.
"""

from __future__ import annotations

import pytest

from tests.setup_world import seal_token
from tracker.domain.supabase import SealedAccessToken
from tracker.infrastructure.supabase_sign_in_crypto import new_sign_in_keys, open_sealed_token
from tracker.shared.errors import SupabaseSignInError


def test_a_token_sealed_for_this_computers_key_opens() -> None:
    keys = new_sign_in_keys()

    opened = open_sealed_token(keys, seal_token(keys.public_key_hex, "sbp_made_up"))

    assert opened.get_secret_value() == "sbp_made_up"
    # An uncompressed P-256 point: 0x04, then 32 bytes for each coordinate.
    assert keys.public_key_hex.startswith("04")
    assert len(keys.public_key_hex) == 130


def test_a_token_sealed_for_another_key_does_not_open() -> None:
    sealed = seal_token(new_sign_in_keys().public_key_hex, "sbp_made_up")

    with pytest.raises(SupabaseSignInError):
        open_sealed_token(new_sign_in_keys(), sealed)


@pytest.mark.parametrize(
    "sealed",
    [
        SealedAccessToken(ciphertext_hex="not hex", public_key_hex="04", nonce_hex="00"),
        SealedAccessToken(ciphertext_hex="00" * 32, public_key_hex="04abcd", nonce_hex="00" * 12),
    ],
    ids=["not-hex", "not-a-point"],
)
def test_a_malformed_answer_does_not_open(sealed: SealedAccessToken) -> None:
    with pytest.raises(SupabaseSignInError):
        open_sealed_token(new_sign_in_keys(), sealed)
