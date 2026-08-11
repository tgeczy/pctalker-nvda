# -*- coding: utf-8 -*-
"""Hungarian letter names, for engines that cannot pronounce a bare consonant.

These are word readers. Handed a single `m` they emit nothing at all, because a
lone consonant is not a pronounceable word — and NVDA sends single characters
constantly, for character echo and for arrowing through text. Silence there is
worse than a wrong sound: the user cannot tell the letter from the end of the
line.

PC-TALKER 5.01 appears to cope, but only by accident. Its exception dictionary
reads bare letters as unit symbols, so `t` becomes *tonna* and `q` becomes
*mázsa* (métermázsa). That is a useful table doing the wrong job — for spelling
it is simply incorrect, so the same names are applied to all three voices.

Vowels are left alone: in Hungarian a vowel's name is the vowel itself, and the
engines already say them correctly, long forms included.
"""

_NAMES = {
    "b": "bé", "c": "cé", "d": "dé", "f": "ef", "g": "gé", "h": "há",
    "j": "jé", "k": "ká", "l": "el", "m": "em", "n": "en", "p": "pé",
    "q": "kú", "r": "er", "s": "es", "t": "té", "v": "vé",
    "w": "dupla vé", "x": "iksz", "y": "ipszilon", "z": "zé",
}


def name(ch):
    """The Hungarian name of a single letter, or None if it has none."""
    return _NAMES.get(ch.lower())


def expand(text):
    """Replace a lone letter with its Hungarian name; leave anything else.

    Deliberately only for a single character. Inside a word these consonants
    are pronounced perfectly well, and rewriting them there would turn every
    `m` into `em` and ruin the speech.
    """
    stripped = text.strip()
    if len(stripped) != 1:
        return text
    said = name(stripped)
    return said if said else text
