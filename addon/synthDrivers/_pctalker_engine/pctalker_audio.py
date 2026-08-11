# -*- coding: utf-8 -*-
"""Audio helpers shared by every engine in this add-on.

Both engines produce the same thing -- a stream of 8-bit unsigned samples at a
rate nobody's sound card wants -- so conversion, resampling and text chunking
belong here rather than in either one.  PC-TALKER 5.01 writes its bytes to the
Sound Blaster's direct DAC at 9178 Hz; SPEAKER 1.0 writes pulse widths to PIT
channel 2 at 18356 Hz.  After this module they are indistinguishable.
"""

import struct


def to_pcm16(pcm8, zero=128, shift=8):
    """Unsigned samples -> 16-bit signed, centred on `zero`.

    The two engines do not agree on where silence sits.  PC-TALKER 5.01 writes
    a full 8-bit byte to the Sound Blaster DAC, so silence is 128.  SPEAKER's
    interrupt handler halves every sample before it reaches the PWM
    (`shr al,1`), so its stream is SEVEN bits centred on 64 -- converting it as
    if it were 128 puts the entire waveform below zero with a DC offset of
    about -16500, and every time the audio stream starts or stops the speaker
    steps to that offset and back.  That is audible as a click at the joins,
    which is exactly how Kiraly reported it.
    """
    out = bytearray(len(pcm8) * 2)
    for i, b in enumerate(pcm8):
        v = (b - zero) << shift
        if v > 32767:
            v = 32767
        elif v < -32768:
            v = -32768
        out[i * 2] = v & 0xFF
        out[i * 2 + 1] = (v >> 8) & 0xFF
    return bytes(out)


def apply_gain(data, gain):
    """Scale 16-bit PCM in place-ish.  `gain` of 1.0 returns the input."""
    if gain == 1.0 or not data:
        return data
    n = len(data) // 2
    vals = struct.unpack("<%dh" % n, data)
    return struct.pack("<%dh" % n,
                       *[max(-32768, min(32767, int(v * gain))) for v in vals])


class EdgeTrimmer(object):
    """Drop the silence an engine emits before and after an utterance.

    Every one of these programs pads: about 63 ms of dead air before the first
    sound, and READSPF another 49 ms after the last.  On its own that is
    nothing, but NVDA speaks in short bursts -- a word, a line, a character --
    and paying it on every burst is what makes continuous reading sound broken
    up.

    Silence INSIDE the utterance is kept: those are the pauses the synthesizer
    put there on purpose.  Only the run at the very start and the run still
    outstanding at the end are removed, which is why quiet samples are held
    back rather than dropped -- if speech follows them they were a real pause,
    and they get emitted after all.
    """

    #: Quiet samples kept immediately before the first sound, in samples at
    #: 18356 Hz -- about 3 ms.  Cutting exactly at the onset makes the block
    #: begin at whatever amplitude the speech happens to start on, and against
    #: the previous chunk's last sample that step is a click.  A few samples of
    #: real silence give the waveform somewhere to start from.
    LEAD_IN = 55

    #: Length of the fade applied to the first sound of an utterance, in
    #: samples at 18356 Hz -- about 2 ms.  Keeping a little silence is not
    #: enough on its own: if the utterance opens on a plosive the waveform
    #: still jumps from nothing to full amplitude in one sample, and that step
    #: is heard as a chop partway into the word.  Ramping in removes the step
    #: without softening anything audible; 2 ms is far below a syllable.
    FADE_IN = 36

    def __init__(self, zero=128, tol=2):
        self.zero = zero
        self.tol = tol
        self.started = False
        self.pending = bytearray()
        self.leadin = bytearray()
        self.faded = 0

    def feed(self, pcm8):
        out = bytearray()
        zero, tol = self.zero, self.tol
        for b in pcm8:
            quiet = -tol <= b - zero <= tol
            if not self.started:
                if quiet:
                    # remember only the last few, as a soft place to begin
                    self.leadin.append(b)
                    if len(self.leadin) > self.LEAD_IN:
                        del self.leadin[0]
                    continue
                self.started = True
                if self.leadin:
                    out += self.leadin
                    del self.leadin[:]
            if quiet:
                self.pending.append(b)
            else:
                if self.pending:
                    out += self.pending
                    del self.pending[:]
                out.append(b)
        return self._fade(out)

    def _fade(self, buf):
        """Ramp the opening samples up from silence, once per utterance."""
        n = self.FADE_IN
        if self.faded >= n or not buf:
            return bytes(buf)
        zero = self.zero
        done = self.faded
        for i in range(len(buf)):
            if done >= n:
                break
            buf[i] = int(zero + (buf[i] - zero) * (done / float(n)))
            done += 1
        self.faded = done
        return bytes(buf)


class Resampler(object):
    """Streaming linear resampler for 16-bit mono.

    Carries phase and the last sample across calls, so feeding audio in blocks
    gives the same continuous result as converting the whole utterance at once
    -- resampling each block independently would leave a discontinuity, and
    therefore a click, at every boundary.
    """

    def __init__(self, src_rate, dst_rate, speed=1.0):
        self.dst_rate = float(dst_rate)
        self.speed = float(speed)
        self.src_rate = float(src_rate)
        self.ratio = (self.src_rate / self.dst_rate) * self.speed
        self.pos = 0.0
        self.prev = 0

    def set_source_rate(self, src_rate):
        """Follow a source rate that moves while the utterance is playing.

        PC-TALKER 5.01 does not settle on its final PIT divisor immediately, so
        the first blocks of the first utterance arrive at a rate that then
        changes.  Fixing the ratio at the first block leaves those blocks
        resampled wrongly, which is heard as the pitch wobbling before it
        steadies.  Phase and the carried sample are kept, so following the rate
        costs nothing at the join.
        """
        if float(src_rate) == self.src_rate:
            return
        self.src_rate = float(src_rate)
        self.ratio = (self.src_rate / self.dst_rate) * self.speed

    def feed(self, pcm16):
        if not pcm16:
            return b""
        n = len(pcm16) // 2
        src = struct.unpack("<%dh" % n, pcm16)
        out = []
        pos, prev = self.pos, self.prev
        while pos < n:
            i = int(pos)
            frac = pos - i
            a = prev if i == 0 else src[i - 1]
            b = src[i]
            out.append(int(a + (b - a) * frac))
            pos += self.ratio
        self.pos = pos - n
        self.prev = src[n - 1]
        return struct.pack("<%dh" % len(out), *out) if out else b""


def split_text(text, limit=200, encoding="cp852"):
    """Chunk text so an engine's internal buffer limit never truncates it.

    Prefers sentence ends, then any whitespace, and only cuts mid-word when a
    single run is longer than the limit.  Both engines clamp silently, so this
    is what keeps the end of a long line from simply vanishing.
    """
    text = " ".join(text.split())
    if not text:
        return []
    out = []
    while text:
        if len(encode(text, encoding)) <= limit:
            out.append(text)
            break
        cut = limit
        while cut > 1 and len(encode(text[:cut], encoding)) > limit:
            cut -= 1
        piece = text[:cut]
        idx = max(piece.rfind(". "), piece.rfind("! "), piece.rfind("? "))
        if idx < limit // 3:
            idx = piece.rfind(" ")
        if idx <= 0:
            idx = cut - 1
        else:
            idx += 1
        out.append(text[:idx].strip())
        text = text[idx:].strip()
    return [p for p in out if p]


# -- Hungarian text encoding ----------------------------------------------
#
# The two engines do NOT agree on how Hungarian is spelled in bytes, and the
# difference is a year of history.  PC-TALKER 5.01 (1991) is happy with CP852,
# the IBM Latin-2 page that arrived with DOS 5.  SPEAKER (1990) predates it and
# expects CWI-2, the Hungarian page in general use before CP852 existed: CP437
# with the two double-acute letters occupying the circumflex slots, because
# Hungarian never needs o-circumflex or u-circumflex.
#
# This is not a guess.  Király's own demo text REKLAMSP uses byte 93h inside
# lehetővé, tetszőleges and minőségileg -- real Hungarian words -- and 93h is
# o-circumflex in CP852, which is not a Hungarian letter at all.  Feeding CP852
# to SPEAKER puts 8Bh where 93h belongs, and 8Bh has no speech element: the
# long vowel comes out as a click.
#
# CP437 has no uppercase accented vowels beyond É, Ö and Ü, so the rest fold to
# their lowercase byte.  Nothing is lost: these engines speak words, not case.
_CWI2 = {
    "á": 0xA0, "é": 0x82, "í": 0xA1, "ó": 0xA2, "ö": 0x94,
    "ő": 0x93, "ú": 0xA3, "ü": 0x81, "ű": 0x96,
    "Á": 0xA0, "É": 0x90, "Í": 0xA1, "Ó": 0xA2, "Ö": 0x99,
    "Ő": 0x93, "Ú": 0xA3, "Ü": 0x9A, "Ű": 0x96,
}


def encode(text, encoding="cp852"):
    """Text -> the bytes the engine expects.  `encoding` may be "cwi2"."""
    if isinstance(text, bytes):
        return text
    if encoding != "cwi2":
        return text.encode(encoding, "replace")
    out = bytearray()
    for ch in text:
        b = _CWI2.get(ch)
        if b is not None:
            out.append(b)
            continue
        try:
            out += ch.encode("cp437")
        except UnicodeEncodeError:
            out.append(0x3F)                    # "?"
    return bytes(out)
