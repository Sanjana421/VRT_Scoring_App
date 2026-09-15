"""
Scoring log read/write - exact logic from chooseScoringRowRandom.m
and writeReviewerInitials.m, ported to Python.

Scoring log columns (1-indexed):
  A(1): ObsName   B(2): visitnum  C(3): NoiseCond
  D(4): dBSNR     E(5): DistCond  F(6): RunNum
  G(7): R1 initials   H(8): R2 initials   I(9): R3 initials
"""

import os
import random
import re
import openpyxl
from typing import Optional
from file_lock import ScoringLogLock
import config


# -- Initials helper (matches compute_initials / computeInitialsFromName) ------
def compute_initials(full_name: str) -> str:
    full_name = full_name.strip()
    if not full_name:
        return ""
    parts = re.split(r"\s+", full_name)
    if len(parts) == 1:
        letters = re.sub(r"[^A-Za-z]", "", parts[0])
        return letters[:3].upper() if letters else ""
    a = re.sub(r"[^A-Za-z]", "", parts[0])
    b = ""
    for p in parts[1:]:
        t = re.sub(r"[^A-Za-z]", "", p)
        if t:
            b = t
            break
    if not a and not b:
        return ""
    if not b:
        return a[:3].upper()
    if not a:
        # First token had no letters (e.g. "123 Smith"); MATLAB errors on a(1).
        return b[:3].upper()
    return (a[0] + b[0]).upper()


# -- Cell-empty check ----------------------------------------------------------
def _is_empty(val) -> bool:
    if val is None:
        return True
    if isinstance(val, str):
        return val.strip() == ""
    if isinstance(val, float):
        import math
        return math.isnan(val)
    return False


# -- Main: claim a row ---------------------------------------------------------
def claim_scoring_row(reviewer_name: str, log_path: str = None) -> dict:
    """
    Read the scoring log, randomly pick an available row, immediately write
    a placeholder initials value to claim it (prevents Woody and Buzz
    grabbing the same row), then return the DataDet fields.

    Returns dict with keys:
        obs_name, visit_num, noise_cond, snr, dist_cond, run_num,
        rev_num (1 or 2), log_row (1-based Excel row index)
    Raises ValueError if no row is available.
    """
    if log_path is None:
        log_path = config.SCORING_LOG_V5

    current_init = compute_initials(reviewer_name)

    with ScoringLogLock(log_path):
        wb = openpyxl.load_workbook(log_path)
        ws = wb.active

        # Collect candidate rows: rows 2+ where cols A-F are all non-empty
        # AND the subject data folder actually exists on disk (skip future subjects)
        candidates = []
        for row in ws.iter_rows(min_row=2, values_only=False):
            if all(not _is_empty(row[c].value) for c in range(6)):  # cols A-F
                try:
                    obs = str(row[0].value)
                    vis = int(float(str(row[1].value)))
                    data_folder = config.get_data_path(obs, vis)
                    if os.path.isdir(data_folder):
                        candidates.append(row)
                except Exception:
                    pass  # Skip malformed rows

        if not candidates:
            raise ValueError(
                "No scoreable runs found. Either all runs are claimed/complete, "
                "or no subject data folders exist yet."
            )

        # Shuffle and search for R1 (col G empty or missing)
        r1_candidates = [r for r in candidates
                         if len(r) <= 6 or _is_empty(r[6].value)]
        random.shuffle(r1_candidates)

        chosen_row = None
        rev_num = None

        for row in r1_candidates:
            chosen_row = row
            rev_num = 1
            break

        # If no R1, search for R2 (col H empty, col G initials != current)
        if chosen_row is None:
            r2_candidates = [
                r for r in candidates
                if (len(r) <= 7 or _is_empty(r[7].value))          # H empty/missing
                and len(r) > 6 and not _is_empty(r[6].value)        # G has R1
                and not _initials_match(r[6].value, current_init)
            ]
            random.shuffle(r2_candidates)
            for row in r2_candidates:
                chosen_row = row
                rev_num = 2
                break

        if chosen_row is None:
            raise ValueError(
                "No more runs available to score. "
                "Either all runs are claimed or you have already scored all eligible runs."
            )

        # Claim the row immediately by writing a placeholder
        col_idx = 7 if rev_num == 1 else 8   # G or H (1-indexed)
        placeholder = f"--{current_init}--"
        ws.cell(row=chosen_row[0].row, column=col_idx).value = placeholder

        wb.save(log_path)
        wb.close()

        # Extract DataDet fields (same columns as getdatadetails.m)
        log_row = chosen_row[0].row  # actual Excel row number
        return {
            "obs_name":   str(chosen_row[0].value),      # A - cast int->str (Excel stores as number)
            "visit_num":  int(chosen_row[1].value),      # B
            "noise_cond": chosen_row[2].value,           # C
            "snr":        chosen_row[3].value,           # D
            "dist_cond":  int(chosen_row[4].value),      # E
            "run_num":    int(chosen_row[5].value),      # F
            "rev_num":    rev_num,
            "log_row":    log_row,
        }


def is_placeholder(cell_val) -> bool:
    """True if the cell holds an unfinished claim like '--SAN--' rather than
    real initials. Real initials are written only when a run completes."""
    if _is_empty(cell_val):
        return False
    s = str(cell_val).strip()
    return s.startswith("--") and s.endswith("--") and len(s) > 4


def release_scoring_row(log_row: int, rev_num: int, log_path: str = None):
    """
    Clear a placeholder claim, returning the row to the queue. Used when a run
    is claimed but turns out to be unscoreable, so the row isn't stranded.
    Only clears placeholders - never real initials.
    """
    if log_path is None:
        log_path = config.SCORING_LOG_V5
    col_idx = 6 + rev_num  # G=7, H=8, I=9
    with ScoringLogLock(log_path):
        wb = openpyxl.load_workbook(log_path)
        ws = wb.active
        cell = ws.cell(row=log_row, column=col_idx)
        if is_placeholder(cell.value):
            cell.value = None
            wb.save(log_path)
        wb.close()


def _initials_match(cell_val, current_init: str) -> bool:
    if not current_init:
        return False
    cell_str = str(cell_val).strip().upper()
    # strip placeholder prefix/suffix if present
    cell_str = cell_str.strip("-")
    return cell_str == current_init.upper()


# -- Write final initials after run is complete --------------------------------
def write_reviewer_initials(reviewer_name: str, log_row: int,
                             rev_num: int, log_path: str = None):
    """
    Replace the placeholder in the scoring log with the real initials.
    rev_num: 1 -> col G, 2 -> col H, 3 -> col I
    Matches writeReviewerInitials.m exactly.
    """
    if log_path is None:
        log_path = config.SCORING_LOG_V5

    initials = compute_initials(reviewer_name)
    col_idx = 6 + rev_num  # G=7, H=8, I=9  (1-indexed)
    col_letter = chr(ord('G') + rev_num - 1)  # 'G', 'H', 'I'

    with ScoringLogLock(log_path):
        wb = openpyxl.load_workbook(log_path)
        ws = wb.active
        ws.cell(row=log_row, column=col_idx).value = initials
        wb.save(log_path)
        wb.close()


# -- Check if all runs for every subject are fully scored (R1+R2) -------------
def get_completion_status(log_path: str = None) -> dict:
    """
    Returns info about which datasets are fully scored (R1 and R2 both done).
    Used by the professor view to surface ready datasets.
    """
    if log_path is None:
        log_path = config.SCORING_LOG_V5

    wb = openpyxl.load_workbook(log_path, read_only=True)
    ws = wb.active

    def _is_done(val) -> bool:
        """A reviewer slot counts as complete only when it holds real initials.
        A '--XX--' placeholder means claimed-but-unfinished, not done."""
        return not _is_empty(val) and not is_placeholder(val) and str(val).strip() != ""

    by_subject = {}   # obs_name -> {total, r1_done, r2_done, claimed}
    runs_both_complete = 0
    for row in ws.iter_rows(min_row=2, values_only=True):
        if len(row) < 6 or all(_is_empty(row[c]) for c in range(6)):
            continue
        obs = str(int(row[0])) if row[0] is not None else "?"
        r1  = row[6] if len(row) > 6 else None   # col G - may not exist yet
        r2  = row[7] if len(row) > 7 else None   # col H - may not exist yet
        if obs not in by_subject:
            by_subject[obs] = {"total": 0, "r1_done": 0, "r2_done": 0, "claimed": 0}
        by_subject[obs]["total"] += 1
        if _is_done(r1):
            by_subject[obs]["r1_done"] += 1
        if _is_done(r2):
            by_subject[obs]["r2_done"] += 1
        if is_placeholder(r1) or is_placeholder(r2):
            by_subject[obs]["claimed"] += 1
        if _is_done(r1) and _is_done(r2):
            runs_both_complete += 1

    wb.close()

    ready = []
    all_done = True
    total_runs   = 0
    r1_complete  = 0
    r2_complete  = 0
    runs_claimed = 0
    for obs, counts in by_subject.items():
        total_runs   += counts["total"]
        r1_complete  += counts["r1_done"]
        r2_complete  += counts["r2_done"]
        runs_claimed += counts["claimed"]
        both_done = (counts["r1_done"] == counts["total"] and
                     counts["r2_done"] == counts["total"])
        if both_done:
            ready.append(obs)
        else:
            all_done = False

    # total_runs / r1_complete / r2_complete / both_complete are RUN counts.
    # subjects_complete is a SUBJECT count. (These were previously mixed.)
    return {
        "all_complete":      all_done,
        "ready_subjects":    ready,
        "by_subject":        by_subject,
        "total_runs":        total_runs,
        "r1_complete":       r1_complete,
        "r2_complete":       r2_complete,
        "both_complete":     runs_both_complete,   # runs with real R1 AND R2
        "subjects_complete": len(ready),           # subjects fully done
        "runs_claimed":      runs_claimed,         # claimed but unfinished
    }
