PCTALKER Printer version - Hungarian - DEMO
===========================================

NVDA add-on version 0.1.5

This addon demonstrates the audio quality of the Hungarian PCTALKER Printer
version developed by J. Kiraly between 1989 and 1991.

1. Historical version
---------------------
The original DOS Printer version of PCTALKER used an external digital-to-analog
(D/A) converter connected to the PC parallel/printer port. Unlike the PC Speaker
version, it did not need one-bit PWM to represent speech amplitude. The program
sent successive multi-level speech sample values to the printer-port D/A
hardware.

The preserved resources are:
- OLVAS_P.ASM: historical conversion and speech-element tables
- RAWHUSR: historical speech sample data
- SZOTAR.TBL: dictionary and exception substitutions

2. Character encoding: CWI-2 / CP-HU
------------------------------------
Version 0.1.5 corrects an important historical reconstruction detail. Earlier
Python/NVDA versions used CP852. Testing of the PCTALKER family showed that the
historical Hungarian software used CWI-2 / CP-HU byte positions.

This add-on now uses an explicit Unicode -> CWI-2 mapping before running the
original byte-oriented PCTALKER conversion logic.

For compatibility with the historical Printer-version tables, these uppercase
characters are mapped to their audible lowercase equivalents before CWI-2
encoding:

    Ó -> ó
    Ú -> ú
    Ő -> ő
    Í -> í

Lowercase ő and ű are now sent to their proper CWI-2 table positions; the old
CP852-era workaround ű -> ü has been removed.

3. How the NVDA add-on works
----------------------------
NVDA supplies Unicode Hungarian text. The Python reconstruction:
1. expands numbers,
2. applies SZOTAR.TBL dictionary/exception substitutions,
3. converts text using the historical OLVAS_P.ASM logic,
4. selects the corresponding speech segments from RAWHUSR,
5. produces unsigned 8-bit mono PCM at a nominal 8,500 Hz,
6. sends the PCM through NVDA's native WavePlayer and the Windows audio system.

The modern sound card therefore replaces the physical printer-port D/A
converter, while the historical speech data and text/speech conversion logic
are preserved.

4. Rate and responsiveness
--------------------------
NVDA Rate 50 corresponds to the nominal 1.0x playback speed. Rate changes
resample synthesized speech in software. As with changing playback timing in
the historical implementation, this changes both duration and pitch somewhat.

The driver uses one persistent speech worker with cancellation support so newer
NVDA cursor/navigation speech can replace obsolete pending speech.

5. Printer version versus PC Speaker version
---------------------------------------------
Printer version:
    text -> PCTALKER conversion -> RAWHUSR multi-level samples
    -> printer-port D/A -> analog audio

Current Printer-version emulation:
    Unicode text -> CWI-2/PCTALKER conversion -> RAWHUSR samples
    -> 8-bit 8,500 Hz PCM -> NVDA WavePlayer -> Windows audio

PC Speaker version:
    text -> PCTALKER conversion -> speaker speech data
    -> one-bit PWM / PIT timing -> physical internal speaker

Therefore PWM carrier, True PWM, Real PWM and PC-speaker filter variants belong
to the separate PC Speaker demonstration. They are not part of this Printer
version.

6. Demonstration status
-----------------------
This is a historical reconstruction and demonstration build. Its purpose is to
preserve and demonstrate the characteristic audio quality and speech-generation
logic of the Hungarian PCTALKER Printer version.

Version 0.1.5 changes
---------------------
- Replaced CP852 text encoding with explicit CWI-2 / CP-HU mapping.
- Removed the old ű -> ü compatibility substitution.
- Added PCTALKER table-lookup mappings:
      Ó -> ó
      Ú -> ú
      Ő -> ő
      Í -> í
- Renamed synthesizer to:
      PCTALKER Printer version - Hungarian - DEMO
- Renamed add-on to:
      PCTALKER Printer version - Hungarian - DEMO
- Updated add-on metadata and documentation.
