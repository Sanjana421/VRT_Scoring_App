"""
Audio file handling:
  - get_waveform_data: reads WAV, returns downsampled float list + window info
  - get_wav_path:      resolves the file path
  - RESP_WINDOW / RESP_MARK_PROP logic matches edit_onsets_2 in scoreVRT_v5.m
"""

import os
import math
import numpy as np
import scipy.io.wavfile as wav
import config


def get_waveform_data(obs_name, visit_num: int, snr, dist_cond: int,
                      run_num: int, trial_num: int,
                      version: str = "v5") -> dict:
    """
    Read a WAV file and return everything the frontend needs:
      - samples: downsampled waveform (list of floats, ~2000 points)
      - duration: total duration in seconds
      - sample_rate: original sample rate
      - window_start: recommended view start (seconds)
      - window_end:   recommended view end (seconds)
      - marker_default: default marker position (0.0 s - reviewer places it)
    """
    wav_path = config.get_wav_path(
        obs_name, visit_num, snr, dist_cond, run_num, trial_num, version
    )

    if not os.path.isfile(wav_path):
        raise FileNotFoundError(f"WAV file not found: {wav_path}")

    srate, data = wav.read(wav_path)

    # Convert to mono float32 in [-1, 1]
    if data.ndim > 1:
        data = data[:, 0]
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float32) / 2147483648.0
    elif data.dtype == np.uint8:
        data = (data.astype(np.float32) - 128.0) / 128.0
    else:
        data = data.astype(np.float32)

    duration = len(data) / srate

    # Default window: 4-second window starting at t=0 (marker at 0)
    # Reviewer will move the marker; window follows as in show_stim_and_marker_2
    resp_onset = 0.0
    t1 = max(0.0, resp_onset - config.RESP_MARK_PROP * config.RESP_WINDOW)
    t2 = t1 + config.RESP_WINDOW
    if t2 > duration:
        t2 = duration
        t1 = max(0.0, t2 - config.RESP_WINDOW)

    # Downsample for display - pick the peak sample per block (preserves sign and shape)
    n_display = config.WAVEFORM_POINTS
    if len(data) > n_display:
        block = len(data) // n_display
        trimmed = data[:block * n_display].reshape(n_display, block)
        # Index of max-absolute-value sample in each block
        max_idx = np.argmax(np.abs(trimmed), axis=1)
        display = trimmed[np.arange(n_display), max_idx]
    else:
        display = data.copy()

    # Normalize to peak amplitude so waveform fills the display (matches MATLAB auto-scale)
    peak = np.max(np.abs(display))
    if peak > 1e-6:
        display = display / peak

    return {
        "wav_path":      wav_path,
        "samples":       display.tolist(),
        "duration":      round(duration, 6),
        "sample_rate":   srate,
        "n_samples":     len(data),
        "window_start":  round(t1, 6),
        "window_end":    round(t2, 6),
        "marker_time":   round(t1 + config.RESP_MARK_PROP * config.RESP_WINDOW, 6),
        "resp_window":   config.RESP_WINDOW,
        "mark_prop":     config.RESP_MARK_PROP,
    }


def wav_exists(obs_name, visit_num: int, snr, dist_cond: int,
               run_num: int, trial_num: int, version: str = "v5") -> bool:
    return os.path.isfile(
        config.get_wav_path(obs_name, visit_num, snr, dist_cond,
                            run_num, trial_num, version)
    )


def get_wav_filepath(obs_name, visit_num: int, snr, dist_cond: int,
                     run_num: int, trial_num: int,
                     version: str = "v5") -> str:
    p = config.get_wav_path(obs_name, visit_num, snr, dist_cond,
                            run_num, trial_num, version)
    if not os.path.isfile(p):
        raise FileNotFoundError(f"WAV not found: {p}")
    return p
