# Disk Killer in DEM1 and DEM2

**Summary: two of Király's 1990 demo recordings carry a 2,560-byte fragment of
the *Disk Killer* (a.k.a. Ogre) boot-sector virus, written over the audio on the
original diskette. Nothing in this repository is affected, no file in the archive
is an infected executable, and the fragment cannot run on any machine made this
century. It is what got `pctalker-archive` darkened on archive.org.**

Internet Archive flagged `pctalker-archive.zip` on 2026-08-12 (ticket 1602856).
VirusTotal: 12/60, every label a variant of `Dkiller.A` / `Disk Killer (Ogre) 2`.
Twelve labels, but only about four independent engines — ALYac, Arcabit,
BitDefender, Emsisoft, eScan, GData and VIPRE all run the BitDefender engine, and
Avast and AVG are one engine. VirusTotal reports the zip, not the member file, so
the report alone does not say which of the 38 files is responsible.

## Finding the file

The demo recordings are raw 8-bit PCM clamped to 7..250, so **any byte outside
that range is not audio**. Scanning every file in the archive for out-of-range
bytes isolates the contamination immediately:

| file | foreign bytes | where |
|---|---|---|
| `CASIO`, `DEM3`, `DEM4`, `DEM6`, `DEM7`, `DEM71`, `DEM8`, `GITAR` | 0–1 | final byte only (EOF marker) |
| **`DEM1`** | **374** | one region, `0xBE00`..EOF |
| **`DEM2`** | **218** | one region, `0x0000`..`0x03FF` |

Every other demo is clean apart from its terminator byte. `DEM1` and `DEM2` each
have exactly one contiguous foreign region, and both regions sit against a file
boundary — the end of one, the start of the other.

The same two files appear four times in the archive: under `PCTAKER_SP/`, under
`PCTALKER_SP2/`, and inside both nested original zips. They are byte-identical in
every copy (`DEM1` SHA-256 `0B7A93AD60BE1A00…`, `DEM2` `5CC5E0D53FB59AA1…`).

## What is in them

`DEM1` at `0xBE00` — a 512-byte sector boundary, exactly:

```
00BDF0  84 81 7C 79 79 7B 7B 7D 7A 7F 84 85 82 83 80 80  ..|yy{{}z.......   <- audio
00BE00  FA 2E C6 06 64 01 83 33 C0 8E D8 A1 20 00 A3 04  ....d..3.... ...   <- cli; cs: mov …
```

and at the end of the same file, real 16-bit real-mode code followed by the start
of the virus's banner:

```
00C320  18 BB 08 00 CD 10 B4 02 B7 00 BA 00 0C CD 10 BB  ................
00C330  2C 00 BE DF 07 E8 51 01 EB FE 44 69 73 6B 20 4B  ,.....Q...Disk K
00C340  69 6C 6C 65 72 20 2D 2D 20 56 65 72 73 69 6F 6E  iller -- Version
00C350  20 31                                             1
```

`CD 10` is INT 10h (video), `EB FE` is `jmp $` — print the message, then hang
forever. `DEM2` opens with the *last line* of that same message and more code,
including `CD 13` (INT 13h, disk):

```
000000  0A 49 20 77 69 73 68 20 79 6F 75 20 6C 75 63 6B  .I wish you luck
000010  20 21 00 57 B9 3A 00 BE A5 08 BF 03 00 FC F3 A4   !.W.:..........
```

and the region ends on the boot-sector signature, with audio resuming at exactly
`0x400`:

```
0003F0  00 00 00 00 00 00 00 00 00 00 00 00 00 00 55 AA  ..............U.
000400  7D 7C 7C 7C 7C 7B 7B 7B 7A 7A 7A 7B 7C 7C 7C 7D  }||||{{{zzz{|||}   <- audio
```

## Reconstruction

The two fragments are one object. `DEM1` is 50,002 bytes; the next 512-byte
boundary is 50,176, so **174 bytes of the last sector were slack and were
discarded when the file was copied off the diskette by length**. The missing
middle of the Disk Killer banner — `.00 by COMPUTER OGRE 04/01/1989`, the
`Warning !! Don't turn off the power…` line, `PROCESSING`, and `Now you can turn
off the power.` — is about 174 bytes. It fits the hole exactly.

Add it up:

```
DEM1  0xBE00..EOF     1362 bytes
      lost slack        174 bytes
DEM2  0x0000..0x03FF  1024 bytes
                      ---------
                       2560 bytes = 5 sectors, ending in 55 AA
```

So `DEM1` and `DEM2` were **physically adjacent on Király's 1990 diskette, and
Disk Killer overwrote a contiguous five-sector run straddling the boundary
between them** — its own body plus the relocated original boot sector, which is
why the run terminates in `55 AA`. His audio was underneath, and the virus took
it. The damage is audible: roughly 0.15 s of noise at the end of `DEM1` and
0.11 s at the start of `DEM2`, at 9178 Hz.

Disk Killer is a 1989 boot-sector infector. It spread by floppy, which is exactly
how software moved in Budapest in 1990, and it counted reboots before scrambling
the disk. Király's development machine was infected while he was recording these
demos, and the evidence has sat inside his own files for thirty-six years.

## Why it is inert

* It is a **boot-sector** virus. It infects boot sectors, not programs. No
  executable in this archive is infected — the scanners agree, the single family
  label is the only hit across all 38 files.
* The fragment is **incomplete**: 2,560 of its bytes with 174 missing from the
  middle. It is not a runnable copy of anything.
* It lives inside a **data file** that is only ever read as PCM samples. Nothing
  branches into it.
* It is **16-bit real-mode code**. 64-bit Windows cannot execute 16-bit code at
  all, and it would have to be in a boot sector to get control in the first place.

Detection here is a byte-pattern match doing its job correctly on a fossil.

## Reproducing

```powershell
# isolate non-audio regions in the demo files
$b=[IO.File]::ReadAllBytes('DEM1')
0..($b.Length-1) | Where-Object { $b[$_] -lt 7 -or $b[$_] -gt 250 }
```

See also `pcspeaker-plan.md` for the rest of the archaeology.
