"""Assemble the pctalker NVDA add-on and (optionally) install it."""
import os, shutil, sys, zipfile

ROOT = r"C:\git\pctalker-nvda"
ADDON = os.path.join(ROOT, "addon")
ENGDIR = os.path.join(ADDON, "synthDrivers", "_pctalker_engine")
LIB = os.path.join(ENGDIR, "lib")
UNICORN_SRC = r"C:\Python313\Lib\site-packages\unicorn"
VERSION = "2.7.0"

# --- engine image ---------------------------------------------------------
shutil.copy2(os.path.join(ROOT, "engine.bin"), os.path.join(ENGDIR, "engine.bin"))
open(os.path.join(ENGDIR, "__init__.py"), "w").close()

# core.py -> pctalker_core.py so a bare `import core` can never collide
src = os.path.join(ENGDIR, "core.py")
dst = os.path.join(ENGDIR, "pctalker_core.py")
if os.path.exists(src):
    shutil.move(src, dst)

# --- bundle the 64-bit unicorn -------------------------------------------
tgt = os.path.join(LIB, "unicorn")
if os.path.isdir(tgt):
    shutil.rmtree(tgt)
# unicorn.lib is a ~50 MB STATIC LINK LIBRARY for compiling C programs against
# Unicorn.  The Python bindings load unicorn.dll via ctypes and never touch it,
# so shipping it wastes 79% of the package.  Same for headers and debug info.
shutil.copytree(UNICORN_SRC, tgt,
                ignore=shutil.ignore_patterns(
                    "__pycache__", "*.pyc", "*.pyo",
                    "*.lib", "*.a", "*.exp", "*.pdb", "*.h", "include"))
dll = os.path.join(tgt, "lib", "unicorn.dll")
with open(dll, "rb") as f:
    b = f.read(0x200)
import struct
pe = struct.unpack_from("<I", b, 0x3C)[0]
mach = struct.unpack_from("<H", b, pe + 4)[0]
if mach != 0x8664:
    raise SystemExit("bundled unicorn.dll is not x64 (machine %#x) - NVDA is 64-bit" % mach)
print("bundled unicorn.dll: x64 OK")

# --- manifest -------------------------------------------------------------
manifest = f"""name = pctalker
summary = "PC-TALKER 5.01 (Király József, 1991)"
description = \"\"\"PC-TALKER 5.01 (1991) — Király József Sound Blaster-es magyar beszédszintetizátora, az eredeti DOS-motorral, a Unicorn CPU-emulátorban, az NVDA saját folyamatán belül futtatva. Nincs DOSBox és nincs külső program.

A rezidens meghajtó memóriaképéből fut. Halvány térhatás hallható benne, ami a beszédelemeket összesimító fokozatból ered — ez a motor sajátja, nem a bővítményé.

Király József 1987-ben kezdte a PC-TALKER-t, a beszédelemeket a saját hangjáról készült 8 kHz-es felvételekből vágta ki. 1988-ban mutatta be a budapesti vásáron, nyomtatóportra kötött átalakítóval. Forgalmazta a Technorecord, a Műszertechnika és az SZKI Recognita. A szerző kifejezett engedélyével, 2026 augusztusában.

A két PC-hangszórós hang (READSPF 1990, SPEAKER 1.0 1991) a szerző kérésére átmenetileg nem választható. Lassabb gépen a beszédük szaggatottá válik: az emulációjuk mintánként lép, így nem tartanak elég előnyt a lejátszással szemben. A motorjuk a forráskódban maradt — amint a sebesség rendben lesz, visszakerülnek.

A sebesség újramintavételezéssel készül, ezért a hangmagasság együtt mozog vele. A szerző szerint az eredeti programokban is így működött az intonáció vezérlése.\"\"\"
author = "Király József (motor, 1991) — NVDA-meghajtó: tgeczy"
url = "https://github.com/tgeczy"
version = {VERSION}
docFileName = readme.html
minimumNVDAVersion = 2023.1
lastTestedNVDAVersion = 2026.1
"""
open(os.path.join(ADDON, "manifest.ini"), "w", encoding="utf-8").write(manifest)

# --- docs -----------------------------------------------------------------
# doc/en/readme.html and doc/hu/readme.html are maintained as real files in the
# addon tree, not generated here.  NVDA picks the folder matching its locale and
# falls back to en.
for _lang in ("en", "hu"):
    _p = os.path.join(ADDON, "doc", _lang, "readme.html")
    if not os.path.isfile(_p):
        raise SystemExit("missing documentation: %s" % _p)
print("docs present: en, hu")

# --- package --------------------------------------------------------------
out = os.path.join(ROOT, f"pctalker-{VERSION}.nvda-addon")
if os.path.exists(out):
    os.remove(out)
n = 0
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for base, dirs, files in os.walk(ADDON):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith((".pyc", ".pyo")):
                continue
            full = os.path.join(base, f)
            z.write(full, os.path.relpath(full, ADDON))
            n += 1
print(f"built {out}  ({n} files, {os.path.getsize(out)/1024/1024:.1f} MB)")

# --- install --------------------------------------------------------------
if "--install" in sys.argv:
    dest = os.path.join(os.environ["APPDATA"], "nvda", "addons", "pctalker")
    # Sync in place rather than rmtree: once NVDA has loaded unicorn.dll the
    # file is locked, and wiping the tree fails with a PermissionError even
    # though that DLL has not changed.
    copied = skipped = locked = 0
    for base, dirs, files in os.walk(ADDON):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        rel = os.path.relpath(base, ADDON)
        outdir = dest if rel == "." else os.path.join(dest, rel)
        os.makedirs(outdir, exist_ok=True)
        for f in files:
            if f.endswith((".pyc", ".pyo")):
                continue
            s, d = os.path.join(base, f), os.path.join(outdir, f)
            if os.path.exists(d) and os.path.getsize(s) == os.path.getsize(d) \
                    and open(s, "rb").read() == open(d, "rb").read():
                skipped += 1
                continue
            try:
                shutil.copy2(s, d)
                copied += 1
            except PermissionError:
                locked += 1
                print("  LOCKED (restart NVDA to update):", os.path.relpath(d, dest))
    print(f"installed to {dest}  ({copied} copied, {skipped} unchanged, {locked} locked)")
