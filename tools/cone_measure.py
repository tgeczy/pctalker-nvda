# -*- coding: utf-8 -*-
"""What the cone filter actually does, measured the way the ear hears it.

RMS is useless here: a low-pass at 3500 Hz changes the level of this material
by about 2%, because speech energy lives at the bottom and the click does not
carry energy -- it carries a STEP.  The number that matters is slew: how far
the waveform moves between one sample and the next.  A 125 -> 2 jump in 54
microseconds is inaudible as loudness and unmistakable as a tick.

    py -3 tools/cone_measure.py
"""

import os
import struct
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ENGINE = os.path.join(_ROOT, "addon", "synthDrivers", "_pctalker_engine")
for _p in (_ENGINE, os.path.join(_ENGINE, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pctalker_audio                                          # noqa: E402
import pctalker_engines                                        # noqa: E402

TEXT = ("A kutya ugat, a karaván halad. Ötvenegy, hatvanhárom. "
        "Így beszélt a PC-TALKER ezerkilencszázkilencvenben.")

VARIANTS = [
    ("raw",          None),
    ("lp5000",       (5000.0, 0.0)),
    ("lp4200",       (4200.0, 0.0)),
    ("lp3500",       (3500.0, 0.0)),
    ("lp2800",       (2800.0, 0.0)),
]

FULL = 32768.0


def unpack(pcm16):
    return struct.unpack("<%dh" % (len(pcm16) // 2), pcm16)


def slew_profile(vals):
    """Max and tail-percentile jump between adjacent samples, as % of full."""
    d = sorted(abs(vals[i] - vals[i - 1]) for i in range(1, len(vals)))
    n = len(d)
    return {
        "max": 100.0 * d[-1] / FULL,
        "p99.9": 100.0 * d[int(n * 0.999)] / FULL,
        "p99": 100.0 * d[int(n * 0.99)] / FULL,
        "over25pct": sum(1 for v in d if v > 0.25 * FULL),
    }


def main():
    registry = pctalker_engines.build_registry()
    voice = registry.get("readspf1990") or registry.get("speaker10")
    if voice is None or not voice.cone:
        print("no speaker voice available")
        return 1

    blocks, rate = [], [None]

    def on_block(pcm8, r):
        rate[0] = r
        blocks.append(pcm8)

    for piece in voice.split(TEXT):
        voice.speak(piece, on_block=lambda p, r: on_block(p, r))
    pcm8 = b"".join(blocks)
    rate = rate[0] or 18356

    # How much of the stream is a repeat of the previous sample?  The PWM runs
    # at twice the audio rate, so a clean zero-order-hold would be ~50%.
    same = sum(1 for i in range(1, len(pcm8)) if pcm8[i] == pcm8[i - 1])
    print("engine: %s at %d Hz, %d bytes" % (voice.id, rate, len(pcm8)))
    print("  8-bit range %d..%d, repeats previous sample %.1f%% of the time"
          % (min(pcm8), max(pcm8), 100.0 * same / (len(pcm8) - 1)))
    raw16 = voice.to_pcm16(pcm8)

    print("\n%-10s %8s %8s %8s %10s" %
          ("variant", "max%", "p99.9%", "p99%", "jumps>25%"))
    for label, cone in VARIANTS:
        data = raw16 if cone is None else \
            pctalker_audio.SpeakerCone(rate, cone[0], cone[1]).feed(raw16)
        s = slew_profile(unpack(data))
        print("%-10s %8.1f %8.1f %8.1f %10d"
              % (label, s["max"], s["p99.9"], s["p99"], s["over25pct"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
