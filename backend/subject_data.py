"""
Read subject trial data file (CSV/text, no extension).
Finds the row matching SNR + DistCond + RunNum + TrialNum and returns
StimWord and StimTalker - same lookup as scoreVRT_v5.m lines 103-112.

Expected columns (0-indexed):
  0:ObsName 1:TimeStamp 2:VisitNum 3:WordLevel 4:NoiseCond 5:SNR
  6:DistCond 7:DistLevel 8:DistTime 9:RunNum 10:TrialNum 11:StimTalker
  12:ListNum 13:StimWord ...
"""

import os
import csv
import math
from typing import Optional
import config


def _float_eq(a, b, tol=1e-6) -> bool:
    """Tolerant float comparison for SNR (can be -4.55 etc.)."""
    try:
        return abs(float(a) - float(b)) < tol
    except Exception:
        return str(a).strip() == str(b).strip()


def read_trial_info(obs_name, visit_num: int, bundle_version: str,
                    snr, dist_cond, run_num: int, trial_num: int,
                    version: str = "v5") -> dict:
    """
    Returns {'stim_word': str, 'stim_talker': str, 'row_index': int}
    Raises FileNotFoundError if data file missing,
           ValueError if matching row not found.
    """
    base = config.get_subject_data_path(obs_name, visit_num, bundle_version, version)

    # Try with and without .txt extension (some files have it, some don't)
    candidates = [base, base + ".txt", base + ".csv", base + ".xlsx", base + ".xlsm"]
    data_file = None
    for c in candidates:
        if os.path.isfile(c):
            data_file = c
            break

    if data_file is None:
        raise FileNotFoundError(
            f"Subject data file not found. Tried: {candidates}"
        )

    with open(data_file, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader, None)  # skip header row

        for idx, row in enumerate(reader):
            if len(row) < 14:
                continue
            try:
                row_snr      = float(row[5])
                row_distcond = float(row[6])
                row_runnum   = int(float(row[9]))
                row_trialnum = int(float(row[10]))
            except (ValueError, IndexError):
                continue

            if (_float_eq(row_snr, snr) and
                    _float_eq(row_distcond, dist_cond) and
                    row_runnum == int(run_num) and
                    row_trialnum == int(trial_num)):
                return {
                    "stim_talker": row[11].strip(),
                    "stim_word":   row[13].strip(),
                    "row_index":   idx + 1,   # 1-based (matches MATLAB k)
                }

    raise ValueError(
        f"No matching row found for SNR={snr}, DistCond={dist_cond}, "
        f"RunNum={run_num}, TrialNum={trial_num} in {data_file}"
    )


def get_all_trials(obs_name, visit_num: int, bundle_version: str,
                   snr, dist_cond, run_num: int,
                   version: str = "v5") -> list:
    """
    Returns list of dicts for all 25 trials in a run, sorted by TrialNum.
    Each dict: {trial_num, stim_word, stim_talker, row_index}
    """
    base = config.get_subject_data_path(obs_name, visit_num, bundle_version, version)
    candidates = [base, base + ".txt", base + ".csv", base + ".xlsx", base + ".xlsm"]
    data_file = None
    for c in candidates:
        if os.path.isfile(c):
            data_file = c
            break
    if data_file is None:
        raise FileNotFoundError(f"Subject data file not found. Tried: {candidates}")

    trials = []
    with open(data_file, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)
        for idx, row in enumerate(reader):
            if len(row) < 14:
                continue
            try:
                row_snr      = float(row[5])
                row_distcond = float(row[6])
                row_runnum   = int(float(row[9]))
                row_trialnum = int(float(row[10]))
            except (ValueError, IndexError):
                continue
            if (_float_eq(row_snr, snr) and
                    _float_eq(row_distcond, dist_cond) and
                    row_runnum == int(run_num)):
                trials.append({
                    "trial_num":   row_trialnum,
                    "stim_word":   row[13].strip(),
                    "stim_talker": row[11].strip(),
                    "row_index":   idx + 1,
                })

    trials.sort(key=lambda x: x["trial_num"])
    return trials
