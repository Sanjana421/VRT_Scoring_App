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
    """A reviewer score cell counts as done only when it holds a real value."""
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


def get_run_progress(
    obs_name,
    visit_num: int,
    snr,
    dist_cond,
    run_num: int,
    version: str = "v5",
) -> dict:
    """
    Read the subject's .xlsx and report which trials each reviewer has scored
    for one run. The workbook is the source of truth for cross-person handoff.

    Missing file or columns -> empty sets.
    """
    empty = {
        1: {"scored": set(), "contributors": set()},
        2: {"scored": set(), "contributors": set()},
    }

    excel_path = config.get_excel_path(obs_name, visit_num, version)
    if not os.path.isfile(excel_path):
        return empty

    try:
        wb = openpyxl.load_workbook(
            excel_path,
            read_only=True,
            data_only=True,
        )
        ws = wb.active
        hdr = [
            str(cell.value).strip() if cell.value is not None else ""
            for cell in ws[1]
        ]

        def ci(name):
            return hdr.index(name) if name in hdr else None

        c_snr = ci("SNR")
        c_dist = ci("DistCond")
        c_run = ci("RunNum")
        c_trial = ci("TrialNum")
        cols = {
            1: (ci("RespScore1"), ci("Reviewer1")),
            2: (ci("RespScore2"), ci("Reviewer2")),
        }

        if None in (c_snr, c_dist, c_run, c_trial):
            wb.close()
            return empty

        result = {
            1: {"scored": set(), "contributors": set()},
            2: {"scored": set(), "contributors": set()},
        }

        for vals in ws.iter_rows(min_row=2, values_only=True):
            try:
                if not _float_eq(vals[c_snr], snr):
                    continue
                if not _float_eq(vals[c_dist], dist_cond):
                    continue
                if int(float(str(vals[c_run]))) != int(run_num):
                    continue
                trial_num = int(float(str(vals[c_trial])))
            except Exception:
                continue

            for reviewer_num, (score_col, reviewer_col) in cols.items():
                if score_col is None:
                    continue
                if _cell_meaningful(vals[score_col]):
                    result[reviewer_num]["scored"].add(trial_num)
                    if reviewer_col is not None and vals[reviewer_col] is not None:
                        initials = str(vals[reviewer_col]).strip().upper()
                        if initials:
                            result[reviewer_num]["contributors"].add(initials)

        wb.close()
        return result
    except Exception:
        return empty


def _float_eq(a, b, tol=1e-6) -> bool:
    """Tolerant float comparison for SNR values."""
    try:
        return abs(float(a) - float(b)) < tol
    except Exception:
        return str(a).strip() == str(b).strip()


def _trial_data_candidates(obs_name, visit_num, bundle_version, version):
    """
    The collector writes the trial metadata as an extensionless text file.
    Also accept .txt and .csv copies of that text file.
    """
    base = config.get_subject_data_path(
        obs_name,
        visit_num,
        bundle_version,
        version,
    )
    return [base, base + ".txt", base + ".csv"]


def read_trial_info(
    obs_name,
    visit_num: int,
    bundle_version: str,
    snr,
    dist_cond,
    run_num: int,
    trial_num: int,
    version: str = "v5",
) -> dict:
    """
    Return StimWord and StimTalker for the requested trial.
    Raises FileNotFoundError if the trial data file is missing,
    or ValueError if the matching row is not found.
    """
    candidates = _trial_data_candidates(
        obs_name, visit_num, bundle_version, version
    )
    data_file = next((path for path in candidates if os.path.isfile(path)), None)

    if data_file is None:
        raise FileNotFoundError(
            f"Subject data file not found. Tried: {candidates}"
        )

    with open(data_file, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)

        for idx, row in enumerate(reader):
            if len(row) < 14:
                continue
            try:
                row_snr = float(row[5])
                row_distcond = float(row[6])
                row_runnum = int(float(row[9]))
                row_trialnum = int(float(row[10]))
            except (ValueError, IndexError):
                continue

            if (
                _float_eq(row_snr, snr)
                and _float_eq(row_distcond, dist_cond)
                and row_runnum == int(run_num)
                and row_trialnum == int(trial_num)
            ):
                return {
                    "stim_talker": row[11].strip(),
                    "stim_word": row[13].strip(),
                    "row_index": idx + 1,
                }

    raise ValueError(
        f"No matching row found for SNR={snr}, DistCond={dist_cond}, "
        f"RunNum={run_num}, TrialNum={trial_num} in {data_file}"
    )


def get_all_trials(
    obs_name,
    visit_num: int,
    bundle_version: str,
    snr,
    dist_cond,
    run_num: int,
    version: str = "v5",
) -> list:
    """
    Return trials in a run, sorted by TrialNum.
    Each trial includes its number, word, talker, and source row index.
    """
    candidates = _trial_data_candidates(
        obs_name, visit_num, bundle_version, version
    )
    data_file = next((path for path in candidates if os.path.isfile(path)), None)

    if data_file is None:
        raise FileNotFoundError(
            f"Subject data file not found. Tried: {candidates}"
        )

    trials = []
    with open(data_file, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)

        for idx, row in enumerate(reader):
            if len(row) < 14:
                continue
            try:
                row_snr = float(row[5])
                row_distcond = float(row[6])
                row_runnum = int(float(row[9]))
                row_trialnum = int(float(row[10]))
            except (ValueError, IndexError):
                continue

            if (
                _float_eq(row_snr, snr)
                and _float_eq(row_distcond, dist_cond)
                and row_runnum == int(run_num)
            ):
                trials.append({
                    "trial_num": row_trialnum,
                    "stim_word": row[13].strip(),
                    "stim_talker": row[11].strip(),
                    "row_index": idx + 1,
                })

    trials.sort(key=lambda trial: trial["trial_num"])
    return trials


# The collector writes the full 18-column metadata row. The scorer copies it to
# the output workbook so trial metadata is retained alongside reviewer scores.
EXPECTED_VARS = [
    "ObsName", "TimeStamp", "VisitNum", "WordLevel", "NoiseCond", "SNR",
    "DistCond", "DistLevel", "DistTime", "RunNum", "TrialNum", "StimTalker",
    "ListNum", "StimWord", "DistPresent", "DistItem", "TargetSide", "Response",
]

# Columns the MATLAB scorer treats as numeric.
_NUMERIC_IDX = {0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16}


def _coerce(idx, raw):
    s = (raw or "").strip()
    if idx in _NUMERIC_IDX and s != "":
        try:
            value = float(s)
            return int(value) if value == int(value) else value
        except Exception:
            return s
    return s


def get_full_trial_row(
    obs_name,
    visit_num: int,
    bundle_version: str,
    snr,
    dist_cond,
    run_num: int,
    trial_num: int,
    version: str = "v5",
) -> Optional[dict]:
    """
    Return the full 18-column metadata row for a trial.
    Return None if the text data bundle or matching row is unavailable.
    """
    candidates = _trial_data_candidates(
        obs_name, visit_num, bundle_version, version
    )
    data_file = next((path for path in candidates if os.path.isfile(path)), None)

    if data_file is None:
        return None

    try:
        with open(data_file, "r", newline="", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader, None)

            for row in reader:
                if len(row) < 18:
                    continue
                try:
                    matches = (
                        _float_eq(row[5], snr)
                        and _float_eq(row[6], dist_cond)
                        and int(float(row[9])) == int(run_num)
                        and int(float(row[10])) == int(trial_num)
                    )
                except (ValueError, IndexError):
                    continue

                if matches:
                    return {
                        EXPECTED_VARS[i]: _coerce(i, row[i])
                        for i in range(18)
                    }
    except Exception:
        return None

    return None
