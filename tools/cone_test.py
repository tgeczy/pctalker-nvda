# -*- coding: utf-8 -*-
"""Render one sentence through several speaker-cone settings, for listening.

Kiraly Jozsef, 2026-08-11, when asked whether the affricate click should be
left alone as authentic engine output or smoothed the way a real PC speaker
would have smoothed it:

    mivel emulációról van szó, azt hiszem elfogadható az a megoldás ami az
    eredeti hangminőséghez közelebbi megoldást ad, tehát figyelembe veszi a
    kis belső hangszóró elsimító hatását is

So the filter goes in.  What is NOT settled is how much, and that is an ear
question, not a metric -- every audible defect in this add-on so far was found
by ear and missed by measurement.  This writes the candidates side by side.

    py -3 tools/cone_test.py            all voices, all variants
    py -3 tools/cone_test.py speaker10  one voice

Output lands in work/cone/ as <voice>__<variant>.wav, at the engine's own rate
so nothing is confounded by resampling.  Levels are matched to the unfiltered
take, because an A/B where one side is quieter is not an A/B.
"""

import os
import struct
import sys
import wave

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENGINE = os.path.join(_ROOT, "addon", "synthDrivers", "_pctalker_engine")
for _p in (_ENGINE, os.path.join(_ENGINE, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pctalker_audio                                          # noqa: E402
import pctalker_engines                                        # noqa: E402

OUT_DIR = os.path.join(_ROOT, "work", "cone")

#: Affricates ("kutya" -- the ty is where the click lives), long vowels, and
#: numbers, which SPEAKER cannot say without pctalker_hunum.
TEXT = ("A kutya ugat, a karaván halad. Ötvenegy, hatvanhárom. "
        "Így beszélt a PC-TALKER ezerkilencszázkilencvenben.")

#: (label, (lowpass Hz, highpass Hz)).  None means no filtering at all -- what
#: ships today.  The high-pass models the bass a 2-inch cone cannot make; it is
#: physically real but it thins the voice, so it is offered separately rather
#: than assumed.
VARIANTS = [
    ("0-raw",          None),
    ("1-lp5000",       (5000.0, 0.0)),
    ("2-lp4200",       (4200.0, 0.0)),
    ("3-lp3500",       (3500.0, 0.0)),
    ("4-lp4200-hp400", (4200.0, 400.0)),
    ("5-lp3500-hp500", (3500.0, 500.0)),
    ("6-SHIPPING",     None),           # filled in from SPEAKER_CONE below
]
VARIANTS[-1] = ("6-SHIPPING", pctalker_engines.SPEAKER_CONE)


def render(voice):
    """Synthesize TEXT once, returning (16-bit PCM, rate) unfiltered."""
    blocks, rate = [], [None]

    def on_block(pcm8, r):
        rate[0] = r
        blocks.append(voice.to_pcm16(pcm8))

    for piece in voice.split(TEXT):
        voice.speak(piece, on_block=on_block)
    return b"".join(blocks), (rate[0] or 18356)


def rms(pcm16):
    n = len(pcm16) // 2
    if not n:
        return 0.0
    vals = struct.unpack("<%dh" % n, pcm16)
    return (sum(float(v) * v for v in vals) / n) ** 0.5


def peak(pcm16):
    v = struct.unpack("<%dh" % (len(pcm16) // 2), pcm16)
    return max(max(v), -min(v)) if v else 0


def clip_count(pcm16):
    """Samples sitting on a rail -- the filter overshoots, so this matters."""
    v = struct.unpack("<%dh" % (len(pcm16) // 2), pcm16)
    return sum(1 for x in v if x >= 32767 or x <= -32768)


def scaled(pcm16, gain):
    n = len(pcm16) // 2
    vals = struct.unpack("<%dh" % n, pcm16)
    out = [max(-32768, min(32767, int(v * gain))) for v in vals]
    return struct.pack("<%dh" % n, *out)


def write_wav(path, pcm16, rate):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(rate))
        w.writeframes(pcm16)


def continuity_check(pcm16, rate):
    """Filtering in blocks must equal filtering in one go, byte for byte.

    The resampler and the trimmer both carry state across blocks for exactly
    this reason; a filter that reset per block would put a step at every block
    boundary, which is the click we are trying to remove.  Cheap to assert, and
    this codebase has shipped that bug twice in other guises.
    """
    cone = pctalker_engines.SPEAKER_CONE
    whole = pctalker_audio.SpeakerCone(rate, *cone).feed(pcm16)
    split = pctalker_audio.SpeakerCone(rate, *cone)
    out, step = [], 4096
    for i in range(0, len(pcm16), step):
        out.append(split.feed(pcm16[i:i + step]))
    return whole == b"".join(out)


def main():
    wanted = sys.argv[1:] or None
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    registry = pctalker_engines.build_registry()
    if not registry:
        print("no engines available in", _ENGINE)
        return 1

    checked = False
    for vid, voice in registry.items():
        if wanted and vid not in wanted:
            continue
        if not voice.cone:
            print("%-14s no cone (real DAC) -- skipped" % vid)
            continue
        print("%-14s rendering..." % vid, end=" ", flush=True)
        raw, rate = render(voice)
        base = rms(raw)
        print("%d samples at %d Hz, rms %.0f" % (len(raw) // 2, rate, base))

        if not checked:
            ok = continuity_check(raw, rate)
            print("%-14s block continuity: %s" % ("", "OK" if ok else "BROKEN"))
            if not ok:
                return 2
            checked = True

        for label, cone in VARIANTS:
            data = raw if cone is None else \
                pctalker_audio.SpeakerCone(rate, *cone).feed(raw)
            level = rms(data)
            # The candidates are level-matched so the comparison is about
            # timbre; the shipping setting is written at its REAL level,
            # because that is the one whose loudness has to live next to 5.01.
            shipping = label.endswith("SHIPPING")
            gain = 1.0 if shipping else ((base / level) if level else 1.0)
            out = scaled(data, gain)
            clipped = clip_count(out)
            path = os.path.join(OUT_DIR, "%s__%s.wav" % (vid, label))
            write_wav(path, out, rate)
            print("    %-16s rms %6.0f  gain %.2fx  peak %6d  clipped %d%s"
                  % (label, level, gain, peak(out), clipped,
                     "  <-- SHIPPING" if shipping else ""))
            if shipping and clipped:
                print("       *** the shipped setting CLIPS -- lower the "
                      "gain in SPEAKER_CONE ***")
    print("\nwrote to", OUT_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
