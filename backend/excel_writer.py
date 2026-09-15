"""
Python equivalent of appendRowToExcel.m

Matches on ObsName + SNR + DistCond + RunNum + TrialNum.
Updates ONLY reviewer columns (Reviewer1/VRT1/RespScore1/Recheck1/Cutoff1
and equivalents for R2, R3).  Never touches columns 1-18.

Uses openpyxl so it preserves the .xlsm format.
File-locks the Excel file before read+write.
"""

import os
import math
import openpyxl
from file_lock import ScoringLogLock   # same lock mechanism
import config

# Reviewer column sets - must match MATLAB reorderReviewerBlock
REVIEWER_COLS = [
    "Reviewer1", "RespScore1", "VRT1", "Recheck1", "Cutoff1",
    "Reviewer2", "RespScore2", "VRT2", "Recheck2", "Cutoff2",
    "Reviewer3", "RespScore3", "VRT3", "Recheck3", "Cutoff3",
]

MATCH_KEYS = ["ObsName", "SNR", "DistCond", "RunNum", "TrialNum"]

STRING_COLS = {"Reviewer1", "RespScore1", "Reviewer2", "RespScore2",
               "Reviewer3", "RespScore3"}


def _is_meaningful(val) -> bool:
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


def _float_eq(a, b, tol=1e-6) -> bool:
    try:
        return abs(float(a) - float(b)) < tol
    except Exception:
        return str(a).strip() == str(b).strip()


def _row_matches(header: list, row_vals: list, match_data: dict) -> bool:
    for key in MATCH_KEYS:
        if key not in header:
            return False
        col = header.index(key)
        cell_val = row_vals[col] if col < len(row_vals) else None
        target   = match_data.get(key)
        if key in ("SNR", "DistCond"):
            if not _float_eq(cell_val, target):
                return False
        else:
            try:
                if int(float(str(cell_val))) != int(float(str(target))):
                    return False
            except Exception:
                if str(cell_val).strip() != str(target).strip():
                    return False
    return True


def save_trial(obs_name, visit_num: int, snr, dist_cond,
               run_num: int, trial_num: int,
               rev_num: int, reviewer_initials: str,
               vrt: float, resp_score: str,
               recheck: int, cutoff: int,
               version: str = "v5"):
    """
    Write one trial's scoring data to the subject's .xlsm file.
    Creates the file (with correct headers) if it doesn't exist yet.
    """
    excel_path = config.get_excel_path(obs_name, visit_num, version)

    # Build the incoming data dict
    suffix = str(rev_num)
    incoming = {
        f"Reviewer{suffix}":  reviewer_initials,
        f"RespScore{suffix}": resp_score,
        f"VRT{suffix}":       None if (vrt is None or (isinstance(vrt, float) and math.isnan(vrt))) else vrt,
        f"Recheck{suffix}":   float(recheck),
        f"Cutoff{suffix}":    float(cutoff),
    }
    match_data = {
        "ObsName":  obs_name,
        "SNR":      snr,
        "DistCond": dist_cond,
        "RunNum":   run_num,
        "TrialNum": trial_num,
    }

    with ScoringLogLock(excel_path):
        if not os.path.isfile(excel_path):
            _create_new_file(excel_path, match_data, incoming)
            return

        wb = openpyxl.load_workbook(excel_path, keep_vba=True)
        ws = wb.active

        # Read header row
        header = [str(c.value).strip() if c.value else ""
                  for c in ws[1]]

        # Ensure reviewer columns exist in header
        header, ws = _ensure_reviewer_cols(header, ws)

        # Find matching row
        match_row = None
        for r_idx in range(2, ws.max_row + 1):
            row_vals = [ws.cell(r_idx, c).value for c in range(1, len(header) + 1)]
            if _row_matches(header, row_vals, match_data):
                match_row = r_idx
                break

        if match_row is None:
            # Append new row (shouldn't normally happen - data file pre-exists)
            _append_row(ws, header, match_data, incoming)
        else:
            _update_row(ws, header, match_row, incoming)

        wb.save(excel_path)
        wb.close()


def _ensure_reviewer_cols(header: list, ws) -> tuple:
    """Add any missing reviewer columns to the worksheet header."""
    changed = False
    for col_name in REVIEWER_COLS:
        if col_name not in header:
            header.append(col_name)
            col_num = len(header)
            ws.cell(1, col_num).value = col_name
            changed = True
    return header, ws


def _update_row(ws, header: list, row_idx: int, incoming: dict):
    for col_name, value in incoming.items():
        if col_name not in header:
            continue
        if not _is_meaningful(value):
            continue
        col_num = header.index(col_name) + 1
        ws.cell(row_idx, col_num).value = value


def _append_row(ws, header: list, match_data: dict, incoming: dict):
    new_row_idx = ws.max_row + 1
    for col_name, value in {**match_data, **incoming}.items():
        if col_name in header:
            col_num = header.index(col_name) + 1
            ws.cell(new_row_idx, col_num).value = value


def _create_new_file(excel_path: str, match_data: dict, incoming: dict):
    """
    Create a brand-new subject workbook with the standard header.
    MATLAB parity: appendRowToExcel.m does the same when the file is missing
    (writetable on an empty table, which also produces no VBA). Excel may warn
    about the .xlsm extension on first open - logged so it is never a surprise.
    """
    import logging
    logging.getLogger("vrt").warning(
        "Subject workbook did not exist; creating a new one at %s "
        "(no VBA project - Excel may warn about the .xlsm extension).",
        excel_path,
    )
    os.makedirs(os.path.dirname(excel_path), exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active

    all_headers = [
        "ObsName", "TimeStamp", "VisitNum", "WordLevel", "NoiseCond", "SNR",
        "DistCond", "DistLevel", "DistTime", "RunNum", "TrialNum", "StimTalker",
        "ListNum", "StimWord", "DistPresent", "DistItem", "TargetSide", "Response",
    ] + REVIEWER_COLS

    for i, h in enumerate(all_headers, 1):
        ws.cell(1, i).value = h

    row_data = {**match_data, **incoming}
    for i, h in enumerate(all_headers, 1):
        if h in row_data:
            ws.cell(2, i).value = row_data[h]

    wb.save(excel_path)
    wb.close()
