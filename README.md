# PC-TALKER for NVDA

Three Hungarian speech synthesizers from 1990 and 1991, running as NVDA voices —
not reimplemented, not sampled. The original 16-bit DOS programs execute
instruction by instruction under the Unicorn CPU emulator, inside NVDA's own
process. No DOSBox, no external program, no DOS.

> PCTALKER verziókat én készítettem 1989 - 1991 között.
>
> — Király József

## Which one do you want?

There are **four** PC-TALKER add-ons for NVDA, and they split cleanly in two.

| | This repository | [**pctalker-python**](https://github.com/tgeczy/pctalker-python) |
|---|---|---|
| What runs | the original 1990–91 DOS programs, emulated | Python, no emulation |
| Who wrote it | the emulator: tgeczy. The engines: Király József | Király József, all of it |
| Add-ons | one, with three voices | three, one per edition |
| Speed | 5× real time on 5.01, 1.7× on the speaker voices | instant |
| Use it to | ask what the original programs actually did | **read your screen** |

**If you just want a Hungarian voice that works, install
[pctalker-python](https://github.com/tgeczy/pctalker-python).** In August 2026
the author rewrote all three editions himself, in Python, from his own assembly
sources. They emulate nothing and answer instantly.

This repository is the **reference build**. It is the only place the original
binaries still run, which is what makes it worth keeping: his Sound Blaster
rewrite was checked against the 1991 program running here — same echo, same
pitch. In his own words:

> Az Ön által készített, az eredeti .exe fájlokat használó emuláció óriási érték,
> az én verzióim sem lennének hitelesek ezek nélkül.

It is also the only place `READSPF.EXE` runs at all: it is the one edition he did
not rewrite.

## The three voices

**READSPF (1990) — PC speaker.** The earliest of the three, dated
18 March 1990, and the build the author's own `READSPF.ASM` describes. It reads
standard input directly and speaks numbers by itself, so it needs none of the
workarounds the 1991 build requires. This is the version `READDEMO.BAT` was
always written for; the binary archived in the 1992 package was a different,
later one, which is why that batch file appeared not to work. The author found
this copy on 10 August 2026.

**SPEAKER 1.0 (1991) — PC speaker.** Built for a machine with no sound card at
all: amplitude becomes pulse width on channel 2 of the 8253 timer, at 18356 Hz.
Never commercially released. The program that runs is the original
`OLVASSP.EXE`; its banner reads *PC-TALKER Beszédszintetizátor / SPEAKER_ v.
1.0*, Copyright 1990, and the recordings it is assembled from are dated 1989.
No smoothing stage between speech elements, and therefore no echo.

**PC-TALKER 5.01 (1991) — Sound Blaster.** *(default)* The last version, run
from a memory image of the resident driver, called through its `INT F1h` entry
point. Slightly warmer, with a faint room echo — which is deliberate, and named
in the author's `OLVAS_S.ASM`: the `HANG` routine keeps a circular delay buffer
controlled by a variable called `keses`, Hungarian for *delay*, whose output is
fed back into the input so the echoes decay recursively. The manual's `#vnnnn`
command adds to it and cannot subtract, because 250 samples are already there.
It is the default because it is by far the fastest of the three.

Király József began PC-TALKER in 1987, cutting its speech elements from 8 kHz
recordings of his own voice. It was shown at the 1988 Budapest fair driving a
converter on the printer port, then gained its own sound card. Distributed by
Technorecord, Microsystem Kft. (as Micro-Phone) and later SZKI Recognita.

## Install

Download the `.nvda-addon` from
[Releases](https://github.com/tgeczy/pctalker-nvda/releases), open it, restart
NVDA, and pick PC-TALKER in the synthesizer list.

## How it works

The engines are built completely differently, and the driver knows about none
of them: `engines.py` presents them behind one interface, so audio arrives as
8-bit samples with a rate attached.

```
addon/synthDrivers/
  pctalker.py                   NVDA driver; voices come from a registry
  _pctalker_engine/
    pctalker_engines.py         Voice classes — add a third engine here
    pctalker_audio.py           resampling, gain, chunking, CP852/CWI-2 codec
    pctalker_hunum.py           Hungarian numerals (see below)
    pctalker_core.py            5.01: TSR snapshot, INT F1h
    pctalker_speaker.py         1990: OLVASSP.EXE loaded and run as a program
    pctalker_doshost.py         DOS-on-Unicorn: MZ loader, INT 21h, PIT, PPI
```

Audio is captured at the port: every `OUT 42h` from the speaker build is one PWM
sample, every direct-DAC write from the Sound Blaster build is one byte. Both
are fed to nvwave as they are produced, so speech starts before synthesis
finishes.

**The audio path is verified exactly.** Replaying `GITAR` — a guitar recording
shipped with the 1990 package — through this host reproduces the original file
with a mean absolute error of **0.000**, once compared against the interleave
the interrupt handler actually implements.

## What this repository does not contain

None of Király József's own files live here — not the programs, not the memory
image, not the speech data. Only the driver, the emulator and the research are
in the tree. There are two places to get the rest:

- **The released add-on** already contains everything and needs nothing else.
  Download it from
  [Releases](https://github.com/tgeczy/pctalker-nvda/releases), open it, restart
  NVDA.
- **The full archive**, for study rather than use, is at the
  [Internet Archive](https://archive.org/details/pctalker-archive): the original
  executables, the speech element banks, the 1990 demo recordings and the
  decoded audio.

To build from a fresh clone, two files have to be placed by hand:

| file | where it goes |
|---|---|
| `OLVASSP.EXE` | `addon/synthDrivers/_pctalker_engine/` |
| `engine.bin` | `addon/synthDrivers/_pctalker_engine/` and the repository root |

`engine.bin` is a 640 KB image of conventional memory with the PC-TALKER 5.01
resident driver already loaded; `tools/make_snapshot.py` regenerates it from the
original distribution under DOSBox-X.

### The speech element banks

Worth knowing about even if you never build anything. `RAWSP` — the bank the
1990 speaker build reads — is 46,552 bytes of clipped 8-bit PCM: **5.07 seconds
at 9178 Hz**, and every Hungarian word this synthesizer has ever spoken is cut
from it. It decodes with no emulator at all: `(byte - 128)` at 9178 Hz.
`rawhusr.mp3`, the PC-TALKER bank rendered by Király József for his 2018 NJSZT
talk and published at his suggestion, is in the archive item alongside it.

The 1989 source header reads `hangfile = rawsp`, so the elements once lived in a
separate file; the archived `OLVASSP.EXE` carries them embedded instead — one of
the signs that the binary saved in 1992 is a later, different build.

## What the reverse engineering found

`docs/pcspeaker-plan.md` is the full account, kept as a working document —
including the wrong conclusions, marked superseded. The short version:

- **OLVASSP was never broken.** With an empty command tail it prints its banner,
  drops the printer port and terminates in one millisecond, entirely correctly.
  A week of "it is mute" was a week of recording a program that had already
  exited. The tail's first character selects: `*` speaks the rest of the tail,
  `+n`/`-n` set speed, `.` is a *disk sector editor*, and anything else exits.
- **The text encoding is CWI-2, not CP852.** CP852 arrived with DOS 5 in 1991;
  this is a 1990 program and wants the Hungarian page that preceded it — CP437
  with `ő` and `ű` in the circumflex slots. Getting it wrong makes every long
  vowel a silent click. Király's own demo text settles it: byte `93h` appears
  inside `lehetővé`, `tetszőleges` and `minőségileg`.
- **The 1990 engine cannot say digits at all.** `51` renders exactly zero
  samples. `minőségileg` is fine. Hence `pctalker_hunum.py`, which writes
  numbers out as Hungarian words before they reach the engine.
- **Five emulator bugs each produced silence** indistinguishable from a broken
  1990 binary — a frozen DOS clock, zero-cost interrupts (which made the
  program's own CPU-speed calibration overflow a `div` and die, having measured
  a 2026 machine as impossibly fast), Unicorn halting on `hlt`, IRQ0 delivered
  inside the guest's own `cli` window, and ISR vectors installed by direct
  writes to the interrupt table.

Almost every finding that mattered at the end was found by ear, not by
measurement.

## Building

```
python tools/build_addon.py            # -> pctalker-X.Y.Z.nvda-addon
python tools/build_addon.py --install  # sync into %APPDATA%\nvda\addons
```

`tools/sp_trace.py` runs either DOS binary standalone with every DOS call, port
write and stdin byte logged; `tools/sp_dis.py` disassembles by `CS:IP` from a
trace.

## Credits and permission

The engines, the voice and the speech elements are the work of **Király
József**, who made the PC-TALKER versions between 1989 and 1991. He gave
express permission for all of it to be published — the executables, the speech
data and the reverse engineering alike — and asked for no restriction on its
use. His files are kept out of this tree by choice rather than necessity: they
belong with the archive and the released package, where they stay together and
stay findable.

The NVDA driver, the DOS host and the research are by **tgeczy** and are MIT
licensed; see `LICENSE`.
