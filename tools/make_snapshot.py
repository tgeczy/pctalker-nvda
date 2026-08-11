"""Capture a 640K conventional-memory snapshot with PC-TALKER's OLVRES resident.

Runs DOSBox-X on a hidden desktop: mounts the TALK package at C:\\TALK, loads
OLVRES (the TSR), speaks one line so any lazy initialisation is done, then runs
SNAP.COM to dump linear 0..A0000 to SNAP.BIN.

SNAP.COM is reused verbatim from robot-re (63 bytes, hand-assembled).
"""
import ctypes, os, shutil, time
from ctypes import wintypes

ROOT = r"C:\git\pctalker-nvda"
SRC = r"C:\git\Brailab-wrapper\jatekok_x\TALK\TALK"
SNAPCOM = r"C:\git\robot-re\tools\SNAP.COM"
DOSBOX = r"C:\DOSBox-X\dosbox-x.exe"
WORK = os.path.join(ROOT, "work")
DRIVE = os.path.join(WORK, "c")
TALK = os.path.join(DRIVE, "TALK")
TITLE = "PCTSNAP"

if os.path.isdir(DRIVE):
    shutil.rmtree(DRIVE)
os.makedirs(TALK)
for f in os.listdir(SRC):
    shutil.copy2(os.path.join(SRC, f), TALK)
shutil.copy2(SNAPCOM, os.path.join(TALK, "SNAP.COM"))

conf = f"""[sdl]
windowposition = 20000,20000
titlebar       = {TITLE}
autolock       = false

[dosbox]
memsize     = 16
startbanner = false

[cpu]
core    = normal
cputype = 486_prefetch
cycles  = 20000

[mixer]
nosound = true

[sblaster]
sbtype = sb16
sbbase = 220
irq    = 7
dma    = 1
hdma   = 5

[autoexec]
mount c "{DRIVE}"
set BLASTER=A220 I7 D1 H5 T6
c:
cd \\talk
olvres
olvit PC. talker.
snap
exit
"""
confpath = os.path.join(WORK, "snap.conf")
open(confpath, "w").write(conf)

u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
desktop = u32.CreateDesktopW("pctsnap_desk", None, None, 0, 0x10000000, None)


class SI(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_void_p), ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]


class PI(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]


si = SI(); si.cb = ctypes.sizeof(si); si.lpDesktop = "pctsnap_desk"
pi = PI()
if not k32.CreateProcessW(None, f'"{DOSBOX}" -conf "{confpath}" -noconsole',
                          None, None, False, 0, None, WORK,
                          ctypes.byref(si), ctypes.byref(pi)):
    raise SystemExit("CreateProcessW failed")
print(f"dosbox-x pid {pi.dwProcessId}, waiting for SNAP.BIN ...")

target = os.path.join(TALK, "SNAP.BIN")
t0 = time.time()
last = -1
while time.time() - t0 < 90:
    time.sleep(0.5)
    if os.path.exists(target):
        sz = os.path.getsize(target)
        if sz == last and sz >= 640 * 1024:
            break
        last = sz
k32.WaitForSingleObject(pi.hProcess, 5000)
k32.TerminateProcess(pi.hProcess, 0)
u32.CloseDesktop(desktop)

if not os.path.exists(target):
    raise SystemExit("SNAP.BIN was never written")
out = os.path.join(ROOT, "engine.bin")
shutil.copy2(target, out)
print(f"snapshot: {os.path.getsize(out)} bytes -> {out}")

# INT F1h vector lives in the IVT at linear 0xF1*4, which is inside the dump
img = open(out, "rb").read()
off = img[0xF1 * 4] | (img[0xF1 * 4 + 1] << 8)
seg = img[0xF1 * 4 + 2] | (img[0xF1 * 4 + 3] << 8)
print(f"INT F1h vector -> {seg:04X}:{off:04X}   (linear {seg*16+off:#07x})")
print(f"signature word at ES:0 = {img[seg*16] | (img[seg*16+1] << 8):#06x}  (expect 0x07a4)")
