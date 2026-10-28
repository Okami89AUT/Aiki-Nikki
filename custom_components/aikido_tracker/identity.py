"""Namen, Kennungen und Zugangscodes (reine Python-Datei, ohne Home-Assistant-Anteile).

* normalize_name(roh)  -> (kennung, anzeigename)   oder InvalidName
* normalize_code(roh)  -> code                      oder InvalidCode
* hash_code(code)      -> scrypt-Hash als Wörterbuch (der Code selbst wird nie gespeichert)
* verify_code(code, hash) -> True/False             (wirft nie)
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import unicodedata

from .const import (
    MAX_CODE_LEN,
    MAX_NAME_LEN,
    MIN_CODE_LEN,
    SCRYPT_N,
    SCRYPT_P,
    SCRYPT_R,
)


class IdentityError(ValueError):
    """Gemeinsame Oberklasse für ungültige Namen/Codes."""


class InvalidName(IdentityError):
    pass


class InvalidCode(IdentityError):
    pass


# Buchstaben, die sich nicht durch Zerlegen (NFKD) in a–z umschreiben lassen
_ID_MAP = str.maketrans(
    {"ø": "o", "đ": "d", "ł": "l", "æ": "ae", "œ": "oe", "þ": "th", "ð": "d", "ħ": "h", "ı": "i"}
)
_NAME_EXTRA = "_.'- "


def _group_words(text: str) -> list[str]:
    """Zerlegt in Wörter aus Buchstaben/Ziffern/Zeichen-Zusätzen (alles andere trennt)."""
    words: list[str] = []
    cur: list[str] = []
    for char in text:
        if unicodedata.category(char)[0] in "LNM":
            cur.append(char)
        elif cur:
            words.append("".join(cur))
            cur = []
    if cur:
        words.append("".join(cur))
    return words


def _make_id(display: str) -> str:
    folded = unicodedata.normalize("NFKD", display.casefold())
    folded = "".join(c for c in folded if unicodedata.category(c)[0] != "M").translate(_ID_MAP)
    slug_chars: list[str] = []
    pending_dash = False
    for char in folded:
        if "a" <= char <= "z" or "0" <= char <= "9":
            if pending_dash and slug_chars:
                slug_chars.append("-")
            pending_dash = False
            slug_chars.append(char)
        else:
            pending_dash = True
    slug = "".join(slug_chars)[:MAX_NAME_LEN].strip("-")
    if slug:
        return slug
    key = "-".join(_group_words(unicodedata.normalize("NFKC", display.casefold())))
    return "p-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def normalize_name(raw) -> tuple[str, str]:
    """Prüft einen Namen und liefert (Kennung, Anzeigename)."""
    if not isinstance(raw, str):
        raise InvalidName("Der Name muss Text sein.")
    text = unicodedata.normalize("NFC", raw).replace("’", "'")
    text = "".join(" " if unicodedata.category(c) == "Zs" else c for c in text).strip()
    while "  " in text:
        text = text.replace("  ", " ")
    if not 1 <= len(text) <= MAX_NAME_LEN:
        raise InvalidName(f"Der Name muss 1 bis {MAX_NAME_LEN} Zeichen lang sein.")
    has_letter_or_digit = False
    for char in text:
        category = unicodedata.category(char)[0]
        if category in "LN":
            has_letter_or_digit = True
        elif category == "M" or char in _NAME_EXTRA:
            continue
        else:
            raise InvalidName("Der Name enthält unerlaubte Zeichen.")
    if not has_letter_or_digit:
        raise InvalidName("Der Name braucht mindestens einen Buchstaben oder eine Ziffer.")
    return _make_id(text), text


def normalize_code(raw) -> str:
    """Prüft einen Zugangscode (Leerzeichen am Rand bleiben erhalten)."""
    if not isinstance(raw, str):
        raise InvalidCode("Der Zugangscode muss Text sein.")
    code = unicodedata.normalize("NFC", raw)
    if not MIN_CODE_LEN <= len(code) <= MAX_CODE_LEN:
        raise InvalidCode(f"Der Zugangscode muss {MIN_CODE_LEN} bis {MAX_CODE_LEN} Zeichen lang sein.")
    if not code.strip():
        raise InvalidCode("Der Zugangscode darf nicht nur aus Leerzeichen bestehen.")
    if any(unicodedata.category(c)[0] == "C" for c in code):
        raise InvalidCode("Der Zugangscode enthält unerlaubte Steuerzeichen.")
    return code


# ---- Hash (scrypt) -------------------------------------------------------------------------------------------------
_MAX_SCRYPT_BYTES = 64 * 1024 * 1024  # Obergrenze für gespeicherte Parameter (Schutz vor manipulierten Dateien)


def _scrypt(code: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    maxmem = 128 * r * (n + p + 2) + 2 * 1024 * 1024
    return hashlib.scrypt(code.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=maxmem, dklen=32)


def hash_code(code: str, n: int = SCRYPT_N) -> dict:
    salt = secrets.token_bytes(16)
    digest = _scrypt(code, salt, n, SCRYPT_R, SCRYPT_P)
    return {"alg": "scrypt", "n": n, "r": SCRYPT_R, "p": SCRYPT_P, "salt": salt.hex(), "hash": digest.hex()}


def verify_code(code, auth) -> bool:
    """Prüft einen Code gegen den gespeicherten Hash. Wirft nie; kaputte Angaben ergeben False."""
    try:
        if not isinstance(code, str) or not isinstance(auth, dict) or auth.get("alg") != "scrypt":
            return False
        n, r, p = auth["n"], auth["r"], auth["p"]
        if any(type(v) is not int for v in (n, r, p)):
            return False
        if n < 2 or n & (n - 1) or not 1 <= r <= 32 or not 1 <= p <= 16 or 128 * r * n > _MAX_SCRYPT_BYTES:
            return False
        salt = bytes.fromhex(auth["salt"])
        expected = bytes.fromhex(auth["hash"])
        if not 8 <= len(salt) <= 64 or len(expected) != 32:
            return False
        return hmac.compare_digest(_scrypt(code, salt, n, r, p), expected)
    except Exception:  # noqa: BLE001 - jede Unstimmigkeit bedeutet "nicht verifiziert"
        return False
