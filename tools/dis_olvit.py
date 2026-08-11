"""Disassemble OLVIT.EXE around its INT F1h calls to recover the TSR protocol.

OLVIT is the tiny client that speaks one line ("olvit PC. talker."), so its
whole job is: find the resident engine, hand it text, ask it to speak.
"""
import struct, sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_16

PATH = r"C:\git\Brailab-wrapper\jatekok_x\TALK\TALK\OLVIT.EXE"
raw = open(PATH, "rb").read()

(sig, lastpage, pages, nreloc, hdrpara, minal, maxal,
 ss, sp, csum, ip, cs, relocoff, overlay) = struct.unpack("<2s13H", raw[:28])
hdr = hdrpara * 16
image = raw[hdr:]
print(f"MZ: hdr={hdr:#x}  image={len(image)} bytes  entry={cs:#06x}:{ip:#06x}  "
      f"SS:SP={ss:#06x}:{sp:#06x}  relocs={nreloc}")

md = Cs(CS_ARCH_X86, CS_MODE_16)
md.detail = False


def dis(start, end, label=""):
    print(f"\n--- {label}  image {start:#06x}-{end:#06x} ---")
    for i in md.disasm(bytes(image[start:end]), start):
        mark = "  <<<" if i.mnemonic == "int" and i.op_str.strip() == "0xf1" else ""
        print(f"  {i.address:04X}  {i.bytes.hex():<14} {i.mnemonic:<7} {i.op_str}{mark}")


# file offsets found earlier -> image offsets
FILE_SITES = [0x8e1, 0x9ba, 0x9c1, 0x9c8, 0x9f4]
sites = [o - hdr for o in FILE_SITES]
print("INT F1h image offsets:", [hex(s) for s in sites])

# entry point first - shows how it locates the engine
dis(cs * 16 + ip, cs * 16 + ip + 0x60, "ENTRY")

for s in sites:
    dis(max(0, s - 0x40), s + 0x08, f"before INT F1h @ {s:#06x}")
