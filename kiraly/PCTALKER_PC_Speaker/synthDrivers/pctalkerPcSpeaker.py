import threading
from collections import OrderedDict

import config
import nvwave
from logHandler import log
from synthDriverHandler import (
    SynthDriver as BaseSynthDriver,
    VoiceInfo,
    StringParameterInfo,
    synthIndexReached,
    synthDoneSpeaking,
)
from speech.commands import IndexCommand

from . import _pcspeakerlib
from ._pcspeakerlib import PCSpeakerEngine
from ._pcspeakerlib.speaker_engine import SynthesisCancelled


OUTPUT_RATE = 16000


class SynthDriver(BaseSynthDriver):
    name = "pctalkerPcSpeaker"
    description = "PCTALKER PC Speaker - Hungarian - DEMO"

    supportedSettings = (
        BaseSynthDriver.RateSetting(),
        BaseSynthDriver.VariantSetting(),
    )
    supportedCommands = {IndexCommand}
    supportedNotifications = {synthIndexReached, synthDoneSpeaking}

    @classmethod
    def check(cls):
        return True

    def __init__(self):
        super().__init__()
        self._rate = 50
        self._variant = "fast"
        self._generation = 0
        self._pending = None
        self._shutdown = False
        self._cond = threading.Condition()
        self._pcmCache = OrderedDict()
        self._pcmCacheMax = 128

        self._engine = self._newEngine()

        self._player = self._createPlayer()

        self._worker = threading.Thread(
            target=self._workerLoop,
            name="PCTALKER-PCSPK-Worker",
            daemon=True,
        )
        self._worker.start()

    def _outputRateForVariant(self, variant=None):
        variant = self._variant if variant is None else variant
        return 48000 if variant in ("realPwm", "realPwm35") else 16000

    def _createPlayer(self):
        return nvwave.WavePlayer(
            channels=1,
            samplesPerSec=self._outputRateForVariant(),
            bitsPerSample=16,
            outputDevice=config.conf["audio"]["outputDevice"],
        )

    def _newEngine(self):
        return PCSpeakerEngine(
            base_dir=_pcspeakerlib.__path__[0],
            language="hu_HU",
            mode=self._variant,
            pwm_filter_cutoff=4500.0,
        )

    @staticmethod
    def _rateToSpeed(rate):
        rate = max(0, min(100, int(rate)))
        return 2.0 ** ((rate - 50) / 50.0)

    def _get_rate(self):
        return self._rate

    def _set_rate(self, value):
        value = max(0, min(100, int(value)))
        if value == self._rate:
            return
        with self._cond:
            self._rate = value
            self._generation += 1
            self._pending = None
            self._pcmCache.clear()
            self._cond.notify_all()
        try:
            self._player.stop()
        except Exception:
            log.exception("PCTALKER PC Speaker: error stopping after rate change")

    def _get_language(self):
        return "hu_HU"

    def _get_variant(self):
        return self._variant

    def _set_variant(self, value):
        if value not in ("fast", "pwm", "realPwm", "realPwm35"):
            value = "fast"
        if value == self._variant:
            return

        with self._cond:
            self._variant = value
            self._generation += 1
            self._pending = None
            self._pcmCache.clear()
            self._engine = self._newEngine()
            self._cond.notify_all()

        oldPlayer = self._player
        try:
            oldPlayer.stop()
        except Exception:
            log.exception("PCTALKER PC Speaker: error stopping after variant change")
        try:
            oldPlayer.close()
        except Exception:
            pass
        self._player = self._createPlayer()

    def _get_availableVariants(self):
        return OrderedDict([
            ("fast", StringParameterInfo("fast", "Fast envelope (no PWM carrier)")),
            ("pwm", StringParameterInfo("pwm", "True PWM (PC-speaker acoustic emulation)")),
            ("realPwm", StringParameterInfo("realPwm", "Real PWM 48 kHz")),
            ("realPwm35", StringParameterInfo("realPwm35", "Real PWM 48 kHz + 3.5 kHz filter")),
        ])

    def speak(self, speechSequence):
        textParts = []
        indexes = []

        for item in speechSequence:
            if isinstance(item, str):
                textParts.append(item)
            elif isinstance(item, IndexCommand):
                indexes.append(item.index)
            else:
                log.debugWarning(
                    "PCTALKER PC Speaker: unsupported speech command %r",
                    item,
                )

        text = "".join(textParts)
        if not text and not indexes:
            return

        with self._cond:
            self._generation += 1
            generation = self._generation
            self._pending = (generation, text, indexes, self._rate, self._engine)
            self._cond.notify()

        try:
            self._player.stop()
        except Exception:
            log.exception("PCTALKER PC Speaker: error stopping previous speech")

    def _cacheGet(self, key):
        pcm = self._pcmCache.get(key)
        if pcm is not None:
            self._pcmCache.move_to_end(key)
        return pcm

    def _cachePut(self, key, pcm):
        # Cache only short navigation utterances; long passages are unlikely
        # to repeat and would consume unnecessary memory.
        if len(key[0]) > 160:
            return
        self._pcmCache[key] = pcm
        self._pcmCache.move_to_end(key)
        while len(self._pcmCache) > self._pcmCacheMax:
            self._pcmCache.popitem(last=False)

    def _isStale(self, generation):
        # Tiny lock-protected check used by DSP loops to abandon obsolete
        # cursor/navigation speech before the full utterance is rendered.
        with self._cond:
            return self._shutdown or generation != self._generation

    def _workerLoop(self):
        while True:
            with self._cond:
                while self._pending is None and not self._shutdown:
                    self._cond.wait()
                if self._shutdown:
                    return
                generation, text, indexes, rate, engine = self._pending
                self._pending = None

            try:
                cacheKey = (text, rate, self._variant)
                pcm = self._cacheGet(cacheKey) if text else b""
                if text and pcm is None:
                    pcm = engine.synthesize(
                        text,
                        speed=self._rateToSpeed(rate),
                        cancel_check=lambda: self._isStale(generation),
                    )
                    self._cachePut(cacheKey, pcm)

                with self._cond:
                    if self._shutdown or generation != self._generation:
                        continue

                if pcm:
                    self._player.feed(pcm)
                    self._player.idle()

                with self._cond:
                    if self._shutdown or generation != self._generation:
                        continue

                for index in indexes:
                    synthIndexReached.notify(synth=self, index=index)
                synthDoneSpeaking.notify(synth=self)

            except SynthesisCancelled:
                # Expected during rapid cursor/navigation changes.
                continue
            except Exception:
                log.exception("PCTALKER PC Speaker: error in speech worker")

    def cancel(self):
        with self._cond:
            self._generation += 1
            self._pending = None
            self._cond.notify_all()
        try:
            self._player.stop()
        except Exception:
            log.exception("PCTALKER PC Speaker: error cancelling speech")

    def pause(self, switch):
        try:
            self._player.pause(bool(switch))
        except Exception:
            log.exception("PCTALKER PC Speaker: error changing pause state")

    def terminate(self):
        with self._cond:
            self._generation += 1
            self._pending = None
            self._shutdown = True
            self._cond.notify_all()

        try:
            self._player.stop()
        except Exception:
            pass

        if self._worker.is_alive():
            self._worker.join(timeout=2.0)

        try:
            self._player.close()
        except Exception:
            log.exception("PCTALKER PC Speaker: error closing WavePlayer")

        self._player = None
        self._engine = None
        super().terminate()
