PCTALKER Sound Blaster version - Hungarian - DEMO
================================================

NVDA add-on version 0.1.0

This addon demonstrates the audio quality, improved intonation and echo
capability of the Hungarian PCTALKER Sound Blaster version developed by
J. Kiraly in 1991.

Historical source
-----------------
The supplied OLVAS_S.ASM identifies itself as:

    PC-TALKER Sound-Blaster version 5.01
    Last update: 1991 Jan. 13

It uses the same RAWHUSR speech data and SZOTAR.TBL dictionary family as the
Printer version.

Sound Blaster output
--------------------
The DOS program auto-detects a Sound Blaster DSP base address from 210h through
260h, resets the DSP through base+6, checks for the AAh reset response at
base+0Ah, enables the speaker with DSP command D1h, and writes 8-bit samples
using the DSP direct-DAC command 10h at approximately 8.5 kHz.

The NVDA reconstruction replaces those hardware port operations with unsigned
8-bit mono PCM at 8,500 Hz played through NVDA WavePlayer.

Improved intonation
-------------------
The active Sound Blaster PHONSOUT code uses symmetrical punctuation ramps:

    period: +4 / reset above 12
    comma:  +4 / reset above 12

The earlier Printer reconstruction used the older comma +5 / reset above 15
behavior. This Sound Blaster version uses the active 5.01 logic.

Echo
----
OLVAS_S.ASM contains a recursive circular-buffer echo.

The delayed OUTPUT signal is mixed back at approximately 50% amplitude, so
successive repeats decay naturally.

Original default:
    keses = 250 samples

At 8,500 Hz, 250 samples is approximately 29.4 milliseconds.

The NVDA add-on exposes:
    Echo delay (samples)

Default:
    250

Range:
    0..4999

For modern usability, 0 disables echo. Positive values reproduce the recursive
feedback algorithm.

Character encoding
------------------
The reconstruction uses CWI-2 / CP-HU, consistent with the corrected Hungarian
PCTALKER versions.

For compatibility with the historical tables:
    Ó -> ó
    Ú -> ú
    Ő -> ő
    Í -> í

NVDA controls
-------------
Rate:
    controls overall PCTALKER speech speed.

Echo delay (samples):
    controls the Sound Blaster echo delay.

The underlying output remains unsigned 8-bit mono PCM at 8,500 Hz.
