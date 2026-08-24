from __future__ import annotations

import math
import re
import sys
from array import array
from functools import lru_cache
from pathlib import Path

from . import olvas_text_engine as ote

PIT_CLOCK = 1_193_182.0
IRQ_DIVISOR = 65
IRQS_PER_SOURCE_SAMPLE = 2
SLOT_PIT_TICKS = IRQ_DIVISOR * IRQS_PER_SOURCE_SAMPLE
SOURCE_RATE = PIT_CLOCK / SLOT_PIT_TICKS
FAST_OUTPUT_RATE = 16_000
PWM_OUTPUT_RATE = 192_000
NVDA_OUTPUT_RATE = 16_000
REAL_PWM_OUTPUT_RATE = 48_000

TABLE_RE = re.compile(
    r"^\s*c(\d{3})c\w*\s+dw\s+(\d+)\s*,\s*(\d+)",
    re.IGNORECASE | re.MULTILINE,
)

class SynthesisCancelled(Exception):
    pass

def _check_cancel(cancel_check):
    if cancel_check is not None and cancel_check():
        raise SynthesisCancelled()

@lru_cache(maxsize=4)
def load_table(path: str):
    text = Path(path).read_text(encoding="latin-1")
    table = {}
    for code_s, start_s, length_s in TABLE_RE.findall(text):
        table[int(code_s)] = (int(start_s), int(length_s))
    return table

def text_to_codes(text: str, asm: Path, szotar: Path):
    expanded = ote.expand_numbers(text)
    _, codes = ote.dictionary_convert(expanded, asm, szotar)
    return list(codes)

def codes_to_raw(codes, raw: bytes, table):
    out = bytearray()
    extend = out.extend
    for code in codes:
        item = table.get(int(code))
        if not item:
            continue
        start, length = item
        if start < 0 or length <= 0 or start + length > len(raw):
            continue
        extend(raw[start:start + length])
    return bytes(out)

_GAIN = 0.15

# Fast envelope lookup: exact average bipolar value per historical PWM slot.
_PCM_LUT = tuple(
    int(round(max(-1.0, min(1.0, ((2.0 * (b >> 1) / SLOT_PIT_TICKS) - 1.0) * _GAIN)) * 32767.0))
    for b in range(256)
)

def raw_to_pcm16_fast(raw: bytes, speed: float = 1.0, cancel_check=None) -> bytes:
    if not raw:
        return b""

    speed = max(0.35, min(3.0, float(speed)))
    duration = len(raw) / SOURCE_RATE / speed
    out_len = max(1, int(round(duration * FAST_OUTPUT_RATE)))
    step = SOURCE_RATE * speed / FAST_OUTPUT_RATE
    pos = 0.0

    pcm = array("h")
    append = pcm.append
    raw_len = len(raw)
    lut = _PCM_LUT

    for j in range(out_len):
        if (j & 0x7FF) == 0:
            _check_cancel(cancel_check)
        idx = int(pos)
        if idx >= raw_len:
            idx = raw_len - 1
        append(lut[raw[idx]])
        pos += step

    _check_cancel(cancel_check)
    if sys.byteorder != "little":
        pcm.byteswap()
    return pcm.tobytes()

def _one_pole_alpha(sample_rate, cutoff_hz):
    if cutoff_hz <= 0:
        return 1.0
    dt=1.0/sample_rate
    rc=1.0/(2.0*math.pi*cutoff_hz)
    return dt/(rc+dt)

def render_pwm_to_pcm16_onepass(raw: bytes, speed: float=1.0,
                                filter_cutoff=None, filter_poles: int=1,
                                cancel_check=None) -> bytes:
    if not raw:
        return b""
    speed=max(0.35,min(3.0,float(speed)))
    slot_ticks=float(SLOT_PIT_TICKS)
    total_duration=len(raw)*(slot_ticks/PIT_CLOCK)/speed
    out_len=max(1,int(round(total_duration*NVDA_OUTPUT_RATE)))
    ticks_per_output=PIT_CLOCK*speed/NVDA_OUTPUT_RATE

    do_filter=filter_cutoff is not None and filter_cutoff>0
    poles=max(1,int(filter_poles)) if do_filter else 0
    alpha=_one_pole_alpha(NVDA_OUTPUT_RATE,filter_cutoff) if do_filter else 1.0
    states=[0.0]*poles

    pcm=array("h"); append=pcm.append; raw_len=len(raw)

    for n in range(out_len):
        if (n & 0x3FF)==0:
            _check_cancel(cancel_check)

        win_start=n*ticks_per_output
        win_end=win_start+ticks_per_output
        pos=win_start
        area=0.0

        while pos < win_end:
            slot_index=int(pos//slot_ticks)
            if slot_index>=raw_len:
                break
            slot_start=slot_index*slot_ticks
            slot_end=slot_start+slot_ticks
            seg_end=min(win_end,slot_end)
            high_end=slot_start+float(raw[slot_index]>>1)

            if pos < high_end:
                h=min(seg_end,high_end)
                if h>pos:
                    area += h-pos
                    pos=h
                    if pos>=seg_end:
                        continue
            if pos<seg_end:
                area -= seg_end-pos
                pos=seg_end

        value=(area/ticks_per_output if ticks_per_output>0 else 0.0)*_GAIN

        if do_filter:
            x=value
            for i in range(poles):
                states[i] += alpha*(x-states[i])
                x=states[i]
            value=x

        value=max(-1.0,min(1.0,value))
        append(int(round(value*32767.0)))

    _check_cancel(cancel_check)
    if sys.byteorder!="little":
        pcm.byteswap()
    return pcm.tobytes()


def float_to_pcm16(x):
    pcm = array("h")
    append = pcm.append
    for v in x:
        v = max(-1.0, min(1.0, v))
        append(int(round(v * 32767.0)))
    if sys.byteorder != "little":
        pcm.byteswap()
    return pcm.tobytes()



def _biquad_lowpass_coeffs(sample_rate, cutoff_hz, q):
    """RBJ cookbook low-pass biquad."""
    w0 = 2.0 * math.pi * cutoff_hz / sample_rate
    cos_w0 = math.cos(w0)
    sin_w0 = math.sin(w0)
    alpha = sin_w0 / (2.0 * q)

    b0 = (1.0 - cos_w0) / 2.0
    b1 = 1.0 - cos_w0
    b2 = (1.0 - cos_w0) / 2.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha

    return (
        b0 / a0, b1 / a0, b2 / a0,
        a1 / a0, a2 / a0,
    )

def _butterworth4_sections(sample_rate, cutoff_hz):
    """
    4th-order Butterworth low-pass as two cascaded biquads.
    Q values are the standard 4th-order Butterworth section Qs.
    """
    q1 = 0.541196100146197
    q2 = 1.306562964876377
    return (
        _biquad_lowpass_coeffs(sample_rate, cutoff_hz, q1),
        _biquad_lowpass_coeffs(sample_rate, cutoff_hz, q2),
    )

def _biquad_process_sample(x, coeffs, state):
    b0, b1, b2, a1, a2 = coeffs
    x1, x2, y1, y2 = state
    y = b0*x + b1*x1 + b2*x2 - a1*y1 - a2*y2
    state[1] = x1
    state[0] = x
    state[3] = y1
    state[2] = y
    return y


def render_real_pwm_pcm16(
    raw: bytes,
    speed: float = 1.0,
    cancel_check=None,
) -> bytes:
    """
    Unfiltered REAL PWM demonstration path.

    Samples the instantaneous historical square-wave state directly at 48 kHz.
    This intentionally preserves carrier/aliasing character.
    """
    if not raw:
        return b""

    speed = max(0.35, min(3.0, float(speed)))
    slot_ticks = float(SLOT_PIT_TICKS)
    total_duration = len(raw) * (slot_ticks / PIT_CLOCK) / speed
    out_len = max(1, int(round(total_duration * REAL_PWM_OUTPUT_RATE)))
    ticks_per_output = PIT_CLOCK * speed / REAL_PWM_OUTPUT_RATE

    pcm = array("h")
    append = pcm.append
    raw_len = len(raw)

    for n in range(out_len):
        if (n & 0x7FF) == 0:
            _check_cancel(cancel_check)

        t_ticks = n * ticks_per_output
        slot_index = int(t_ticks // slot_ticks)

        if slot_index >= raw_len:
            value = 0.0
        else:
            slot_start = slot_index * slot_ticks
            phase = t_ticks - slot_start
            high_ticks = float(raw[slot_index] >> 1)
            value = (1.0 if phase < high_ticks else -1.0) * _GAIN

        append(int(round(max(-1.0, min(1.0, value)) * 32767.0)))

    _check_cancel(cancel_check)

    if sys.byteorder != "little":
        pcm.byteswap()
    return pcm.tobytes()


def render_real_pwm_filtered_pcm16(
    raw: bytes,
    speed: float = 1.0,
    cutoff_hz: float = 4000.0,
    cancel_check=None,
) -> bytes:
    """
    Physically more realistic filtered REAL PWM path.

    Pipeline:
        instantaneous PWM at 192 kHz
        -> 4th-order Butterworth low-pass at 192 kHz
        -> decimate 4:1 to 48 kHz
        -> PCM16

    Filtering before downsampling prevents high PWM harmonics from aliasing
    into the speech band before the speaker filter can suppress them.
    """
    if not raw:
        return b""

    speed = max(0.35, min(3.0, float(speed)))
    slot_ticks = float(SLOT_PIT_TICKS)

    internal_rate = PWM_OUTPUT_RATE       # 192 kHz
    output_rate = REAL_PWM_OUTPUT_RATE   # 48 kHz
    decim = internal_rate // output_rate
    if decim != 4:
        raise RuntimeError("Expected 192 kHz -> 48 kHz decimation by 4.")

    total_duration = len(raw) * (slot_ticks / PIT_CLOCK) / speed
    internal_len = max(1, int(round(total_duration * internal_rate)))
    ticks_per_internal = PIT_CLOCK * speed / internal_rate

    sections = _butterworth4_sections(internal_rate, float(cutoff_hz))
    states = [
        [0.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0],
    ]

    pcm = array("h")
    append = pcm.append
    raw_len = len(raw)

    # For each 48 kHz sample, process four true 192 kHz PWM points through
    # the filter and keep the final filtered point. This is streaming and
    # avoids a large 192 kHz intermediate buffer.
    n_out = max(1, internal_len // decim)

    internal_index = 0
    for out_index in range(n_out):
        if (out_index & 0x3FF) == 0:
            _check_cancel(cancel_check)

        filtered = 0.0

        for _ in range(decim):
            t_ticks = internal_index * ticks_per_internal
            slot_index = int(t_ticks // slot_ticks)

            if slot_index >= raw_len:
                value = 0.0
            else:
                slot_start = slot_index * slot_ticks
                phase = t_ticks - slot_start
                high_ticks = float(raw[slot_index] >> 1)
                value = (1.0 if phase < high_ticks else -1.0) * _GAIN

            filtered = _biquad_process_sample(value, sections[0], states[0])
            filtered = _biquad_process_sample(filtered, sections[1], states[1])

            internal_index += 1

        filtered = max(-1.0, min(1.0, filtered))
        append(int(round(filtered * 32767.0)))

    _check_cancel(cancel_check)

    if sys.byteorder != "little":
        pcm.byteswap()
    return pcm.tobytes()


class PCSpeakerEngine:
    def __init__(
        self,
        base_dir=None,
        language="hu_HU",
        mode="fast",
        pwm_filter_cutoff=4500.0,
        **_ignored,
    ):
        self.base_dir = Path(base_dir or Path(__file__).resolve().parent)
        self.language = "hu_HU"
        self.mode = mode if mode in ("fast", "pwm", "realPwm", "realPwm35") else "fast"
        self.pwm_filter_cutoff = float(pwm_filter_cutoff)

        self.asm = self.base_dir / "data" / "OLVASSP.ASM"
        self.raw_path = self.base_dir / "data" / "RAWSP"
        self.szotar = self.base_dir / "data" / "SZOTAR.TBL"

        self.raw = self.raw_path.read_bytes()
        self.table = load_table(str(self.asm))

    def synthesize(self, text: str, speed: float = 1.0, cancel_check=None) -> bytes:
        _check_cancel(cancel_check)
        codes = text_to_codes(text, self.asm, self.szotar)
        _check_cancel(cancel_check)
        raw = codes_to_raw(codes, self.raw, self.table)
        _check_cancel(cancel_check)

        if self.mode == "fast":
            return raw_to_pcm16_fast(raw, speed, cancel_check)

        if self.mode == "pwm":
            return render_pwm_to_pcm16_onepass(
                raw, speed, None, 1, cancel_check
            )

        if self.mode == "realPwm":
            return render_real_pwm_pcm16(
                raw, speed, cancel_check
            )

        if self.mode == "realPwm35":
            return render_real_pwm_filtered_pcm16(
                raw, speed, 3500.0, cancel_check
            )

        return raw_to_pcm16_fast(raw, speed, cancel_check)
