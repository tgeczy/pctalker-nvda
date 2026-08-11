# -*- coding: utf-8 -*-
"""
A small DOS host on Unicorn, enough to run the BraiLab-era programs.

Same idea as the Dr. Sbaitso addon and as talkhun.py: emulate the CPU, shim the
handful of DOS and BIOS calls the software actually uses, and keep everything
self-contained -- no DOSBox, no external emulator, nothing to build.

Scope was measured, not guessed.  Scanning all 100 executables in the JATEKOK
corpus for INT sites gives:

    int 21h  1537 sites, dominated by AH=40 write, 3F read, 4C exit, 35 get
             vector, 3E close, 25 set vector, 48/4A/49 memory, 02/06/09 console
    int 10h   236   BIOS video (text mode)
    int 16h   225   BIOS keyboard
    int 1Ah    81   BIOS clock
    int 13h    79   BIOS disk (rare paths)
    int 14h    36   *** the TALKHUN speech path, in 16 files incl. FERDIT ***
    int 33h    91   mouse (stubbed; these are keyboard programs)

74 of the executables also write text video memory at B800 directly, which is
how the resident screen reader saw them.

What makes this worth doing rather than patching an emulator: TALKHUN.COM is
itself just a .COM we already load and run, so the speech path inside the guest
is the original 1991 code, and the LPT bit-bang it emits is decoded by the same
code that already works in talkhun.py.
"""

import os
import struct

from unicorn import (
    Uc, UcError, UC_ARCH_X86, UC_MODE_16, UC_PROT_ALL,
    UC_HOOK_INSN, UC_HOOK_INTR, UC_HOOK_BLOCK,
)
from unicorn.x86_const import (
    UC_X86_INS_IN, UC_X86_INS_OUT,
    UC_X86_REG_AX, UC_X86_REG_BX, UC_X86_REG_CX, UC_X86_REG_DX,
    UC_X86_REG_SI, UC_X86_REG_DI, UC_X86_REG_BP, UC_X86_REG_SP,
    UC_X86_REG_CS, UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_SS,
    UC_X86_REG_IP, UC_X86_REG_EFLAGS, UC_X86_REG_AL, UC_X86_REG_AH,
)

MEM_SIZE = 0x110000
#: Conventional memory laid out like a real machine: PSPs and programs from
#: 0x0800 up, with the BIOS data area and IVT below as usual.
FIRST_SEG = 0x0800
LAST_SEG = 0x9000
VIDEO_SEG = 0xB800                  # colour text mode
BIOS_TICK = 0x46C
BIOS_LPT1 = 0x408

SCREEN_COLS = 80
SCREEN_ROWS = 25

#: 8253/8254 PIT and the speaker gate.  Channel 2 drives the PC speaker:
#: write a divisor to 0x42 and the tone is 1193182/divisor Hz; port 0x61
#: bits 0 and 1 gate it on.  Games in this corpus play a little signature
#: through it on startup -- the programmers' way of saying whose game this is.
PIT_HZ = 1193182.0
PORT_PIT_CH2 = 0x42
PORT_PIT_CMD = 0x43
PORT_SPEAKER = 0x61

#: Guest cycles assumed per byte of translated code, and the virtual CPU rate.
#: These only have to be consistent enough that speaker tones last about the
#: right time; the era's machines ran anywhere from an 8086 to a 486.
CYCLES_PER_BYTE = 3.0
DEFAULT_CPU_HZ = 8_000_000.0

#: Port 0x61 bit 4 is the DRAM refresh bit, which flips at ~15.09 kHz on real
#: hardware, and bit 5 follows the PIT channel 2 output.  Delay loops count
#: those flips to time themselves, so both MUST be derived from virtual time.
#: Toggling bit 4 once per read instead makes every delay finish instantly:
#: the speaker tones come out correct but with no silence between them, which
#: sounds like a single tick rather than a tune.
REFRESH_HZ = 15085.0
#: BIOS tick at 0040:006C runs at 18.2065 Hz.
BIOS_TICK_HZ = 1193182.0 / 65536.0

#: A reserved segment standing in for the ROM BIOS.  Everything the guest has
#: to be able to *call* rather than just trigger lives here: the trampolines a
#: resident driver chains to, and the teletype loop that pushes DOS console
#: output back out through INT 10h.
BIOS_SEG = 0xF000
OFF_TELETYPE = 0x0000       # the DS:SI -> INT 10h AH=0E loop
OFF_CFGSEND = 0x0040        # the DS:SI -> INT 14h AH=01 loop
OFF_TRAMPOLINES = 0x0100    # four bytes per vector
OFF_TEXTBUF = 0x0400        # scratch for console strings
TEXTBUF_MAX = 0x0C00
OFF_CFGBUF = 0x1000         # scratch for driver control sequences
OFF_CFGDONE = OFF_CFGSEND + 0x16
OFF_IDLE = 0x0080           # `jmp $`, for letting the driver's pump drain
BIOS_STACK = 0x2000

#: Vectors given a trampoline in the reserved segment.  A TSR saves whatever it
#: finds in the IVT and chains to it with `ljmp cs:[saved]`; if the IVT held
#: 0000:0000 that jump lands in the interrupt table itself.  TALKHUN v4 chains
#: 08h, 10h and 2Fh, so these must be populated *before* it goes resident.
TRAMPOLINED = (0x08, 0x09, 0x10, 0x13, 0x14, 0x16, 0x17, 0x1A,
               0x1C, 0x21, 0x23, 0x24, 0x28, 0x2F, 0x33)
#: `int n` numbers used only as private markers meaning "this is the ROM".
MARKER_BASE = 0xF0


class DosError(OSError):
    """Derived from OSError so a refused path reaches the guest as a failed
    open rather than tearing down the emulator: every file handler already
    turns an OSError into the appropriate DOS error code."""


def render_speaker(events, end_time, rate=44100, level=0.22):
    """Turn (time, freq) speaker events into audio -- the startup signatures."""
    import numpy as np
    if not events:
        return np.zeros(0, dtype=np.int16)
    n = max(1, int((end_time + 0.05) * rate))
    out = np.zeros(n, dtype=np.float64)
    phase = 0.0
    for i, (t0, f) in enumerate(events):
        t1 = events[i + 1][0] if i + 1 < len(events) else end_time
        a, b = int(t0 * rate), min(n, int(t1 * rate))
        if b <= a:
            continue
        if f and 20.0 < f < rate / 2:
            step = f / rate
            ph = phase + step * np.arange(b - a)
            # square wave, as the PIT's mode-3 output actually is
            out[a:b] = level * np.sign(np.sin(2.0 * np.pi * ph))
            phase = (phase + step * (b - a)) % 1.0
    return (out * 32767).astype(np.int16)


class MemoryManager:
    """DOS-style paragraph allocator: a linked list of MCBs, simplified."""

    def __init__(self, first=FIRST_SEG, last=LAST_SEG):
        self.free = [(first, last - first)]     # (segment, size in paragraphs)
        self.blocks = {}                        # segment -> paragraphs

    def alloc(self, paragraphs):
        for i, (seg, size) in enumerate(self.free):
            if size >= paragraphs:
                self.free[i] = (seg + paragraphs, size - paragraphs)
                self.blocks[seg] = paragraphs
                return seg
        return None

    def largest(self):
        return max((s for _, s in self.free), default=0)

    def free_block(self, seg):
        n = self.blocks.pop(seg, None)
        if n is not None:
            self.free.append((seg, n))
        return n is not None

    def resize(self, seg, paragraphs):
        have = self.blocks.get(seg)
        if have is None:
            return False
        if paragraphs <= have:
            if paragraphs < have:
                self.free.append((seg + paragraphs, have - paragraphs))
            self.blocks[seg] = paragraphs
            return True
        return False                            # growing is not supported


class Screen:
    """The 80x25 text plane, kept in guest memory at B800 and readable here.

    Programs in this corpus mostly write it directly, which is exactly how the
    resident screen reader saw them -- so this is the surface a screen reader
    integration would watch.
    """

    def __init__(self, uc):
        self.uc = uc
        self.cursor = (0, 0)

    def clear(self, attr=0x07):
        blank = struct.pack('<BB', 0x20, attr) * (SCREEN_COLS * SCREEN_ROWS)
        self.uc.mem_write(VIDEO_SEG * 16, blank)

    def line(self, row):
        raw = self.uc.mem_read(VIDEO_SEG * 16 + row * SCREEN_COLS * 2,
                               SCREEN_COLS * 2)
        return bytes(raw[0::2]).decode('cp852', 'replace').rstrip()

    def text(self):
        return '\n'.join(self.line(r) for r in range(SCREEN_ROWS))

    def putchar(self, ch, attr=0x07):
        row, col = self.cursor
        if ch == '\r':
            col = 0
        elif ch == '\n':
            row, col = row + 1, 0
        elif ch == '\b':
            col = max(0, col - 1)
        else:
            off = (row * SCREEN_COLS + col) * 2
            self.uc.mem_write(VIDEO_SEG * 16 + off,
                              ch.encode('cp852', 'replace')[:1] + bytes([attr]))
            col += 1
        if col >= SCREEN_COLS:
            row, col = row + 1, 0
        if row >= SCREEN_ROWS:
            self.scroll()
            row = SCREEN_ROWS - 1
        self.cursor = (row, col)

    def scroll(self, attr=0x07):
        base = VIDEO_SEG * 16
        body = self.uc.mem_read(base + SCREEN_COLS * 2,
                                SCREEN_COLS * 2 * (SCREEN_ROWS - 1))
        self.uc.mem_write(base, bytes(body))
        self.uc.mem_write(base + SCREEN_COLS * 2 * (SCREEN_ROWS - 1),
                          struct.pack('<BB', 0x20, attr) * SCREEN_COLS)


class DosHost:
    """Loads and runs DOS programs, with the speech port left to a callback."""

    def __init__(self, cwd, on_lpt=None, lpt_status=None,
                 cpu_hz=DEFAULT_CPU_HZ):
        self.cwd = cwd
        self.cpu_hz = cpu_hz
        self.cycles = 0.0
        # PC speaker state
        self._pit_latch = []
        self._pit_divisor = 0
        self._spk_on = False
        self._port61 = 0x00      # readable latch; see _on_in
        self.speaker_events = []        # (virtual_time_s, freq_hz or None)
        self.on_lpt = on_lpt                    # (port, value) for LPT writes
        self.lpt_status = lpt_status            # callable -> status byte
        self.handles = {0: 'stdin', 1: 'stdout', 2: 'stderr'}
        self.next_handle = 5
        self.files = {}
        self.output = []
        self.keys = []                          # queued scancode/ascii pairs
        self.exited = None
        self.exit_code = 0
        self.hooked_vectors = set()   # vectors a guest TSR has taken over
        #: Only these are dispatched to guest handlers.  Dispatching every
        #: hooked vector regressed the games badly -- they install their own
        #: int 1Ch/24h/etc handlers and re-entering those from here breaks
        #: their control flow.
        #:
        #: 10h is the one that actually makes the games talk: TALKHUN.COM v4 is
        #: a screen reader, and its INT 10h handler tests AH against 0Eh/09h/
        #: 0Ah/13h -- the BIOS text-output calls -- and speaks what it sees.
        #: 14h is the direct speech API, 2Fh its installation check, 08h the
        #: timer tick that drives its output pump.
        self.dispatch_vectors = {0x08, 0x10, 0x14, 0x2F}
        #: Segment range occupied by resident drivers.  Interrupts raised from
        #: inside one are never dispatched back into it -- TALKHUN's own
        #: handlers call INT 10h to read the cursor, and re-entering would spin
        #: forever.
        self.resident_lo = 0
        self.resident_hi = 0
        self._marker_vec = {}
        self._pending_irq = None
        self._no_irq = False
        self._slice_end = None
        #: Block on keyboard reads instead of returning nothing.
        #: Interactive callers set this; headless runs must not,
        #: or a program waiting for input never terminates.
        self.block_on_input = False
        #: Disk transfer address for find-first/find-next.
        self.dta = (0, 0x80)
        self._finds = []
        self._irq0_tick = -1
        self._ticks = 0
        self._build()

    # -- construction ------------------------------------------------------
    def _build(self):
        uc = Uc(UC_ARCH_X86, UC_MODE_16)
        uc.mem_map(0, MEM_SIZE, UC_PROT_ALL)
        self.uc = uc
        self.mem = MemoryManager()
        self.screen = Screen(uc)
        self.screen.clear()
        uc.mem_write(BIOS_LPT1, struct.pack('<H', 0x378))
        uc.mem_write(BIOS_TICK, struct.pack('<I', 0))
        # BIOS data area: 80x25 colour text, one LPT, equipment word
        uc.mem_write(0x449, bytes([0x03]))           # video mode 3
        uc.mem_write(0x44A, struct.pack('<H', 80))   # columns
        uc.mem_write(0x484, bytes([SCREEN_ROWS - 1]))
        uc.hook_add(UC_HOOK_INSN, self._on_in, None, 1, 0, UC_X86_INS_IN)
        uc.hook_add(UC_HOOK_INSN, self._on_out, None, 1, 0, UC_X86_INS_OUT)
        uc.hook_add(UC_HOOK_INTR, self._on_intr)
        uc.hook_add(UC_HOOK_BLOCK, self._on_block)
        self._install_bios()

    def _install_bios(self):
        """Lay out the reserved segment and point the IVT at it.

        Two things live here.  First a trampoline per vector, `int <marker>`
        followed by `iret`: a driver that chains to the original vector lands
        on the marker, our INTR hook runs the real shim, and the `iret` then
        consumes the frame the original `int` left and returns to the caller.
        Unicorn's INTR hook does not push a frame of its own, so this is the
        only way a chained handler can ever return correctly.

        Second the teletype loop.  TALKHUN watches INT 10h, not INT 21h, so DOS
        console output has to be re-emitted a character at a time through the
        BIOS the way the real DOS console driver did -- otherwise the driver
        loads, the game runs, and nothing is ever spoken.
        """
        uc = self.uc
        for i, vec in enumerate(TRAMPOLINED):
            marker = MARKER_BASE + i
            if marker > 0xFF:
                raise DosError('out of marker interrupts')
            self._marker_vec[marker] = vec
            off = OFF_TRAMPOLINES + i * 4
            uc.mem_write(BIOS_SEG * 16 + off, bytes([0xCD, marker, 0xCF]))
            uc.mem_write(vec * 4, struct.pack('<HH', off, BIOS_SEG))

        # push ax/bx/si/ds, walk a NUL-terminated string at BIOS_SEG:OFF_TEXTBUF
        # through INT 10h AH=0Eh, restore, iret
        uc.mem_write(BIOS_SEG * 16 + OFF_TELETYPE, bytes([
            0x50, 0x53, 0x56, 0x1E,                     # push ax bx si ds
            0xB8, BIOS_SEG & 0xFF, BIOS_SEG >> 8,       # mov ax, BIOS_SEG
            0x8E, 0xD8,                                 # mov ds, ax
            0xBE, OFF_TEXTBUF & 0xFF, OFF_TEXTBUF >> 8,  # mov si, OFF_TEXTBUF
            0xAC,                                       # lodsb
            0x08, 0xC0,                                 # or al, al
            0x74, 0x09,                                 # jz done
            0xB4, 0x0E,                                 # mov ah, 0Eh
            0xBB, 0x07, 0x00,                           # mov bx, 0007h
            0xCD, 0x10,                                 # int 10h
            0xEB, 0xF2,                                 # jmp lodsb
            0x1F, 0x5E, 0x5B, 0x58,                     # pop ds si bx ax
            0xCF,                                       # iret
        ]))

        # The same idea for the other direction: walk a NUL-terminated control
        # string out through INT 14h AH=01, which is how `copy BIOS10BE com4`
        # reached the driver.  Runs standalone rather than as a handler, so it
        # ends on a nop that emu_start is told to stop at.
        uc.mem_write(BIOS_SEG * 16 + OFF_CFGSEND, bytes([
            0xB8, BIOS_SEG & 0xFF, BIOS_SEG >> 8,       # mov ax, BIOS_SEG
            0x8E, 0xD8,                                 # mov ds, ax
            0xBE, OFF_CFGBUF & 0xFF, OFF_CFGBUF >> 8,   # mov si, OFF_CFGBUF
            0xAC,                                       # lodsb
            0x08, 0xC0,                                 # or al, al
            0x74, 0x09,                                 # jz done
            0xB4, 0x01,                                 # mov ah, 01h
            0xBA, 0x03, 0x00,                           # mov dx, 0003h (COM4)
            0xCD, 0x14,                                 # int 14h
            0xEB, 0xF2,                                 # jmp lodsb
            0x90,                                       # done: nop
        ]))
        uc.mem_write(BIOS_SEG * 16 + OFF_IDLE,
                     bytes([0x90, 0xEB, 0xFD]))         # nop; jmp $-1

    def _pump(self, addr, max_insns, max_vtime, name='guest'):
        """Run until the guest stops, delivering timer interrupts as they fall.

        Emulation happens in stretches: raising IRQ0 means stopping, building
        its stack frame and resuming inside the handler, which cannot be done
        from within a single emu_start.
        """
        uc = self.uc
        while True:
            try:
                uc.emu_start(addr, 0, count=max_insns)
            except UcError as e:
                if self.exited is None:
                    raise DosError('fault in %s: %s (cs:ip=%04x:%04x)'
                                   % (name, e, uc.reg_read(UC_X86_REG_CS),
                                      uc.reg_read(UC_X86_REG_IP)))
                break
            if self._pending_irq is None or self.exited is not None:
                break
            vec = self._pending_irq
            self._pending_irq = None
            if vec in self.hooked_vectors:
                self._dispatch_guest(vec)
            if self.vtime > max_vtime:
                self.exited = self.exited or 'timeout'
                break
            addr = uc.reg_read(UC_X86_REG_CS) * 16 + uc.reg_read(UC_X86_REG_IP)
        return self.exited

    def say(self, text, seconds=6.0, max_insns=20_000_000):
        """Print text through BIOS teletype and let the driver speak it.

        This is the route the games take -- nothing in the corpus asks to be
        spoken, it just writes to the screen and a resident reader picks it up.
        Driving the same path directly is the honest way to test the chain.
        """
        uc = self.uc
        raw = text.encode('cp852', 'replace').replace(b'\0', b' ')
        uc.mem_write(BIOS_SEG * 16 + OFF_TEXTBUF, raw[:TEXTBUF_MAX - 1] + b'\0')
        uc.reg_write(UC_X86_REG_CS, BIOS_SEG)
        uc.reg_write(UC_X86_REG_SS, BIOS_SEG)
        uc.reg_write(UC_X86_REG_SP, BIOS_STACK)
        # the teletype loop ends in iret, so leave it a frame returning to the
        # idle spin, where the timer can go on draining the speech queue
        uc.reg_write(UC_X86_REG_IP, OFF_IDLE)
        self._dispatch_far(BIOS_SEG, OFF_TELETYPE)
        deadline = self.vtime + seconds
        keep, self.exited = self.exited, None
        self._pump(BIOS_SEG * 16 + OFF_TELETYPE, max_insns, deadline, 'say')
        self.exited = keep
        return self.vtime

    def idle(self, seconds, max_insns=20_000_000):
        """Spin for `seconds` of virtual time so the driver can finish talking.

        Speech is not emitted by the call that produces the text; the driver
        queues it and the timer handler feeds the port a frame at a time.  A
        guest that has stopped running never lets that queue drain.
        """
        uc = self.uc
        deadline = self.vtime + seconds
        keep, self.exited = self.exited, None
        uc.reg_write(UC_X86_REG_CS, BIOS_SEG)
        uc.reg_write(UC_X86_REG_SS, BIOS_SEG)
        uc.reg_write(UC_X86_REG_SP, BIOS_STACK)
        uc.reg_write(UC_X86_REG_IP, OFF_IDLE)
        self._pump(BIOS_SEG * 16 + OFF_IDLE, max_insns, deadline, 'idle')
        self.exited = keep
        return self.vtime

    def send_com4(self, data):
        """Feed a control string to the resident driver, as DOS `copy` did.

        BraiLab was configured by copying tiny files of escape sequences to
        COM4 -- BIOS10BE is `ESC A F`, FURCSABE is `ESC F 1`.  Without at least
        the first of those, TALKHUN v4 loads, hooks INT 10h, watches every
        character go past and stays completely silent: the mask at [0xaf44]
        that decides which BIOS calls to speak starts out zero.
        """
        if isinstance(data, str):
            data = data.encode('cp852', 'replace')
        data = data.replace(b'\0', b'')
        if not data or 0x14 not in self.hooked_vectors:
            return False
        uc = self.uc
        uc.mem_write(BIOS_SEG * 16 + OFF_CFGBUF, data + b'\0')
        uc.reg_write(UC_X86_REG_CS, BIOS_SEG)
        uc.reg_write(UC_X86_REG_SS, BIOS_SEG)
        uc.reg_write(UC_X86_REG_SP, BIOS_STACK)
        uc.reg_write(UC_X86_REG_IP, OFF_CFGSEND)
        # this stretch runs to a fixed end address, so a timer interrupt
        # stopping it early would abandon the rest of the string
        self._no_irq = True
        try:
            uc.emu_start(BIOS_SEG * 16 + OFF_CFGSEND,
                         BIOS_SEG * 16 + OFF_CFGDONE, count=2_000_000)
        finally:
            self._no_irq = False
        return True

    # -- ports -------------------------------------------------------------
    def _on_in(self, uc, port, size, user):
        if port == 0x379 and self.lpt_status:
            return self.lpt_status()
        if port == PORT_SPEAKER:
            # Read back what was written -- programs drive the speaker with
            # in/or 3/out then in/and FCh/out, so a constant 0xFF collapses the
            # "on" write onto the "off" one and no tone is ever detected.
            v = self._port61 & 0x0F
            t = self.vtime
            if int(t * REFRESH_HZ) & 1:
                v |= 0x10                       # refresh bit
            f = self._speaker_state()
            if f and int(t * f * 2.0) & 1:
                v |= 0x20                       # timer 2 output
            return v
        return 0xFF

    @property
    def vtime(self):
        return self.cycles / self.cpu_hz

    def _speaker_state(self):
        if self._spk_on and self._pit_divisor > 0:
            return PIT_HZ / self._pit_divisor
        return None

    def _note(self):
        f = self._speaker_state()
        if not self.speaker_events or self.speaker_events[-1][1] != f:
            self.speaker_events.append((self.vtime, f))

    def _on_out(self, uc, port, size, value, user):
        v = value & 0xFF
        if port in (0x378, 0x37A) and self.on_lpt:
            self.on_lpt(port, v)
        elif port == PORT_PIT_CMD:
            if (v >> 6) == 2:               # selecting channel 2
                self._pit_latch = []
        elif port == PORT_PIT_CH2:
            self._pit_latch.append(v)
            if len(self._pit_latch) == 2:
                self._pit_divisor = self._pit_latch[0] | (self._pit_latch[1] << 8)
                self._pit_latch = []
                self._note()
        elif port == PORT_SPEAKER:
            self._port61 = v
            on = (v & 3) == 3               # gate AND data enable
            if on != self._spk_on:
                self._spk_on = on
                self._note()

    @property
    def bios_ticks(self):
        """0040:006C, derived from virtual time so delay loops run true."""
        return int(self.vtime * BIOS_TICK_HZ) & 0xFFFFFFFF

    def _on_block(self, uc, address, size, user):
        self.cycles += size * CYCLES_PER_BYTE
        self._ticks += 1
        # End a slice here rather than waiting for the next timer interrupt:
        # a guest that runs a long stretch between ticks would otherwise
        # overrun by seconds, and interactive input would arrive far too late.
        if self._slice_end is not None and self.vtime > self._slice_end:
            self._pending_irq = None
            uc.emu_stop()
            return
        if self._ticks % 64 == 0:
            uc.mem_write(BIOS_TICK, struct.pack('<I', self.bios_ticks))
        # Raise IRQ0 when virtual time crosses a tick.  TALKHUN v4's output
        # pump lives on the timer: its INT 08h handler runs the cursor poll and
        # the speech queue, so without this the driver sees text and still
        # never says it.  Never re-enter it from inside the driver itself.
        if (0x08 in self.hooked_vectors and self._pending_irq is None
                and not self._no_irq):
            tick = self.bios_ticks
            if tick != self._irq0_tick:
                self._irq0_tick = tick
                cs = uc.reg_read(UC_X86_REG_CS)
                if not self.resident_lo <= cs < self.resident_hi:
                    self._pending_irq = 0x08
                    uc.emu_stop()

    # -- program loading ---------------------------------------------------
    def _make_env(self, path):
        r"""Build a DOS 3+ environment block and return its segment.

        The tail matters more than the variables: after the strings and their
        terminator comes a word 0001 and the program's own full path, which is
        how a program finds its own image on disk.  A self-extracting archive
        needs that to read the archive out of itself -- with the environment
        segment left at zero it prints its banner, fails to open anything and
        exits, which is indistinguishable from a corrupt archive.
        """
        name = os.path.basename(path).upper().encode('cp852', 'replace')
        env = (b'PATH=C:\\\x00COMSPEC=C:\\COMMAND.COM\x00\x00'
               + struct.pack('<H', 1) + b'C:\\' + name + b'\x00')
        seg = self.mem.alloc((len(env) + 15) // 16 + 1)
        if seg is None:
            return 0
        self.uc.mem_write(seg * 16, env)
        return seg

    def _make_psp(self, seg, tail=b'', env_seg=0):
        psp = bytearray(0x100)
        psp[0:2] = b'\xcd\x20'
        psp[2:4] = struct.pack('<H', LAST_SEG)
        psp[0x2C:0x2E] = struct.pack('<H', env_seg)
        psp[0x50:0x53] = b'\xcd\x21\xcb'
        psp[0x80] = min(len(tail), 0x7E)
        psp[0x81:0x81 + len(tail)] = tail[:0x7E]
        psp[0x81 + min(len(tail), 0x7E)] = 0x0D
        self.uc.mem_write(seg * 16, bytes(psp))

    def load(self, path, args=''):
        """Load a .COM or MZ .EXE.  Returns (cs, ip, ss, sp)."""
        data = open(path, 'rb').read()
        tail = (' ' + args).encode('cp852') if args else b''

        if data[:2] in (b'MZ', b'ZM'):
            (_, lastpage, pages, nreloc, hdrpara, minalloc, maxalloc,
             ss, sp, csum, ip, cs, reltab, overlay) = struct.unpack('<14H', data[:28])
            load_off = hdrpara * 16
            img_size = (pages - 1) * 512 + (lastpage or 512) - load_off
            image = data[load_off:load_off + img_size]
            need = (len(image) + 15) // 16 + 0x10 + max(minalloc, 0x10)
            psp_seg = self.mem.alloc(need)
            if psp_seg is None:
                raise DosError('out of memory loading %s' % path)
            load_seg = psp_seg + 0x10
            self._make_psp(psp_seg, tail, self._make_env(path))
            self.uc.mem_write(load_seg * 16, image)
            # apply relocations
            for i in range(nreloc):
                off, seg = struct.unpack_from('<HH', data, reltab + i * 4)
                addr = (load_seg + seg) * 16 + off
                val = struct.unpack('<H', self.uc.mem_read(addr, 2))[0]
                self.uc.mem_write(addr, struct.pack('<H', (val + load_seg) & 0xFFFF))
            return (load_seg + cs) & 0xFFFF, ip, (load_seg + ss) & 0xFFFF, sp, psp_seg

        # flat .COM
        need = 0x10 + (len(data) + 15) // 16 + 0x1000
        psp_seg = self.mem.alloc(need)
        if psp_seg is None:
            raise DosError('out of memory loading %s' % path)
        self._make_psp(psp_seg, tail, self._make_env(path))
        self.uc.mem_write(psp_seg * 16 + 0x100, data)
        return psp_seg, 0x100, psp_seg, 0xFFFE, psp_seg

    def start(self, path, args=''):
        """Load a program and set up its entry state without running it.

        Split out of run() so a caller can drive the guest in slices, which is
        what interactive use needs: a game only reacts to a keypress if there
        is somewhere to deliver one between slices.
        """
        cs, ip, ss, sp, psp = self.load(path, args)
        self.cur_psp = psp
        uc = self.uc
        for r in (UC_X86_REG_AX, UC_X86_REG_BX, UC_X86_REG_CX, UC_X86_REG_DX,
                  UC_X86_REG_SI, UC_X86_REG_DI, UC_X86_REG_BP):
            uc.reg_write(r, 0)
        uc.reg_write(UC_X86_REG_DS, psp)
        uc.reg_write(UC_X86_REG_ES, psp)
        uc.reg_write(UC_X86_REG_SS, ss)
        uc.reg_write(UC_X86_REG_SP, sp)
        uc.reg_write(UC_X86_REG_CS, cs)
        uc.reg_write(UC_X86_REG_IP, ip)
        self.exited = None
        self._pending_irq = None
        self._name = os.path.basename(path)
        return cs * 16 + ip

    def resume(self, seconds, max_insns=20_000_000):
        """Run the started program for a further `seconds` of guest time.

        Reaching the end of a slice is not the program ending, so the timeout
        marker `_pump` leaves behind is cleared again here.
        """
        uc = self.uc
        addr = uc.reg_read(UC_X86_REG_CS) * 16 + uc.reg_read(UC_X86_REG_IP)
        self._slice_end = self.vtime + seconds
        try:
            res = self._pump(addr, max_insns, self._slice_end,
                             getattr(self, '_name', 'guest'))
        finally:
            self._slice_end = None
        if res == 'timeout':
            self.exited = None
            return None
        return res

    def run(self, path, args='', max_insns=200_000_000, resident=False,
            max_vtime=600.0):
        cs, ip, ss, sp, psp = self.load(path, args)
        self.cur_psp = psp
        uc = self.uc
        for r in (UC_X86_REG_AX, UC_X86_REG_BX, UC_X86_REG_CX, UC_X86_REG_DX,
                  UC_X86_REG_SI, UC_X86_REG_DI, UC_X86_REG_BP):
            uc.reg_write(r, 0)
        uc.reg_write(UC_X86_REG_DS, psp)
        uc.reg_write(UC_X86_REG_ES, psp)
        uc.reg_write(UC_X86_REG_SS, ss)
        uc.reg_write(UC_X86_REG_SP, sp)
        uc.reg_write(UC_X86_REG_CS, cs)
        uc.reg_write(UC_X86_REG_IP, ip)
        self.exited = None
        self._pending_irq = None
        return self._pump(cs * 16 + ip, max_insns, max_vtime,
                          os.path.basename(path))

    # -- interrupts --------------------------------------------------------
    def _cf(self, on):
        f = self.uc.reg_read(UC_X86_REG_EFLAGS)
        self.uc.reg_write(UC_X86_REG_EFLAGS, (f | 1) if on else (f & ~1))

    def _path(self, seg, off):
        r"""Map a guest filename into the one directory the guest can see.

        The drive letter is dropped and everything lands under `cwd`, so the
        program's whole world is the folder it was launched from.  Any attempt
        to climb out of it with `..` is refused rather than clamped, because a
        program that asked for C:\..\..\AUTOEXEC.BAT and silently got a file in
        its own directory would be a stranger bug than an error.

        This matters more since the host learned to create and delete files:
        without it a thirty-year-old binary could reach anywhere on the disk.
        """
        raw = bytes(self.uc.mem_read(seg * 16 + off, 128))
        end = raw.find(b'\0')
        name = raw[:end if end >= 0 else len(raw)].decode('cp852', 'replace')
        name = name.replace('\\', os.sep).split(':')[-1].lstrip(os.sep)
        root = os.path.abspath(self.cwd)
        full = os.path.abspath(os.path.join(root, name))
        if os.path.normcase(full) != os.path.normcase(root) and \
                not os.path.normcase(full).startswith(
                    os.path.normcase(root) + os.sep):
            raise DosError('guest path escapes %s: %r' % (root, name))
        return full

    def _dispatch_guest(self, intno):
        """Invoke a guest-installed handler the way a real INT would."""
        uc = self.uc
        off, seg = struct.unpack('<HH', uc.mem_read(intno * 4, 4))
        if not (seg or off):
            return False
        for val in (uc.reg_read(UC_X86_REG_EFLAGS),
                    uc.reg_read(UC_X86_REG_CS),
                    uc.reg_read(UC_X86_REG_IP)):
            sp = (uc.reg_read(UC_X86_REG_SP) - 2) & 0xFFFF
            ss = uc.reg_read(UC_X86_REG_SS)
            uc.mem_write(ss * 16 + sp, struct.pack('<H', val & 0xFFFF))
            uc.reg_write(UC_X86_REG_SP, sp)
        uc.reg_write(UC_X86_REG_CS, seg)
        uc.reg_write(UC_X86_REG_IP, off)
        return True

    def _dispatch_far(self, seg, off):
        """Enter seg:off as if by INT, so its `iret` returns to the caller."""
        uc = self.uc
        for val in (uc.reg_read(UC_X86_REG_EFLAGS),
                    uc.reg_read(UC_X86_REG_CS),
                    uc.reg_read(UC_X86_REG_IP)):
            sp = (uc.reg_read(UC_X86_REG_SP) - 2) & 0xFFFF
            ss = uc.reg_read(UC_X86_REG_SS)
            uc.mem_write(ss * 16 + sp, struct.pack('<H', val & 0xFFFF))
            uc.reg_write(UC_X86_REG_SP, sp)
        uc.reg_write(UC_X86_REG_CS, seg)
        uc.reg_write(UC_X86_REG_IP, off)

    def _in_resident(self):
        cs = self.uc.reg_read(UC_X86_REG_CS)
        return self.resident_lo <= cs < self.resident_hi

    def _console_out(self, text):
        """Emit console text so a resident screen reader can see it.

        With no INT 10h handler installed this is just a write to the screen.
        With one -- TALKHUN v4 -- the characters have to travel the route they
        took on real hardware: DOS console driver to BIOS teletype, one at a
        time, past the driver that is listening there.
        """
        if not text:
            return False
        if 0x10 not in self.hooked_vectors or self._in_resident():
            for ch in text:
                self.screen.putchar(ch)
            return False
        raw = text.encode('cp852', 'replace').replace(b'\0', b' ')[:TEXTBUF_MAX - 1]
        self.uc.mem_write(BIOS_SEG * 16 + OFF_TEXTBUF, raw + b'\0')
        self._dispatch_far(BIOS_SEG, OFF_TELETYPE)
        return True

    def _on_intr(self, uc, intno, user):
        # a driver chaining to the original vector landed on our trampoline
        if intno in self._marker_vec:
            self._service(self._marker_vec[intno])
            return
        if (intno in self.dispatch_vectors and intno in self.hooked_vectors
                and not self._in_resident() and self._dispatch_guest(intno)):
            return
        self._service(intno)

    def _service(self, intno):
        uc = self.uc
        ax = uc.reg_read(UC_X86_REG_AX)
        ah, al = (ax >> 8) & 0xFF, ax & 0xFF
        if intno == 0x21:
            self._dos(ah, al, ax)
        elif intno == 0x20:
            self.exited = 'int20'
            uc.emu_stop()
        elif intno == 0x10:
            self._bios_video(ah, al)
        elif intno == 0x16:
            self._bios_key(ah)
        elif intno == 0x1A:
            if ah == 0x00:
                t = self.bios_ticks
                uc.reg_write(UC_X86_REG_CX, (t >> 16) & 0xFFFF)
                uc.reg_write(UC_X86_REG_DX, t & 0xFFFF)
        elif intno == 0x08:
            # the hardware timer: keep 0040:006C moving and acknowledge the
            # interrupt controller, exactly as the ROM handler did
            uc.mem_write(BIOS_TICK, struct.pack('<I', self.bios_ticks))
        elif intno == 0x33:
            uc.reg_write(UC_X86_REG_AX, 0)      # no mouse
        else:
            self._cf(False)

    def _bios_video(self, ah, al):
        uc = self.uc
        if ah == 0x00:                          # set video mode
            self.screen.clear()
        elif ah == 0x02:                        # set cursor
            dx = uc.reg_read(UC_X86_REG_DX)
            self.screen.cursor = ((dx >> 8) & 0xFF, dx & 0xFF)
        elif ah == 0x03:
            r, c = self.screen.cursor
            uc.reg_write(UC_X86_REG_DX, (r << 8) | c)
            uc.reg_write(UC_X86_REG_CX, 0x0607)
        elif ah in (0x06, 0x07):                # scroll
            n = al or SCREEN_ROWS
            for _ in range(min(n, SCREEN_ROWS)):
                self.screen.scroll()
        elif ah in (0x09, 0x0A):                # write char at cursor
            self.screen.putchar(chr(al))
        elif ah == 0x0E:                        # teletype
            self.screen.putchar(chr(al))
        elif ah == 0x0F:
            uc.reg_write(UC_X86_REG_AX, (SCREEN_COLS << 8) | 0x03)

    def _wait_for_key(self):
        """Re-execute the current INT so a blocking read really blocks.

        Unicorn's hook leaves IP after the `int n`, so stepping it back two
        bytes makes the guest ask again on the next instruction.  Without this
        a wait-for-key returns immediately with whatever was in AX, which the
        program takes for a keystroke -- a typing tutor reads a stream of
        garbage and a menu picks its own entries.

        Only for interactive use: a headless run has nobody to press anything,
        so there it still returns nothing and lets the program finish.
        """
        if not self.block_on_input:
            return False
        uc = self.uc
        uc.reg_write(UC_X86_REG_IP, (uc.reg_read(UC_X86_REG_IP) - 2) & 0xFFFF)
        return True

    def _bios_key(self, ah):
        uc = self.uc
        if ah in (0x00, 0x10):
            if self.keys:
                uc.reg_write(UC_X86_REG_AX, self.keys.pop(0))
            elif not self._wait_for_key():
                uc.reg_write(UC_X86_REG_AX, 0)
        elif ah in (0x01, 0x11):
            f = uc.reg_read(UC_X86_REG_EFLAGS)
            if self.keys:
                uc.reg_write(UC_X86_REG_AX, self.keys[0])
                uc.reg_write(UC_X86_REG_EFLAGS, f & ~0x40)
            else:
                uc.reg_write(UC_X86_REG_EFLAGS, f | 0x40)
        elif ah == 0x02:
            uc.reg_write(UC_X86_REG_AX, 0)

    def _fill_find(self, path):
        """Write one DOS find record into the guest's transfer address.

        Layout is the documented one: 21 reserved bytes of search state, then
        attribute, time, date, size and a 13-byte ASCIZ name.  The search state
        stays on this side -- nothing in the corpus inspects it, and keeping
        the enumeration in Python avoids pretending to have a FAT directory.
        """
        try:
            st = os.stat(path)
            size = st.st_size
        except OSError:
            size = 0
        name = os.path.basename(path).upper()
        stem, _, ext = name.partition('.')
        dos = (stem[:8] + ('.' + ext[:3] if ext else '')).encode('cp852',
                                                                 'replace')
        rec = bytearray(43)
        rec[21] = 0x10 if os.path.isdir(path) else 0x20
        rec[22:24] = struct.pack('<H', 0x6000)      # 12:00:00
        rec[24:26] = struct.pack('<H', 0x2101)      # 1 Jan 1996
        rec[26:30] = struct.pack('<I', size & 0xFFFFFFFF)
        rec[30:30 + len(dos[:12])] = dos[:12]
        seg, off = self.dta
        self.uc.mem_write(seg * 16 + off, bytes(rec))

    def _dos(self, ah, al, ax):
        uc = self.uc
        ds = uc.reg_read(UC_X86_REG_DS)
        dx = uc.reg_read(UC_X86_REG_DX)
        cx = uc.reg_read(UC_X86_REG_CX)
        bx = uc.reg_read(UC_X86_REG_BX)
        ok = lambda: self._cf(False)

        if ah == 0x4C:
            self.exited, self.exit_code = 'exit', al
            uc.emu_stop()
        elif ah == 0x31:
            self.exited, self.exit_code = 'tsr', al
            # Remember what the driver kept.  Interrupts raised from inside
            # this range are served by the shim rather than dispatched back at
            # the driver -- TALKHUN's handlers issue INT 10h themselves.
            if self.resident_hi:
                self.resident_lo = min(self.resident_lo, self.cur_psp)
            else:
                self.resident_lo = self.cur_psp
            self.resident_hi = max(self.resident_hi, self.cur_psp + max(dx, 1))
            uc.emu_stop()
        elif ah in (0x02, 0x06) and not (ah == 0x06 and (dx & 0xFF) == 0xFF):
            ok()
            # console writes go last in each branch: they may hand control to
            # the BIOS teletype loop, and everything the caller sees on return
            # has to be set before that
            self._console_out(bytes([dx & 0xFF]).decode('cp852', 'replace'))
        elif ah == 0x09:                        # print $-terminated
            buf = bytes(uc.mem_read(ds * 16 + dx, TEXTBUF_MAX))
            end = buf.find(b'$')
            ok()
            self._console_out(buf[:end if end >= 0 else 0]
                              .decode('cp852', 'replace'))
        elif ah in (0x01, 0x07, 0x08):          # character input
            if not self.keys and self._wait_for_key():
                return
            # Interactive programs sit on these waiting for a keypress; with no
            # handler they never advance past their first prompt and never
            # speak.  Returns 0 when the queue is empty rather than blocking,
            # so a headless run still terminates.
            k = self.keys.pop(0) if self.keys else 0
            ch = k & 0xFF
            if ah == 0x01 and ch:
                self.screen.putchar(chr(ch))
            uc.reg_write(UC_X86_REG_AX, (ax & 0xFF00) | ch)
            ok()
        elif ah == 0x0A:                        # buffered line input
            base = ds * 16 + dx
            maxlen = self.uc.mem_read(base, 1)[0]
            line = []
            while self.keys and len(line) < max(1, maxlen - 1):
                ch = self.keys.pop(0) & 0xFF
                if ch in (0, 13):
                    break
                line.append(ch)
            data = bytes(line)
            uc.mem_write(base + 1, bytes([len(data)]))
            uc.mem_write(base + 2, data + b'\r')
            for c in data.decode('cp852', 'replace'):
                self.screen.putchar(c)
            self.screen.putchar('\r')
            self.screen.putchar('\n')
            self.screen.putchar('\n')
            ok()
        elif ah in (0x0B, 0x0C):                # check input status / flush
            if ah == 0x0B:
                uc.reg_write(UC_X86_REG_AX, 0xFF if self.keys else 0x00)
            ok()
        elif ah == 0x30:
            uc.reg_write(UC_X86_REG_AX, 0x0005)
            ok()
        elif ah == 0x35:                        # get interrupt vector
            off, seg = struct.unpack('<HH', uc.mem_read(al * 4, 4))
            uc.reg_write(UC_X86_REG_ES, seg)
            uc.reg_write(UC_X86_REG_BX, off)
            ok()
        elif ah == 0x25:                        # set interrupt vector
            uc.mem_write(al * 4, struct.pack('<HH', dx, ds))
            # Remember it: Unicorn's INTR hook intercepts `int n` and does NOT
            # dispatch through the IVT, so unless we do it by hand a resident
            # handler (TALKHUN's INT 14h) never runs and the guest's speech
            # calls vanish into the shim.
            self.hooked_vectors.add(al)
            ok()
        elif ah == 0x1A:                        # set disk transfer address
            self.dta = (ds, dx)
            ok()
        elif ah == 0x2F:                        # get disk transfer address
            uc.reg_write(UC_X86_REG_ES, self.dta[0])
            uc.reg_write(UC_X86_REG_BX, self.dta[1])
            ok()
        elif ah in (0x4E, 0x4F):                # find first / find next
            if ah == 0x4E:
                try:
                    pat = self._path(ds, dx)
                except DosError:
                    pat = None
                self._finds = []
                if pat:
                    import fnmatch
                    d = os.path.dirname(pat) or self.cwd
                    m = os.path.basename(pat).upper() or '*.*'
                    if m == '*.*':
                        m = '*'
                    try:
                        for e in sorted(os.listdir(d)):
                            if fnmatch.fnmatch(e.upper(), m):
                                self._finds.append(os.path.join(d, e))
                    except OSError:
                        pass
            if not self._finds:
                uc.reg_write(UC_X86_REG_AX, 18)     # no more files
                self._cf(True)
                return
            self._fill_find(self._finds.pop(0))
            uc.reg_write(UC_X86_REG_AX, 0)
            ok()
        elif ah == 0x47:                        # get current directory
            # One directory is all the guest can see, so it is always the root.
            uc.mem_write(ds * 16 + uc.reg_read(UC_X86_REG_SI), b'\0')
            uc.reg_write(UC_X86_REG_AX, 0x0100)
            ok()
        elif ah == 0x3B:                        # change directory
            try:
                if not os.path.isdir(self._path(ds, dx)):
                    raise OSError
                ok()
            except OSError:
                uc.reg_write(UC_X86_REG_AX, 3)
                self._cf(True)
        elif ah == 0x39:                        # create directory
            try:
                os.makedirs(self._path(ds, dx), exist_ok=True)
                ok()
            except OSError:
                uc.reg_write(UC_X86_REG_AX, 3)
                self._cf(True)
        elif ah == 0x3A:                        # remove directory
            try:
                os.rmdir(self._path(ds, dx))
                ok()
            except OSError:
                uc.reg_write(UC_X86_REG_AX, 3)
                self._cf(True)
        elif ah == 0x41:                        # delete file
            try:
                os.remove(self._path(ds, dx))
                ok()
            except OSError:
                uc.reg_write(UC_X86_REG_AX, 2)
                self._cf(True)
        elif ah == 0x57:                        # get/set file date and time
            # Nothing here cares what the timestamp is, but a self-extracting
            # archive stamps every file it writes and treats a failure as a
            # failed extraction.
            if al == 0x00:
                uc.reg_write(UC_X86_REG_CX, 0x6000)     # 12:00:00
                uc.reg_write(UC_X86_REG_DX, 0x2101)     # 1 Jan 1996
            ok()
        elif ah in (0x3C, 0x5B):                # create file / create new
            try:
                p = self._path(ds, dx)
                if ah == 0x5B and os.path.exists(p):
                    uc.reg_write(UC_X86_REG_AX, 80)     # already exists
                    self._cf(True)
                    return
                d = os.path.dirname(p)
                if d:
                    os.makedirs(d, exist_ok=True)
                f = open(p, 'w+b')
                h = self.next_handle
                self.next_handle += 1
                self.files[h] = f
                uc.reg_write(UC_X86_REG_AX, h)
                ok()
            except OSError:
                uc.reg_write(UC_X86_REG_AX, 3)
                self._cf(True)
        elif ah == 0x3D:                        # open file
            try:
                p = self._path(ds, dx)
                f = open(p, 'r+b' if (al & 3) else 'rb')
                h = self.next_handle
                self.next_handle += 1
                self.files[h] = f
                uc.reg_write(UC_X86_REG_AX, h)
                ok()
            except OSError:
                uc.reg_write(UC_X86_REG_AX, 2)
                self._cf(True)
        elif ah == 0x3E:                        # close
            f = self.files.pop(bx, None)
            if f:
                f.close()
            ok()
        elif ah == 0x3F:                        # read
            f = self.files.get(bx)
            if f is None:
                uc.reg_write(UC_X86_REG_AX, 0)
                ok()
            else:
                data = f.read(cx)
                uc.mem_write(ds * 16 + dx, data)
                uc.reg_write(UC_X86_REG_AX, len(data))
                ok()
        elif ah == 0x40:                        # write
            data = bytes(uc.mem_read(ds * 16 + dx, cx)) if cx else b''
            if bx in (1, 2):
                self.output.append(data)
                uc.reg_write(UC_X86_REG_AX, len(data))
                ok()
                self._console_out(data.decode('cp852', 'replace'))
                return
            f = self.files.get(bx)
            if f:
                f.write(data)
            uc.reg_write(UC_X86_REG_AX, len(data))
            ok()
        elif ah == 0x42:                        # seek
            f = self.files.get(bx)
            if f:
                pos = (cx << 16) | dx
                f.seek(pos, al)
                uc.reg_write(UC_X86_REG_AX, f.tell() & 0xFFFF)
                uc.reg_write(UC_X86_REG_DX, (f.tell() >> 16) & 0xFFFF)
            ok()
        elif ah == 0x48:                        # allocate memory
            seg = self.mem.alloc(bx)
            if seg is None:
                uc.reg_write(UC_X86_REG_AX, 8)
                uc.reg_write(UC_X86_REG_BX, self.mem.largest())
                self._cf(True)
            else:
                uc.reg_write(UC_X86_REG_AX, seg)
                ok()
        elif ah == 0x49:                        # free memory
            self.mem.free_block(uc.reg_read(UC_X86_REG_ES))
            ok()
        elif ah == 0x4A:                        # resize memory
            self.mem.resize(uc.reg_read(UC_X86_REG_ES), bx)
            ok()
        elif ah == 0x54:                        # get verify flag
            uc.reg_write(UC_X86_REG_AX, 0)
            ok()
        elif ah in (0x2A, 0x2C):                # date / time
            uc.reg_write(UC_X86_REG_CX, 0)
            uc.reg_write(UC_X86_REG_DX, 0)
            ok()
        elif ah == 0x19:                        # current drive
            uc.reg_write(UC_X86_REG_AX, 2)
            ok()
        else:
            ok()
