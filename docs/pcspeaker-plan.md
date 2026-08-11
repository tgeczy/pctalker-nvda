# PC-TALKER, PC speaker edition — feasibility and plan

Király József's PC speaker build of PC-TALKER, sent 2026-08-07 (`PCTAKER_SP.zip`).
**Never commercially released.** He asked directly whether an emulator could make it
speak again; this is the answer to that question.

## What is in the package

```
EXE/OLVASSP.EXE    147,280   pure DOS MZ   the reader
EXE/OLVASSP0.EXE    79,536   pure DOS MZ   variant
EXE/PLAYSP10.EXE    78,876   pure DOS MZ   player
REKLAMSP             1,410   CP852 Hungarian promo text
DEM1..DEM8, GITAR, CASIO     demo/music data
READDEMO.BAT   ->  exe\olvassp  <reklamsp
PLAYDEMO.BAT   ->  exe\playsp10 <demosp      (DEMOSP = "&gitar &dem1 ... &gitar")
```

`GITAR` (57 KB) and `CASIO` (27 KB) are **music** demos through the PC speaker.

## Why this is easier than the SoundBlaster build was

- **Pure DOS MZ**, no NE/PE — unlike TextAssist, which is 16-bit *Windows* and would
  need a Win3.1 API layer. See [[nvda-host32-vcruntime]] for the unrelated bridge work.
- **Not a TSR.** It reads text on **stdin** (`olvassp <reklamsp`), so there is no
  INT F1h protocol to reverse — feed bytes, collect audio.
- The DOS surface is tiny. All 38 `INT 21h` sites resolve to ~10 functions:
  `06, 09, 0A, 0B, 2C, 35, 3D, 3E, 3F, 42` (+ `4C` to exit).

MZ header: 147,280 bytes image, **15 relocations**, header 512 bytes,
`CS:IP 2266:0351`, `SS:SP 2236:0300`, minalloc 0.

## The audio path (confirmed by port scan)

Classic PWM-on-8253, exactly as he described it:

```
43h  PIT control    program channel 2
42h  PIT ch2 data   <-- the pulse width IS the speech amplitude
61h  PPI port B     speaker gate
40h  PIT ch0        paces the sample interrupt
20h  PIC EOI
```

**Emulation recovers better audio than the real hardware.** On a real PC the amplitude
became a pulse width driving a speaker cone; under Unicorn we read the intended value
straight off the `OUT 42h` writes. The sample rate comes from the channel-0 divisor the
same way the SoundBlaster build gives 1193181.666/130 = 9178 Hz.

## Plan

1. **MZ loader** — parse header, load image, apply the 15 relocations, build a PSP,
   set `CS:IP` / `SS:SP`. Reuse the Unicorn setup in
   `addon/synthDrivers/_pctalker_engine/pctalker_core.py`, which already has
   `UC_HOOK_INSN` on IN/OUT and `UC_HOOK_INTR`.
2. **Minimal INT 21h** — the ten functions above. `AH=3F` on handle 0 is where our text
   goes in; `AH=09`/`06` output goes to a sink.
3. **Timer** — drive `INT 08h` from the channel-0 divisor rather than real time, so the
   run is deterministic and as fast as the host allows.
4. **Capture** — each `OUT 42h` is a sample; convert to PCM at the channel-0 rate.
5. Wrap as a voice/variant in the existing PC-TALKER add-on rather than a second add-on.

## Results, 2026-08-09

> **Superseded in part — read "SOLVED, 2026-08-10" below first.** Everything in
> this section about the audio format, the rate and PLAYSP10 stands. Everything
> about *why OLVASSP is mute* is wrong: the queue-empty test at `0x234d4`, the
> two-PWM-handler theory, and the claim that it "processes the whole script"
> were all reasoning about a program that had already exited. It exits by
> design when the command tail is empty. The one static reading that turned out
> to be right is the command-tail gate at `0x22c56`, retracted on 2026-08-09
> and now reinstated by execution.

**It speaks.** `PLAYSP10` runs under DOSBox-X and 45 s of audio was captured
(rig: `C:\pctalker_temp\run_sp.py`, modelled on `robot-re/_pcrobot_engine`).
Two traps: a batch invoked from `[autoexec]` needs `call` or `exit` never runs,
and DOSBox drops the buffered tail on exit — so let it keep running and trim the
trailing silence afterwards instead.

**The demo files are raw 8-bit PCM**, no container: values clamped to 7..250
(PWM can't use the rails), mean |delta| 7.5-15 between consecutive bytes.
468,687 bytes total = **51.1 s at 9178 Hz**, the same rate as the SoundBlaster
build. So they can be decoded straight to WAV with no emulator at all, which
sounds **better than the DOSBox capture** — confirmed by ear. `OUT 42h` gives
18,356 Hz = exactly 2x 9178, i.e. a 2-tick PWM carrier per audio sample.

**`PLAYSP10` paces itself with CPU busy-waits, not the timer.** At `cycles=fixed
315` the demo runs 62.3 s; at `cycles=max`, 45.4 s — a 1.37x shift that could not
happen if playback were purely PIT-driven. A Unicorn port must therefore model
instruction timing, not merely service `INT 08h`.

**This package is not PC-TALKER's speaker port — it is a separate product,
`SPEAKER`.** Whisper transcribed the demo: *"Jó napot kívánok! Király József
vagyok, a Speaker Program kifejlesztője... A Speaker segítségével minden hardware
kiegészítés vagy módosítás nélkül olyan programokat készíthetünk, melyekből
szóban is [üzenhetünk] a felhasználónak. A hangfelvételek elkészítéséhez a
PC-TALKER rendszert használhatjuk."* SPEAKER is a developer toolkit for putting
digitized speech in your own programs with no sound hardware; PC-TALKER is how
you produce the audio. Hence the banner `PC-TALKER Beszédszintetizátor /
SPEAKER_ v. 1.0`.

**The text format mixes synthesis with playback.** `REKLAMSP` (decoded to
`out/reklamsp.txt`) contains inline `&name` commands — `&casio &dem1 &casio`,
`&gitar` — that splice a digitized clip into the middle of spoken text. The
`B5..C3` run is a **rising 15-byte sequence appearing inline** right after
"speciális hangeffektusokkal", so it is a sound effect (a sweep), not a header.

**`OLVASSP` remains mute, and the reason is upstream of audio.** It is not a
resident-driver problem: none of the three binaries is a TSR (no `AH=31`, no
`INT 27h`) and all three use the identical DOS call set. It is not calibration:
mute at both `cycles=max` and XT speed. It does have output code - **8 `OUT 42h`
sites against PLAYSP10's 4** - and it processes the whole script (82-88 s of
runtime). The tell: it does not even play the `&casio`/`&dem1`/`&gitar` clips
embedded in `REKLAMSP`, which PLAYSP10 plays perfectly. So something gates output
before it is reached. `OLVASSP` and `OLVASSP0` are 86.9% identical, with
`OLVASSP` ~68 KB larger (probably embedded voice data).

**The integrity-check theory was WRONG** (disassembly, 2026-08-09). The
"A program virussal fertőződött !" block at file `0x22bc4` is **dead code**: the
live entry path at `0x22bc1` is an unconditional `EB 35  jmp 0398h` straight over
it. Even when reached it only prints and exits - it sets no mute flag. Do not
chase it again.

**The real gate is a queue-empty test.** OLVASSP has *two* PWM interrupt
handlers, chosen through `cs:[000A]` at file `0x23ebe`: `0x0B77` (the same shape
PLAYSP10 uses) and `0x0CE3`, an extra *queued/segmented* handler unique to
OLVASSP. Playback is skipped before it starts, at file `0x234d4`:

```asm
39 06 A8 BC   cmp [0bca8h],ax   ; ax = 0bcach  (queue base + 4)
76 03         jbe 0c7dh         ; no queued segments -> skip playback
```

So nothing ever fills the segment queue. The `out 42h` sites themselves are NOT
additionally muted relative to PLAYSP10 - the handler guards are the same pattern,
just `[0eaf0h]` here against `[0f64ch]` there.

**Tried and failed:** the binary embeds the string `gitar.vmf` at `0x11be0` (and
contains no `casio`/`dem1` strings), suggesting `&name` resolves to `NAME.VMF`
while the archive ships extensionless files. Creating `.VMF` copies of all ten
demo files changed nothing - still peak 0 over 97 s. So the queue starves for
some other reason.

**Disassembly of the producer (2026-08-09), all verified statically:**

- Queue base is `0xBCAC`, tail pointer `[0xBCA8]`, initialised at `0x2309d`.
  Append routines `0x07EA` (called from `0x23205`) and `0x0857` (called from
  `0x22cff`, `0x23143`).
- **The sound-element lookup is fine.** REKLAMSP's `0xB5..0xC3` all resolve to
  populated table entries with nonzero lengths (e.g. `0xB5` -> file `0x00c941`,
  `0xC3` -> file `0x00c979`). The hangelemtár is present and indexed correctly.
- `cs:[000A]` is not the problem: written only at `0x23398` (=1, external-file
  path) and `0x234f6` (=0, queued path). The queued path selects the working
  handler `0x0CE3` by itself.
- Byte dispatch is table-driven at `0x22879`/`0x22890`. Note `&` (0x26) dispatches
  to the *same* ordinary handler `0x0235` as text and sound indices, so `&casio`
  is **not** treated as a file-splice in this stdin/text mode.
- **The entry gate is the PSP command tail**, at `0x22c56`:
  `cmp byte ptr [si],0` / `je 042Ch` — with no argument the program exits at
  `0x22c59` *before* reading stdin at all.

**Tried and failed (do not repeat):**
1. `.VMF` copies of all ten demo files — still peak 0.
2. `exe\olvassp x <reklamsp` (supplying a command tail, second PSP byte not one
   of `* . + -`) — still peak 0, output still the banner only.

**Correction to an earlier claim in this file:** the "82-97 s of runtime" cited as
proof it was processing the script was an artefact of the harness — `exit` had
been replaced with `rem`, so DOSBox was idling at the DOS prompt. It is *not*
evidence the program ran. Consistent with the command-tail gate above, OLVASSP
most likely exits almost immediately.

**The author settles the invocation (2026-08-09).** There is no switch and no
parameter: *"a főkönyvtárban lévő READDEMO.BAT fájllal, vagy ugyaninnen az
`exe\olvassp <reklamsp` paranccsal… OLVASSP-nek is a standard inputról lehetett
odaadni a felolvasandó szöveget"* — plain stdin, exactly as PLAYSP10 takes it.
So the command-tail reading of `0x22c56` cannot be a hard gate; his own
`READDEMO.BAT` supplies no argument and worked on real hardware.

**The decisive A/B, and it isolates the fault.** He notes OLVASSP plays music and
recordings *"ugyanúgy, ahogy azt a PLAYSP10 tette"*. So feed OLVASSP the very
input that makes PLAYSP10 work: `exe\olvassp <demosp` (69 bytes, nothing but
`&name` commands — no text, no sound-element bytes). Result: **still peak 0.**

Therefore the fault is **not** input format, text parsing, sound-element lookup,
`.VMF` naming, or the command tail. OLVASSP emits nothing on *any* input while its
sibling, sharing 49% of its code and the same guard pattern, plays perfectly in
the identical DOSBox configuration. That is the cleanest possible experiment for
tomorrow: run both binaries on the same 69-byte file under a debugger and diff
where control diverges.

**Remaining blocker:** the `Start :` / `Hossz :` / `Szöveg :` prompts go out via
`AH=06` direct console I/O, which bypasses redirection, so stdout capture cannot
show how far execution gets. Progress needs actual runtime visibility — the
DOSBox-X debugger, or instrumenting the program under Unicorn — rather than more
black-box invocation guesses.

## SOLVED, 2026-08-10 — OLVASSP was never broken

**It speaks.** Under `tools/sp_trace.py` (a `DosHost` subclass on Unicorn, no
DOSBox) OLVASSP synthesizes Hungarian from the command line:

```
python tools/sp_trace.py olvassp --args "*jo napot kivanok kiraly jozsef vagyok"
    -> 58,411 PWM writes = 3.18 s at 18356 Hz
```

**The gate is the PSP command tail after all, and `04B1` is a deliberate exit,
not a fault.** At `03F6` (file `0x22C56`, the address flagged above):

```asm
03EE  mov ds, cs:[0]      ; DS := PSP, verified at a breakpoint: DS=0800
03F3  mov si, 0080h
03F6  cmp byte [si], 0    ; tail length zero?
03F9  je  042C  ────► 042C: pop ds / jmp 04B1
                      04B1: mov dx,[0] (=0378h) / mov al,0 / out dx,al / retf
```

The `retf` returns to `PSP:0000`, which is `INT 20h` — the normal .EXE
termination. So with no argument OLVASSP prints its banner, drops the LPT port
and quits in 0.001 s. Every DOSBox run we ever made was watching a program that
had already exited.

**The switch table.** The tail's third byte (`PSP:0082`, i.e. the first real
character) is matched against four characters:

| switch | meaning | result |
|---|---|---|
| `*` | **speak the rest of the tail** | works; audio scales with text length |
| `.` | **not speech** — a disk sector utility | see below |
| `+n` | speed up (`[0004] := ([0002]>>3) * n`) | |
| `-n` | slow down (`[0006] := ...`) | |

Anything else — including the `x` tried on 2026-08-09 — falls through to
`042C` and exits. That is why that test failed, and it was not a null result.

**`.` mode is a disk sector editor — do not run it on real hardware.** It takes
the magic handshake `C3 3D 17` one byte at a time through `AH=06/DL=FF`, then a
buffered line (`AH=0A`), adds each byte's own index to it, and ends at `054C`:

```asm
054C  mov ah, 3      ; BIOS write sectors
054E  mov al, 1      ; one sector
      ...
055E  int 13h        ; AX=0301 observed in the trace
```

Those are the `Start :` / `Hossz :` / `Szöveg :` prompts that were invisible
under DOSBox — a sector patcher, almost certainly how the hangelemtár was
maintained. It speaks nothing. Any host running this must refuse INT 13h
writes; ours ignores them.

**The `*` path is the one to build on, and its 126-byte PSP limit is not a real
limit.** The branch at `03FB` copies the tail to `[018Ah]`, bumps the length
byte, sets `[0068h] := 1` and jumps to `0488`. A driver can do the same thing
directly — write arbitrary-length text at `[018Ah]`, set the count, jump to
`0488` — exactly as `pctalker_core.py` calls the 5.01 TSR's handler instead of
going through `OLVIT`. That, not the command line, is the synth interface.

**There is also a stdin path, and the tail check jumps over it.** At `04A2`:

```asm
04A2  cmp word [68h], 1
04A7  je  04B1           ; a filename was given -> nothing to do here
04A9  mov ah, 0Bh
04AB  int 21h            ; check standard input status
04AD  cmp al, 0
04AF  jne 0455           ; input waiting -> do the work
04B1  ...                ; nothing waiting -> exit
```

`04A2` is only reached when `[0068h] != 0`, and `[0068h]` is set only by the
`*` branch. So on the shipped 1991 build, `exe\olvassp <reklamsp` cannot reach
the stdin check. Worth telling Király: `READDEMO.BAT` is dated **17 Mar 1992**,
the EXE **27 Jan 1991** — the batch file may have been written for a later
build than the one in the archive.

**The audio path, now confirmed by execution rather than by reading.**
PLAYSP10 at `0AF9`:

```asm
mov al,41h / out 40h,al / mov al,0 / out 40h,al   ; ch0 divisor 65 = 18356.6 Hz
mov al,92h / out 43h,al                           ; ch2, LSB-only, MODE 1 = PWM
```

18,356 Hz is exactly the `OUT 42h` rate measured off the DOSBox capture, and
exactly 2x 9178: the ISR emits **each source byte twice**, so the write rate is
double the audio rate. The ISR is entered at `0B26` and never returns — it
ends `add sp,si` (si=6, discarding the IRET frame), `sti`, `hlt`, so the next
timer tick re-enters it. One sample per interrupt, forever, until the buffer
end at `[0F64Ch]`.

**`gitar` is opened with no extension** (`AH=3D` on `C:\...\SP\gitar`). The
`.VMF` theory is dead for good; delete the `*.VMF` copies from the work dir.

### The text encoding is CWI-2, not CP852

Found by ear (Tomi, 2026-08-10): `ö` spoke, `ő` gave a silent click. The cause
is a year of history. CP852 arrived with DOS 5 in 1991; SPEAKER is from 1990
and expects **CWI-2**, the Hungarian page in general use before it — CP437 with
the two double-acute letters in the circumflex slots, since Hungarian never
needs `ô` or `û`:

| letter | CWI-2 | CP852 |
|---|---|---|
| `ő` | **93h** (CP437 `ô`) | 8Bh |
| `ű` | **96h** (CP437 `û`) | FBh |

Not a guess: `REKLAMSP` — Király's own demo text — uses `93h` inside
`lehetővé`, `tetszőleges` and `minőségileg`. Under CP852 those read `lehetôvé`,
`tetszôleges`, `minôségileg`, which is not Hungarian. Every other high byte in
that file (81 82 90 94 99 A0 A2) matches CP437 exactly.

**PC-TALKER 5.01 is unaffected** — it accepts CP852 — so the encoding belongs
to the engine, not the driver: `Voice.encoding` in `pctalker_engines.py`.
CP437 carries no uppercase accented vowels beyond `É Ö Ü`, so the rest fold to
their lowercase byte; these engines speak words, not case.

### SPEAKER has no digits at all

`51` renders **zero samples**. So does `5`, and `2026`. `a 51 szam` speaks "a"
and "szam" with silence between them — the engine does not spell digits or get
them wrong, there is simply no speech element for any of them. PC-TALKER 5.01
says `51` correctly in 1.02 s, which is part of what its extra 68 KB of kivétel
szótár buys.

Found by ear: NVDA announced "Rate: slider 51" and the *51* was silent, which
is indistinguishable from a slider that has no value — the bug reported itself
as "the rate and volume sliders are empty".

Fixed in the driver, for that voice only: `pctalker_hunum.py` writes numbers out
as Hungarian words before they reach the engine (`ötvenegy`, `kétezerhuszonhat`,
`huszonkétezer` — `kettő` becomes `két` before száz/ezer/millió, and 100/1000
are `száz`/`ezer`, never `egyszáz`/`egyezer`). Anything past a milliárd is read
digit by digit rather than dropped.

### Five host bugs that manufactured silence

All of these produced "no audio" indistinguishable from a broken 1990 binary.
Anyone repeating this work needs all five:

1. **`INT 21h AH=2C` returned 00:00:00.00 forever.** PLAYSP10 measures the CPU
   by counting iterations across 0.30 s of DOS clock (`03C0`-`03E6`); with a
   frozen clock it spins there permanently. 200,000 calls, no progress.
2. **Serviced interrupts cost zero guest cycles.** With DOS calls free the
   calibration counted ~88,000 iterations per pass; `div byte [00CEh]` (=2)
   overflows a byte quotient above 2040, so the program died of **divide
   overflow** before playing a note. Charging ~2000 cycles per INT 21h at
   4.77 MHz puts the count in an era-plausible range.
3. **Unicorn stops dead on `hlt`** and reports nothing — to the host a halted
   guest is indistinguishable from a finished one. Symptom: identical guest
   time at every instruction budget. This software halts once per sample, so
   without treating `hlt` as "sleep until the next interrupt" it can never play
   more than one.
4. **IRQ0 was delivered with IF clear.** The timer fired the instant the IVT
   store landed — inside the guest's own `cli` window — so the ISR ran before
   the registers it works from were loaded. The tell was in the port log:
   `out 61h,43h` and `out 41h,E1h` where the code sets `cl=4Bh`, `ch=20h`.
   Stale registers, plausible-looking output, completely wrong.
5. **Vectors installed by writing the IVT directly** (no `AH=25`) were invisible
   to the base host, and **stdin redirection** reached only `AH=3F`; PLAYSP10
   reads its script with `AH=0A` and OLVASSP polls with `AH=0B`.

## ANSWERED by Király József, 2026-08-09

1. **PWM is linear.** "Az impulzus szélesség arányos a jel pillanatnyi
   amplitúdójával" - at half maximum amplitude the period is 50% high / 50% low.
   No companding. Our `(byte - 128)` decode is therefore correct as-is.
2. **Same rate as the SoundBlaster build**, i.e. **9178 Hz** - confirming the
   figure derived independently from 468,687 bytes / 51.1 s.
3. **The `B5..C3` bytes are sound elements recorded from a music synthesizer.**
   PC-TALKER could generate sound effects as well as read text, and those inline
   characters index a **hangelemtár** (sound-element library). Separately,
   `&filename` splices a recorded file into the text - confirming the `&` syntax
   read off `REKLAMSP`.
4. **`OLVASSP` is the file to use**: it already has the **hangelemtár** and the
   **kivétel szótár** (exception dictionary) integrated. This confirms the
   inference from the 86.9% code overlap and ~68 KB size delta against
   `OLVASSP0` - the extra bulk is exactly that embedded data.

**What this implies for the mute bug.** The `B5..C3` run is not decoration: it is
a lookup into the embedded sound-element library, and the segment queue at
`[0bca8h]` that Codex found empty is very likely the queue those elements feed.
So the failure is in resolving sound elements / dictionary data out of the
embedded tables, not in the audio path. Look for what parses the high-byte run
and writes `[0bca8h]`.

## Open questions for Király József

Only he can answer these, and they are cheap for him:

- Is the pulse width linear in amplitude, or companded?
- Which channel-0 divisor did the speaker build use — the same 130 (9178 Hz) as the
  SoundBlaster version, or slower for the PC speaker?
- Does `OLVASSP` expect any control bytes ahead of the text? `REKLAMSP` opens with
  `B5 B6 ... C3` repeated three times before the Hungarian text.
- What is `OLVASSP0` versus `OLVASSP`?
