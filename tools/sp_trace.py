# -*- coding: utf-8 -*-
r"""Run SPEAKER's DOS binaries under Unicorn with full visibility.

Why not DOSBox: OLVASSP is silent there and DOSBox cannot say why -- its
prompts go out through direct console I/O and its state is unreachable.  This
host runs the same 1990 code with every DOS call, every port write and every
byte of stdin logged, so the question "where does OLVASSP diverge from
PLAYSP10 on identical input" becomes a diff instead of a guess.

The base is talkhun_emu/dos_host.py, already proven on the JATEKOK corpus.
Four things it does not do are added here:

  * stdin redirection.  The host wires handle 0 to the keyboard queue only, so
    a program reading a redirected file sees nothing.  All six input routes
    (AH=01/06.FF/07/08/0A/0B and AH=3F on handle 0) are fed from one shared
    file position, the way DOS feeds them.
  * PWM capture.  The base treats port 42h as a tone divisor -- two writes make
    a frequency.  In this software each single write IS an audio sample, so
    every one is logged with its timestamp and filtered afterwards.
  * IRQ0 at the programmed rate.  The base raises the timer at the BIOS 18.2 Hz
    no matter what the guest wrote to channel 0.  A sample interrupt at 9178 Hz
    would never fire.
  * Vectors installed by writing the IVT directly, with no AH=25 -- normal for
    a 1990 sample ISR, and invisible to the base's hooked-vector set.

Usage:
    python sp_trace.py playsp10 --stdin demosp --seconds 3
    python sp_trace.py olvassp  --stdin demosp --seconds 3
"""
import argparse
import os
import struct
import sys
import wave

sys.path.insert(0, r"C:\git\Brailab-wrapper\talkhun_emu")

from dos_host import (                                       # noqa: E402
    DosHost, DosError, CYCLES_PER_BYTE, BIOS_TICK, BIOS_TICK_HZ, PIT_HZ,
)
from unicorn import (                                        # noqa: E402
    UcError, UC_HOOK_MEM_WRITE, UC_HOOK_CODE,
)
from unicorn.x86_const import (                              # noqa: E402
    UC_X86_REG_AX, UC_X86_REG_BX, UC_X86_REG_CX, UC_X86_REG_DX,
    UC_X86_REG_SI, UC_X86_REG_DI, UC_X86_REG_BP, UC_X86_REG_SP,
    UC_X86_REG_CS, UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_SS,
    UC_X86_REG_IP, UC_X86_REG_EFLAGS,
)

SP = r"C:\pctalker_temp\x\SP"
OUT = r"C:\pctalker_temp\out"
#: Both binaries have a 512-byte MZ header, so a file offset quoted from a
#: disassembly maps to the loaded image by subtracting this.
HDR = 0x200


class SpeakerHost(DosHost):
    """DosHost plus stdin redirection, PWM capture and a real timer rate."""

    def __init__(self, cwd, stdin_bytes=b"", cpu_hz=4_770_000.0,
                 int_cycles=2000.0):
        # every attribute the hooks touch must exist before _build() runs
        self.stdin = stdin_bytes
        self.stdin_pos = 0
        self.stdin_eof_hits = 0
        self.pwm = []                   # (vtime, value) for every OUT 42h
        self.port_counts = {}
        self.ch0_divisor = 0
        self.ch0_latch = []
        self.log = []
        self.log_limit = 400_000
        self.mute_calls = {0x2C}
        self.muted_calls = {}
        self.stop_reason = None
        self.halts = 0
        self.port_log_left = 40      # raised by --port-log
        #: A serviced interrupt costs the guest nothing here, because no guest
        #: instruction runs for it -- but on the machine this was written for,
        #: INT 21h AH=2C went through DOS and the BIOS tick and cost hundreds
        #: of cycles.  With it free, PLAYSP10's speed calibration counts about
        #: 90,000 iterations per 0.30 s, `div byte [00CEh]` (=2) overflows a
        #: byte quotient at 2040, and the program dies of divide overflow
        #: before it plays anything.  The count has to land in an era-plausible
        #: range or the measurement is meaningless.
        self.int_cycles = int_cycles
        self.breakpoints = {}           # linear address -> label
        self.bp_hits = []
        self.load_seg = 0
        self._ivt_seen = set()
        super().__init__(cwd, cpu_hz=cpu_hz)

    # -- construction ------------------------------------------------------
    def _build(self):
        super()._build()
        # A driver that installs its ISR with CLI + a direct IVT store never
        # goes through AH=25, so the base would never dispatch its timer.
        self.uc.hook_add(UC_HOOK_MEM_WRITE, self._on_ivt, None, 0, 0x3FF)

    def _on_ivt(self, uc, access, address, size, value, user):
        for a in range(address, address + size):
            vec = a >> 2
            if vec not in self._ivt_seen:
                self._ivt_seen.add(vec)
                self.hooked_vectors.add(vec)
                self._note_log("IVT", "vector %02Xh written directly" % vec)

    def _note_log(self, kind, text):
        if len(self.log) < self.log_limit:
            self.log.append((self.vtime, kind, text))

    # -- stdin -------------------------------------------------------------
    def _stdin_left(self):
        return len(self.stdin) - self.stdin_pos

    def _stdin_read(self, n):
        data = self.stdin[self.stdin_pos:self.stdin_pos + n]
        self.stdin_pos += len(data)
        if not data:
            self.stdin_eof_hits += 1
        return data

    def _stdin_getc(self):
        if self.stdin_pos >= len(self.stdin):
            self.stdin_eof_hits += 1
            return None
        ch = self.stdin[self.stdin_pos]
        self.stdin_pos += 1
        return ch

    # -- ports -------------------------------------------------------------
    def _on_in(self, uc, port, size, user):
        # The 8259.  `in al,20h / and al,1 / jne` is this software's way of
        # waiting for IRQ0 to clear before it halts; the base host answers 0xFF
        # for unknown ports, which leaves bit 0 set and spins there forever.
        if port in (0x20, 0x21, 0x40, 0x41, 0x42, 0x43):
            return 0x00
        return super()._on_in(uc, port, size, user)

    def _on_out(self, uc, port, size, value, user):
        v = value & 0xFF
        self.port_counts[port] = self.port_counts.get(port, 0) + 1
        if self.port_log_left > 0:
            self.port_log_left -= 1
            self._note_log("OUT", "%02Xh <- %02X  @%04X:%04X"
                           % (port, v, uc.reg_read(UC_X86_REG_CS),
                              uc.reg_read(UC_X86_REG_IP)))
        if port == 0x43:
            if (v >> 6) == 0:                   # selecting channel 0
                self.ch0_latch = []
        elif port == 0x40:
            self.ch0_latch.append(v)
            if len(self.ch0_latch) == 2:
                d = self.ch0_latch[0] | (self.ch0_latch[1] << 8)
                self.ch0_latch = []
                if d != self.ch0_divisor:
                    self.ch0_divisor = d
                    self._note_log("PIT", "channel 0 divisor %d -> %.1f Hz"
                                   % (d, PIT_HZ / d if d else 18.2))
        elif port == 0x42:
            # One write, one sample.  Do not try to pair them into a divisor:
            # this software programs channel 2 LSB-only precisely so that a
            # single byte can be the instantaneous amplitude.
            self.pwm.append((self.vtime, v))
        super()._on_out(uc, port, size, value, user)

    # -- timer -------------------------------------------------------------
    def _dispatch_guest(self, intno):
        """Enter a guest handler the way real hardware does: with IF cleared.

        A real-mode interrupt clears IF and TF before the handler runs, and
        this ISR relies on it -- it re-enables interrupts itself with an
        explicit `sti` immediately before each `hlt`.
        """
        ok = super()._dispatch_guest(intno)
        if ok:
            f = self.uc.reg_read(UC_X86_REG_EFLAGS)
            self.uc.reg_write(UC_X86_REG_EFLAGS, f & ~0x300)
        return ok

    def _irq_enabled(self):
        return bool(self.uc.reg_read(UC_X86_REG_EFLAGS) & 0x200)

    def _next_irq0(self):
        """When the next channel-0 interrupt is due, and at what rate.

        PLAYSP10 writes divisor 65 -> 18356 Hz, which is exactly the OUT 42h
        rate measured off the DOSBox capture and twice the 9178 Hz of the
        recordings: one PWM write per interrupt, two interrupts per sample.
        """
        rate = (PIT_HZ / self.ch0_divisor) if self.ch0_divisor else BIOS_TICK_HZ
        return (int(self.vtime * rate) + 1) / rate, rate

    def _pump(self, addr, max_insns, max_vtime, name="guest"):
        """As the base, but `hlt` means "sleep until the next interrupt".

        Unicorn stops emulating at `hlt` and reports nothing, so to the base
        host a halted guest looks exactly like a finished one -- the run ends
        at the first sample, with identical guest time at every instruction
        budget.  This software halts once per sample, so without this it can
        never play more than one.
        """
        uc = self.uc
        while True:
            try:
                uc.emu_start(addr, 0, count=max_insns)
            except UcError as e:
                if self.exited is None:
                    self.stop_reason = "fault: %s" % e
                    raise DosError("fault in %s: %s (cs:ip=%04x:%04x)"
                                   % (name, e, uc.reg_read(UC_X86_REG_CS),
                                      uc.reg_read(UC_X86_REG_IP)))
                break
            if self.exited is not None:
                break
            cs, ip = uc.reg_read(UC_X86_REG_CS), uc.reg_read(UC_X86_REG_IP)
            if self._pending_irq is not None:
                vec = self._pending_irq
                self._pending_irq = None
                if vec in self.hooked_vectors:
                    self._dispatch_guest(vec)
            elif uc.mem_read(cs * 16 + ((ip - 1) & 0xFFFF), 1)[0] == 0xF4:
                self.halts += 1
                due, rate = self._next_irq0()
                if due > max_vtime:
                    self.stop_reason = "guest-time budget (halted)"
                    break
                if 0x08 not in self.hooked_vectors:
                    self.stop_reason = "halted with no timer handler installed"
                    break
                self.cycles = due * self.cpu_hz
                self._irq0_tick = int(due * rate)
                self._dispatch_guest(0x08)
            else:
                self.stop_reason = self.stop_reason or \
                    "emulation stopped at %04X:%04X" % (cs, ip)
                break
            if self.vtime > max_vtime:
                self.stop_reason = self.stop_reason or "guest-time budget"
                break
            addr = (uc.reg_read(UC_X86_REG_CS) * 16
                    + uc.reg_read(UC_X86_REG_IP))
        return self.exited

    def _on_block(self, uc, address, size, user):
        self.cycles += size * CYCLES_PER_BYTE
        self._ticks += 1
        if self._slice_end is not None and self.vtime > self._slice_end:
            self._pending_irq = None
            self.stop_reason = "guest-time budget"
            uc.emu_stop()
            return
        if self._ticks % 64 == 0:
            uc.mem_write(BIOS_TICK, struct.pack('<I', self.bios_ticks))
        if (0x08 in self.hooked_vectors and self._pending_irq is None
                and not self._no_irq and self._irq_enabled()):
            # Without the IF test the timer fires the moment the IVT store
            # lands, which is inside the guest's own `cli` window: the ISR runs
            # before the program has loaded the registers it works from, and
            # every sample comes out of stale register contents.
            rate = (PIT_HZ / self.ch0_divisor) if self.ch0_divisor \
                else BIOS_TICK_HZ
            n = int(self.vtime * rate)
            if n != self._irq0_tick:
                self._irq0_tick = n
                cs = uc.reg_read(UC_X86_REG_CS)
                if not self.resident_lo <= cs < self.resident_hi:
                    self._pending_irq = 0x08
                    uc.emu_stop()

    # -- DOS ---------------------------------------------------------------
    def _service(self, intno):
        uc = self.uc
        ax = uc.reg_read(UC_X86_REG_AX)
        if intno in (0x21, 0x10, 0x16, 0x1A):
            self.cycles += self.int_cycles
        if intno == 0x21:
            ah = (ax >> 8) & 0xFF
            # The calibration loop alone is 200k calls; logging it buries
            # everything that matters and hits the log cap before playback.
            if ah in self.mute_calls:
                self.muted_calls[ah] = self.muted_calls.get(ah, 0) + 1
                return super()._service(intno)
            self._note_log("INT21", "AH=%02X AL=%02X BX=%04X CX=%04X DX=%04X "
                                    "@%04X:%04X"
                           % ((ax >> 8) & 0xFF, ax & 0xFF,
                              uc.reg_read(UC_X86_REG_BX),
                              uc.reg_read(UC_X86_REG_CX),
                              uc.reg_read(UC_X86_REG_DX),
                              uc.reg_read(UC_X86_REG_CS),
                              uc.reg_read(UC_X86_REG_IP)))
        elif intno < 0x08:
            # CPU exceptions arrive here too: #DE from `div` is intno 0, and a
            # calibration count that does not fit a byte quotient is a very
            # real way for this program to die on a machine it never met.
            self._note_log("CPUEX", "INT %02X AX=%04X @%04X:%04X"
                           % (intno, ax, uc.reg_read(UC_X86_REG_CS),
                              uc.reg_read(UC_X86_REG_IP)))
            self.stop_reason = "CPU exception INT %02Xh" % intno
            uc.emu_stop()
            self.exited = "fault"
            return
        elif intno not in (0x08, 0x10, 0x16, 0x1A):
            self._note_log("INT", "%02Xh AX=%04X @%04X:%04X"
                           % (intno, ax, uc.reg_read(UC_X86_REG_CS),
                              uc.reg_read(UC_X86_REG_IP)))
        super()._service(intno)

    def _dos(self, ah, al, ax):
        uc = self.uc
        ds = uc.reg_read(UC_X86_REG_DS)
        dx = uc.reg_read(UC_X86_REG_DX)
        cx = uc.reg_read(UC_X86_REG_CX)
        bx = uc.reg_read(UC_X86_REG_BX)

        # -- handle-based read from stdin
        if ah == 0x3F and bx == 0:
            data = self._stdin_read(cx)
            if data:
                uc.mem_write(ds * 16 + dx, data)
            uc.reg_write(UC_X86_REG_AX, len(data))
            self._cf(False)
            self._note_log("STDIN", "AH=3F %d/%d bytes %r"
                           % (len(data), cx, data[:32]))
            return

        # -- direct console input, the route that survives redirection
        if ah == 0x06 and (dx & 0xFF) == 0xFF:
            ch = self._stdin_getc()
            f = uc.reg_read(UC_X86_REG_EFLAGS)
            if ch is None:
                uc.reg_write(UC_X86_REG_AX, ax & 0xFF00)
                uc.reg_write(UC_X86_REG_EFLAGS, f | 0x40)      # ZF -> no char
            else:
                uc.reg_write(UC_X86_REG_AX, (ax & 0xFF00) | ch)
                uc.reg_write(UC_X86_REG_EFLAGS, f & ~0x40)
            self._cf(False)
            return

        if ah in (0x01, 0x07, 0x08):
            ch = self._stdin_getc()
            uc.reg_write(UC_X86_REG_AX, (ax & 0xFF00) | (ch or 0))
            self._cf(False)
            return

        if ah == 0x0B:
            uc.reg_write(UC_X86_REG_AX,
                         (ax & 0xFF00) | (0xFF if self._stdin_left() else 0x00))
            self._cf(False)
            return

        if ah == 0x0A:                          # buffered line from stdin
            base = ds * 16 + dx
            maxlen = uc.mem_read(base, 1)[0]
            line = bytearray()
            while self._stdin_left() and len(line) < max(1, maxlen - 1):
                ch = self._stdin_getc()
                if ch in (None, 13, 26):
                    break
                line.append(ch)
            uc.mem_write(base + 1, bytes([len(line)]))
            uc.mem_write(base + 2, bytes(line) + b"\r")
            self._cf(False)
            self._note_log("STDIN", "AH=0A %r" % bytes(line[:40]))
            return

        if ah == 0x2C:
            # The base host answers 00:00:00.00 forever, and PLAYSP10 sits in a
            # calibration loop at 1A69:03DE waiting for the hundredths field to
            # change -- so a working clock is what lets it start at all.  This
            # is how it measures the machine and derives its busy-wait pacing.
            t = self.vtime
            cs_ = int(t * 100) % 100
            sec = int(t) % 60
            mnt = (int(t) // 60) % 60
            hr = (int(t) // 3600) % 24
            uc.reg_write(UC_X86_REG_CX, (hr << 8) | mnt)
            uc.reg_write(UC_X86_REG_DX, (sec << 8) | cs_)
            self._cf(False)
            return

        if ah == 0x2A:                          # date: 1 Jan 1990, Monday
            uc.reg_write(UC_X86_REG_CX, 1990)
            uc.reg_write(UC_X86_REG_DX, (1 << 8) | 1)
            uc.reg_write(UC_X86_REG_AX, (ax & 0xFF00) | 1)
            self._cf(False)
            return

        if ah == 0x3D:
            try:
                p = self._path(ds, dx)
                self._note_log("OPEN", "%s  %s" % (p, "ok" if os.path.exists(p)
                                                   else "MISSING"))
            except OSError as e:
                self._note_log("OPEN", "refused: %s" % e)

        super()._dos(ah, al, ax)

    # -- breakpoints -------------------------------------------------------
    def add_breakpoint(self, linear, label):
        self.breakpoints[linear] = label
        self.uc.hook_add(UC_HOOK_CODE, self._on_bp, None, linear, linear)

    def _on_bp(self, uc, address, size, user):
        label = self.breakpoints.get(address)
        if label is None:
            return
        regs = dict(
            AX=uc.reg_read(UC_X86_REG_AX), BX=uc.reg_read(UC_X86_REG_BX),
            CX=uc.reg_read(UC_X86_REG_CX), DX=uc.reg_read(UC_X86_REG_DX),
            SI=uc.reg_read(UC_X86_REG_SI), DI=uc.reg_read(UC_X86_REG_DI),
            BP=uc.reg_read(UC_X86_REG_BP), SP=uc.reg_read(UC_X86_REG_SP),
            DS=uc.reg_read(UC_X86_REG_DS), ES=uc.reg_read(UC_X86_REG_ES),
            SS=uc.reg_read(UC_X86_REG_SS), CS=uc.reg_read(UC_X86_REG_CS),
            IP=uc.reg_read(UC_X86_REG_IP))
        try:
            at_si = bytes(uc.mem_read(regs["DS"] * 16 + regs["SI"], 16))
        except Exception:
            at_si = b""
        self.bp_hits.append((self.vtime, label, regs, at_si))
        self._note_log("BP", "%s %s [DS:SI]=%s" % (
            label, " ".join("%s=%04X" % (k, v) for k, v in regs.items()),
            at_si.hex()))


def write_wav(path, samples, rate):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"".join(
            struct.pack("<h", max(-32768, min(32767, (s - 128) << 8)))
            for s in samples))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("program", help="playsp10 | olvassp | olvassp0")
    ap.add_argument("--stdin", default="demosp")
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--insns", type=int, default=400_000_000)
    ap.add_argument("--bp", action="append", default=[],
                    help="file offset in hex, e.g. 22c56")
    ap.add_argument("--wav")
    ap.add_argument("--trace")
    ap.add_argument("--port-log", type=int, default=40)
    ap.add_argument("--args", default="", help="PSP command tail")
    ap.add_argument("--cpu-hz", type=float, default=4_770_000.0)
    ap.add_argument("--int-cycles", type=float, default=2000.0)
    args = ap.parse_args()

    exe = os.path.join(SP, "EXE", args.program.upper() + ".EXE")
    stdin_bytes = open(os.path.join(SP, args.stdin), "rb").read()
    print("%s  <%s (%d bytes)" % (os.path.basename(exe), args.stdin,
                                  len(stdin_bytes)))

    host = SpeakerHost(SP, stdin_bytes, cpu_hz=args.cpu_hz,
                       int_cycles=args.int_cycles)
    host.port_log_left = args.port_log
    entry = host.start(exe, args.args)
    host.load_seg = host.cur_psp + 0x10
    print("loaded at seg %04X, entry %04X:%04X"
          % (host.load_seg, host.uc.reg_read(UC_X86_REG_CS),
             host.uc.reg_read(UC_X86_REG_IP)))

    for spec in args.bp:
        off = int(spec, 16)
        linear = host.load_seg * 16 + off - HDR
        host.add_breakpoint(linear, "file+%05X" % off)
        print("breakpoint at file 0x%05X -> linear 0x%06X" % (off, linear))

    res = host.resume(args.seconds, max_insns=args.insns)
    print("\n-- result ------------------------------------------------")
    print("exited      : %r  code %d" % (res, host.exit_code))
    print("stopped by  : %s" % (host.stop_reason or
                                "instruction budget (%d)" % args.insns))
    if host.muted_calls:
        print("muted calls : %s" % " ".join(
            "AH=%02X x%d" % (a, n) for a, n in sorted(host.muted_calls.items())))
    print("guest time  : %.3f s   (%d blocks)" % (host.vtime, host._ticks))
    print("stopped at  : %04X:%04X  (image %06X)"
          % (host.uc.reg_read(UC_X86_REG_CS), host.uc.reg_read(UC_X86_REG_IP),
             (host.uc.reg_read(UC_X86_REG_CS) - host.load_seg) * 16
             + host.uc.reg_read(UC_X86_REG_IP)))
    print("stdin       : %d/%d bytes consumed, %d EOF hits"
          % (host.stdin_pos, len(host.stdin), host.stdin_eof_hits))
    print("ports       : %s" % " ".join(
        "%02Xh=%d" % (p, n) for p, n in sorted(host.port_counts.items())))
    print("OUT 42h     : %d samples" % len(host.pwm))
    print("ch0 divisor : %d" % host.ch0_divisor)
    print("vectors     : %s" % " ".join(
        "%02Xh" % v for v in sorted(host.hooked_vectors)))

    if host.pwm:
        vals = [v for _, v in host.pwm]
        print("PWM range   : %d..%d  mean %d"
              % (min(vals), max(vals), sum(vals) // len(vals)))
        span = host.pwm[-1][0] - host.pwm[0][0]
        if span > 0:
            print("PWM rate    : %.0f writes/s of guest time"
                  % (len(vals) / span))

    # Persist before printing: a console that cannot encode a box-drawing
    # character must not be able to throw the trace away.
    if args.trace:
        with open(args.trace, "w", encoding="utf-8") as f:
            for t, kind, text in host.log:
                f.write("%9.6f  %-6s %s\n" % (t, kind, text))
            f.write("\n-- screen --\n")
            for row in host.screen.text().splitlines():
                if row.strip():
                    f.write("|" + row.rstrip() + "\n")
            f.write("\n-- stdout --\n")
            f.write(b"".join(host.output).decode("cp852", "replace"))
        print("\ntrace: %s  (%d entries)" % (args.trace, len(host.log)))

    print("\n-- screen ------------------------------------------------")
    for row in host.screen.text().splitlines():
        if row.strip():
            print("  |" + row.rstrip())

    print("\n-- stdout (AH=40) ----------------------------------------")
    raw = b"".join(host.output)
    if raw:
        print("  " + raw.decode("cp852", "replace").replace("\n", "\n  "))

    if args.wav and host.pwm:
        # Each OUT 42h is one PWM write, and this software emits every source
        # byte twice -- so the write rate is the WAV rate, and 18356 Hz here is
        # the same 9178 Hz stream the recordings hold, simply 2x oversampled.
        rate = int(PIT_HZ / host.ch0_divisor) if host.ch0_divisor else 0
        if not rate:
            span = host.pwm[-1][0] - host.pwm[0][0]
            rate = int(len(host.pwm) / span) if span > 0 else 18356
        write_wav(args.wav, [v for _, v in host.pwm], rate)
        print("wav: %s  (%d samples @ %d Hz)" % (args.wav, len(host.pwm), rate))
    return 0


if __name__ == "__main__":
    # The banner is CP852 box drawing; a cp1252 console would abort on it.
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    os.makedirs(OUT, exist_ok=True)
    sys.exit(main())
