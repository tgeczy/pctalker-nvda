# -*- coding: utf-8 -*-
"""
Emulation core for PC-TALKER 5.01 (Kiraly Jozsef, 1991).

Runs the original 16-bit DOS speech engine under Unicorn and returns PCM.
No DOS and no DOSBox: the image is a snapshot of conventional memory taken
with OLVRES already resident, mapped verbatim at linear 0 so every far
pointer inside it stays valid.

Engine interface, read out of the TSR itself (handler +062B):
    INT F1h, AH = 0, ES:DI -> text, CX = length      -> speak
    AH = 3                                           -> stop / restore timer
    install check: INT F1h vector segment, word at :0000 == 07A4h

The call does NOT synthesize.  It queues the utterance, reprograms PIT
channel 0, and returns; audio then comes out of the INT 8 timer ISR, one
direct-DAC byte per tick (DSP command 10h to base+0Ch, then the sample).
There is no DMA anywhere in this engine.

The divisor written to port 40h IS the sample rate: 1193181.666 / divisor.
Measured 130 -> 9178 Hz.
"""

import os
import struct

from unicorn import (
    Uc, UcError, UC_ARCH_X86, UC_MODE_16, UC_PROT_ALL,
    UC_HOOK_INSN, UC_HOOK_INTR,
)
from unicorn.x86_const import (
    UC_X86_INS_IN, UC_X86_INS_OUT,
    UC_X86_REG_AX, UC_X86_REG_BX, UC_X86_REG_CX, UC_X86_REG_DI,
    UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_SS, UC_X86_REG_SP,
    UC_X86_REG_CS, UC_X86_REG_IP, UC_X86_REG_EFLAGS,
)

MEM_SIZE = 0x110000
STACK_SEG = 0x8000
STACK_SP = 0xFFF0
SENTINEL_SEG = 0x9F00
SENTINEL = SENTINEL_SEG * 16
TEXT_SEG = 0x9000
SB_BASE = 0x220
PIT_HZ = 1193181.666
SIGNATURE = 0x07A4

#: The engine clamps to 255 itself (`cmp cx,0FFh / jae`), silently truncating.
#: Callers must chunk; 200 leaves room for the leading space and the CR.
MAX_TEXT = 200

#: Reverb ("visszhangosítás"), embedded in the text as `#vnnnn`.  From the 1991
#: manual: "A felolvasandó szövegben elhelyezhetünk egy visszhangosítást vezérlő
#: parancsot is ... Alapértelmezésben a paraméter értéke 250.  A parancsot a
#: rendszer nem olvassa fel."  This is the smoothing algorithm Kiraly describes in
#: his 2018 talk as what joins the concatenated voice elements -- unlike rate, a
#: genuine engine parameter rather than something faked during playback.
DEFAULT_REVERB = 250
MAX_REVERB = 9999

#: AH=4 status values, from the manual.
ST_IDLE = 0x00
ST_SPEAKING = 0x02
ST_SUSPENDED = 0x12
#: Poll AH=4 every N timer ticks.  DISABLED (0) pending investigation: re-entering
#: the TSR ~128x/second is far outside how the original software used it (OLVIT /r
#: was a one-shot), and AH=4 writes cs:[30h]/cs:[32h] -- the same scratch words the
#: AH=0 entry path uses.  Enable only with a controlled A/B against the known-good
#: QUIET_TICKS behaviour.
STATUS_EVERY = 0

MAX_INSNS = 20_000_000
MAX_TICKS = 400_000
#: Fallback only.  With AH=4 polling this should never be reached; kept so a
#: damaged image cannot spin forever.
QUIET_TICKS = 1200


class EngineError(RuntimeError):
    pass


class Engine(object):
    """Holds the engine image and synthesizes utterances.

    The image is a snapshot of an idle, already-initialised TSR.  The original
    software called it repeatedly without reloading anything, so one Unicorn
    instance is reused across utterances -- rebuilding costs about a
    millisecond, but reuse is what the engine was designed for.
    """

    def __init__(self, image_path):
        with open(image_path, "rb") as f:
            self.image = f.read()
        if len(self.image) < 0xA0000:
            raise EngineError("engine image is too small to be a 640K snapshot")
        self.f1_off, self.f1_seg = self._vector(0xF1)
        self.t8_off, self.t8_seg = self._vector(0x08)
        sig = self._word(self.f1_seg * 16)
        if sig != SIGNATURE:
            raise EngineError(
                "engine image was captured without OLVRES resident "
                "(signature %04Xh, expected %04Xh)" % (sig, SIGNATURE))
        self._uc = None
        self._dirty = False
        # The port hooks fire on any call into the TSR, including AH=1..4, so
        # these must be valid before speak() has ever run.
        self.divisor = 130
        self._pit = []
        self._expect_sample = False
        self._timer_restored = False
        self._sink = lambda v: None

    # -- image helpers -----------------------------------------------------
    def _vector(self, n):
        b = self.image[n * 4:n * 4 + 4]
        return b[0] | (b[1] << 8), b[2] | (b[3] << 8)

    def _word(self, linear):
        return self.image[linear] | (self.image[linear + 1] << 8)

    # -- emulation ---------------------------------------------------------
    def reset(self):
        self._uc = None
        self._dirty = False

    def _ensure(self):
        if self._uc is not None and not self._dirty:
            return self._uc
        uc = Uc(UC_ARCH_X86, UC_MODE_16)
        uc.mem_map(0, MEM_SIZE, UC_PROT_ALL)
        uc.mem_write(0, self.image)
        uc.hook_add(UC_HOOK_INSN, self._on_out, None, 1, 0, UC_X86_INS_OUT)
        uc.hook_add(UC_HOOK_INSN, self._on_in, None, 1, 0, UC_X86_INS_IN)
        uc.hook_add(UC_HOOK_INTR, self._on_intr)
        self._uc = uc
        self._dirty = False
        return uc

    # -- device hooks ------------------------------------------------------
    def _on_out(self, uc, port, size, value, ud):
        v = value & 0xFF
        if port == SB_BASE + 0x0C:
            if self._expect_sample:
                self._sink(v)
                self._expect_sample = False
            elif v == 0x10:                 # DSP: direct DAC, next byte is data
                self._expect_sample = True
            else:
                self._expect_sample = False
        elif port == 0x40:
            self._pit.append(v)
            if len(self._pit) == 2:
                d = self._pit[0] | (self._pit[1] << 8)
                del self._pit[:]
                if d == 0 or d > 20000:
                    # Restored to the BIOS rate -- the utterance is over.
                    self._timer_restored = True
                else:
                    self.divisor = d
                    self._timer_restored = False

    def _on_in(self, uc, port, size, ud):
        if port == SB_BASE + 0x0C:
            return 0x00                     # write buffer always ready
        if port == SB_BASE + 0x0E:
            return 0x80
        if port == SB_BASE + 0x0A:
            return 0xAA                     # DSP reset handshake
        return 0xFF

    def _on_intr(self, uc, intno, ud):
        ax = uc.reg_read(UC_X86_REG_AX)
        ah, al = (ax >> 8) & 0xFF, ax & 0xFF
        if intno == 0x21:
            if ah == 0x35:
                off, seg = struct.unpack("<HH", uc.mem_read(al * 4, 4))
                uc.reg_write(UC_X86_REG_ES, seg)
                uc.reg_write(UC_X86_REG_BX, off)
            elif ah == 0x25:
                ds = uc.reg_read(UC_X86_REG_DS)
                dx = uc.reg_read(UC_X86_REG_CX)
                uc.mem_write(al * 4, struct.pack("<HH", dx, ds))
            elif ah == 0x30:
                uc.reg_write(UC_X86_REG_AX, 0x0005)
            uc.reg_write(UC_X86_REG_EFLAGS,
                         uc.reg_read(UC_X86_REG_EFLAGS) & ~0x01)
        elif intno == 0x16:
            uc.reg_write(UC_X86_REG_AX, 0)

    # -- calling into the TSR ---------------------------------------------
    def _enter(self, uc, seg, off):
        """Enter an interrupt handler; its IRET lands on the sentinel."""
        uc.reg_write(UC_X86_REG_SS, STACK_SEG)
        uc.reg_write(UC_X86_REG_SP, STACK_SP)
        sp = STACK_SP
        flags = uc.reg_read(UC_X86_REG_EFLAGS) & ~0x200
        for w in (flags, SENTINEL_SEG, 0x0000):
            sp = (sp - 2) & 0xFFFF
            uc.mem_write(STACK_SEG * 16 + sp, struct.pack("<H", w))
        uc.reg_write(UC_X86_REG_SP, sp)
        # CS must be right: the handler is full of `mov word ptr cs:[..]`.
        uc.reg_write(UC_X86_REG_CS, seg)
        uc.reg_write(UC_X86_REG_IP, off)
        uc.emu_start(seg * 16 + off, SENTINEL, count=MAX_INSNS)

    # -- documented AH=1..4 functions --------------------------------------
    def _call(self, ah, al=0):
        uc = self._ensure()
        uc.reg_write(UC_X86_REG_AX, ((ah & 0xFF) << 8) | (al & 0xFF))
        self._enter(uc, self.f1_seg, self.f1_off)
        return (uc.reg_read(UC_X86_REG_AX) & 0xFF,
                uc.reg_read(UC_X86_REG_BX) & 0xFFFF)

    def status(self):
        """AH=4 -> (AL, BX).

        AL: 0 idle, 2 speaking, 12h suspended.  BX: bytes of text remaining.
        """
        return self._call(4)

    def suspend(self):
        """AH=1 - felfuggesztes."""
        self._call(1)

    def resume(self):
        """AH=2 - korabban felfuggesztett felolvasas folytatasa."""
        self._call(2)

    def abort(self):
        """AH=3 - abortalas.  Also restores the timer."""
        self._call(3)

    def speak(self, text, on_block=None, should_cancel=None, block=1024,
              reverb=None):
        """Synthesize one chunk.  Returns (pcm8_bytes, sample_rate).

        `on_block(data, rate)` receives audio as it is produced, so playback
        can start on the first timer tick instead of waiting for the whole
        utterance.  When given, the returned PCM is empty.
        """
        if isinstance(text, bytes):
            raw = text
        else:
            raw = text.encode("cp852", "replace")
        raw = raw[:MAX_TEXT]
        if not raw.strip():
            return b"", int(PIT_HZ / 130)

        prefix = b""
        if reverb is not None:
            prefix = b"#v%04d" % max(0, min(MAX_REVERB, int(reverb)))
        payload = b" " + prefix + raw + b"\r"
        uc = self._ensure()

        self.divisor = 130
        self._pit = []
        self._expect_sample = False
        self._timer_restored = False
        pending = bytearray()
        collected = bytearray()

        def sink(v):
            if on_block is None:
                collected.append(v)
            else:
                pending.append(v)

        self._sink = sink

        try:
            uc.mem_write(TEXT_SEG * 16, payload)
            uc.reg_write(UC_X86_REG_ES, TEXT_SEG)
            uc.reg_write(UC_X86_REG_DI, 0)
            uc.reg_write(UC_X86_REG_CX, len(payload))
            uc.reg_write(UC_X86_REG_DS, TEXT_SEG)
            uc.reg_write(UC_X86_REG_AX, 0x0000)      # AH=0 -> speak
            self._enter(uc, self.f1_seg, self.f1_off)

            ticks = 0
            quiet = 0
            produced = 0
            while ticks < MAX_TICKS:
                if should_cancel is not None and should_cancel():
                    self.abort()
                    break
                self._enter(uc, self.t8_seg, self.t8_off)
                ticks += 1
                now = len(pending) + len(collected)
                if now != produced:
                    produced = now
                    quiet = 0
                    if on_block is not None and len(pending) >= block:
                        on_block(bytes(pending), self.rate)
                        del pending[:]
                else:
                    quiet += 1
                    if self._timer_restored and produced:
                        break
                    if quiet >= QUIET_TICKS and produced:
                        break
                # Ask the engine whether it is finished instead of inferring it
                # from silence.  AH=4 is documented and exact.
                if STATUS_EVERY and produced and ticks % STATUS_EVERY == 0:
                    al, _rem = self.status()
                    if al == ST_IDLE:
                        break
        except UcError as e:
            self._dirty = True
            raise EngineError("emulation fault: %s" % e)

        if on_block is not None:
            if pending:
                on_block(bytes(pending), self.rate)
            return b"", self.rate
        return bytes(collected), self.rate

    #: Kept as an alias; AH=3 is the documented abort.
    stop = abort

    @property
    def rate(self):
        return int(round(PIT_HZ / (self.divisor or 130)))


# -- audio helpers ---------------------------------------------------------
# Moved to audio.py, which both engines share; re-exported so nothing that
# imported them from here has to change.
from pctalker_audio import to_pcm16, Resampler, split_text, apply_gain   # noqa: F401,E402
