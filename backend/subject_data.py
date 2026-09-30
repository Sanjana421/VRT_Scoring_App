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
import openpyxl
import config


def _cell_meaningful(val) -> bool:
    """A reviewer score cell counts as 'done' only when it holds a real value
    (not blank, not the 999 sentinel). Mirrors excel_writer._is_meaningful."""
    if val is None:
        return False
    if isinstance(val, str):
        s = val.strip()
        return s != "" and s != "999"
    if isinstance(val, float):
        return not math.isnan(val) and val != 999
    if isinstance(val, int):
        return val != 999
    return False


def get_run_progress(obs_name, visit_num: int, snr, dist_cond,
                     run_num: int, version: str = "v5") -> dict:
    """
    Read the subject's .xlsm and report, for one run, which trials each reviewer
    has already scored and who scored them. This is the source of truth for
    cross-person handoff: the scoring log only says a pass is claimed/complete,
    but the per-trial Reviewer#/RespScore# columns say exactly how far each pass
    got and which initials contributed.

    Returns:
        {
          1: {"scored": set(trial_nums), "contributors": set(initials)},
          2: {"scored": set(trial_nums), "contributors": set(initials)},
        }
    Missing file / columns -> empty sets (treated as nothing scored yet).
    """
    empty = {1: {"scored": set(), "contributors": set()},
             2: {"scored": set(), "contributors": set()}}
    excel_path = config.get_excel_path(obs_name, visit_num, version)
    if not os.path.isfile(excel_path):
        return empty

    try:
        wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
        ws = wb.active
        hdr = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]

        def ci(name):
            return hdr.index(name) if name in hdr else None

        c_snr, c_dist, c_run, c_trial = ci("SNR"), ci("DistCond"), ci("RunNum"), ci("TrialNum")
        cols = {
            1: (ci("RespScore1"), ci("Reviewer1")),
            2: (ci("RespScore2"), ci("Reviewer2")),
        }
        if None in (c_snr, c_dist, c_run, c_trial):
            wb.close()
            return empty

        result = {1: {"scored": set(), "contributors": set()},
                  2: {"scored": set(), "contributors": set()}}
        for vals in ws.iter_rows(min_row=2, values_only=True):
            try:
                if not _float_eq(vals[c_snr], snr):
                    continue
                if not _float_eq(vals[c_dist], dist_cond):
                    continue
                if int(float(str(vals[c_run]))) != int(run_num):
                    continue
                tnum = int(float(str(vals[c_trial])))
            except Exception:
                continue
            for rev, (rs_col, rv_col) in cols.items():
                if rs_col is None:
                    continue
                if _cell_meaningful(vals[rs_col]):
                    result[rev]["scored"].add(tnum)
                    if rv_col is not None and vals[rv_col] is not None:
                        init = str(vals[rv_col]).strip().upper()
                        if init:
                            result[rev]["contributors"].add(init)
        wb.close()
        return result
    except Exception:
        return empty


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


# The 18 columns of the subject data bundle, in order, exactly as scoreVRT_v5.m
# overwrites them (expectedVars). MATLAB reads this whole row and writes it to
# the output workbook, so we must too - otherwise only the match-key columns get
# saved and the rest of the row is blank ("half the data").
EXPECTED_VARS = ["ObsName", "TimeStamp", "VisitNum", "WordLevel", "NoiseCond",
                 "SNR", "DistCond", "DistLevel", "DistTime", "RunNum", "TrialNum",
                 "StimTalker", "ListNum", "StimWord", "DistPresent", "DistItem",
                 "TargetSide", "Response"]
# Columns MATLAB infers as numeric (the rest stay text).
_NUMERIC_IDX = {0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16}


def _coerce(idx, raw):
    s = (raw or "").strip()
    if idx in _NUMERIC_IDX and s != "":
        try:
            f = float(s)
            return int(f) if f == int(f) else f
        except Exception:
            return s
    return s


def get_full_trial_row(obs_name, visit_num: int, bundle_version: str,
                       snr, dist_cond, run_num: int, trial_num: int,
                       version: str = "v5") -> Optional[dict]:
    """
    Return the FULL 18-column metadata row for one trial, read positionally from
    the subject data bundle (DistVRT_<ver>_<obs>) - the same source scoreVRT_v5.m
    reads. Keys are EXPECTED_VARS. Returns None if the bundle or row is missing,
    so the caller can fall back to the match keys.
    """
    base = config.get_subject_data_path(obs_name, visit_num, bundle_version, version)
    data_file = None
    for c in [base, base + ".txt", base + ".csv", base + ".xlsx", base + ".xlsm"]:
        if os.path.isfile(c):
            data_file = c
            break
    if data_file is None:
        return None

    try:
        with open(data_file, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader, None)  # header (names are overwritten by position anyway)
            for row in reader:
                if len(row) < 18:
                    continue
                try:
                    if not (_float_eq(row[5], snr) and _float_eq(row[6], dist_cond)
                            and int(float(row[9])) == int(run_num)
                            and int(float(row[10])) == int(trial_num)):
                        continue
                except (ValueError, IndexError):
                    continue
                return {EXPECTED_VARS[i]: _coerce(i, row[i]) for i in range(18)}
    except Exception:
        return None
    return None
