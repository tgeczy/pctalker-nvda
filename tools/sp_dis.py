# -*- coding: utf-8 -*-
"""Disassemble a segment of one of the SPEAKER binaries by CS:IP.

The trace prints guest addresses as CS:IP, so the useful lookup is "show me
that segment", not "show me that file offset".  Give it the load segment the
tracer printed and it does the arithmetic.
"""
import argparse
import os
import sys

from capstone import Cs, CS_ARCH_X86, CS_MODE_16

SP = r"C:\pctalker_temp\x\SP"
HDR = 0x200


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("program")
    ap.add_argument("cs", help="segment from the trace, hex")
    ap.add_argument("ip", help="offset to start at, hex")
    ap.add_argument("--load", default="810", help="load segment, hex")
    ap.add_argument("--count", type=int, default=60)
    args = ap.parse_args()

    data = open(os.path.join(SP, "EXE", args.program.upper() + ".EXE"),
                "rb").read()[HDR:]
    cs, ip, load = int(args.cs, 16), int(args.ip, 16), int(args.load, 16)
    base = (cs - load) * 16
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    md.detail = False
    print("%s  CS=%04X (image %06X)  from IP %04X"
          % (args.program.upper(), cs, base, ip))
    for i in md.disasm(data[base + ip:base + ip + args.count * 8], ip):
        print("  %04X  %-22s %s %s"
              % (i.address, i.bytes.hex(), i.mnemonic, i.op_str))
        if i.address - ip > args.count * 3:
            break


if __name__ == "__main__":
    sys.exit(main())
