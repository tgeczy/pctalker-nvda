PCTALKER Sound Blaster version - Hungarian - DEMO
================================================
Technical README: reconstruction of PC-TALKER Sound-Blaster version 5.01
NVDA add-on / standalone version 0.1.0

1. Purpose of this reconstruction
---------------------------------
The PCTALKER Sound Blaster version - Hungarian - DEMO reconstructs the Sound Blaster branch of the Hungarian PCTALKER speech system for modern Windows and NVDA.
The supplied OLVAS_S.ASM identifies the historical program as PC-TALKER Sound-Blaster version 5.01, last updated 13 January 1991. The goal is to preserve the historical speech data and linguistic conversion while reproducing the Sound Blaster-specific intonation and echo behavior in software.

2. Historical Sound Blaster output
----------------------------------
The Sound Blaster version uses the same RAWHUSR speech-data family and SZOTAR.TBL dictionary as the Printer version, but replaces the external printer-port D/A converter with the Sound Blaster DSP.
The source auto-detects a Sound Blaster base I/O address from 210h to 260h. It resets the DSP through base+6, checks for the standard AAh reset response at base+0Ah, enables the card speaker with command D1h, and uses DSP direct-DAC command 10h to send successive 8-bit speech samples.
The speech timing remains approximately 8.5 kHz. In the modern reconstruction, direct DSP port access is replaced by unsigned 8-bit mono PCM at 8,500 Hz played through NVDA WavePlayer or Windows audio.

3. Historical speech resources and CWI-2
----------------------------------------
OLVAS_S.ASM contains the Sound Blaster conversion and speech-element tables. RAWHUSR contains the historical speech samples, and SZOTAR.TBL contains dictionary/exception substitutions.
The reconstruction uses CWI-2 / CP-HU rather than CP852. For compatibility with the historical tables, uppercase Ó, Ú, Ő and Í are mapped to their lowercase equivalents ó, ú, ő and í before byte-oriented PCTALKER conversion.

4. Improved Sound Blaster intonation
------------------------------------
The active PHONSOUT routine in OLVAS_S.ASM differs from the older Printer reconstruction in its punctuation timing. The period ramp adds 4 per phoneme and resets above 12; the comma ramp also adds 4 per phoneme and resets above 12.
The reconstructed Sound Blaster engine uses that active 5.01 behavior. As in the existing PCTALKER Python family, exclamation and question marks are treated compatibly with period and comma for practical modern text reading.

5. Recursive echo
-----------------
The Sound Blaster HANG routine contains a circular delay buffer controlled by the variable keses. The source default is 250 samples.
For each current speech sample, the delayed output sample is centered around the unsigned 8-bit midpoint and mixed back at approximately half amplitude. The newly mixed output is then written into the delay buffer. Because the delayed output is fed back rather than merely copied once, repeated echoes decay recursively.
At 8,500 Hz, 250 samples is approximately 29.4 ms. The NVDA add-on provides an Echo delay (samples) setting with a default of 250. The standalone program provides --echo-delay. For modern usability, a value of 0 disables echo; positive values reproduce the recursive feedback algorithm.

6. NVDA implementation
----------------------
The add-on uses a persistent synthesis worker and NVDA's native WavePlayer. The final stream is unsigned 8-bit mono PCM at 8,500 Hz.
NVDA Rate controls overall speech speed. Echo delay is exposed as a separate numeric synthesizer setting. Embedded external audio, where used by the reconstructed engine, is not passed through the speech echo path, matching the separation visible in the historical source.

7. Standalone implementation
----------------------------
The standalone version uses the same Sound Blaster speech engine and supports text from the command line or standard input, speech-speed control, echo-delay control, WAV export, direct Windows playback, CWI-2 diagnostics and intonation diagnostics.
The default echo delay is 250 samples. Use --echo-delay 0 to compare the speech with echo disabled.

8. Sound Blaster versus Printer version
---------------------------------------
Both versions use closely related PCTALKER text conversion, RAWHUSR speech data and SZOTAR.TBL dictionary processing.
The Printer version sends multi-level samples to an external D/A converter on the parallel port. The Sound Blaster version sends 8-bit samples to the Sound Blaster DSP and adds a recursive echo path plus revised punctuation intonation.
Neither version requires the one-bit PWM reconstruction used by the separate PCTALKER PC Speaker version.

9. Simplified signal path
-------------------------
Historical Sound Blaster version: Hungarian text -> SZOTAR/OLVAS_S conversion -> speech-element table -> RAWHUSR samples -> per-phoneme Sound Blaster intonation timing -> recursive echo -> Sound Blaster DSP direct DAC -> speaker.
Modern reconstruction: Unicode text -> CWI-2/PCTALKER conversion -> RAWHUSR speech elements -> per-phoneme software intonation -> recursive 8-bit echo -> 8,500 Hz PCM -> NVDA WavePlayer / Windows audio.

10. Demonstration status
------------------------
This is a historical reconstruction and demonstration build. It is intended to preserve and compare the Sound Blaster branch of PCTALKER with the Printer and PC Speaker versions rather than to redesign the original synthesizer into a modern voice.

11. Technical summary
---------------------
Historical source: OLVAS_S.ASM, Sound-Blaster version 5.01, 13 Jan 1991
Speech data: RAWHUSR
Dictionary: SZOTAR.TBL
Text encoding: CWI-2 / CP-HU
Historical audio hardware: Sound Blaster DSP direct 8-bit DAC
Nominal sample rate: 8,500 Hz
Improved comma intonation: +4 per phoneme; reset above 12
Echo algorithm: Recursive circular delay; delayed output at ~50% feedback
Historical default echo delay: 250 samples (~29.4 ms at 8.5 kHz)
NVDA echo control: Echo delay (samples), 0..4999; 0 = off
Modern output: Unsigned 8-bit mono PCM through NVDA/Windows