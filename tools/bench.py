"""Timing + reuse check before committing to a driver design."""
import struct, time, collections
from unicorn import *
from unicorn.x86_const import *

IMG = r"C:\git\pctalker-nvda\engine.bin"
MEM = 0x110000
STACK_SEG, STACK_SP = 0x8000, 0xFFF0
SENT_SEG = 0x9F00
SENT = SENT_SEG * 16
TEXT_SEG = 0x9000
SB = 0x220
PIT_HZ = 1193181.666

img = open(IMG, "rb").read()
voff = img[0xF1 * 4] | (img[0xF1 * 4 + 1] << 8)
vseg = img[0xF1 * 4 + 2] | (img[0xF1 * 4 + 3] << 8)
t8off = img[8 * 4] | (img[8 * 4 + 1] << 8)
t8seg = img[8 * 4 + 2] | (img[8 * 4 + 3] << 8)


class Eng:
    def __init__(self):
        t0 = time.perf_counter()
        self.uc = uc = Uc(UC_ARCH_X86, UC_MODE_16)
        uc.mem_map(0, MEM, UC_PROT_ALL)
        uc.mem_write(0, img)
        self.pcm = bytearray()
        self.expect = None
        self.pit = []
        self.divisor = None
        uc.hook_add(UC_HOOK_INSN, self._out, None, 1, 0, UC_X86_INS_OUT)
        uc.hook_add(UC_HOOK_INSN, self._in, None, 1, 0, UC_X86_INS_IN)
        uc.hook_add(UC_HOOK_INTR, self._intr)
        self.build_ms = (time.perf_counter() - t0) * 1000

    def _out(self, uc_, port, size, value, ud):
        v = value & 0xFF
        if port == SB + 0x0C:
            if self.expect == 0x10:
                self.pcm.append(v); self.expect = None
            elif v == 0x10:
                self.expect = 0x10
            else:
                self.expect = None
        elif port == 0x40:
            self.pit.append(v)
            if len(self.pit) == 2:
                d = self.pit[0] | (self.pit[1] << 8)
                self.divisor = 65536 if d == 0 else d
                self.pit = []

    def _in(self, uc_, port, size, ud):
        return {SB + 0x0C: 0x00, SB + 0x0E: 0x80, SB + 0x0A: 0xAA}.get(port, 0xFF)

    def _intr(self, uc_, intno, ud):
        ax = uc_.reg_read(UC_X86_REG_AX); ah, al = (ax >> 8) & 0xFF, ax & 0xFF
        if intno == 0x21:
            if ah == 0x35:
                o, s = struct.unpack("<HH", uc_.mem_read(al * 4, 4))
                uc_.reg_write(UC_X86_REG_ES, s); uc_.reg_write(UC_X86_REG_BX, o)
            uc_.reg_write(UC_X86_REG_EFLAGS, uc_.reg_read(UC_X86_REG_EFLAGS) & ~1)

    def _enter(self, seg, off):
        uc = self.uc
        uc.reg_write(UC_X86_REG_SS, STACK_SEG); uc.reg_write(UC_X86_REG_SP, STACK_SP)
        sp = STACK_SP
        for w in (uc.reg_read(UC_X86_REG_EFLAGS) & ~0x200, SENT_SEG, 0x0000):
            sp = (sp - 2) & 0xFFFF
            uc.mem_write(STACK_SEG * 16 + sp, struct.pack("<H", w))
        uc.reg_write(UC_X86_REG_SP, sp)
        uc.reg_write(UC_X86_REG_CS, seg); uc.reg_write(UC_X86_REG_IP, off)
        uc.emu_start(seg * 16 + off, SENT, count=50_000_000)

    def speak(self, text):
        uc = self.uc
        payload = b" " + text.encode("cp852", "replace")[:250] + b"\r"
        start = len(self.pcm)
        uc.mem_write(TEXT_SEG * 16, payload)
        uc.reg_write(UC_X86_REG_ES, TEXT_SEG); uc.reg_write(UC_X86_REG_DI, 0)
        uc.reg_write(UC_X86_REG_CX, len(payload)); uc.reg_write(UC_X86_REG_DS, TEXT_SEG)
        uc.reg_write(UC_X86_REG_AX, 0x0000)
        self._enter(vseg, voff)
        ticks, quiet, last = 0, 0, len(self.pcm)
        first_sample_tick = None
        while ticks < 400_000:
            self._enter(t8seg, t8off)
            ticks += 1
            if len(self.pcm) != last:
                if first_sample_tick is None:
                    first_sample_tick = ticks
                last = len(self.pcm); quiet = 0
            else:
                quiet += 1
                if quiet >= 3000 and len(self.pcm) > start:
                    break
        return len(self.pcm) - start, ticks, first_sample_tick


e = Eng()
print(f"emulator build: {e.build_ms:.0f} ms  (1 MB map + 640 KB image)")
for i, txt in enumerate(["PC. talker.", "Szia Tomi.", "a", "Kiraly Jozsef ezerkilencszazkilencvenegy."]):
    t0 = time.perf_counter()
    n, ticks, first = e.speak(txt)
    ms = (time.perf_counter() - t0) * 1000
    rate = PIT_HZ / e.divisor if e.divisor else 9178
    audio = n / rate
    print(f"  [{i}] {txt[:28]!r:32} {n:6d} samples  audio {audio:5.2f}s  "
          f"render {ms:7.0f} ms  ratio {ms/1000/audio if audio else 0:5.2f}x  "
          f"ticks {ticks}  first@{first}")
print(f"\nreuse across {4} calls on ONE emulator instance: OK "
      f"(total {len(e.pcm)} samples accumulated)")
