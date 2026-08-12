"""Cryptographically random base62 short codes."""

import secrets

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE = len(ALPHABET)  # 62


def generate_short_code(length: int = 10) -> str:
    """Return a uniformly random base62 code of the given length.

    Uses ``secrets.randbelow`` so codes are not guessable from a sequence
    (important once private images exist).
    """
    return "".join(ALPHABET[secrets.randbelow(BASE)] for _ in range(length))
