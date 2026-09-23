"""
Scoring log read/write - exact logic from chooseScoringRowRandom.m
and writeReviewerInitials.m, ported to Python.

Scoring log columns (1-indexed):
  A(1): ObsName   B(2): visitnum  C(3): NoiseCond
  D(4): dBSNR     E(5): DistCond  F(6): RunNum
  G(7): R1 initials   H(8): R2 initials   I(9): R3 initials
"""

import os
import json
import time
import random
import re
import openpyxl
from typing import Optional
from file_lock import ScoringLogLock
import config
from subject_data import get_run_progress

# A claimed-but-unfinished pass holds a "lease". While the lease is fresh, the
# person is actively scoring and nobody else may take that pass. Once it goes
# stale (they logged out / closed the tab), the partial pass becomes the top
# priority for the next person, who resumes from the first unscored trial.
LEASE_STALE_SECONDS = 90


# -- Lease sidecar (next to the scoring log) ----------------------------------
def _lease_path(log_path: str) -> str:
    return os.path.join(os.path.dirname(log_path), ".vrt_leases.json")


def read_leases(log_path: str) -> dict:
    try:
        with open(_lease_path(log_path), "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_leases(log_path: str, data: dict):
    try:
        with open(_lease_path(log_path), "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def _lease_key(log_row: int, rev_num: int) -> str:
    return f"{log_row}:{rev_num}"


def lease_is_active(leases: dict, log_row: int, rev_num: int,
                    now: float = None) -> bool:
    """True if this pass is being actively scored right now (fresh lease)."""
    rec = leases.get(_lease_key(log_row, rev_num))
    if not rec:
        return False
    now = now if now is not None else time.time()
    return (now - float(rec.get("ts", 0))) < LEASE_STALE_SECONDS


def set_lease(log_row: int, rev_num: int, initials: str, log_path: str = None):
    """Refresh (or create) the lease for a pass. Call on claim, heartbeat, save."""
    if log_path is None:
        log_path = config.SCORING_LOG_V5
    with ScoringLogLock(log_path):
        leases = read_leases(log_path)
        leases[_lease_key(log_row, rev_num)] = {
            "holder": initials, "ts": time.time()}
        _write_leases(log_path, leases)


def clear_lease(log_row: int, rev_num: int, log_path: str = None):
    if log_path is None:
        log_path = config.SCORING_LOG_V5
    with ScoringLogLock(log_path):
        leases = read_leases(log_path)
        if leases.pop(_lease_key(log_row, rev_num), None) is not None:
            _write_leases(log_path, leases)


def _is_real_initials(val) -> bool:
    """A pass is complete only when its log cell holds real initials -
    not blank and not a '--XX--' placeholder."""
    return (not _is_empty(val)) and (not is_placeholder(val)) and str(val).strip() != ""


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
def _combined_initials(contributors) -> str:
    """Join every reviewer who contributed to a pass, e.g. {'AN','SB'} -> 'AN/SB'.
    Sorted for a stable label. The authoritative per-trial record stays in the
    subject workbook's Reviewer# column; this is just the scoring-log summary."""
    return "/".join(sorted({str(c).strip().upper() for c in contributors if str(c).strip()}))


def claim_scoring_row(reviewer_name: str, log_path: str = None,
                      version: str = "v5") -> dict:
    """
    Pick the next pass for this reviewer and claim it. Priority order:

      1. Resume a partially-scored R1 whose scorer has left (stale lease)
      2. Resume a partially-scored R2 whose scorer has left (stale lease)
      3. A fresh R1 (never started)
      4. A fresh R2 (R1 complete, R2 not started)

    A pass is only handed out if the current reviewer has NOT already scored any
    trial of the OTHER pass on that run - every trial must be double-coded by two
    different people. Blinding makes it irrelevant WHO finishes a pass, so a pass
    may be split across several people; the resume always continues from the first
    unscored trial and never lets anyone overwrite an earlier scorer's trials.

    Returns dict: obs_name, visit_num, noise_cond, snr, dist_cond, run_num,
                  rev_num, log_row, scored_trials (list), is_resume (bool)
    Raises ValueError if nothing is available.
    """
    if log_path is None:
        log_path = config.SCORING_LOG_V5

    current_init = compute_initials(reviewer_name)
    now = time.time()

    with ScoringLogLock(log_path):
        wb = openpyxl.load_workbook(log_path)
        ws = wb.active
        leases = read_leases(log_path)

        # Usable rows: cols A-F present and the subject data folder exists.
        usable = []
        for row in ws.iter_rows(min_row=2, values_only=False):
            if not all(not _is_empty(row[c].value) for c in range(6)):
                continue
            try:
                obs = str(row[0].value)
                vis = int(float(str(row[1].value)))
                if os.path.isdir(config.get_data_path(obs, vis)):
                    usable.append((row, obs, vis))
            except Exception:
                pass

        if not usable:
            raise ValueError(
                "No scoreable runs found. Either all runs are claimed/complete, "
                "or no subject data folders exist yet."
            )

        prog_cache = {}
        def progress(row, obs, vis):
            lr = row[0].row
            if lr not in prog_cache:
                prog_cache[lr] = get_run_progress(
                    obs, vis, row[3].value, int(row[4].value),
                    int(row[5].value), version)
            return prog_cache[lr]

        resume_r1, resume_r2, fresh_r1, fresh_r2 = [], [], [], []
        log_dirty = False

        for (row, obs, vis) in usable:
            lr = row[0].row
            g = row[6].value if len(row) > 6 else None
            h = row[7].value if len(row) > 7 else None

            # --- R1 slot ---
            if _is_empty(g):
                fresh_r1.append((row, obs, vis))
                continue
            if is_placeholder(g):
                if lease_is_active(leases, lr, 1, now):
                    continue                      # someone scoring R1 right now
                pr = progress(row, obs, vis)
                if len(pr[1]["scored"]) >= 25:
                    # 25/25 but never finalized (scorer crashed at the end) -> heal
                    ws.cell(lr, 7).value = _combined_initials(pr[1]["contributors"]) or f"--{current_init}--"
                    leases.pop(_lease_key(lr, 1), None)
                    log_dirty = True
                    g = ws.cell(lr, 7).value      # now real initials -> fall through to R2
                elif current_init not in pr[1]["contributors"]:
                    resume_r1.append((row, obs, vis))
                    continue
                else:
                    continue                      # current person already in this R1
            # g is real initials here -> R1 complete, consider R2
            if not _is_real_initials(g):
                continue

            # --- R2 slot (only once R1 is complete) ---
            pr = progress(row, obs, vis)
            if current_init in pr[1]["contributors"]:
                continue                          # can't R2 a run you helped R1
            if _is_empty(h):
                fresh_r2.append((row, obs, vis))
            elif is_placeholder(h):
                if lease_is_active(leases, lr, 2, now):
                    continue
                if len(pr[2]["scored"]) >= 25:
                    ws.cell(lr, 8).value = _combined_initials(pr[2]["contributors"]) or f"--{current_init}--"
                    leases.pop(_lease_key(lr, 2), None)
                    log_dirty = True
                elif current_init not in pr[2]["contributors"]:
                    resume_r2.append((row, obs, vis))
            # h real initials -> R2 complete -> nothing to do

        for bucket in (resume_r1, resume_r2, fresh_r1, fresh_r2):
            random.shuffle(bucket)

        chosen, rev_num = None, None
        if resume_r1:
            chosen, rev_num = resume_r1[0], 1
        elif resume_r2:
            chosen, rev_num = resume_r2[0], 2
        elif fresh_r1:
            chosen, rev_num = fresh_r1[0], 1
        elif fresh_r2:
            chosen, rev_num = fresh_r2[0], 2

        if chosen is None:
            if log_dirty:
                wb.save(log_path)
                _write_leases(log_path, leases)
            wb.close()
            raise ValueError(
                "No more runs available to score. Either all runs are claimed, "
                "actively being scored, or you have already scored all eligible runs."
            )

        row, obs, vis = chosen
        lr = row[0].row
        col_idx = 6 + rev_num                     # G=7, H=8
        pr = progress(row, obs, vis)
        scored_trials = sorted(pr[rev_num]["scored"])
        is_resume = len(scored_trials) > 0

        # Claim: placeholder in the log cell + a fresh lease under our initials.
        ws.cell(lr, col_idx).value = f"--{current_init}--"
        leases[_lease_key(lr, rev_num)] = {"holder": current_init, "ts": time.time()}
        wb.save(log_path)
        _write_leases(log_path, leases)
        wb.close()

        return {
            "obs_name":      str(row[0].value),
            "visit_num":     int(row[1].value),
            "noise_cond":    row[2].value,
            "snr":           row[3].value,
            "dist_cond":     int(row[4].value),
            "run_num":       int(row[5].value),
            "rev_num":       rev_num,
            "log_row":       lr,
            "scored_trials": scored_trials,
            "is_resume":     is_resume,
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


def write_pass_initials(log_row: int, rev_num: int, initials_str: str,
                        log_path: str = None):
    """
    Finalize a completed pass: write the (possibly combined) contributor
    initials to the scoring log and clear the lease. Used at run completion so
    a pass split across several people records everyone who scored it, e.g.
    'AN/SB'. The per-trial Reviewer# column in the subject workbook remains the
    authoritative record of exactly who scored which trial.
    """
    if log_path is None:
        log_path = config.SCORING_LOG_V5
    col_idx = 6 + rev_num  # G=7, H=8, I=9
    with ScoringLogLock(log_path):
        wb = openpyxl.load_workbook(log_path)
        ws = wb.active
        ws.cell(row=log_row, column=col_idx).value = initials_str
        wb.save(log_path)
        leases = read_leases(log_path)
        if leases.pop(_lease_key(log_row, rev_num), None) is not None:
            _write_leases(log_path, leases)
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
