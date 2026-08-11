"""Drive PC-TALKER's resident engine under Unicorn and capture its audio.

Protocol recovered from OLVIT.EXE:
    INT 21h AX=35F1h -> ES = TSR segment (we read the IVT directly instead)
    ES:0    = length byte
    ES:1..  = payload, which OLVIT builds as " " + text + CR
    AH = 0, INT F1h -> speak

Audio: OLVRES uses Sound Blaster DIRECT DAC (DSP command 0x10), not DMA -
so every sample is a single byte written to base+0Ch right after a 0x10
command.  We just collect them.
"""
import struct, sys, collections
from unicorn import *
from unicorn.x86_const import *

IMG = r"C:\git\pctalker-nvda\engine.bin"
MEM = 0x110000
STACK_SEG, STACK_SP = 0x8000, 0xFFF0
SENT_SEG = 0x9F00
SENT = SENT_SEG * 16
SB = 0x220
MAX_INSN = 200_000_000

img = open(IMG, "rb").read()
voff = img[0xF1 * 4] | (img[0xF1 * 4 + 1] << 8)
vseg = img[0xF1 * 4 + 2] | (img[0xF1 * 4 + 3] << 8)
print(f"INT F1h handler {vseg:04X}:{voff:04X}")

text = (sys.argv[1] if len(sys.argv) > 1 else "PC. talker.").encode("cp852", "replace")
payload = b" " + text + b"\r"

uc = Uc(UC_ARCH_X86, UC_MODE_16)
uc.mem_map(0, MEM, UC_PROT_ALL)
uc.mem_write(0, img)

pcm = bytearray()
state = {"expect_data": None, "ports": collections.Counter(),
         "unknown_out": collections.Counter(), "unknown_in": collections.Counter(),
         "ints": collections.Counter(), "reset": 0, "speaker": 0}


def on_out(uc_, port, size, value, ud):
    v = value & 0xFF
    state["ports"][port] += 1
    if port == SB + 0x0C:
        if state["expect_data"] == 0x10:
            pcm.append(v)                       # <- a sample
            state["expect_data"] = None
            return
        if v == 0x10:
            state["expect_data"] = 0x10
        elif v in (0xD1, 0xD3):
            state["speaker"] += 1
            state["expect_data"] = None
        else:
            state["expect_data"] = None
    elif port == SB + 0x06:
        state["reset"] += 1
    elif port not in (SB + 0x04, SB + 0x05, 0x20, 0x21, 0x43, 0x40, 0x61):
        state["unknown_out"][port] += 1


def on_in(uc_, port, size, ud):
    if port == SB + 0x0C:
        return 0x00                             # write buffer always ready
    if port == SB + 0x0E:
        return 0x80                             # read data available
    if port == SB + 0x0A:
        return 0xAA                             # reset handshake
    if port == 0x61:
        return 0x00
    if port in (0x40, 0x41, 0x42):
        state["ports"][port] += 1
        return state["ports"][port] & 0xFF      # keep any PIT poll moving
    state["unknown_in"][port] += 1
    return 0xFF


def on_intr(uc_, intno, ud):
    state["ints"][intno] += 1
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
        elif ah in (0x2A, 0x2C):
            uc_.reg_write(UC_X86_REG_CX, 0); uc_.reg_write(UC_X86_REG_DX, 0)
        uc_.reg_write(UC_X86_REG_EFLAGS, uc_.reg_read(UC_X86_REG_EFLAGS) & ~1)
    elif intno == 0x16:
        if ah in (0x01, 0x11):
            uc_.reg_write(UC_X86_REG_EFLAGS, uc_.reg_read(UC_X86_REG_EFLAGS) | 0x40)
        uc_.reg_write(UC_X86_REG_AX, 0)
    elif intno == 0x1A and ah == 0x00:
        uc_.reg_write(UC_X86_REG_CX, 0); uc_.reg_write(UC_X86_REG_DX, 0)


uc.hook_add(UC_HOOK_INSN, on_out, None, 1, 0, UC_X86_INS_OUT)
uc.hook_add(UC_HOOK_INSN, on_in, None, 1, 0, UC_X86_INS_IN)
uc.hook_add(UC_HOOK_INTR, on_intr)

# --- set up the call ---------------------------------------------------
# Convention (from the TSR itself, +062B): ES:DI -> text, CX = length, AH = 0.
# The engine copies it straight into its own data segment, so the buffer can
# live anywhere.  OLVIT parked it at 0000:0001 - the IVT - which we need not
# imitate.
TEXT_SEG = 0x9000
uc.mem_write(TEXT_SEG * 16, payload)
uc.reg_write(UC_X86_REG_ES, TEXT_SEG)
uc.reg_write(UC_X86_REG_DI, 0)
uc.reg_write(UC_X86_REG_CX, len(payload))
uc.reg_write(UC_X86_REG_DS, TEXT_SEG)
uc.reg_write(UC_X86_REG_SS, STACK_SEG)
uc.reg_write(UC_X86_REG_SP, STACK_SP)
uc.reg_write(UC_X86_REG_AX, 0x0000)          # AH=0 -> speak

# fake an INT F1h: the handler ends in IRET, which pops IP, CS, FLAGS
sp = STACK_SP
for w in (uc.reg_read(UC_X86_REG_EFLAGS), SENT_SEG, 0x0000):
    sp = (sp - 2) & 0xFFFF
    uc.mem_write(STACK_SEG * 16 + sp, struct.pack("<H", w))
uc.reg_write(UC_X86_REG_SP, sp)

# CS matters: the handler is full of `mov word ptr cs:[..]` accesses, so CS
# must be the TSR segment or every one of them lands in low memory.
uc.reg_write(UC_X86_REG_CS, vseg)
uc.reg_write(UC_X86_REG_IP, voff)

print(f"speaking {text!r} ({len(payload)} byte payload)")
try:
    uc.emu_start(vseg * 16 + voff, SENT, count=MAX_INSN)
    print("returned cleanly to sentinel")
except UcError as e:
    cs, ip = uc.reg_read(UC_X86_REG_CS), uc.reg_read(UC_X86_REG_IP)
    print(f"emulation stopped: {e}   at {cs:04X}:{ip:04X}")

print(f"\nPCM bytes captured: {len(pcm)}")
print(f"speaker on/off cmds: {state['speaker']}   DSP resets: {state['reset']}")
print("interrupts:", dict(state["ints"]))
print("top ports:", state["ports"].most_common(8))
if state["unknown_out"]:
    print("UNKNOWN OUT:", state["unknown_out"].most_common(8))
if state["unknown_in"]:
    print("UNKNOWN IN :", state["unknown_in"].most_common(8))

if pcm:
    lo, hi = min(pcm), max(pcm)
    print(f"sample range {lo}..{hi}  (silence would be flat)")
    import wave
    out = r"C:\git\pctalker-nvda\work\raw_test.wav"
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(1); w.setframerate(11025)
        w.writeframes(bytes(pcm))
    print("wrote", out, "(rate is a placeholder pending calibration)")
