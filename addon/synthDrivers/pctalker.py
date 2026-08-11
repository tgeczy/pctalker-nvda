# -*- coding: utf-8 -*-
"""NVDA synthesizer driver for Kiraly Jozsef's PC-TALKER family.

Two of his engines are selectable as voices, both running under Unicorn inside
NVDA's own process -- no DOSBox, no external program, no DOS:

    SPEAKER 1.0 (1990)    the PC speaker build, `OLVASSP.EXE` run as a program
    PC-TALKER 5.01 (1991) the Sound Blaster build, a snapshot of the resident TSR

The driver itself knows nothing about either: `_pctalker_engine/engines.py`
presents them behind one interface, and audio arrives here as 8-bit samples
with a rate attached.  Adding a third engine does not touch this file.
"""

import os
import sys
import threading
import queue

import nvwave
import synthDriverHandler
from synthDriverHandler import SynthDriver, VoiceInfo, synthIndexReached, synthDoneSpeaking
from logHandler import log
import speech.commands

_HERE = os.path.dirname(__file__)
_ENGINE_DIR = os.path.join(_HERE, "_pctalker_engine")
_LIB = os.path.join(_ENGINE_DIR, "lib")
for _p in (_ENGINE_DIR, _LIB):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pctalker_audio                 # noqa: E402  (from _pctalker_engine, via sys.path)
import pctalker_engines                # noqa: E402

#: nvwave is happiest with a common rate; the engine's 9178 Hz is not one.
OUT_RATE = 22050

# Reverb ("visszhangosítás") is deliberately NOT a setting.  The 1991 manual
# documents a `#vnnnn` command embedded in the text, default 250, and it does
# change the rendered bytes -- but listening tests showed it only ADDS delay on
# top of an echo that is already there.  5.01's echo comes from the smoothing
# stage that joins its concatenated voice elements, so no value of `#v` can
# remove it; the slider would only ever make things worse.  That is also why
# SPEAKER 1.0 sounds cleaner: it has no smoothing stage at all.


class SynthDriver(SynthDriver):
    name = "pctalker"
    #: Kiraly Jozsef asked, 2026-08-11, that the synthesizer list show
    #: "- Hungarian -" here rather than his name.
    description = "PC-TALKER - Hungarian -"

    # NOTE: the reverb setting is deliberately NOT exposed yet.  `#vnnnn` is
    # documented in the 1991 manual under OLVAS, and it is not established that
    # OLVRES honours it: changing the value alters the rendered bytes, but by ear
    # it produced echo pile-up rather than a clean reverb control.  Until that is
    # understood, the driver must not inject anything into the text stream.
    supportedSettings = (
        SynthDriver.VoiceSetting(),
        SynthDriver.RateSetting(),
        SynthDriver.VolumeSetting(),
    )
    supportedCommands = {speech.commands.IndexCommand}
    supportedNotifications = {synthIndexReached, synthDoneSpeaking}

    @classmethod
    def check(cls):
        return bool(pctalker_engines.build_registry())

    def __init__(self):
        super().__init__()
        self._rate = 50
        self._volume = 100
        self._voices = pctalker_engines.build_registry()
        if not self._voices:
            raise RuntimeError("no PC-TALKER engine data found in %s" % _ENGINE_DIR)
        self._voiceId = pctalker_engines.default_voice(self._voices)
        self._player = self._makePlayer()
        self._queue = queue.Queue()
        self._cancelFlag = threading.Event()
        self._stopped = False
        self._worker = threading.Thread(target=self._run, name="pctalker", daemon=True)
        self._worker.start()

    def _makePlayer(self):
        """Build the WavePlayer across NVDA config generations.

        NVDA 2025.1 moved the output device: config.conf["speech"]["outputDevice"]
        was REMOVED in favour of config.conf["audio"]["outputDevice"] (a string
        endpoint id), and WASAPI became mandatory.  Each attempt has to be a
        callable -- building the argument dicts up front would evaluate every
        config lookup before the first try: block could catch anything.
        """
        import config
        base = dict(channels=1, samplesPerSec=OUT_RATE, bitsPerSample=16)
        try:
            from nvwave import AudioPurpose
            purpose = {"purpose": AudioPurpose.SPEECH}
        except Exception:
            purpose = {}

        def modern():        # 2025.1 and later
            return nvwave.WavePlayer(
                outputDevice=config.conf["audio"]["outputDevice"], **base, **purpose)

        def legacy():        # 2024.x and earlier
            return nvwave.WavePlayer(
                outputDevice=config.conf["speech"]["outputDevice"], **base)

        def default():       # let NVDA pick the device
            return nvwave.WavePlayer(**base, **purpose)

        def bare():
            return nvwave.WavePlayer(1, OUT_RATE, 16)

        last = None
        for attempt in (modern, legacy, default, bare):
            try:
                return attempt()
            except Exception as e:
                last = e
        raise last

    # -- NVDA interface ----------------------------------------------------
    def speak(self, speechSequence):
        items = []
        for item in speechSequence:
            if isinstance(item, str):
                items.append(("text", item))
            elif isinstance(item, speech.commands.IndexCommand):
                items.append(("index", item.index))
        self._queue.put(items)

    def cancel(self):
        self._cancelFlag.set()
        try:
            self._player.stop()
        except Exception:
            pass
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def pause(self, switch):
        # The engine has real pause/resume (AH=1 / AH=2, per the 1991 manual), but
        # rendering runs ~5x faster than playback, so by the time the user pauses
        # the utterance is usually already synthesized and sitting in the player.
        # Pause both: the player is what the listener hears, the engine call
        # matters only when a long piece is still being rendered.
        # AH=1/AH=2 exist and work, but rendering runs ~5x faster than playback,
        # so by the time the user pauses the audio is already in the player.
        # Pausing the player is what the listener actually hears; calling into
        # the engine here adds a variable for no benefit.
        try:
            self._player.pause(switch)
        except Exception:
            pass

    def terminate(self):
        self._stopped = True
        self.cancel()
        self._queue.put(None)
        try:
            self._player.close()
        except Exception:
            pass

    # -- settings ----------------------------------------------------------
    def _get_rate(self):
        return self._rate

    def _set_rate(self, value):
        self._rate = max(0, min(100, int(value)))

    def _get_volume(self):
        return self._volume

    def _set_volume(self, value):
        self._volume = max(0, min(100, int(value)))

    @property
    def _speed(self):
        """Playback speed multiplier.

        The engine has no rate control of its own -- it speaks at whatever
        the PIT divisor gives -- so rate is applied by resampling, exactly
        as a tape-speed control would.  Pitch moves with it; that is honest
        for this engine rather than a defect.

        The midpoint MUST be 1.0 so the default setting reproduces the engine
        exactly: anything else and NVDA plays PC-TALKER at the wrong pitch
        out of the box.

        The range is deliberately narrow.  It was 0.6x..1.4x, and at the ends
        that is not a rate control any more -- 0 is a tape running flat and 100
        is a chipmunk, because the pitch moves with it.  +/-18% is as far as
        this can go while still sounding like the same person talking.
        """
        return 0.82 + (self._rate / 100.0) * 0.36    # 0.82x .. 1.18x, 50 -> 1.0

    # -- worker ------------------------------------------------------------
    def _run(self):
        while not self._stopped:
            job = self._queue.get()
            if job is None:
                break
            self._cancelFlag.clear()
            try:
                self._speakJob(job)
            except Exception:
                # This thread must survive anything.  If it dies the synthesizer
                # goes permanently silent with no way back short of restarting
                # NVDA -- a far worse outcome than one lost utterance.  The
                # engine is rebuilt either way: a fault leaves emulation stopped
                # part-way through, and both engines rebuild in milliseconds.
                log.error("PC-TALKER speech failed; rebuilding engine",
                          exc_info=True)
                try:
                    self._voice.reset()
                except Exception:
                    log.error("PC-TALKER engine rebuild failed", exc_info=True)
            if not self._cancelFlag.is_set():
                synthDoneSpeaking.notify(synth=self)

    def _speakJob(self, items):
        for kind, value in items:
            if self._cancelFlag.is_set():
                return
            if kind == "index":
                synthIndexReached.notify(synth=self, index=value)
                continue
            # One resampler for the whole utterance.  Building a fresh one per
            # chunk restarts its phase and drops the sample it was carrying,
            # which is a discontinuity -- and therefore a click -- at every
            # chunk boundary in the middle of a sentence.
            state = {"resampler": None}
            for piece in self._voice.split(value):
                if self._cancelFlag.is_set():
                    return
                self._speakPiece(piece, state)

    def _speakPiece(self, piece, state):
        gain = self._volume / 100.0
        voice = self._voice

        def on_block(pcm8, rate):
            if self._cancelFlag.is_set():
                return
            if state["resampler"] is None:
                state["resampler"] = pctalker_audio.Resampler(
                    rate, OUT_RATE, self._speed)
            data = pctalker_audio.apply_gain(
                state["resampler"].feed(voice.to_pcm16(pcm8)), gain)
            if data:
                self._player.feed(data)

        # `#vnnnn` persists in the engine until changed, so only emit it when the
        # value actually moves.  Sending it every time would override whatever
        # the engine's own resting state is, which changes the voice even at the
        # documented default of 250.
        self._voice.speak(piece, on_block=on_block,
                          should_cancel=self._cancelFlag.is_set)
        # Do NOT block on idle() while more speech is pending or a cancel is in
        # flight.  NVDA cancels and re-speaks on every keystroke; waiting here for
        # the player to drain makes each character wait out the previous one's
        # audio and reverb tail, and nothing can preempt it because this thread
        # is asleep inside idle().
        if not self._cancelFlag.is_set() and self._queue.empty():
            try:
                self._player.idle()
            except Exception:
                pass

    # -- voices ------------------------------------------------------------
    @property
    def _voice(self):
        return self._voices[self._voiceId]

    def _get_availableVoices(self):
        # VoiceInfo without a language raises inside normalizeLanguage; both of
        # these are Hungarian and always were.
        return {v.id: VoiceInfo(v.id, v.label, v.language)
                for v in self._voices.values()}

    def _get_voice(self):
        return self._voiceId

    def _set_voice(self, value):
        if value not in self._voices or value == self._voiceId:
            return
        # Switching engines mid-utterance would feed the player audio at the
        # wrong rate, so drop whatever is queued first.
        self.cancel()
        self._voiceId = value
