# PC-TALKER for NVDA

**Four** NVDA speech synthesizers for the Hungarian PC-TALKER, which **Király
József** wrote between 1987 and 1991. Three of them he rewrote himself, in
Python, in August 2026, and they are in [`kiraly/`](kiraly/). The fourth runs
his original DOS programs under a CPU emulator, instruction by instruction,
inside NVDA's own process — no DOSBox, no external program, no DOS.

> PCTALKER verziókat én készítettem 1989 - 1991 között.
>
> — Király József

## Which one do you want?

**Install one of his.** [`kiraly/`](kiraly/) holds the three editions as he
rebuilt them — Printer, PC Speaker and Sound Blaster. They emulate nothing and
answer instantly, which is what a screen reader needs. For nearly everyone these
are the answer, and **Sound Blaster** is the one to start with: it is the last
version he wrote, and the intonation work is in it.

The emulated add-on stays beside them as the **reference**.

| | [`kiraly/`](kiraly/) — his rewrites | the emulated add-on |
|---|---|---|
| What runs | Python, ported from his own assembly | the original 1990–91 DOS programs |
| Who wrote it | Király József, all of it | the emulator: tgeczy. The engines: his |
| Packages | three, one per edition | one, with three voices |
| Speed | instant | 5× real time on 5.01, 1.7× on the speaker voices |
| Reach for it to | **read your screen** | ask what the original really did |

Calling one of them the reference is not a consolation prize. It is what proved
the other right: his Sound Blaster rewrite was checked against the 1991 program
running here, and it matched — same echo, same pitch. In his own words:

> Az Ön által készített, az eredeti .exe fájlokat használó emuláció óriási érték,
> az én verzióim sem lennének hitelesek ezek nélkül.

It is also the only place `READSPF.EXE` runs at all: the one edition he did not
rewrite.

## Why it went this way

He could have treated a stranger taking his 1991 code apart as an intrusion.
He did the opposite. He took the interest as a reason to give the work a second
life, and spent August 2026 rewriting all three editions as native code that
runs anywhere Python does.

That changes what survives. Hungarian speech synthesis of 1989–91 is no longer
readable only as a disassembly or a 640 KB memory image; it is readable as
source, and it still speaks. Anyone who later wants to study how speech was
actually produced on these machines — how a whole language was cut out of five
seconds of one man's voice, and how it was pushed through a beeper — now has
something to read rather than something to excavate.

So the emulator being superseded for daily use is the good outcome, not a
grudging one. It did the job it was for: it got the originals running again,
and it gave his rewrites something to be verified against.

## His three add-ons

See [`kiraly/README.md`](kiraly/README.md) for what each edition is, how they
relate, and why they sound alike. The short version: they are not three
alternatives but three milestones toward the last one, and each ships its own
assembly source and parses it at run time — the `.ASM` is the data file, not
documentation.

Download them from
[Releases](https://github.com/tgeczy/pctalker-nvda/releases) (tag
`kiraly-2026.08.23`); the emulated add-on is released separately, under its own
version.

## The emulated add-on — three voices

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

Everything is on the
[Releases](https://github.com/tgeczy/pctalker-nvda/releases) page. Download an
`.nvda-addon`, open it, restart NVDA, and pick it in the synthesizer list.

| Release | What it holds |
|---|---|
| `kiraly-2026.08.23` | his three native add-ons — **start here** |
| `v2.8.0` and earlier | the emulated add-on, the reference build |

They can all be installed at once; each appears separately in the synthesizer
list and none of them conflict.

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

This applies to the **emulated** add-on only. None of the DOS-era files it runs
live here — not the programs, not the memory image, not the speech data. Only
the driver, the emulator and the research are in the tree.

(`kiraly/` is the exception, and deliberately so: those are his own 2026 Python
rewrites, published at his request, so they are tracked here in full.)

There are two places to get the rest:

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
