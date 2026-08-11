# -*- coding: utf-8 -*-
"""Hungarian numbers as words, for an engine that cannot read digits.

SPEAKER 1.0 (1990) has no speech element for any digit: `51` produces exactly
zero samples, and `a 51 szam` speaks "a" and "szam" with silence between them.
It is not that it spells them or gets them wrong -- there is simply nothing
there.  PC-TALKER 5.01 gained number handling a year later, which is part of
what its extra 68 KB of kivétel szótár pays for, so this is needed only for the
older voice.

Found the way everything else in this project was found: Tomi heard NVDA say
"Rate: slider 51" with the 51 missing, which sounded exactly like an empty
slider control.
"""

import re

_UNITS = ("nulla", "egy", "kettő", "három", "négy",
          "öt", "hat", "hét", "nyolc", "kilenc")
_TEENS = ("tíz", "tizenegy", "tizenkettő", "tizenhárom", "tizennégy",
          "tizenöt", "tizenhat", "tizenhét", "tizennyolc", "tizenkilenc")
_TWENTIES = ("húsz", "huszonegy", "huszonkettő", "huszonhárom", "huszonnégy",
             "huszonöt", "huszonhat", "huszonhét", "huszonnyolc",
             "huszonkilenc")
_TENS = {3: "harminc", 4: "negyven", 5: "ötven", 6: "hatvan",
         7: "hetven", 8: "nyolcvan", 9: "kilencven"}

_MILLION = 10 ** 6
_BILLION = 10 ** 9


def _under_100(n):
    if n < 10:
        return _UNITS[n]
    if n < 20:
        return _TEENS[n - 10]
    if n < 30:
        return _TWENTIES[n - 20]
    tens, unit = divmod(n, 10)
    return _TENS[tens] + (_UNITS[unit] if unit else "")


def _under_1000(n):
    if n < 100:
        return _under_100(n)
    hundreds, rest = divmod(n, 100)
    # 100 is "száz", not "egyszáz"
    out = ("" if hundreds == 1 else _multiplier(hundreds)) + "száz"
    return out + (_under_100(rest) if rest else "")


def _multiplier(n):
    """The form used before száz / ezer / millió: `kettő` becomes `két`."""
    out = _under_1000(n)
    if out.endswith("kettő"):
        out = out[:-5] + "két"
    return out


def _under_million(n):
    if n < 1000:
        return _under_1000(n)
    thousands, rest = divmod(n, 1000)
    # 1000 is "ezer", not "egyezer"
    out = ("" if thousands == 1 else _multiplier(thousands)) + "ezer"
    return out + (_under_1000(rest) if rest else "")


def number(n):
    """Integer -> Hungarian words.  None if it is too large to say sensibly."""
    if n < 0:
        said = number(-n)
        return None if said is None else "mínusz " + said
    if n < _MILLION:
        return _under_million(n)
    if n < _BILLION:
        millions, rest = divmod(n, _MILLION)
        out = _multiplier(millions) + "millió"
        return out + (" " + _under_million(rest) if rest else "")
    return None


def _digits(text):
    return " ".join(_UNITS[int(c)] for c in text if c.isdigit())


def _replace(match):
    whole, frac = match.group(1), match.group(2)
    said = number(int(whole))
    if said is None:
        # Beyond a milliárd, or anything else unreasonable: read it out digit
        # by digit rather than saying nothing, which is what the engine would
        # otherwise do.
        said = _digits(whole)
    if frac:
        said += " egész " + _digits(frac)
    return said


#: A run of digits, optionally with a decimal comma or point.  Hungarian writes
#: the decimal separator as a comma; NVDA may deliver either.
_NUMBER = re.compile(r"(\d+)(?:[.,](\d+))?")


def expand(text):
    """Replace every number in `text` with its Hungarian name."""
    return _NUMBER.sub(_replace, text)
