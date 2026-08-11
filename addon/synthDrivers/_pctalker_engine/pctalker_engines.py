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
        """Last chance to rewrite text into something the engine can say."""
        return text

    def to_pcm16(self, pcm8):
        return pctalker_audio.to_pcm16(pcm8, self.pcm_zero, self.pcm_shift)

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
        self.engine.speak(self.encode(text), on_block=on_block,
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
        return pctalker_hunum.expand(text)

    def speak(self, text, on_block, should_cancel=None):
        engine = self.engine
        rate = engine.rate
        engine.speak(self.encode(text), on_block=lambda pcm8: on_block(pcm8, rate),
                     should_cancel=should_cancel)


VOICES = (Speaker10, PCTalker501)

#: SPEAKER is the default deliberately: it is the cleaner voice, having no
#: smoothing stage and therefore no echo.  Stated rather than inferred from
#: dict order, because it is the most user-visible decision in the add-on.
DEFAULT_VOICE = Speaker10.id


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
