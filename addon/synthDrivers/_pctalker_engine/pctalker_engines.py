# -*- coding: utf-8 -*-
"""The engines this add-on can speak with, behind one interface.

Two of Kiraly Jozsef's synthesizers ship here, and they are built completely
differently: PC-TALKER 5.01 is a resident driver called through INT F1h and
captured as a memory snapshot, while SPEAKER 1.0 is an ordinary DOS program
that has to be loaded and run.  One writes bytes to a Sound Blaster DAC, the
other writes pulse widths to the PC speaker's timer.

The driver should not have to know any of that.  Everything above this module
sees a voice with an id, a label and a `speak()` that streams 8-bit samples.

Adding a third engine means adding a class here and a line to VOICES.
"""

import os

import pctalker_audio

_HERE = os.path.dirname(os.path.abspath(__file__))

#: Corner frequencies of the PC speaker cone model, in Hz, as (lowpass,
#: highpass).  Both speaker voices share it because it describes the HARDWARE,
#: not the engine -- the same little speaker played all of these.  A highpass of
#: 0 disables that stage.  See pctalker_audio.SpeakerCone for why this exists.
#:
#: Chosen by ear from six candidates, 2026-08-13: the one that sounded like a
#: speaker CONE rather than merely less harsh.  The high-pass is what does that
#: -- a two-inch cone in a plastic can has no bass, and leaving it out left the
#: voice a body the original never had.  It costs about 5 dB, but 5.01 turns out
#: to be a quiet engine (speech RMS 3917 against 5115 here), so these still land
#: about 2 dB above it and switching voices does not jump.
#:
#: 4200 Hz cuts the worst sample-to-sample jump from 192% of full scale to 112%
#: (tools/cone_measure.py).  0.82 is headroom, not taste -- see SpeakerCone.
SPEAKER_CONE = (4200.0, 400.0, 0.82)


class EngineError(RuntimeError):
    pass


class Voice(object):
    """One selectable voice, and the engine behind it.

    The engine is built on first use rather than at import: loading both would
    cost start-up time for a voice the user may never select, and a missing
    data file should disable one voice, not the whole synthesizer.
    """

    id = None
    label = None
    language = "hu"
    #: Longest text the engine will accept in one call, in encoded bytes.
    chunk = 200
    #: How this engine spells Hungarian.  See pctalker_audio.encode.
    encoding = "cp852"
    #: Where silence sits in this engine's sample stream, and how far to shift
    #: to fill 16 bits.  Getting it wrong is a DC offset, heard as a click.
    pcm_zero = 128
    pcm_shift = 8
    #: Response of the thing this engine actually drove, as (lowpass, highpass)
    #: in Hz, or None for a voice that went through a real DAC.  See
    #: pctalker_audio.SpeakerCone -- reproducing the captured bytes exactly is
    #: the less faithful choice for a voice that came out of a PC speaker.
    cone = None

    def __init__(self):
        self._engine = None

    # -- lifecycle ---------------------------------------------------------
    def available(self):
        raise NotImplementedError

    def _build(self):
        raise NotImplementedError

    @property
    def engine(self):
        if self._engine is None:
            self._engine = self._build()
        return self._engine

    def reset(self):
        self._engine = None

    # -- speech ------------------------------------------------------------
    def split(self, text):
        return pctalker_audio.split_text(self.preprocess(text), self.chunk,
                                         self.encoding)

    def encode(self, text):
        return pctalker_audio.encode(text, self.encoding)

    def preprocess(self, text):
        """Last chance to rewrite text into something the engine can say.

        All three of these are word readers, so a bare consonant produces
        nothing (or, on 5.01, the wrong thing -- its exception dictionary reads
        `t` as *tonna*).  NVDA sends single characters constantly, so every
        voice gets Hungarian letter names.
        """
        import pctalker_hulet
        return pctalker_hulet.expand(text)

    def to_pcm16(self, pcm8):
        return pctalker_audio.to_pcm16(pcm8, self.pcm_zero, self.pcm_shift)

    def make_filter(self, rate):
        """A per-utterance output filter for this voice, or None.

        Built per utterance rather than per voice because it carries state:
        one shared filter would leak the tail of one utterance into the head
        of the next.  The rate is not known until the first block arrives.
        """
        if not self.cone:
            return None
        return pctalker_audio.SpeakerCone(rate, *self.cone)

    def _trimmed(self, on_block):
        """Wrap a block sink so the padding around each utterance is dropped."""
        trimmer = pctalker_audio.EdgeTrimmer(self.pcm_zero)

        def sink(pcm8, rate):
            data = trimmer.feed(pcm8)
            if data:
                on_block(data, rate)
        return sink

    def speak(self, text, on_block, should_cancel=None):
        """Synthesize `text`, calling `on_block(pcm8, rate)` as audio appears."""
        raise NotImplementedError


class PCTalker501(Voice):
    """The 1991 Sound Blaster engine, run from a snapshot of the resident TSR.

    Its concatenated voice elements are joined by a smoothing stage, which is
    audible as a slight room echo.  The `#vnnnn` reverb command documented in
    the 1991 manual only ADDS to that -- it cannot take it away -- so it is not
    exposed as a setting.
    """

    id = "pctalker501"
    label = "PC-TALKER 5.01 (1991) - Sound Blaster"
    chunk = 200

    def available(self):
        return os.path.isfile(os.path.join(_HERE, "engine.bin"))

    def _build(self):
        import pctalker_core
        return pctalker_core.Engine(os.path.join(_HERE, "engine.bin"))

    def speak(self, text, on_block, should_cancel=None):
        self.engine.speak(self.encode(text), on_block=self._trimmed(on_block),
                          should_cancel=should_cancel)


class Speaker10(Voice):
    """The 1990 PC speaker engine, the original `OLVASSP.EXE` run as a program.

    No sound card and no smoothing stage, which is why it is the cleaner of the
    two by ear.  It is also the older voice: the recordings it is assembled
    from are dated 1989, the banner is Copyright 1990, and the binary itself
    27 January 1991.
    """

    id = "speaker10"
    label = "SPEAKER 1.0 (1990) - PC speaker"
    #: Matches the engine's own buffer; see MAX_TEXT in pctalker_speaker.
    chunk = 120
    #: Predates CP852; see pctalker_audio.  Getting this wrong is audible as a
    #: click where a long vowel should be.
    encoding = "cwi2"
    #: The ISR halves every sample (`shr al,1`) before writing the PWM, so this
    #: stream is 7-bit centred on 64.
    pcm_zero = 64
    pcm_shift = 9
    #: It came out of the PC speaker, so it is filtered like one.
    cone = SPEAKER_CONE

    def available(self):
        return os.path.isfile(os.path.join(_HERE, "OLVASSP.EXE"))

    def _build(self):
        import pctalker_speaker
        return pctalker_speaker.Engine()

    def preprocess(self, text):
        """This engine has no digit elements at all -- see pctalker_hunum.

        `51` renders zero samples, which is why a slider announcing its value
        sounded like an empty control.  5.01 needs none of this; it grew number
        handling in 1991.
        """
        import pctalker_hunum
        return pctalker_hunum.expand(super(Speaker10, self).preprocess(text))

    def speak(self, text, on_block, should_cancel=None):
        engine = self.engine
        rate = engine.rate
        sink = self._trimmed(on_block)
        engine.speak(self.encode(text), on_block=lambda pcm8: sink(pcm8, rate),
                     should_cancel=should_cancel)



class Readspf1990(Voice):
    """The earliest of the three, and the one that needs no help.

    `READSPF.EXE`, 18 March 1990 -- the build the author's own `READSPF.ASM`
    describes.  It reads standard input directly and speaks numbers by itself,
    so it needs neither the command-tail trick the 1991 build requires nor the
    Hungarian numeral expansion.  Same voice, same 18356 Hz, no smoothing echo.
    """

    id = "readspf1990"
    label = "READSPF (1990) - PC speaker"
    chunk = 200
    encoding = "cwi2"
    pcm_zero = 64
    pcm_shift = 9
    cone = SPEAKER_CONE

    def available(self):
        return os.path.isfile(os.path.join(_HERE, "READSPF.EXE"))

    def _build(self):
        import pctalker_speaker
        return pctalker_speaker.StdinEngine()

    def speak(self, text, on_block, should_cancel=None):
        engine = self.engine
        rate = engine.rate
        sink = self._trimmed(on_block)
        engine.speak(self.encode(text),
                     on_block=lambda pcm8: sink(pcm8, rate),
                     should_cancel=should_cancel)


#: WITHDRAWN, not removed, at the author's request on 2026-08-14.  He reported
#: the two speaker voices as "nem folyamatos, szakadozo" -- not continuous,
#: broken up -- and he is right.  Measured on one machine, warmed:
#:
#:     PC-TALKER 5.01   5.0x faster than real time, first block 22 ms
#:     READSPF          1.7x                        first block 72 ms
#:     SPEAKER 1.0      1.8x                        first block 72 ms
#:
#: A 1.7x margin does not survive a slower machine, a Say All, or any load:
#: the player runs dry and speech breaks up.  5.01's 5x does.  The cause is
#: structural rather than mysterious -- the speaker engines halt once per
#: SAMPLE, so they make ~18356 round trips into Python per second of audio,
#: twice the rate 5.01 needs and at a higher cost each.  The per-sample loop
#: still does a ctypes mem_read to probe for HLT and two float divisions every
#: iteration; all three are cacheable.
#:
#: The classes stay, the engines stay, tools/ still drives them.  Put them back
#: in this tuple when the pump loop is fast enough to deserve it.
_WITHDRAWN = (Readspf1990, Speaker10)

#: Ordered by date, so the voice list reads as a lineage.
VOICES = (PCTalker501,)

#: The Sound Blaster build is the default, at the author's request (2026-08-11):
#: on his machine the speaker voices still did not match what he remembers, and
#: 5.01 is the one that reaches a new user sounding the way it should.  The other
#: two stay in the list -- he asked for them to be withdrawn while the speaker
#: output was wrong, not removed, and the cone model above is that fix.
#: Stated rather than inferred from dict order, because it is the most
#: user-visible decision in this file.
DEFAULT_VOICE = PCTalker501.id


def default_voice(registry):
    """The voice to start with: the preferred one if present, else any."""
    if DEFAULT_VOICE in registry:
        return DEFAULT_VOICE
    return next(iter(registry))


def build_registry():
    """Instantiate every voice whose data files are actually present."""
    out = {}
    for cls in VOICES:
        v = cls()
        if v.available():
            out[v.id] = v
    return out
