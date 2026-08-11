"""PC-TALKER under Unicorn, driven the way the real machine drove it.

The AH=0 call does NOT synthesize.  It queues the utterance, reprograms PIT
channel 0 to the sample rate, and returns.  Audio then comes out of the INT 8
timer ISR, one direct-DAC byte per tick.  So we call AH=0, read the divisor it
programmed, then pump the timer ISR until it stops producing samples.

PIT input clock is 1193181.666 Hz, so rate = 1193182 / divisor.
"""
import struct, sys, collections, wave
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
MAX_INSN = 50_000_000
MAX_TICKS = 400_000
QUIET_TICKS = 4000          # stop after this many ticks with no new samples

img = open(IMG, "rb").read()
voff = img[0xF1 * 4] | (img[0xF1 * 4 + 1] << 8)
vseg = img[0xF1 * 4 + 2] | (img[0xF1 * 4 + 3] << 8)
t8off = img[8 * 4] | (img[8 * 4 + 1] << 8)
t8seg = img[8 * 4 + 2] | (img[8 * 4 + 3] << 8)
print(f"INT F1h -> {vseg:04X}:{voff:04X}    INT 08h -> {t8seg:04X}:{t8off:04X}")

text = (sys.argv[1] if len(sys.argv) > 1 else "PC. talker.").encode("cp852", "replace")
payload = b" " + text + b"\r"

uc = Uc(UC_ARCH_X86, UC_MODE_16)
uc.mem_map(0, MEM, UC_PROT_ALL)
uc.mem_write(0, img)

pcm = bytearray()
st = {"expect": None, "pit": [], "divisor": None, "ports": collections.Counter()}


def on_out(uc_, port, size, value, ud):
    v = value & 0xFF
    st["ports"][port] += 1
    if port == SB + 0x0C:
        if st["expect"] == 0x10:
            pcm.append(v)
            st["expect"] = None
        elif v == 0x10:
            st["expect"] = 0x10
        else:
            st["expect"] = None
    elif port == 0x40:
        st["pit"].append(v)
        if len(st["pit"]) == 2:
            d = st["pit"][0] | (st["pit"][1] << 8)
            st["divisor"] = 65536 if d == 0 else d
            st["pit"] = []


def on_in(uc_, port, size, ud):
    if port == SB + 0x0C:
        return 0x00
    if port == SB + 0x0E:
        return 0x80
    if port == SB + 0x0A:
        return 0xAA
    return 0xFF


def on_intr(uc_, intno, ud):
    ax = uc_.reg_read(UC_X86_REG_AX)
    ah, al = (ax >> 8) & 0xFF, ax & 0xFF
    if intno == 0x21:
        if ah == 0x35:
            o, s = struct.unpack("<HH", uc_.mem_read(al * 4, 4))
            uc_.reg_write(UC_X86_REG_ES, s); uc_.reg_write(UC_X86_REG_BX, o)
        elif ah == 0x25:
            ds = uc_.reg_read(UC_X86_REG_DS); dx = uc_.reg_read(UC_X86_REG_DX)
            uc_.mem_write(al * 4, struct.pack("<HH", dx, ds))
        elif ah == 0x30:
            uc_.reg_write(UC_X86_REG_AX, 0x0005)
        uc_.reg_write(UC_X86_REG_EFLAGS, uc_.reg_read(UC_X86_REG_EFLAGS) & ~1)
    elif intno == 0x16:
        uc_.reg_write(UC_X86_REG_AX, 0)


uc.hook_add(UC_HOOK_INSN, on_out, None, 1, 0, UC_X86_INS_OUT)
uc.hook_add(UC_HOOK_INSN, on_in, None, 1, 0, UC_X86_INS_IN)
uc.hook_add(UC_HOOK_INTR, on_intr)


def far_call(seg, off, setup):
    """Enter an interrupt handler and run until it IRETs to the sentinel."""
    uc.reg_write(UC_X86_REG_SS, STACK_SEG)
    uc.reg_write(UC_X86_REG_SP, STACK_SP)
    setup()
    sp = STACK_SP
    for w in (uc.reg_read(UC_X86_REG_EFLAGS) & ~0x200, SENT_SEG, 0x0000):
        sp = (sp - 2) & 0xFFFF
        uc.mem_write(STACK_SEG * 16 + sp, struct.pack("<H", w))
    uc.reg_write(UC_X86_REG_SP, sp)
    uc.reg_write(UC_X86_REG_CS, seg)
    uc.reg_write(UC_X86_REG_IP, off)
    uc.emu_start(seg * 16 + off, SENT, count=MAX_INSN)


def speak_setup():
    uc.mem_write(TEXT_SEG * 16, payload)
    uc.reg_write(UC_X86_REG_ES, TEXT_SEG)
    uc.reg_write(UC_X86_REG_DI, 0)
    uc.reg_write(UC_X86_REG_CX, len(payload))
    uc.reg_write(UC_X86_REG_DS, TEXT_SEG)
    uc.reg_write(UC_X86_REG_AX, 0x0000)


print(f"speaking {text!r}")
far_call(vseg, voff, speak_setup)
print(f"  AH=0 returned; PIT divisor = {st['divisor']}", end="")
rate = PIT_HZ / st["divisor"] if st["divisor"] else None
print(f"  -> {rate:.1f} Hz" if rate else "  (timer not reprogrammed)")

# pump the timer ISR
ticks, last_len, quiet = 0, 0, 0
while ticks < MAX_TICKS:
    try:
        far_call(t8seg, t8off, lambda: None)
    except UcError as e:
        print(f"  ISR fault after {ticks} ticks: {e}")
        break
    ticks += 1
    if len(pcm) == last_len:
        quiet += 1
        if quiet >= QUIET_TICKS and len(pcm):
            break
    else:
        quiet = 0
        last_len = len(pcm)

print(f"  ticks pumped: {ticks}")
print(f"\nPCM bytes: {len(pcm)}")
print("ports:", st["ports"].most_common(6))
if pcm:
    print(f"sample range {min(pcm)}..{max(pcm)}   duration {len(pcm)/(rate or 8000):.2f}s")
    out = r"C:\git\pctalker-nvda\work\raw_test.wav"
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(1); w.setframerate(int(rate or 8000))
        w.writeframes(bytes(pcm))
    print("wrote", out)
