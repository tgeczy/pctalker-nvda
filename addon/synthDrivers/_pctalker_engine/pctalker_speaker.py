# -*- coding: utf-8 -*-
"""Emulation core for SPEAKER 1.0 / OLVASSP (Kiraly Jozsef, 1990).

The PC speaker sibling of PC-TALKER: the same voice, built for a machine with
no sound card at all.  Amplitude becomes pulse width on PIT channel 2, and the
timer ISR writes one byte per interrupt at 18356 Hz -- twice the 9178 Hz of the
recordings, because every source sample is emitted twice.

Unlike PC-TALKER 5.01 this is not a TSR, so there is no snapshot and no INT F1h
entry point: the original `OLVASSP.EXE` is loaded and run as a DOS program.
Its command line selects what it does, and `*` means "speak the rest of the
tail" -- but that branch only copies the tail into the text buffer at DS:018Ah,
sets the flag at DS:0068h and jumps to 0488h.  Doing those three things
directly removes the 126-byte limit the PSP would impose, which is what makes
this usable as a synthesizer rather than a demo.

Everything here was read out of the binary under instrumentation; see
docs/pcspeaker-plan.md.  The audio path is verified exactly: replaying GITAR
through this host reproduces the file with zero error.
"""

import os
import struct

from pctalker_doshost import DosHost, DosError, PIT_HZ
from unicorn import UcError, UC_HOOK_CODE, UC_HOOK_MEM_WRITE
from unicorn.x86_const import (
    UC_X86_REG_AX, UC_X86_REG_BX, UC_X86_REG_CX, UC_X86_REG_DX,
    UC_X86_REG_SI, UC_X86_REG_DI, UC_X86_REG_BP, UC_X86_REG_SP,
    UC_X86_REG_CS, UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_SS,
    UC_X86_REG_IP, UC_X86_REG_EFLAGS,
)

#: Channel 0 divisor 65 -> 18356.6 Hz, written by the program itself at 0CA5h.
#: Each source sample is written twice, so this is 9178 Hz audio 2x oversampled
#: and playing the raw write stream at this rate gives the correct pitch.
SAMPLE_RATE = 18356

#: Offsets in the program's data segment, all read off the disassembly.
OFF_TEXT = 0x018A          # text buffer; byte 0 is the length
OFF_FLAG = 0x0068          # "a parameter was given" flag
EP_SPEAK = 0x0488          # where the `*` branch jumps once the text is in

#: The `hlt` opcode.  The sample loop halts once per interrupt, and Unicorn
#: stops emulating there, so every wake is a round trip through here.
HLT = 0xF4

#: A serviced interrupt costs no guest instructions, but on the machine this
#: was written for INT 21h went through DOS and cost hundreds of cycles.  The
#: program measures the CPU by counting AH=2C calls across 0.30 s of DOS clock
#: and then divides; with interrupts free the count overflows a byte quotient
#: and the program dies of divide overflow before it plays a note.
INT_CYCLES = 2000.0
CPU_HZ = 4_770_000.0

#: The longest text to hand the engine at once.  The `*` branch this reuses is
#: fed from the PSP command tail, which DOS caps at 126 bytes, so this is the
#: largest input the program itself was ever given -- and the buffer at
#: DS:018Ah was sized for exactly that.  Going beyond it would write into
#: whatever follows.
MAX_TEXT = 120

#: A safety net, not a limit: this voice runs about 0.08 s of audio per
#: character, so MAX_TEXT is roughly 10 s and this leaves generous headroom.
#: Set too low it would silently clip the end of a sentence, which is a far
#: worse failure than a slow one.
MAX_SAMPLES = SAMPLE_RATE * 20
MAX_INSNS = 40_000_000


class EngineError(RuntimeError):
    pass


class _Host(DosHost):
    """A DOS host tuned for one job: run this program and collect its audio.

    Deliberately without `UC_HOOK_BLOCK`.  The base host uses it to advance
    virtual time and schedule IRQ0, but a Python callback on every basic block
    is the single most expensive thing in the loop, and this program does not
    need it: its clock-calibration loop advances time through INT 21h, and its
    playback is driven by `hlt`, which we service directly.
    """

    def __init__(self, cwd, stdin=b""):
        self.stdin = stdin
        self.stdin_pos = 0
        self.pwm = bytearray()
        self.ch0_divisor = 0
        self._ch0_latch = []
        self._ivt_seen = set()
        self.halts = 0
        #: Set if the run ended because emulation kept stopping for reasons
        #: that were not `hlt`.  One such stop per utterance is normal (the
        #: IVT write); sixty-four is not, and the caller should know.
        self.stalled = False
        super().__init__(cwd, cpu_hz=CPU_HZ)

    # -- construction ------------------------------------------------------
    def _build(self):
        super()._build()
        # This program installs its ISR with a direct IVT store, never AH=25,
        # so without watching the vector table the timer would never dispatch.
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self._on_ivt, None, 0, 0x3FF)

    def _on_ivt(self, uc, access, address, size, value, user):
        for a in range(address, address + size):
            self._ivt_seen.add(a >> 2)
        self.hooked_vectors.update(self._ivt_seen)

    # -- ports -------------------------------------------------------------
    def _on_in(self, uc, port, size, user):
        # `in al,20h / and al,1 / jne` waits for IRQ0 to clear before halting;
        # answering 0xFF for the PIC leaves bit 0 set and spins there forever.
        if port in (0x20, 0x21, 0x40, 0x41, 0x42, 0x43):
            return 0x00
        return super()._on_in(uc, port, size, user)

    def _on_out(self, uc, port, size, value, user):
        if port == 0x42:
            # One write, one PWM sample.  This is the hot path: nothing else
            # may happen here.
            self.pwm.append(value & 0xFF)
            return
        if port == 0x40:
            self._ch0_latch.append(value & 0xFF)
            if len(self._ch0_latch) == 2:
                self.ch0_divisor = (self._ch0_latch[0]
                                    | (self._ch0_latch[1] << 8))
                del self._ch0_latch[:]
        elif port == 0x43 and (value >> 6) == 0:
            del self._ch0_latch[:]
        super()._on_out(uc, port, size, value, user)

    # -- standard input ----------------------------------------------------
    # The base host wires handle 0 to the keyboard queue only, so a program
    # reading redirected input sees nothing.  DOS feeds all of these routes
    # from one file position, and READSPF uses several of them.
    def _getc(self):
        if self.stdin_pos >= len(self.stdin):
            return None
        ch = self.stdin[self.stdin_pos]
        self.stdin_pos += 1
        return ch

    def _dos(self, ah, al, ax):
        uc = self.uc
        if ah == 0x3F and uc.reg_read(UC_X86_REG_BX) == 0:
            cx = uc.reg_read(UC_X86_REG_CX)
            data = self.stdin[self.stdin_pos:self.stdin_pos + cx]
            self.stdin_pos += len(data)
            if data:
                uc.mem_write(uc.reg_read(UC_X86_REG_DS) * 16
                             + uc.reg_read(UC_X86_REG_DX), data)
            uc.reg_write(UC_X86_REG_AX, len(data))
            self._cf(False)
            return
        if ah == 0x06 and (uc.reg_read(UC_X86_REG_DX) & 0xFF) == 0xFF:
            ch = self._getc()
            f = uc.reg_read(UC_X86_REG_EFLAGS)
            if ch is None:
                uc.reg_write(UC_X86_REG_AX, ax & 0xFF00)
                uc.reg_write(UC_X86_REG_EFLAGS, f | 0x40)
            else:
                uc.reg_write(UC_X86_REG_AX, (ax & 0xFF00) | ch)
                uc.reg_write(UC_X86_REG_EFLAGS, f & ~0x40)
            self._cf(False)
            return
        if ah in (0x01, 0x07, 0x08):
            uc.reg_write(UC_X86_REG_AX, (ax & 0xFF00) | (self._getc() or 0))
            self._cf(False)
            return
        if ah == 0x0B:
            left = len(self.stdin) - self.stdin_pos
            uc.reg_write(UC_X86_REG_AX, (ax & 0xFF00) | (0xFF if left else 0))
            self._cf(False)
            return
        if ah == 0x0A:
            base = uc.reg_read(UC_X86_REG_DS) * 16 + uc.reg_read(UC_X86_REG_DX)
            maxlen = uc.mem_read(base, 1)[0]
            line = bytearray()
            while self.stdin_pos < len(self.stdin) and len(line) < max(1, maxlen - 1):
                ch = self._getc()
                if ch in (None, 13, 26):
                    break
                line.append(ch)
            uc.mem_write(base + 1, bytes([len(line)]))
            uc.mem_write(base + 2, bytes(line) + b"\r")
            self._cf(False)
            return
        if ah == 0x2C:
            # These programs measure the machine by counting AH=2C calls across
            # 0.30 s of DOS clock.  A frozen clock is an infinite loop.
            t = self.vtime
            uc.reg_write(UC_X86_REG_CX, (((int(t) // 3600) % 24) << 8)
                         | ((int(t) // 60) % 60))
            uc.reg_write(UC_X86_REG_DX, ((int(t) % 60) << 8) | (int(t * 100) % 100))
            self._cf(False)
            return
        super()._dos(ah, al, ax)

    # -- interrupts --------------------------------------------------------
    def _service(self, intno):
        if intno in (0x21, 0x10, 0x16, 0x1A):
            self.cycles += INT_CYCLES
        elif intno == 0x13:
            # `.` mode is a disk sector editor (AH=03 write).  Nothing in the
            # speech path issues INT 13h, so reaching it means something went
            # wrong -- and it must never touch the host's disk.
            self._cf(True)
            return
        super()._service(intno)

    def _dispatch_guest(self, intno):
        """Enter a handler as hardware does: one stack frame, IF and TF clear.

        The base builds the frame with three separate writes and six register
        round trips.  At one interrupt per sample that cost is measurable, so
        it is done here as a single six-byte store.
        """
        uc = self.uc
        off, seg = struct.unpack('<HH', uc.mem_read(intno * 4, 4))
        if not (seg or off):
            return False
        flags = uc.reg_read(UC_X86_REG_EFLAGS)
        sp = (uc.reg_read(UC_X86_REG_SP) - 6) & 0xFFFF
        ss = uc.reg_read(UC_X86_REG_SS)
        uc.mem_write(ss * 16 + sp, struct.pack(
            '<HHH', uc.reg_read(UC_X86_REG_IP), uc.reg_read(UC_X86_REG_CS),
            flags))
        uc.reg_write(UC_X86_REG_SP, sp)
        uc.reg_write(UC_X86_REG_CS, seg)
        uc.reg_write(UC_X86_REG_IP, off)
        uc.reg_write(UC_X86_REG_EFLAGS, flags & ~0x300)
        return True

    # -- the run loop ------------------------------------------------------
    def pump(self, addr, max_samples=MAX_SAMPLES, on_block=None, block=1024,
             should_cancel=None):
        """Run until the program exits, feeding it timer interrupts.

        `hlt` is the whole story: Unicorn stops emulating there and reports
        nothing, so to an ordinary host a halted guest looks exactly like a
        finished one.  Here it means what it means on hardware -- sleep until
        the next interrupt -- and since this program halts once per sample,
        this loop runs once per sample too.
        """
        uc = self.uc
        rate = SAMPLE_RATE
        sent = 0
        stalls = 0
        while True:
            try:
                uc.emu_start(addr, 0, count=MAX_INSNS)
            except UcError as e:
                if self.exited is None:
                    raise EngineError("emulation fault: %s (cs:ip=%04x:%04x)"
                                      % (e, uc.reg_read(UC_X86_REG_CS),
                                         uc.reg_read(UC_X86_REG_IP)))
                break
            if self.exited is not None:
                break
            cs, ip = uc.reg_read(UC_X86_REG_CS), uc.reg_read(UC_X86_REG_IP)
            if uc.mem_read(cs * 16 + ((ip - 1) & 0xFFFF), 1)[0] == HLT:
                stalls = 0
                self.halts += 1
                if self.ch0_divisor:
                    rate = PIT_HZ / self.ch0_divisor
                self.cycles += self.cpu_hz / rate
                if (0x08 not in self.hooked_vectors
                        or not self._dispatch_guest(8)):
                    break
                if on_block is not None and len(self.pwm) - sent >= block:
                    on_block(bytes(self.pwm[sent:]))
                    sent = len(self.pwm)
                if len(self.pwm) >= max_samples:
                    break
                # Checked here rather than every instruction: one halt is one
                # sample, so this is already the finest granularity the guest
                # offers, and NVDA cancels on every keystroke.
                if should_cancel is not None and should_cancel():
                    break
            else:
                # Unicorn ends a run for reasons of its own -- writing the
                # interrupt vector table invalidates translated code and
                # flushes the block cache, which happens exactly once per
                # utterance when the ISR is installed.  Resuming is correct;
                # only a run that stops making progress is a real stall.
                stalls += 1
                if stalls > 64:
                    self.stalled = True
                    break
            addr = (uc.reg_read(UC_X86_REG_CS) * 16
                    + uc.reg_read(UC_X86_REG_IP))
        if on_block is not None and len(self.pwm) > sent:
            on_block(bytes(self.pwm[sent:]))
        return self.exited


class Engine(object):
    """Speaks text with the 1990 PC speaker engine.

    One initialised image is captured once and restored per utterance, the way
    PC-TALKER 5.01's snapshot is reused: the program's start-up includes a
    three-pass CPU speed calibration against the DOS clock, and paying that on
    every phrase would be most of the cost of speaking.
    """

    #: How the driver presents it.  The banner reads
    #: `PC-TALKER Beszedszintetizator / SPEAKER_ v. 1.0`, Copyright 1990;
    #: the recordings it is built from are dated 1989.
    id = "speaker10"
    label = "SPEAKER 1.0 (1990) - PC speaker"

    def __init__(self, exe_path=None, work_dir=None):
        here = os.path.dirname(os.path.abspath(__file__))
        self.exe = exe_path or os.path.join(here, "OLVASSP.EXE")
        if not os.path.isfile(self.exe):
            raise EngineError("OLVASSP.EXE is missing from %s" % here)
        self.work = work_dir or here
        self.rate = SAMPLE_RATE
        self._snapshot = None
        self._host = None
        self._prime()

    # -- snapshot ----------------------------------------------------------
    def _prime(self):
        """Run start-up once and remember the state it leaves behind.

        Stopping point is the entry to the `*` branch's continuation: by then
        the banner is printed, the CPU is calibrated and the timer programmed,
        and all that is left is to hand it a string.
        """
        host = _Host(self.work)
        # A tail is required: with an empty one the program prints its banner
        # and terminates in a millisecond, by design.  `*` is the shortest
        # that reaches the speak path.
        host.start(self.exe, "*")
        # Code and data do NOT share a segment: the program runs at CS=2A76h
        # while its variables live at DS=0810h, the load segment.  Both are
        # taken from the machine rather than computed, so a different build
        # would still land in the right place.
        code_seg = host.uc.reg_read(UC_X86_REG_CS)
        self._ready = False
        host.uc.hook_add(UC_HOOK_CODE, self._on_ready, None,
                         code_seg * 16 + EP_SPEAK, code_seg * 16 + EP_SPEAK)
        host.pump(code_seg * 16 + host.uc.reg_read(UC_X86_REG_IP),
                  max_samples=1)
        if not self._ready:
            raise EngineError("OLVASSP never reached the speak entry point")
        self._host = host

    def _lin(self, off):
        """Data-segment offset -> linear address, using the DS the program set."""
        return self._regs[UC_X86_REG_DS] * 16 + off

    def _on_ready(self, uc, address, size, user):
        if self._ready:
            return
        self._ready = True
        self._regs = _save_regs(uc)
        self._mem = bytes(uc.mem_read(0, 0x110000))
        uc.emu_stop()

    # -- speaking ----------------------------------------------------------
    def speak(self, text, on_block=None, block=2048, should_cancel=None):
        """Synthesize one phrase.  Returns 8-bit unsigned PWM samples.

        The text goes straight into the buffer the `*` branch fills, so the
        126-byte PSP command tail is not a limit here.
        """
        if isinstance(text, bytes):
            raw = text
        else:
            raw = text.encode("cp852", "replace")
        raw = raw.replace(b"\r", b" ").replace(b"\n", b" ").strip()
        if not raw:
            return b""
        raw = raw[:MAX_TEXT]

        host = self._host
        uc = host.uc
        uc.mem_write(0, self._mem)
        _load_regs(uc, self._regs)
        host.pwm = bytearray()
        host.stalled = False
        host.exited = None
        host._pending_irq = None
        host.cycles = self._regs["cycles"]

        # length byte then the text, exactly as the `*` branch leaves it
        uc.mem_write(self._lin(OFF_TEXT),
                     bytes([len(raw)]) + raw + b"\r")
        uc.mem_write(self._lin(OFF_FLAG), struct.pack("<H", 1))
        # The snapshot was taken standing on EP_SPEAK, so resuming from the
        # restored CS:IP re-enters it without having to know the code segment.
        host.pump(self._regs[UC_X86_REG_CS] * 16 + self._regs[UC_X86_REG_IP],
                  on_block=on_block, block=block, should_cancel=should_cancel)
        return bytes(host.pwm)

    def reset(self):
        """Rebuild from the exe.  Only needed after an emulation fault."""
        self._prime()


_REGS = (UC_X86_REG_AX, UC_X86_REG_BX, UC_X86_REG_CX, UC_X86_REG_DX,
         UC_X86_REG_SI, UC_X86_REG_DI, UC_X86_REG_BP, UC_X86_REG_SP,
         UC_X86_REG_CS, UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_SS,
         UC_X86_REG_IP, UC_X86_REG_EFLAGS)


def _save_regs(uc):
    d = {r: uc.reg_read(r) for r in _REGS}
    d["cycles"] = 0.0
    return d


def _load_regs(uc, d):
    for r in _REGS:
        uc.reg_write(r, d[r])


class StdinEngine(object):
    """The 1990 reader, `READSPF.EXE`, driven the way its author intended.

    Its own source header says `standard input olvasas Ctrl C -ig`, and that is
    exactly what it does: text goes in on standard input and speech comes out.
    No command-tail switch, no buffer to poke, no 126-byte limit -- and unlike
    the 1991 `OLVASSP.EXE` it reads numbers by itself.

    This is the build `READDEMO.BAT` was written for.  The binary archived in
    the 1992 package was a different, later one, which is why that batch file
    appeared not to work.  The author found this copy on 2026-08-10; it is
    dated 18 March 1990 and matches his own `READSPF.ASM`.

    A fresh guest per utterance: this is not a TSR and has no re-entry point,
    so it is loaded, fed and allowed to finish, exactly as DOS ran it.
    """

    id = "readspf1990"

    def __init__(self, exe_path=None, work_dir=None):
        here = os.path.dirname(os.path.abspath(__file__))
        self.exe = exe_path or os.path.join(here, "READSPF.EXE")
        if not os.path.isfile(self.exe):
            raise EngineError("READSPF.EXE is missing from %s" % here)
        self.work = work_dir or here
        self.rate = SAMPLE_RATE

    def speak(self, text, on_block=None, block=2048, should_cancel=None):
        raw = text if isinstance(text, bytes) else text.encode("cp437", "replace")
        raw = raw.replace(b"\r", b" ").replace(b"\n", b" ").strip()
        if not raw:
            return b""
        # CR ends the line and Ctrl-Z ends the input: what DOS delivered from a
        # redirected file, and what this program waits for before it stops.
        host = _Host(self.work, raw + b"\r" + b"\n" + b"\x1a")
        host.start(self.exe)
        host.pump(host.uc.reg_read(UC_X86_REG_CS) * 16
                  + host.uc.reg_read(UC_X86_REG_IP),
                  on_block=on_block, block=block, should_cancel=should_cancel)
        return bytes(host.pwm)

    def reset(self):
        pass
