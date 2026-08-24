from __future__ import annotations
import ctypes
import threading
import queue
import time
import os

import argparse
import re
import sys
import subprocess
import shutil
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

SAMPLE_RATE = 8500
DOS_ENCODING = "cwi2-experimental"

# CWI-2 / CP-HU mapping used by the original Hungarian PCTALKER generation.
# ASCII 0x00..0x7F remains unchanged.
CWI2_ENCODE = {
    "ü": 0x81, "é": 0x82,
    "Í": 0x8D, "Á": 0x8F, "É": 0x90,
    "ő": 0x93, "ö": 0x94, "Ó": 0x95, "ű": 0x96,
    "Ú": 0x97, "Ű": 0x98, "Ö": 0x99, "Ü": 0x9A,
    "á": 0xA0, "í": 0xA1, "ó": 0xA2, "ú": 0xA3,
    "Ő": 0xA7,
}
CWI2_DECODE = {value: key for key, value in CWI2_ENCODE.items()}

def cwi2_encode(text: str, errors: str = "replace") -> bytes:
    out = bytearray()
    for ch in text:
        n = ord(ch)
        if n < 0x80:
            out.append(n)
        elif ch in CWI2_ENCODE:
            out.append(CWI2_ENCODE[ch])
        elif errors == "ignore":
            continue
        elif errors == "strict":
            raise UnicodeEncodeError("cwi2", ch, 0, 1, "character not mapped")
        else:
            out.append(ord("?"))
    return bytes(out)

def cwi2_decode(data: bytes, errors: str = "replace") -> str:
    out = []
    for b in data:
        if b < 0x80:
            out.append(chr(b))
        elif b in CWI2_DECODE:
            out.append(CWI2_DECODE[b])
        elif errors == "ignore":
            continue
        else:
            out.append(chr(b))
    return "".join(out)

def encode_dos(text: str, errors: str = "replace") -> bytes:
    """
    Encode Unicode text for the historical printer-version PCTALKER tables.

    The printer-version source uses CWI-2 / CP-HU byte positions. For table
    lookup, uppercase characters that are silent or problematic in the
    historical tables are mapped to their audible lowercase equivalents:
        Ó -> ó
        Ú -> ú
        Ő -> ő
        Í -> í
    """
    text = (
        text.replace("Ó", "ó")
            .replace("Ú", "ú")
            .replace("Ő", "ő")
            .replace("Í", "í")
    )
    return cwi2_encode(text, errors)

def decode_dos(data: bytes, errors: str = "replace") -> str:
    return cwi2_decode(data, errors)


TABLE_RE = re.compile(
    r"^c(\d{3})c\S*\s+dw\s+(\d+),\s*(\d+)(?:\s*;\s*(.*))?$",
    re.IGNORECASE,
)
DB_RE = re.compile(
    r"db\s+(\d+),\s*'(.{14})',\s*(\d+|0ffh),\s*'(.{14})'",
    re.IGNORECASE,
)

@dataclass(frozen=True)
class TableEntry:
    key: bytes
    replacement: bytes
    key_len: int
    replacement_len: int

def parse_audio_table(asm_path: Path) -> dict[int, tuple[int, int, str]]:
    table = {}
    for raw in asm_path.read_text(encoding="latin-1").splitlines():
        m = TABLE_RE.match(raw.strip())
        if m:
            code = int(m.group(1))
            table[code] = (int(m.group(2)), int(m.group(3)), (m.group(4) or "").strip())
    if len(table) < 200:
        raise RuntimeError(f"Only {len(table)} audio entries found in {asm_path}.")
    return table

def parse_named_db_table(asm_path: Path, label: str, next_labels: tuple[str, ...]) -> list[TableEntry]:
    lines = asm_path.read_text(encoding="latin-1").splitlines()
    active = False
    result = []
    for raw in lines:
        s = raw.strip()
        if re.match(rf"^{re.escape(label)}\s+db\b", s, re.IGNORECASE):
            active = True
        elif active and any(re.match(rf"^{re.escape(x)}\s+db\b", s, re.IGNORECASE) for x in next_labels):
            break
        elif active:
            # stop at an unrelated non-indented label, but allow comments/blank lines
            if s and not s.startswith(";") and re.match(r"^[A-Za-z_]\w*\s+(?:db|dw|proc|ends)\b", s, re.IGNORECASE):
                break
        if active:
            m = DB_RE.search(raw)
            if not m:
                continue
            klen = int(m.group(1))
            rlen = 255 if m.group(3).lower() == "0ffh" else int(m.group(3))
            key = m.group(2).encode("latin-1")[:klen]
            repl = m.group(4).encode("latin-1")[:rlen if rlen != 255 else 14]
            result.append(TableEntry(key, repl, klen, rlen))
    return result

def parse_szotar(path: Path) -> list[TableEntry]:
    result = []
    for raw in path.read_bytes().splitlines():
        # Ignore comments and the disabled old & record.
        m = re.search(rb"\bdb\s+(\d+),\s*'(.{14})',\s*(\d+|0ffh),\s*'(.{14})'", raw, re.I)
        if not m:
            continue
        klen = int(m.group(1))
        rlen = 255 if m.group(3).lower() == b"0ffh" else int(m.group(3))
        key = m.group(2)[:klen]
        repl = m.group(4)[:rlen if rlen != 255 else 14]
        result.append(TableEntry(key, repl, klen, rlen))
    return result

def load_rawhusr(path: Path) -> bytes:
    data = path.read_bytes()
    if not data:
        raise RuntimeError("RAWHUSR is empty.")
    return data

def get_segment(raw: bytes, table, code: int) -> bytes:
    start, length, _ = table[code]
    if start + length > len(raw):
        raise RuntimeError(f"Phoneme {code}: segment exceeds RAWHUSR.")
    return raw[start:start + length]

# These are exactly the combination tables from OLVAS_P.ASM.
PAIR_LABELS = {
    ord("c"): "ctar", ord("C"): "ctar",
    ord("k"): "ktar", ord("K"): "ktar",
    ord("v"): "vtar", ord("V"): "vtar",
    ord("s"): "star", ord("S"): "star",
    ord("z"): "ztar", ord("Z"): "ztar",
    ord("t"): "ttar", ord("T"): "ttar",
    ord("n"): "ntar", ord("N"): "ntar",
    ord("l"): "ltar", ord("L"): "ltar",
    ord("g"): "gtar", ord("G"): "gtar",
    ord("d"): "dtar", ord("D"): "dtar",
    ord("-"): "mntar",
}

def load_pair_tables(asm_path: Path) -> dict[int, list[TableEntry]]:
    labels = ["ctar","ktar","vtar","star","ztar","ttar","ntar","ltar","gtar","dtar","mntar"]
    out = {}
    for code, label in PAIR_LABELS.items():
        # Find exact section and stop at the next named table.
        idx = labels.index(label)
        nexts = tuple(labels[idx+1:]) + ("dseg",)
        entries = parse_named_db_table(asm_path, label, nexts)
        out[code] = [e for e in entries if e.key_len]
    return out

def parse_phoneme_token(token: str) -> list[int]:
    token = token.strip()
    if not token:
        return []
    if re.fullmatch(r"0[xX][0-9a-fA-F]+|\d+", token):
        n = int(token, 0)
        if not 0 <= n <= 255:
            raise ValueError("Phoneme code must be 0..255.")
        return [n]
    # ABC is accepted as A,B,C; whitespace/comma-separated forms are also accepted.
    return [ord(c) for c in token]

def convert_bytes(text: bytes, asm_path: Path) -> bytes:
    """
    Port of the core OLVAS CONVERT routine.

    The original uses special look-ahead tables for c/k/v/s/z/t/n/l/g/d/-
    and otherwise copies the input byte unchanged as its phoneme code.
    """
    tables = load_pair_tables(asm_path)
    out = bytearray()
    i = 0
    while i < len(text):
        ch = text[i]
        entries = tables.get(ch)
        if entries:
            found = None
            for e in entries:
                if text[i:i+e.key_len] == e.key:
                    found = e
                    break
            if found:
                out.extend(found.replacement)
                i += found.key_len
                continue
        out.append(ch)
        i += 1
    return bytes(out)

def apply_dictionary_once(text: bytes, dictionary: list[TableEntry]) -> tuple[bytes, bool, str | None]:
    """Apply one OLVAS-style dictionary pass at word starts.

    The original invokes the dictionary when a new word is encountered.
    We therefore do not search at every character inside a word.  This is
    important because the table contains short entries such as ``A`` and
    ``B`` which are intended as word/context entries, not arbitrary
    substring replacements.
    """
    out = bytearray()
    i = 0
    at_word_start = True
    changed = False
    matched_key = None

    while i < len(text):
        ch = text[i]
        if ch in b" \t\r\n":
            out.append(ch)
            i += 1
            at_word_start = True
            continue

        best = None
        if at_word_start:
            for e in dictionary:
                if e.replacement_len == 255:
                    continue  # embedded audio is implemented later
                if text[i:i + e.key_len] == e.key:
                    if best is None or e.key_len > best.key_len:
                        best = e

        if best is not None:
            out.extend(best.replacement)
            i += best.key_len
            changed = True
            matched_key = best.key.decode("latin-1")
            # A replacement may itself contain spaces.  Re-evaluate from
            # the next byte as a new word only after a separator.
            at_word_start = False
            continue

        out.append(ch)
        i += 1
        at_word_start = False

    return bytes(out), changed, matched_key

def dictionary_convert(text: str, asm_path: Path, szotar_path: Path) -> tuple[bytes, bytes]:
    """
    Repeatedly apply dictionary substitutions, then run the real CONVERT
    combination logic. A safety limit prevents pathological recursive entries.
    """
    raw = encode_dos(text, errors="replace")
    dictionary = parse_szotar(szotar_path)

    current = raw
    for _ in range(8):
        new, changed, _ = apply_dictionary_once(current, dictionary)
        if not changed or new == current:
            break
        current = new

    phonemes = convert_bytes(current, asm_path)
    return current, phonemes

def concatenate_codes(raw: bytes, table, codes: list[int]) -> bytes:
    chunks = []
    for code in codes:
        if code not in table:
            # Keep unknown characters as silence rather than crashing.
            code = 32
        chunks.append(get_segment(raw, table, code))
    return b"".join(chunks)

def write_wav(path: Path, samples: bytes, sample_rate: int = SAMPLE_RATE) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(sample_rate)
        w.writeframes(samples)

def play_wav_windows(path: Path) -> None:
    if sys.platform != "win32":
        raise RuntimeError("Playback requires Windows; use --wav elsewhere.")
    import winsound
    winsound.PlaySound(str(path), winsound.SND_FILENAME)


# ---------------------------------------------------------------------------
# Prototype 0.3: number expansion
# ---------------------------------------------------------------------------

HUNGARIAN_ONES = {
    0: "nulla", 1: "egy", 2: "kettő", 3: "három", 4: "négy",
    5: "öt", 6: "hat", 7: "hét", 8: "nyolc", 9: "kilenc",
}
HUNGARIAN_TEENS = {
    10: "tíz", 11: "tizenegy", 12: "tizenkettő", 13: "tizenhárom",
    14: "tizennégy", 15: "tizenöt", 16: "tizenhat", 17: "tizenhét",
    18: "tizennyolc", 19: "tizenkilenc",
}
HUNGARIAN_TENS = {
    20: "húsz", 30: "harminc", 40: "negyven", 50: "ötven",
    60: "hatvan", 70: "hetven", 80: "nyolcvan", 90: "kilencven",
}

def _hungarian_under_100(n: int) -> str:
    if n < 10:
        return HUNGARIAN_ONES[n]
    if n < 20:
        return HUNGARIAN_TEENS[n]
    tens = (n // 10) * 10
    ones = n % 10
    if ones == 0:
        return HUNGARIAN_TENS[tens]
    stem = "huszon" if tens == 20 else HUNGARIAN_TENS[tens]
    return stem + HUNGARIAN_ONES[ones]

def _hungarian_under_1000(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    out = ""
    if hundreds:
        out += "száz" if hundreds == 1 else HUNGARIAN_ONES[hundreds] + "száz"
    if rest:
        out += _hungarian_under_100(rest)
    return out

def _digits_to_hungarian(text: str) -> str:
    """Read a numeric string digit by digit; used as a safe fallback."""
    return " ".join(HUNGARIAN_ONES[int(ch)] for ch in text if ch.isdigit())

def number_to_hungarian(n: int) -> str:
    """
    Convert ordinary integers using the existing OLVAS-style cardinal rules.

    The original prototype implementation was designed for values up through
    the billions/trillions range. NVDA can encounter arbitrarily long numeric
    IDs, hashes, timestamps, etc. For values beyond the safe cardinal range,
    read the digits individually instead of raising an exception.
    """
    if n == 0:
        return "nulla"
    if n < 0:
        return "mínusz " + number_to_hungarian(-n)

    # Keep the established cardinal behavior where its 3-digit groups are valid.
    if n > 999_999_999_999:
        return _digits_to_hungarian(str(n))

    parts = []
    billions, n = divmod(n, 1_000_000_000)
    millions, n = divmod(n, 1_000_000)
    thousands, rest = divmod(n, 1000)

    if billions:
        parts.append(_hungarian_under_1000(billions) + "milliárd")
    if millions:
        parts.append(_hungarian_under_1000(millions) + "millió")
    if thousands:
        parts.append(_hungarian_under_1000(thousands) + "ezer")
    if rest:
        parts.append(_hungarian_under_1000(rest))
    return "".join(parts)


NUMBER_RE = re.compile(r"(?<![\w])([+-]?)(\d+)(?:[.,](\d+))?(?![\w])")

def _decimal_denominator_name(digits: int) -> str:
    names = {
        1: "tized",
        2: "század",
        3: "ezred",
        4: "tízezred",
        5: "százezred",
        6: "milliomod",
    }
    return names.get(digits, "tized")

def expand_numbers(text: str) -> str:
    """
    Expand integers and decimals without ever failing on long numeric strings.

    Examples:
      123.4   -> százhuszonhárom egész négy tized
      123.45  -> százhuszonhárom egész negyvenöt század

    Long fractional strings (more than 6 digits), which are common in IDs,
    version strings and machine-generated text, are read digit by digit after
    "pont" rather than being treated as an enormous cardinal fraction.
    """
    def repl(m: re.Match) -> str:
        sign, whole, fraction = m.groups()
        prefix = "plusz " if sign == "+" else ("mínusz " if sign == "-" else "")

        # Whole part: normal cardinal when practical; safe digit fallback for huge IDs.
        whole_int = int(whole)
        spoken = prefix + number_to_hungarian(whole_int)

        if fraction is not None:
            if len(fraction) <= 6:
                frac_value = int(fraction)
                denominator = _decimal_denominator_name(len(fraction))
                spoken += " egész " + number_to_hungarian(frac_value) + " " + denominator
            else:
                spoken += " pont " + _digits_to_hungarian(fraction)

        return spoken

    try:
        return NUMBER_RE.sub(repl, text)
    except Exception:
        # Last-resort fail-safe for screen-reader use: never lose the entire
        # utterance because of an unexpected number format.
        return text

# ---------------------------------------------------------------------------
# Prototype 0.6: original OLVAS-style punctuation intonation
# ---------------------------------------------------------------------------

OLVAS_BASE_SPEED = 0x73  # timersz in the original ASM (commented as ~8.5 kHz)

def _resample_u8_segment(segment: bytes, speed: int,
                         base_speed: int = OLVAS_BASE_SPEED) -> bytes:
    """
    Reproduce the DOS timer-speed effect while keeping Windows output fixed
    at SAMPLE_RATE.

    In the original HANG routine a larger timer threshold advances samples
    sooner (higher effective playback rate/pitch), while a smaller threshold
    advances them more slowly. We emulate that by resampling each phoneme.
    """
    if not segment or speed <= 0 or speed == base_speed:
        return segment

    # Higher speed -> fewer output samples; lower speed -> more.
    out_len = max(1, round(len(segment) * base_speed / speed))
    if len(segment) == 1 or out_len == 1:
        return bytes([segment[0]])

    out = bytearray(out_len)
    scale = (len(segment) - 1) / (out_len - 1)
    for j in range(out_len):
        pos = j * scale
        i = int(pos)
        if i >= len(segment) - 1:
            out[j] = segment[-1]
        else:
            frac = pos - i
            value = round(segment[i] * (1.0 - frac) + segment[i + 1] * frac)
            out[j] = max(0, min(255, value))
    return bytes(out)

def olvas_intonation_speeds(codes: list[int],
                            base_speed: int = OLVAS_BASE_SPEED) -> list[int]:
    """
    Port of the active punctuation-intonation section in PHONSOUT.

    Original ASM behavior:
      - look three phoneme codes ahead
      - '.' starts/continues pontkov, adding 4 each phoneme
      - ',' starts/continues veszkov, adding 5 each phoneme
      - period contribution lowers speed
      - comma contribution raises speed
      - ramps reset after their original thresholds

    The original ejtes variable is maintained by the ASM but its continuous
    falling-pitch addition is commented out, so Prototype 0.6 does not invent
    that disabled behavior.
    """
    pontkov = 0
    veszkov = 0
    ejtes = 0
    speeds = []

    for i in range(len(codes)):
        lookahead = codes[i + 3] if i + 3 < len(codes) else None

        # Period ramp: exactly the active ASM logic.
        if lookahead in (ord("."), ord("!")) or pontkov != 0:
            pontkov += 4
            if pontkov > 12:
                pontkov = 0
                ejtes = 25

        # Comma ramp: exactly the active ASM logic.
        if lookahead in (ord(","), ord("?")) or veszkov != 0:
            veszkov += 5
            if veszkov > 15:
                veszkov = 0
                ejtes = 25

        if ejtes >= 1:
            ejtes -= 1

        speed = base_speed + veszkov - pontkov
        speeds.append(max(1, speed))

    return speeds

def concatenate_codes_with_intonation(raw: bytes, table, codes: list[int],
                                      enabled: bool = True,
                                      show: bool = False) -> bytes:
    if not enabled:
        return concatenate_codes(raw, table, codes)

    speeds = olvas_intonation_speeds(codes)
    chunks = []
    for i, (code, speed) in enumerate(zip(codes, speeds)):
        segment = get_segment(raw, table, code)
        chunks.append(_resample_u8_segment(segment, speed))
        if show and speed != OLVAS_BASE_SPEED:
            ch = chr(code) if 32 <= code < 127 else f"0x{code:02X}"
            print(f"Intonation: index={i:3d} code={ch!r:6s} speed={speed}")
    return b"".join(chunks)


# ---------------------------------------------------------------------------
# Prototype 0.5: embedded WAV/MP3 files in text
# ---------------------------------------------------------------------------

AUDIO_TOKEN_RE = re.compile(
    r'&(?:"([^"]+)"|([^\s&]+))',
    re.IGNORECASE,
)

def split_embedded_audio(text: str):
    """
    Split text into ('speech', text) and ('audio', filename) segments.

    Supported:
      &ding.wav
      &intro.mp3
      &"my sound file.wav"
    """
    segments = []
    pos = 0
    for m in AUDIO_TOKEN_RE.finditer(text):
        if m.start() > pos:
            segments.append(("speech", text[pos:m.start()]))
        filename = m.group(1) or m.group(2)
        segments.append(("audio", filename))
        pos = m.end()
    if pos < len(text):
        segments.append(("speech", text[pos:]))
    return segments

def resolve_audio_file(filename: str, base_dir: Path) -> Path:
    """Resolve local/Windows Media WAV or MP3 names, with optional extension."""
    p = Path(filename.strip())
    if p.suffix.lower() in (".wav", ".mp3") or p.suffix:
        names = [p]
    else:
        names = [Path(str(p) + ".wav"), Path(str(p) + ".mp3")]

    roots = []
    if not p.is_absolute():
        roots = [Path.cwd(), base_dir, base_dir / "audio"]
        win_dir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
        if win_dir:
            roots.append(Path(win_dir) / "Media")

    searched = []
    for name in names:
        if name.is_absolute():
            searched.append(name)
            if name.is_file():
                return name.resolve()
        else:
            for search_root in roots:
                candidate = search_root / name
                searched.append(candidate)
                if candidate.is_file():
                    return candidate.resolve()

    # Friendly Windows fallback: &ding may correspond to "Windows Ding.wav".
    if not p.is_absolute() and not p.suffix:
        win_dir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
        if win_dir:
            media = Path(win_dir) / "Media"
            if media.is_dir():
                needle = p.name.casefold()
                matches = sorted(
                    f for f in media.iterdir()
                    if f.is_file()
                    and f.suffix.lower() in (".wav", ".mp3")
                    and needle in f.stem.casefold()
                )
                if len(matches) == 1:
                    return matches[0].resolve()
                suffix_matches = [f for f in matches if f.stem.casefold().endswith(needle)]
                if len(suffix_matches) == 1:
                    return suffix_matches[0].resolve()
                if matches:
                    found = "\n  ".join(str(f) for f in matches[:12])
                    raise FileNotFoundError(
                        f"Embedded audio name '{filename}' is ambiguous.\n"
                        f"Matches:\n  {found}\n"
                        'Use the full filename, e.g. &"Windows Ding.wav".'
                    )

    searched_text = "\n  ".join(str(x) for x in searched)
    raise FileNotFoundError(
        f"Embedded audio file not found: {filename}\n"
        f"Searched:\n  {searched_text}"
    )


def _read_pcm_wav(path: Path) -> tuple[bytes, int, int, int]:
    with wave.open(str(path), "rb") as w:
        channels = w.getnchannels()
        width = w.getsampwidth()
        rate = w.getframerate()
        frames = w.readframes(w.getnframes())
    return frames, rate, channels, width

def _pcm_to_u8_mono_8500(frames: bytes, rate: int, channels: int, width: int) -> bytes:
    """
    Convert uncompressed PCM WAV to unsigned 8-bit mono at SAMPLE_RATE.

    Pure Python implementation: does not use audioop (removed in Python 3.13).
    Supports 8/16/24/32-bit PCM and mono/stereo input.
    """
    if width not in (1, 2, 3, 4):
        raise ValueError(f"Unsupported PCM sample width: {width} bytes")
    if channels not in (1, 2):
        raise ValueError(f"Only mono/stereo WAV is supported, got {channels} channels")
    if rate <= 0:
        raise ValueError(f"Invalid WAV sample rate: {rate}")

    frame_size = width * channels
    usable = len(frames) - (len(frames) % frame_size)
    frames = frames[:usable]
    if not frames:
        return b""

    def read_sample(buf: bytes, off: int) -> int:
        if width == 1:
            # WAV 8-bit PCM is unsigned; center around zero.
            return (buf[off] - 128) << 8
        if width == 2:
            return int.from_bytes(buf[off:off+2], "little", signed=True)
        if width == 3:
            b = buf[off:off+3]
            v = b[0] | (b[1] << 8) | (b[2] << 16)
            if v & 0x800000:
                v -= 1 << 24
            return v >> 8
        # 32-bit signed PCM -> normalize approximately to 16-bit range.
        return int.from_bytes(buf[off:off+4], "little", signed=True) >> 16

    # Decode to signed ~16-bit mono samples.
    mono = []
    for frame_off in range(0, len(frames), frame_size):
        if channels == 1:
            sample = read_sample(frames, frame_off)
        else:
            left = read_sample(frames, frame_off)
            right = read_sample(frames, frame_off + width)
            sample = (left + right) // 2
        mono.append(sample)

    # Linear interpolation resampling to OLVAS's 8500 Hz.
    if rate == SAMPLE_RATE:
        resampled = mono
    else:
        out_len = max(1, round(len(mono) * SAMPLE_RATE / rate))
        resampled = []
        scale = rate / SAMPLE_RATE
        last = len(mono) - 1
        for j in range(out_len):
            pos = j * scale
            i = int(pos)
            if i >= last:
                value = mono[last]
            else:
                frac = pos - i
                value = round(mono[i] * (1.0 - frac) + mono[i + 1] * frac)
            resampled.append(value)

    # Signed 16-bit-ish -> unsigned 8-bit PCM centered on 128.
    out = bytearray(len(resampled))
    for i, sample in enumerate(resampled):
        v = (sample >> 8) + 128
        if v < 0:
            v = 0
        elif v > 255:
            v = 255
        out[i] = v
    return bytes(out)


def decode_wav_to_olvas(path: Path) -> bytes:
    frames, rate, channels, width = _read_pcm_wav(path)
    return _pcm_to_u8_mono_8500(frames, rate, channels, width)

def decode_mp3_to_olvas(path: Path) -> bytes:
    """
    Decode MP3 through ffmpeg if available.

    ffmpeg.exe may be:
      * on PATH, or
      * beside olvas.py, or
      * in an ffmpeg subfolder beside olvas.py.
    """
    here = Path(__file__).resolve().parent
    choices = [
        shutil.which("ffmpeg"),
        str(here / "ffmpeg.exe"),
        str(here / "ffmpeg" / "ffmpeg.exe"),
    ]
    ffmpeg = next((x for x in choices if x and Path(x).is_file()), None)
    if not ffmpeg:
        raise RuntimeError(
            "MP3 playback requires ffmpeg.exe. Put ffmpeg.exe beside olvas.py, "
            "in an ffmpeg subfolder, or install FFmpeg on PATH. WAV files do "
            "not require FFmpeg."
        )

    cmd = [
        ffmpeg, "-v", "error", "-i", str(path),
        "-f", "u8", "-acodec", "pcm_u8",
        "-ac", "1", "-ar", str(SAMPLE_RATE), "-"
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(
            f"FFmpeg could not decode {path.name}: "
            + proc.stderr.decode("utf-8", errors="replace").strip()
        )
    return proc.stdout

def decode_external_audio(path: Path) -> bytes:
    ext = path.suffix.lower()
    if ext == ".wav":
        return decode_wav_to_olvas(path)
    if ext == ".mp3":
        return decode_mp3_to_olvas(path)
    raise ValueError(f"Unsupported embedded audio format: {path.suffix}")

def synthesize_text_segment(text: str, asm: Path, szotar: Path, raw: bytes, table,
                            intonation: bool = True, show_intonation: bool = False) -> bytes:
    if not text:
        return b""
    expanded = expand_numbers(text)
    normalized, phoneme_bytes = dictionary_convert(expanded, asm, szotar)
    return concatenate_codes_with_intonation(
        raw, table, list(phoneme_bytes), intonation, show_intonation
    )


def synthesize_mixed_segments(text: str, asm: Path, szotar: Path,
                              raw: bytes, table, base_dir: Path,
                              show_audio: bool = False,
                              intonation: bool = True,
                              show_intonation: bool = False):
    """
    Return a list of (kind, pcm_bytes) segments.

    kind is:
        "speech" - synthesized OLVAS speech; user --speed applies
        "audio"  - embedded WAV/MP3; always plays at normal speed
    """
    segments = []
    for kind, value in split_embedded_audio(text):
        if kind == "speech":
            pcm = synthesize_text_segment(
                value, asm, szotar, raw, table, intonation, show_intonation
            )
            if pcm:
                segments.append(("speech", pcm))
        else:
            path = resolve_audio_file(value, base_dir)
            if show_audio:
                print(f"Embedded audio: {path}")
            pcm = decode_external_audio(path)
            if pcm:
                segments.append(("audio", pcm))
    return segments

def synthesize_mixed_text(text: str, asm: Path, szotar: Path,
                          raw: bytes, table, base_dir: Path,
                          show_audio: bool = False,
                          intonation: bool = True,
                          show_intonation: bool = False) -> bytes:
    """
    Backward-compatible whole-buffer synthesis.

    Note: when played as one whole buffer, a single playback rate necessarily
    affects every part. OlvasEngine.speak() in Prototype 0.8.4 uses the new
    segmented path so --speed changes speech only.
    """
    parts = synthesize_mixed_segments(
        text, asm, szotar, raw, table, base_dir,
        show_audio, intonation, show_intonation
    )
    return b"".join(pcm for _, pcm in parts)

class StreamingAudioPlayer:
    """
    Queue-based Windows PCM player for OLVAS.

    Prototype 0.8.1 fix:
    Multiple waveOut buffers are prepared and queued ahead of playback.
    This avoids the small gaps caused by waiting for each 80 ms buffer to
    finish before submitting the next one.

    Public API:
        play(samples)
        stop()
        pause()
        resume()
        is_playing()
        wait()
        close()
    """

    WAVE_MAPPER = -1
    CALLBACK_NULL = 0
    WHDR_DONE = 0x00000001
    MMSYSERR_NOERROR = 0
    WAVERR_STILLPLAYING = 33

    class WAVEFORMATEX(ctypes.Structure):
        _fields_ = [
            ("wFormatTag", ctypes.c_ushort),
            ("nChannels", ctypes.c_ushort),
            ("nSamplesPerSec", ctypes.c_uint),
            ("nAvgBytesPerSec", ctypes.c_uint),
            ("nBlockAlign", ctypes.c_ushort),
            ("wBitsPerSample", ctypes.c_ushort),
            ("cbSize", ctypes.c_ushort),
        ]

    class WAVEHDR(ctypes.Structure):
        _fields_ = [
            ("lpData", ctypes.c_void_p),
            ("dwBufferLength", ctypes.c_uint),
            ("dwBytesRecorded", ctypes.c_uint),
            ("dwUser", ctypes.c_size_t),
            ("dwFlags", ctypes.c_uint),
            ("dwLoops", ctypes.c_uint),
            ("lpNext", ctypes.c_void_p),
            ("reserved", ctypes.c_size_t),
        ]

    def __init__(self, sample_rate=SAMPLE_RATE, chunk_ms=80, queue_depth=4):
        if sys.platform != "win32":
            raise RuntimeError("StreamingAudioPlayer currently requires Windows.")

        self.sample_rate = sample_rate
        self.chunk_bytes = max(1, int(sample_rate * chunk_ms / 1000))
        self.queue_depth = max(2, int(queue_depth))

        self._q = queue.Queue()
        self._closed = threading.Event()
        self._busy = threading.Event()
        self._generation = 0
        self._lock = threading.Lock()

        self._winmm = ctypes.WinDLL("winmm")
        self._hwo = ctypes.c_void_p()

        fmt = self.WAVEFORMATEX(
            1, 1, sample_rate, sample_rate, 1, 8, 0
        )
        result = self._winmm.waveOutOpen(
            ctypes.byref(self._hwo),
            ctypes.c_uint(self.WAVE_MAPPER & 0xFFFFFFFF),
            ctypes.byref(fmt),
            0, 0, self.CALLBACK_NULL,
        )
        if result != 0:
            raise RuntimeError(f"waveOutOpen failed with Windows MMRESULT {result}")

        self._thread = threading.Thread(
            target=self._worker, name="OLVAS-Audio", daemon=True
        )
        self._thread.start()

    def play(self, samples: bytes, sample_rate: int | None = None):
        if self._closed.is_set():
            raise RuntimeError("Audio player is closed.")
        if not samples:
            return
        with self._lock:
            generation = self._generation
        if sample_rate is None:
            sample_rate = self.sample_rate
        sample_rate = int(sample_rate)
        if sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        self._busy.set()
        self._q.put((generation, bytes(samples), sample_rate))

    def stop(self):
        with self._lock:
            self._generation += 1

        # waveOutReset immediately stops playback and marks queued headers done.
        try:
            self._winmm.waveOutReset(self._hwo)
        except Exception:
            pass

        while True:
            try:
                self._q.get_nowait()
                self._q.task_done()
            except queue.Empty:
                break

        self._busy.clear()

    def pause(self):
        if not self._closed.is_set():
            self._winmm.waveOutPause(self._hwo)

    def resume(self):
        if not self._closed.is_set():
            self._winmm.waveOutRestart(self._hwo)

    def is_playing(self):
        return self._busy.is_set()

    def wait(self):
        while self.is_playing() and not self._closed.is_set():
            time.sleep(0.01)

    def close(self):
        if self._closed.is_set():
            return
        self.stop()
        self._closed.set()
        self._q.put((-1, b""))
        self._thread.join(timeout=2.0)
        self._winmm.waveOutClose(self._hwo)

    def _set_sample_rate(self, sample_rate: int):
        """Reopen waveOut when the next queued segment needs a different rate."""
        sample_rate = int(sample_rate)
        if sample_rate == self.sample_rate:
            return

        # No buffers are active when worker calls this between queue items.
        self._winmm.waveOutReset(self._hwo)
        self._winmm.waveOutClose(self._hwo)

        self.sample_rate = sample_rate
        self.chunk_bytes = max(1, int(sample_rate * 80 / 1000))

        fmt = self.WAVEFORMATEX(
            1, 1, sample_rate, sample_rate, 1, 8, 0
        )
        result = self._winmm.waveOutOpen(
            ctypes.byref(self._hwo),
            ctypes.c_uint(self.WAVE_MAPPER & 0xFFFFFFFF),
            ctypes.byref(fmt),
            0, 0, self.CALLBACK_NULL,
        )
        if result != 0:
            raise RuntimeError(
                f"waveOutOpen failed changing sample rate to {sample_rate}: {result}"
            )

    def _prepare_and_write(self, chunk: bytes, generation: int):
        with self._lock:
            if generation != self._generation:
                return None

        buf = ctypes.create_string_buffer(chunk)
        hdr = self.WAVEHDR()
        hdr.lpData = ctypes.cast(buf, ctypes.c_void_p)
        hdr.dwBufferLength = len(chunk)

        r = self._winmm.waveOutPrepareHeader(
            self._hwo, ctypes.byref(hdr), ctypes.sizeof(hdr)
        )
        if r != self.MMSYSERR_NOERROR:
            raise RuntimeError(f"waveOutPrepareHeader failed: {r}")

        r = self._winmm.waveOutWrite(
            self._hwo, ctypes.byref(hdr), ctypes.sizeof(hdr)
        )
        if r != self.MMSYSERR_NOERROR:
            self._winmm.waveOutUnprepareHeader(
                self._hwo, ctypes.byref(hdr), ctypes.sizeof(hdr)
            )
            raise RuntimeError(f"waveOutWrite failed: {r}")

        # Keep both alive until Windows has completed this header.
        return (buf, hdr)

    def _unprepare_finished(self, active):
        """
        Remove completed buffers from the front of the active list.
        waveOut plays headers in queue order, so the oldest active header is
        the one that should complete first.
        """
        while active:
            buf, hdr = active[0]
            if not (hdr.dwFlags & self.WHDR_DONE):
                break

            for _ in range(100):
                r = self._winmm.waveOutUnprepareHeader(
                    self._hwo, ctypes.byref(hdr), ctypes.sizeof(hdr)
                )
                if r == self.MMSYSERR_NOERROR:
                    break
                if r != self.WAVERR_STILLPLAYING:
                    break
                time.sleep(0.002)

            active.pop(0)

    def _drain_active(self, active, generation):
        while active and not self._closed.is_set():
            with self._lock:
                cancelled = generation != self._generation
            if cancelled:
                # Reset already marks headers done; continue cleanup.
                pass

            self._unprepare_finished(active)
            if active:
                time.sleep(0.003)

        # Best-effort cleanup after cancellation/reset.
        for buf, hdr in list(active):
            for _ in range(100):
                r = self._winmm.waveOutUnprepareHeader(
                    self._hwo, ctypes.byref(hdr), ctypes.sizeof(hdr)
                )
                if r == self.MMSYSERR_NOERROR:
                    break
                time.sleep(0.002)
        active.clear()

    def _play_samples_gapless(self, samples: bytes, generation: int):
        """
        Feed several buffers ahead of the playback cursor.

        As one buffer completes, immediately queue the next one. Windows
        therefore always has additional audio ready and does not underrun at
        every 80 ms boundary.
        """
        chunks = [
            samples[i:i + self.chunk_bytes]
            for i in range(0, len(samples), self.chunk_bytes)
        ]
        if not chunks:
            return

        active = []
        next_chunk = 0

        # Prime Windows with multiple buffers before playback reaches the end
        # of the first one.
        while next_chunk < len(chunks) and len(active) < self.queue_depth:
            with self._lock:
                if generation != self._generation:
                    return
            item = self._prepare_and_write(chunks[next_chunk], generation)
            if item is None:
                return
            active.append(item)
            next_chunk += 1

        while active and not self._closed.is_set():
            with self._lock:
                if generation != self._generation:
                    break

            before = len(active)
            self._unprepare_finished(active)

            # Refill queue immediately after completed buffers are released.
            while next_chunk < len(chunks) and len(active) < self.queue_depth:
                with self._lock:
                    if generation != self._generation:
                        break
                item = self._prepare_and_write(chunks[next_chunk], generation)
                if item is None:
                    break
                active.append(item)
                next_chunk += 1

            if active and len(active) == before:
                time.sleep(0.002)

        self._drain_active(active, generation)

    def _worker(self):
        try:
            while not self._closed.is_set():
                item = self._q.get()
                if len(item) == 2:
                    generation, samples = item
                    sample_rate = self.sample_rate
                else:
                    generation, samples, sample_rate = item
                if generation == -1:
                    self._q.task_done()
                    break

                try:
                    with self._lock:
                        valid = generation == self._generation
                    if valid:
                        self._set_sample_rate(sample_rate)
                        self._play_samples_gapless(samples, generation)
                finally:
                    self._q.task_done()
                    if self._q.empty():
                        self._busy.clear()
        finally:
            self._busy.clear()


def play_streaming_windows(samples: bytes, sample_rate: int = SAMPLE_RATE):
    """Play one generated utterance through the new streaming player."""
    player = StreamingAudioPlayer(sample_rate=sample_rate)
    try:
        player.play(samples)
        player.wait()
    finally:
        player.close()



# ---------------------------------------------------------------------------
# Prototype 0.8: reusable OLVAS engine API for NVDA integration
# ---------------------------------------------------------------------------

class OlvasEngine:
    """
    Reusable synthesizer facade.

    This class owns the OLVAS data, converter and StreamingAudioPlayer so the
    command-line program and a future NVDA synthDriver can use the same engine.

    Public API:
        speak(text)
        cancel()
        pause()
        resume()
        is_speaking()
        wait()
        synthesize(text)
        close()

    Input text may still contain embedded WAV/MP3 references such as:
        alma &ding körte
    """

    def __init__(self, base_dir: Path | str | None = None,
                 intonation: bool = True,
                 show_audio: bool = False,
                 show_intonation: bool = False,
                 start_player: bool = True,
                 speed: float = 1.0):
        self.base_dir = (
            Path(base_dir).resolve()
            if base_dir is not None
            else Path(__file__).resolve().parent
        )
        self.data_dir = self.base_dir / "data"
        self.asm = self.data_dir / "OLVAS_P.ASM"
        self.raw_path = self.data_dir / "RAWHUSR"
        self.szotar = self.data_dir / "SZOTAR.TBL"

        self.table = parse_audio_table(self.asm)
        self.raw = load_rawhusr(self.raw_path)

        self.intonation = bool(intonation)
        self.show_audio = bool(show_audio)
        self.show_intonation = bool(show_intonation)
        self.speed = float(speed)
        self.playback_sample_rate = speed_to_sample_rate(self.speed)

        self._player = StreamingAudioPlayer(sample_rate=self.playback_sample_rate) if start_player else None
        self._closed = False
        self._speak_lock = threading.RLock()

    def synthesize_segments(self, text: str):
        """
        Return [('speech'|'audio', pcm_bytes), ...].

        Speech segments are intended to play at self.playback_sample_rate.
        Embedded audio segments are intended to play at native SAMPLE_RATE.
        """
        if self._closed:
            raise RuntimeError("OLVAS engine is closed.")
        return synthesize_mixed_segments(
            text,
            self.asm,
            self.szotar,
            self.raw,
            self.table,
            self.base_dir,
            self.show_audio,
            self.intonation,
            self.show_intonation,
        )

    def synthesize(self, text: str) -> bytes:
        """Return unsigned 8-bit mono 8500-Hz PCM for text."""
        if self._closed:
            raise RuntimeError("OLVAS engine is closed.")
        return synthesize_mixed_text(
            text,
            self.asm,
            self.szotar,
            self.raw,
            self.table,
            self.base_dir,
            self.show_audio,
            self.intonation,
            self.show_intonation,
        )

    def play_segments(self, segments, interrupt: bool = True):
        """
        Queue already-synthesized segments for playback.

        This is useful for screen-reader integrations: synthesis can happen
        first, a cancellation/generation check can be performed, and only then
        can the prepared audio be queued.
        """
        if self._closed:
            raise RuntimeError("OLVAS engine is closed.")
        if self._player is None:
            self._player = StreamingAudioPlayer(
                sample_rate=self.playback_sample_rate
            )

        with self._speak_lock:
            if interrupt:
                self._player.stop()
            for kind, samples in segments:
                rate = (
                    self.playback_sample_rate
                    if kind == "speech"
                    else SAMPLE_RATE
                )
                self._player.play(samples, sample_rate=rate)

    def speak(self, text: str, interrupt: bool = True):
        """
        Synthesize and enqueue speech/audio segments.
        """
        segments = self.synthesize_segments(text)
        self.play_segments(segments, interrupt=interrupt)

    def cancel(self):
        """Immediately stop current speech and clear queued audio."""
        if self._player is not None:
            self._player.stop()

    def pause(self):
        if self._player is not None:
            self._player.pause()

    def resume(self):
        if self._player is not None:
            self._player.resume()

    def is_speaking(self) -> bool:
        return bool(self._player and self._player.is_playing())

    def wait(self):
        if self._player is not None:
            self._player.wait()

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._player is not None:
            self._player.close()
            self._player = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


def engine_demo():
    """
    Small manual API demo. Not used by normal CLI operation.
    """
    with OlvasEngine() as synth:
        synth.speak("Ez az OLVAS engine API próbája.")
        synth.wait()



# ---------------------------------------------------------------------------
# Prototype 0.8.2: user playback speed
# ---------------------------------------------------------------------------

MIN_SPEED = 0.50
MAX_SPEED = 2.00

def speed_to_sample_rate(speed: float) -> int:
    """
    Convert a playback-speed multiplier to the Windows/WAV sample rate.

      1.00 -> 8500 Hz
      1.20 -> 10200 Hz
      0.80 -> 6800 Hz

    This intentionally changes both duration and pitch, matching the user's
    requested sampling-rate style speed control.
    """
    speed = float(speed)
    if not (MIN_SPEED <= speed <= MAX_SPEED):
        raise ValueError(
            f"--speed must be between {MIN_SPEED:.2f} and {MAX_SPEED:.2f}"
        )
    return max(1000, round(SAMPLE_RATE * speed))


def main() -> int:
    here = Path(__file__).resolve().parent
    data = here / "data"
    asm = data / "OLVAS_P.ASM"
    raw_path = data / "RAWHUSR"
    szotar = data / "SZOTAR.TBL"

    ap = argparse.ArgumentParser(description="OLVAS Python prototype 0.2")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--phoneme")
    group.add_argument("--phonemes")
    group.add_argument("--text")
    group.add_argument("--stdin", action="store_true")
    ap.add_argument("--wav", type=Path)
    ap.add_argument("--no-play", action="store_true")
    ap.add_argument("--show-expanded", action="store_true",
                    help="Show number-expanded text before OLVAS conversion.")
    ap.add_argument("--show-conversion", action="store_true",
                    help="Print dictionary-normalized text and phoneme byte codes.")
    ap.add_argument("--list-table", action="store_true")
    ap.add_argument("--show-audio", action="store_true",
                    help="Show resolved embedded WAV/MP3 file paths.")
    ap.add_argument("--no-intonation", action="store_true",
                    help="Disable original OLVAS punctuation intonation.")
    ap.add_argument("--show-intonation", action="store_true",
                    help="Show phonemes whose playback speed is changed by intonation.")
    ap.add_argument("--legacy-playback", action="store_true",
                    help="Use the old temporary-WAV/winsound playback path.")
    ap.add_argument("--engine-api", action="store_true",
                    help="Use the reusable OlvasEngine API for text/stdin playback.")
    ap.add_argument("--speed", type=float, default=1.0,
                    help="Playback speed multiplier: 1.0 normal, 1.2 faster, 0.8 slower (0.5..2.0).")
    args = ap.parse_args()
    try:
        playback_sample_rate = speed_to_sample_rate(args.speed)
    except ValueError as exc:
        ap.error(str(exc))

    table = parse_audio_table(asm)
    raw = load_rawhusr(raw_path)

    if args.engine_api and (args.text is not None or args.stdin):
        api_text = sys.stdin.read() if args.stdin else args.text
        if args.no_play or args.wav:
            if args.stdin:
                raise RuntimeError(
                    "--engine-api with --stdin cannot currently be combined "
                    "with --wav or --no-play. Use the normal CLI path instead."
                )
            # Fall through for --text with export/no-play.
        else:
            with OlvasEngine(
                here,
                intonation=not args.no_intonation,
                show_audio=args.show_audio,
                show_intonation=args.show_intonation,
                speed=args.speed,
            ) as eng:
                eng.speak(api_text)
                eng.wait()
            return 0

    if args.list_table:
        for code in sorted(table):
            start, length, comment = table[code]
            label = chr(code) if 32 <= code < 127 else ""
            print(f"{code:3d} {label!r:4s} offset={start:5d} length={length:4d} {comment}")
        return 0

    if args.phoneme is not None:
        codes = parse_phoneme_token(args.phoneme)
        normalized = b""
    elif args.phonemes is not None:
        tokens = [t for t in re.split(r"[\s,]+", args.phonemes.strip()) if t]
        codes = []
        for t in tokens:
            codes.extend(parse_phoneme_token(t))
        normalized = b""
    else:
        text = sys.stdin.read() if args.stdin else args.text

        expanded_text = expand_numbers(text)

        if args.show_expanded:

            print("Input:   ", text.rstrip("\n"))

            print("Expanded:", expanded_text.rstrip("\n"))

        normalized, phoneme_bytes = dictionary_convert(expanded_text, asm, szotar)
        codes = list(phoneme_bytes)
        mixed_samples = synthesize_mixed_text(
            text, asm, szotar, raw, table, here, args.show_audio,
            not args.no_intonation, args.show_intonation
        )
        if args.show_conversion:
            print("Dictionary result:", decode_dos(normalized, errors="replace"))
            print("Phoneme codes:", " ".join(f"{x:02X}" for x in codes))

    if args.phoneme is None and args.phonemes is None:
        samples = mixed_samples
    else:
        samples = concatenate_codes(raw, table, codes)

    if args.wav:
        wav_path = args.wav.resolve()
        write_wav(wav_path, samples, playback_sample_rate)
        print(f"Wrote {len(samples)} samples to {wav_path} at {playback_sample_rate} Hz "
              f"({len(samples)/playback_sample_rate:.3f} s)")
    else:
        fd, name = tempfile.mkstemp(prefix="olvas_", suffix=".wav")
        import os
        os.close(fd)
        wav_path = Path(name)
        write_wav(wav_path, samples, playback_sample_rate)

    if not args.no_play:
        if args.legacy_playback:
            # Legacy whole-WAV mode necessarily applies --speed to the entire
            # mixed stream, including embedded audio.
            play_wav_windows(wav_path)
        elif args.phoneme is None and args.phonemes is None:
            # Normal text playback uses per-segment rates:
            # speech = selected --speed, embedded audio = normal speed.
            with OlvasEngine(
                here,
                intonation=not args.no_intonation,
                show_audio=args.show_audio,
                show_intonation=args.show_intonation,
                speed=args.speed,
            ) as eng:
                eng.speak(text)
                eng.wait()
        else:
            play_streaming_windows(samples, playback_sample_rate)

    if args.wav is None:
        try:
            wav_path.unlink()
        except OSError:
            pass
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
