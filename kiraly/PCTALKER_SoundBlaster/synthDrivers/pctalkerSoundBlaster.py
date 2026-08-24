import threading
from collections import OrderedDict

import config
import nvwave
from autoSettingsUtils.driverSetting import NumericDriverSetting
from logHandler import log
from synthDriverHandler import (
    SynthDriver as BaseSynthDriver,
    VoiceInfo,
    synthIndexReached,
    synthDoneSpeaking,
)
from speech.commands import IndexCommand

from . import _soundblasterlib
from ._soundblasterlib import OlvasEngine


SAMPLE_RATE = 8500


class SynthDriver(BaseSynthDriver):
    name = "pctalkerSoundBlaster"
    description = "PCTALKER Sound Blaster version - Hungarian - DEMO"

    supportedSettings = (
        BaseSynthDriver.RateSetting(),
        NumericDriverSetting(
            "echoDelay",
            "&Echo delay (samples)",
            availableInSettingsRing=True,
            defaultVal=250,
            minVal=0,
            maxVal=4999,
            minStep=10,
            normalStep=50,
            largeStep=250,
            displayName="Echo delay (samples)",
        ),
    )
    supportedCommands = {IndexCommand}
    supportedNotifications = {synthIndexReached, synthDoneSpeaking}

    @classmethod
    def check(cls):
        return True

    def __init__(self):
        super().__init__()
        self._rate = 50
        self._echoDelay = 250
        self._generation = 0
        self._pending = None
        self._shutdown = False
        self._cond = threading.Condition()

        self._engine = OlvasEngine(
            base_dir=_soundblasterlib.__path__[0],
            speed=1.0,
            echo_delay=self._echoDelay,
            start_player=False,
        )

        self._player = nvwave.WavePlayer(
            channels=1,
            samplesPerSec=SAMPLE_RATE,
            bitsPerSample=8,
            outputDevice=config.conf["audio"]["outputDevice"],
        )

        self._worker = threading.Thread(
            target=self._workerLoop,
            name="PCTALKER-SB-NVDA-Worker",
            daemon=True,
        )
        self._worker.start()

    @staticmethod
    def _rateToSpeed(rate):
        rate = max(0, min(100, int(rate)))
        return 2.0 ** ((rate - 50) / 50.0)

    @staticmethod
    def _resampleU8(samples, speed):
        if not samples or abs(speed - 1.0) < 1e-9:
            return samples
        outLen = max(1, round(len(samples) / speed))
        if len(samples) == 1 or outLen == 1:
            return bytes([samples[0]])
        out = bytearray(outLen)
        scale = (len(samples) - 1) / (outLen - 1)
        for j in range(outLen):
            pos = j * scale
            i = int(pos)
            if i >= len(samples) - 1:
                out[j] = samples[-1]
            else:
                frac = pos - i
                value = round(samples[i] * (1.0 - frac) + samples[i + 1] * frac)
                out[j] = max(0, min(255, value))
        return bytes(out)

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
            self._cond.notify_all()
        try:
            self._player.stop()
        except Exception:
            log.exception("PCTALKER SB: error stopping after rate change")

    def _get_echoDelay(self):
        return self._echoDelay

    def _set_echoDelay(self, value):
        value = max(0, min(4999, int(value)))
        if value == self._echoDelay:
            return
        with self._cond:
            self._echoDelay = value
            self._engine.echo_delay = value
            self._generation += 1
            self._pending = None
            self._cond.notify_all()
        try:
            self._player.stop()
        except Exception:
            log.exception("PCTALKER SB: error stopping after echo change")

    def _get_language(self):
        return "hu_HU"

    def _get_voice(self):
        return "pctalkerSoundBlaster"

    def _get_availableVoices(self):
        return OrderedDict([
            (
                "pctalkerSoundBlaster",
                VoiceInfo(
                    "pctalkerSoundBlaster",
                    "PCTALKER Sound Blaster version - Hungarian - DEMO",
                    "hu_HU",
                ),
            ),
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
                log.debugWarning("PCTALKER SB: unsupported speech command %r", item)

        text = "".join(textParts)
        if not text and not indexes:
            return

        with self._cond:
            self._generation += 1
            generation = self._generation
            self._pending = (
                generation,
                text,
                indexes,
                self._rate,
                self._echoDelay,
            )
            self._cond.notify()

        try:
            self._player.stop()
        except Exception:
            log.exception("PCTALKER SB: error stopping previous speech")

    def _workerLoop(self):
        while True:
            with self._cond:
                while self._pending is None and not self._shutdown:
                    self._cond.wait()
                if self._shutdown:
                    return
                generation, text, indexes, rate, echoDelay = self._pending
                self._pending = None

            try:
                self._engine.echo_delay = echoDelay
                segments = self._engine.synthesize_segments(text) if text else []

                with self._cond:
                    if self._shutdown or generation != self._generation:
                        continue

                speed = self._rateToSpeed(rate)
                cancelled = False

                for kind, pcm in segments:
                    with self._cond:
                        if self._shutdown or generation != self._generation:
                            cancelled = True
                            break

                    if kind == "speech":
                        pcm = self._resampleU8(pcm, speed)

                    if pcm:
                        self._player.feed(pcm)

                if cancelled:
                    continue

                self._player.idle()

                with self._cond:
                    if self._shutdown or generation != self._generation:
                        continue

                for index in indexes:
                    synthIndexReached.notify(synth=self, index=index)
                synthDoneSpeaking.notify(synth=self)

            except Exception:
                log.exception("PCTALKER Sound Blaster: error in speech worker")

    def cancel(self):
        with self._cond:
            self._generation += 1
            self._pending = None
            self._cond.notify_all()
        try:
            self._player.stop()
        except Exception:
            log.exception("PCTALKER SB: error cancelling speech")

    def pause(self, switch):
        try:
            self._player.pause(bool(switch))
        except Exception:
            log.exception("PCTALKER SB: error changing pause state")

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
            log.exception("PCTALKER SB: error closing NVDA WavePlayer")

        try:
            self._engine.close()
        except Exception:
            log.exception("PCTALKER SB: error closing synthesis engine")

        self._player = None
        self._engine = None
        super().terminate()
