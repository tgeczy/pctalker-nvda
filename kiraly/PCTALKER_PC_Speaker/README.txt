PCTALKER PC Speaker Emulator - NVDA Prototype 0.1.0

This add-on emulates the original DOS motherboard-speaker version of PCTALKER.

Architecture
------------
- CWI-2 / CP-HU text encoding, as confirmed from the original speaker version.
- Original OLVASSP.ASM phoneme table.
- Original RAWSP data.
- Original SZOTAR.TBL for Hungarian.
- Optional English UTF-8 pronunciation lexicon.
- Software reconstruction of the PIT/Port 61h PWM timing.
- NVDA's own nvwave.WavePlayer for stable WASAPI playback.
- One persistent synthesis worker, following the stability lessons from the
  earlier PCTALKER NVDA add-on.

NVDA Speech settings
--------------------
Voice:
  PCTALKER PC Speaker - Hungarian
  PCTALKER PC Speaker - English

Variant:
  1990 PC speaker filter
  Raw PWM emulation

The filtered variant is the default and uses the same 3-pole, approximately
4.5 kHz low-pass model tested in the standalone PC-speaker prototype.

Rate 50 corresponds to the historical nominal speed.

Prototype limitation
--------------------
Index notifications are currently emitted at utterance completion rather than
at the exact acoustic position.


VERSION 0.1.1 - NUMPY REMOVED
=============================
Fixes:
    ModuleNotFoundError: No module named 'numpy'

NVDA's embedded Python does not include NumPy. All PC-speaker DSP is now
implemented with Python's standard library only:
- array
- math
- pathlib
- re

The NVDA architecture remains:
- one persistent synthesis worker
- nvwave.WavePlayer
- 48 kHz, 16-bit mono
- selectable 1990 PC speaker filter / raw PWM variant


VERSION 0.1.2 - SYNTH DRIVER MODULE NAME FIX
============================================
Fixes:
    ModuleNotFoundError: No module named 'synthDrivers.pctalkerPcSpeaker'

NVDA loads a synthesizer module by its synth ID. The driver identifies itself
as:
    name = "pctalkerPcSpeaker"

Therefore the driver module must be:
    synthDrivers/pctalkerPcSpeaker.py

Earlier builds still packaged it as synthDrivers/olvas.py. Version 0.1.2
renames the module to match the internal synth ID.

The NumPy-free pure-Python speaker engine from 0.1.1 is retained unchanged.


VERSION 0.1.3 - RESPONSIVENESS OPTIMIZATION
============================================
The previous filtered mode explicitly expanded every RAWSP byte into a 192 kHz
1-bit PWM waveform, filtered that large buffer, then resampled to 48 kHz.
That is faithful but CPU-heavy in pure Python and can feel sluggish during
rapid NVDA cursor navigation.

Filtered mode is now optimized:
- For each historical 130-PIT-tick sample slot, compute its exact average PWM
  duty-cycle value directly.
- Resample that compact ~9178 Hz envelope to 48 kHz.
- Apply the same selectable 1990 small-PC-speaker low-pass model at 48 kHz.
- Do not explicitly create the high-frequency carrier that the speaker filter
  is intended to remove anyway.

Raw PWM emulation remains the exact high-rate demonstration path.

The engine also checks for newer NVDA speech requests during synthesis and
immediately abandons stale cursor/navigation speech.

Expected result:
- much faster response to arrow/cursor movement in the default filtered mode
- same CWI-2 text behavior and historical RAWSP/SZOTAR data
- raw PWM variant retained for demonstration


VERSION 0.1.4 - HUNGARIAN-ONLY DEMONSTRATION BUILD
==================================================
This build intentionally exposes only one language/voice:

    PCTALKER PC Speaker - Hungarian

The English voice is temporarily removed from the NVDA UI while the extended
English lexicon is being fine-tuned and tested.

Retained:
- CWI-2 / CP-HU Hungarian encoding
- original OLVASSP.ASM / RAWSP / SZOTAR.TBL
- fast responsive filtered synthesis path
- Raw PWM emulation variant
- 1990 PC speaker filter variant
- NVDA Rate control
- single persistent worker
- stale-synthesis cancellation
- nvwave.WavePlayer output


UPPERCASE CWI-2 SPEAKER-TABLE FIX
=================================
The original OLVASSP.ASM speaker table contains silent placeholder entries for:
    Ó = CWI-2 0x95 / 149 -> c149 = 50,1800
    Ő = CWI-2 0xA7 / 167 -> c167 = 50,1800
    Ű = CWI-2 0x98 / 152 -> c152 = 50,1800

The corresponding lowercase entries contain real speech samples:
    ó = 0xA2 / 162
    ő = 0x93 / 147
    ű = 0x96 / 150

For PCTALKER table lookup only, this version maps:
    Ó -> ó
    Ő -> ő
    Ű -> ű

Canonical CWI-2 mapping remains available internally in cwi2_encode().


VERSION 0.1.6 - SPEED-FIRST DEMONSTRATION BUILD
================================================
This build is deliberately optimized for NVDA cursor/navigation responsiveness,
not for maximum waveform fidelity.

Changes:
- Hungarian only.
- One synthesis mode; Variant selector removed.
- Direct RAWSP duty-envelope -> 16 kHz PCM conversion.
- No 192 kHz carrier buffer.
- No floating-point multi-pass low-pass filtering.
- No separate 48 kHz resampling stage.
- Rate conversion is combined with output-rate conversion in one loop.
- Nearest-neighbor resampling is used for speed.
- 256-entry precomputed PCM lookup table.
- Small 128-entry LRU cache for repeated short navigation utterances.
- Stale-synthesis cancellation retained.
- NVDA's nvwave.WavePlayer retained.

Why 16 kHz?
-----------
The reconstructed duty envelope has a source rate of about 9178 Hz, so its
Nyquist bandwidth is already only about 4.6 kHz.  A 16 kHz output stream is
therefore comfortably adequate for the bandwidth of the historical small
internal PC speaker while greatly reducing the amount of Python processing.

This is a demonstration/latency build.  The higher-fidelity 0.1.5 version
should remain the reference version for acoustic comparison.


VERSION 0.1.7 - FAST OPTIONAL FILTER
====================================
Keeps the speed-first 16 kHz renderer from 0.1.6.

Variant options:
  Fast + PC speaker filter
  Fast unfiltered

The filter is intentionally simple and cheap:
- one-pole RC low-pass
- applied directly at 16 kHz
- default cutoff approximately 4.5 kHz
- no 192 kHz PWM reconstruction
- no multi-pass high-rate filtering

This keeps responsiveness close to 0.1.6 while restoring a filtered/unfiltered
demonstration choice.


VERSION 0.1.8 - THREE DEMONSTRATION MODES
=========================================
Variant choices:

  Fast envelope (no PWM carrier)
      Speed-first practical NVDA mode.
      Uses the average historical PWM duty cycle directly.

  True PWM
      Reconstructs the actual high-rate 1-bit PWM waveform at 192 kHz,
      then resamples it for NVDA playback.

  True PWM + simple filter
      Same true 192 kHz PWM reconstruction, followed by a lightweight
      one-pole low-pass at approximately 4.5 kHz before NVDA playback.

This makes the demonstration distinction clear:
- Fast mode = mathematically bypasses the physical carrier mechanism.
- True PWM = preserves carrier/noise characteristics.
- True PWM + filter = approximates the old small motherboard speaker response.

The true-PWM modes are intentionally slower than Fast mode.


VERSION 0.1.9 - ADDITIONAL 3.5 kHz PWM FILTER
==============================================
Variant choices now include:

  Fast envelope (no PWM carrier)
  True PWM
  True PWM + 4.5 kHz filter
  True PWM + 3.5 kHz filter

The two filtered PWM variants use the same true 192 kHz PWM reconstruction and
the same simple one-pole low-pass. Only the cutoff differs, making direct
3.5 kHz vs 4.5 kHz comparison easy.


VERSION 0.2.0 - STRONGER 3.5 kHz PWM FILTER
============================================
The previous 3.5 kHz PWM filter used a single one-pole low-pass. Its roll-off
was relatively gentle, so some high-frequency PWM carrier remained audible.

The 3.5 kHz variant now cascades TWO identical one-pole filters:

    True PWM + strong 3.5 kHz filter

This gives a much steeper high-frequency roll-off while keeping the same nominal
3.5 kHz cutoff.

Other variants are unchanged:
    Fast envelope (no PWM carrier)
    True PWM
    True PWM + 4.5 kHz filter


VERSION 0.2.1 - ONE-PASS TRUE PWM RENDERER
===========================================
The True PWM variants no longer construct a full 192 kHz float buffer.

Instead, the renderer directly integrates the historical PWM HIGH/LOW timing
into each final 16 kHz output sample in one pass.

Variants retained:
  Fast envelope (no PWM carrier)
  True PWM
  True PWM + 4.5 kHz filter
  True PWM + strong 3.5 kHz filter

For the filtered modes, the simple low-pass is applied directly at 16 kHz.
The 3.5 kHz mode still uses two cascaded poles.

This substantially reduces intermediate memory and Python loop overhead.


VERSION 0.2.2 - FIVE DEMONSTRATION MODES
=========================================
Variants:
  Fast envelope (no PWM carrier)
  True PWM
  REAL PWM
  REAL PWM + 4.5 kHz filter
  REAL PWM + strong 3.5 kHz filter

True PWM keeps the 0.2.1 integrated one-pass renderer.

REAL PWM is different: it samples the instantaneous historical square-wave
state directly at 16 kHz, intentionally preserving more carrier/aliasing.

The two REAL PWM filtered modes use the same direct square-wave path and add:
- one 4.5 kHz pole
- two cascaded 3.5 kHz poles


VERSION 0.2.3 - 48 kHz REAL PWM + 4th-ORDER FILTERS
====================================================
Fast envelope and True PWM are unchanged.

REAL PWM modes now run at 48 kHz:
  REAL PWM 48 kHz
  REAL PWM 48 kHz + 4.0 kHz 4-pole filter
  REAL PWM 48 kHz + 3.5 kHz 4-pole filter

Why:
The historical PWM repetition is about 9.18 kHz. At 16 kHz output that carrier
is above Nyquist and aliases into the audible range. At 48 kHz it can be
represented properly instead of folding down.

The filtered modes use a genuine 4th-order Butterworth low-pass implemented as
two cascaded biquads. This gives much stronger rejection of the 9.18 kHz
carrier while preserving speech below the cutoff better than stacked one-pole
filters.

WavePlayer is automatically recreated at 16 kHz for Fast/True PWM and at
48 kHz for REAL PWM variants.


VERSION 0.2.4 - FILTER BEFORE DOWNSAMPLING
===========================================
Fast envelope and True PWM are unchanged.

REAL PWM variants:
  REAL PWM 48 kHz
  REAL PWM 48 kHz + pre-filtered 4.0 kHz
  REAL PWM 48 kHz + pre-filtered 3.5 kHz

Critical change:
The filtered REAL PWM modes now generate the instantaneous PWM internally at
192 kHz, apply a 4th-order Butterworth low-pass at that high rate, and only
then decimate 4:1 to 48 kHz.

This prevents high PWM harmonics from aliasing into the audible speech band
before the filter can remove them.

Implementation remains streaming:
- no full 192 kHz intermediate buffer
- four 192 kHz PWM/filter steps are processed for each final 48 kHz sample


VERSION 0.2.5 - DEMONSTRATION INTERFACE
========================================
Add-on / synthesizer display name:
    PCTALKER PC Speaker - Hungarian - DEMO

Description:
    This addon demonstrates the audio quality and PC-speaker sound
    characteristics of the Hungarian PCTALKER PC Speaker version developed
    by J. Kiraly between 1989 and 1991.

Variants:
    Fast envelope (no PWM carrier)
    True PWM (PC-speaker acoustic emulation)
    Real PWM 48 kHz
    Real PWM 48 kHz + 3.5 kHz filter

Fast envelope is the default because it provides the best responsiveness for
normal NVDA navigation.

The 4.0 kHz REAL PWM filter variant has been removed to simplify the demo.
