"""
R3 (Third Reviewer) Recheck Log handler.

v5 Rechecks log format:
  A: ObsName   B: visitnum   C: NoiseCond   D: dBSNR
  E: DistCond  F: RunNum     G: TrialNum    H: R3_initials

Workflow:
  1. get_flagged_trials()  - scan all subject Excels for Recheck/Cutoff/NotScored
  2. approve_for_r3()      - professor approves; writes to Rechecks log
  3. claim_r3_trial()      - R3 scorer claims one trial (writes placeholder)
  4. write_r3_initials()   - replace placeholder with real initials after scoring
  5. save_r3_trial()       - write R3 score to subject Excel
"""

import os
import math
import random
import openpyxl
import config
from file_lock import ScoringLogLock
from scoring_log import compute_initials, _is_empty, is_placeholder


R3_HEADERS = ["ObsName", "visitnum", "NoiseCond", "dBSNR",
               "DistCond", "RunNum", "TrialNum", "R3_initials"]

NOT_SCORED_VALUES = {"not scored", "not_scored", ""}


def _is_not_scored(val) -> bool:
    if val is None:
        return True
    return str(val).strip().lower() in NOT_SCORED_VALUES


def _is_flagged(recheck, cutoff, resp_score) -> bool:
    try:
        rc = float(recheck) if recheck is not None else 0
    except Exception:
        rc = 0
    try:
        cf = float(cutoff) if cutoff is not None else 0
    except Exception:
        cf = 0
    return rc == 1 or cf == 1 or _is_not_scored(resp_score)


# -- Auto third-coder rules (from the study protocol) --------------------------
# A trial needs a 3rd coder if ANY of these hold, comparing R1 vs R2:
#   1. Either coder flagged it for review (recheck).
#   2. Either coder's VRT is below VRT_MIN (implausibly early onset).
#   3. The two coders' VRTs differ by more than VRT_DISCREPANCY.
#   4. The accuracy classifications (Correct/Incorrect/No Response) don't match.
# Units are the same as stored VRT (seconds). If none fire, no R3 is needed.
VRT_MIN = 0.25
VRT_DISCREPANCY = 0.25


def _to_float(v):
    try:
        f = float(v)
        return None if (isinstance(f, float) and math.isnan(f)) else f
    except Exception:
        return None


def _norm_score(s):
    return str(s or "").strip().lower()


def needs_third_coder(recheck1, recheck2, resp_score1, resp_score2, vrt1, vrt2):
    """Return a list of reason strings (empty => no 3rd coder needed)."""
    reasons = []
    try:
        rc1 = float(recheck1) == 1
    except Exception:
        rc1 = False
    try:
        rc2 = float(recheck2) == 1
    except Exception:
        rc2 = False
    if rc1 or rc2:
        reasons.append("recheck flag")

    v1, v2 = _to_float(vrt1), _to_float(vrt2)
    if (v1 is not None and v1 < VRT_MIN) or (v2 is not None and v2 < VRT_MIN):
        reasons.append(f"VRT < {VRT_MIN}")
    if v1 is not None and v2 is not None and abs(v1 - v2) > VRT_DISCREPANCY:
        reasons.append(f"VRT differ > {VRT_DISCREPANCY}")

    if _norm_score(resp_score1) != _norm_score(resp_score2):
        reasons.append("accuracy mismatch")
    return reasons


# -- 1. Scan all subject Excels for flagged trials -----------------------------
def get_flagged_trials(log_path=None) -> list:
    """
    Read main scoring log; for every run where BOTH R1 and R2 are complete,
    open the subject Excel and collect trials that need a 3rd coder per the
    study rules (see needs_third_coder). Trials where R1 and R2 agree - same
    accuracy, VRTs within threshold, no recheck flag - are NOT returned, so the
    professor only sees genuine disagreements.

    Both reviewers must have real initials (a '--XX--' placeholder or blank does
    not count) because the rules compare R1 against R2.
    """
    if log_path is None:
        log_path = config.SCORING_LOG_V5

    flagged = []
    wb_log = openpyxl.load_workbook(log_path, read_only=True)
    ws_log = wb_log.active

    for row in ws_log.iter_rows(min_row=2, values_only=True):
        if any(_is_empty(row[c]) for c in range(6)):
            continue
        r1_init = row[6]
        r2_init = row[7]
        r1_done = bool(r1_init) and not is_placeholder(r1_init) and str(r1_init).strip() != ""
        r2_done = bool(r2_init) and not is_placeholder(r2_init) and str(r2_init).strip() != ""
        if not (r1_done and r2_done):
            continue
        r1_str = str(r1_init).strip()
        r2_str = str(r2_init).strip()

        obs_name   = row[0]
        visit_num  = int(row[1])
        noise_cond = row[2]
        snr        = row[3]
        dist_cond  = row[4]
        run_num    = row[5]

        excel_path = config.get_excel_path(obs_name, visit_num)
        if not os.path.isfile(excel_path):
            continue

        flagged += _scan_excel_for_flags(
            excel_path, obs_name, visit_num, noise_cond, snr,
            dist_cond, run_num, r1_str, r2_str, r1_done, r2_done
        )

    wb_log.close()
    return flagged


def _scan_excel_for_flags(excel_path, obs_name, visit_num, noise_cond,
                           snr, dist_cond, run_num, r1_init, r2_init,
                           r1_done=True, r2_done=True):
    results = []
    try:
        wb = openpyxl.load_workbook(excel_path, read_only=True)
        ws = wb.active
        header = [str(c.value).strip() if c.value else "" for c in ws[1]]

        def col(name):
            return header.index(name) if name in header else None

        snr_col  = col("SNR")
        dc_col   = col("DistCond")
        rn_col   = col("RunNum")
        tn_col   = col("TrialNum")
        sw_col   = col("StimWord")
        r1c  = col("Recheck1")
        c1c  = col("Cutoff1")
        rs1c = col("RespScore1")
        vt1c = col("VRT1")
        r2c  = col("Recheck2")
        c2c  = col("Cutoff2")
        rs2c = col("RespScore2")
        vt2c = col("VRT2")

        if snr_col is None or dc_col is None:
            wb.close()
            return results

        # Stream rows once. With read_only=True, random ws.cell(r,c) access is
        # O(n) per call -> O(n2) overall and hangs on real files; iter_rows is O(n).
        for vals in ws.iter_rows(min_row=2, values_only=True):
            try:
                if abs(float(vals[snr_col]) - float(snr)) > 1e-6:
                    continue
                if float(vals[dc_col]) != float(dist_cond):
                    continue
                if int(float(str(vals[rn_col]))) != int(float(str(run_num))):
                    continue
            except Exception:
                continue

            recheck1    = vals[r1c]  if r1c  is not None else None
            cutoff1     = vals[c1c]  if c1c  is not None else None
            resp_score1 = vals[rs1c] if rs1c is not None else None
            vrt1        = vals[vt1c] if vt1c is not None else None
            recheck2    = vals[r2c]  if r2c  is not None else None
            cutoff2     = vals[c2c]  if c2c  is not None else None
            resp_score2 = vals[rs2c] if rs2c is not None else None
            vrt2        = vals[vt2c] if vt2c is not None else None

            # Apply the study's auto third-coder rules (R1 vs R2).
            reasons = needs_third_coder(recheck1, recheck2,
                                        resp_score1, resp_score2, vrt1, vrt2)
            if reasons:
                results.append({
                    "obs_name":    obs_name,
                    "visit_num":   visit_num,
                    "noise_cond":  noise_cond,
                    "snr":         snr,
                    "dist_cond":   dist_cond,
                    "run_num":     run_num,
                    "trial_num":   int(float(str(vals[tn_col]))),
                    "stim_word":   vals[sw_col] if sw_col is not None else "",
                    "r1_initials": r1_init,
                    "r2_initials": r2_init,
                    "reasons":     reasons,
                    "recheck1":    int(recheck1 or 0),
                    "cutoff1":     int(cutoff1  or 0),
                    "resp_score1": str(resp_score1 or ""),
                    "vrt1":        float(vrt1) if vrt1 is not None else None,
                    "recheck2":    int(recheck2 or 0),
                    "cutoff2":     int(cutoff2  or 0),
                    "resp_score2": str(resp_score2 or ""),
                    "vrt2":        float(vrt2) if vrt2 is not None else None,
                })
        wb.close()
    except Exception:
        pass
    return results


# -- 2. Professor approves trials -> write to Rechecks log ---------------------
def approve_for_r3(trials: list, rechecks_path=None) -> int:
    """Write professor-approved trials to the v5 Rechecks log. Returns count added."""
    if rechecks_path is None:
        rechecks_path = config.RECHECKS_LOG_V5

    with ScoringLogLock(rechecks_path):
        if os.path.isfile(rechecks_path):
            wb = openpyxl.load_workbook(rechecks_path)
        else:
            wb = openpyxl.Workbook()
            ws = wb.active
            for i, h in enumerate(R3_HEADERS, 1):
                ws.cell(1, i).value = h

        ws = wb.active
        existing = set()
        for row in ws.iter_rows(min_row=2, values_only=True):
            key = (str(row[0]), str(row[3]), str(row[4]),
                   str(row[5]), str(row[6]))
            existing.add(key)

        added = 0
        for t in trials:
            key = (str(t["obs_name"]), str(t["snr"]),
                   str(t["dist_cond"]), str(t["run_num"]), str(t["trial_num"]))
            if key not in existing:
                ws.append([
                    t["obs_name"], t["visit_num"], t.get("noise_cond", ""),
                    t["snr"], t["dist_cond"], t["run_num"], t["trial_num"], ""
                ])
                existing.add(key)
                added += 1

        wb.save(rechecks_path)
        wb.close()
    return added


# -- 3. R3 scorer claims a trial -----------------------------------------------
def claim_r3_trial(reviewer_name: str, rechecks_path=None) -> dict:
    """
    Pick a random unclaimed trial from the Rechecks log.
    Writes placeholder initials and returns the trial info dict.
    Returns None (not dict) when nothing is available.
    """
    if rechecks_path is None:
        rechecks_path = config.RECHECKS_LOG_V5

    if not os.path.isfile(rechecks_path):
        return None

    current_init = compute_initials(reviewer_name)

    with ScoringLogLock(rechecks_path):
        wb = openpyxl.load_workbook(rechecks_path)
        ws = wb.active

        candidates = []
        for row in ws.iter_rows(min_row=2, values_only=False):
            r3_cell = row[7]
            if _is_empty(r3_cell.value):
                candidates.append(row)

        if not candidates:
            wb.close()
            return None

        random.shuffle(candidates)
        chosen = candidates[0]
        chosen[7].value = "--{}--".format(current_init)
        wb.save(rechecks_path)

        result = {
            "obs_name":   chosen[0].value,
            "visit_num":  int(chosen[1].value),
            "noise_cond": chosen[2].value,
            "snr":        chosen[3].value,
            "dist_cond":  chosen[4].value,
            "run_num":    chosen[5].value,
            "trial_num":  int(chosen[6].value),
            "log_row":    chosen[0].row,
            "rev_num":    3,
            "resp_score1": "",
            "resp_score2": "",
            "vrt1": None,
            "vrt2": None,
        }
        wb.close()

    # Load R1/R2 context from subject Excel (read-only, outside the lock)
    try:
        excel_path = config.get_excel_path(result["obs_name"], result["visit_num"])
        if os.path.isfile(excel_path):
            wb2 = openpyxl.load_workbook(excel_path, read_only=True)
            ws2 = wb2.active
            hdr = [str(c.value).strip() if c.value else "" for c in ws2[1]]

            def ci(name):  # 0-based index into iter_rows tuples
                return hdr.index(name) if name in hdr else None

            snr_c  = ci("SNR")
            dc_c   = ci("DistCond")
            rn_c   = ci("RunNum")
            tn_c   = ci("TrialNum")
            rs1_c  = ci("RespScore1")
            vrt1_c = ci("VRT1")
            rs2_c  = ci("RespScore2")
            vrt2_c = ci("VRT2")

            # Stream rows once (read_only random ws.cell access is O(n2) and hangs).
            for row in ws2.iter_rows(min_row=2, values_only=True):
                try:
                    if (abs(float(row[snr_c]) - float(result["snr"])) < 1e-6
                            and float(row[dc_c]) == float(result["dist_cond"])
                            and int(float(str(row[rn_c]))) == int(result["run_num"])
                            and int(float(str(row[tn_c]))) == int(result["trial_num"])):
                        v1 = row[vrt1_c] if vrt1_c is not None else None
                        v2 = row[vrt2_c] if vrt2_c is not None else None
                        result["resp_score1"] = str(row[rs1_c] or "") if rs1_c is not None else ""
                        result["resp_score2"] = str(row[rs2_c] or "") if rs2_c is not None else ""
                        result["vrt1"] = float(v1) if v1 is not None else None
                        result["vrt2"] = float(v2) if v2 is not None else None
                        break
                except Exception:
                    continue
            wb2.close()
    except Exception:
        pass

    return result


# -- 4. Write R3 initials after scoring ---------------------------------------
def write_r3_initials(reviewer_name: str, log_row: int, rechecks_path=None):
    if rechecks_path is None:
        rechecks_path = config.RECHECKS_LOG_V5

    initials = compute_initials(reviewer_name)
    with ScoringLogLock(rechecks_path):
        wb = openpyxl.load_workbook(rechecks_path)
        ws = wb.active
        ws.cell(row=log_row, column=8).value = initials
        wb.save(rechecks_path)
        wb.close()


# -- 5. Save R3 score to subject Excel ----------------------------------------
def save_r3_trial(obs_name, visit_num: int, snr, dist_cond, run_num: int,
                  trial_num: int, reviewer_initials: str,
                  vrt: float, resp_score: str, recheck: int = 0,
                  cutoff: int = 0, version: str = "v5"):
    """
    Write R3 reviewer columns (Reviewer3, VRT3, RespScore3, Recheck3, Cutoff3)
    to the subject Excel, matching on SNR + DistCond + RunNum + TrialNum.
    Mirrors appendRowToExcel.m / scoreVRT_v4b_check.m col AB-AE logic.

    Cutoff3 included for MATLAB parity: scoreVRT_v5.m writes
    data.Cutoff3(ThisTrial.Row) = cutoff for rev_num == 3.
    """
    excel_path = config.get_excel_path(obs_name, visit_num, version)

    if not os.path.isfile(excel_path):
        raise FileNotFoundError("Subject Excel not found: {}".format(excel_path))

    with ScoringLogLock(excel_path):
        wb = openpyxl.load_workbook(excel_path)
        ws = wb.active
        header = [str(c.value).strip() if c.value else "" for c in ws[1]]

        def col(name):
            return header.index(name) + 1 if name in header else None

        snr_col = col("SNR")
        dc_col  = col("DistCond")
        rn_col  = col("RunNum")
        tn_col  = col("TrialNum")

        # Ensure R3 columns exist
        r3_cols = {
            "Reviewer3":  col("Reviewer3"),
            "VRT3":       col("VRT3"),
            "RespScore3": col("RespScore3"),
            "Recheck3":   col("Recheck3"),
            "Cutoff3":    col("Cutoff3"),
        }
        max_col = ws.max_column
        for colname, cidx in list(r3_cols.items()):
            if cidx is None:
                max_col += 1
                ws.cell(1, max_col).value = colname
                r3_cols[colname] = max_col

        # Find matching row
        match_row = None
        for r_idx in range(2, ws.max_row + 1):
            try:
                row_snr = ws.cell(r_idx, snr_col).value
                row_dc  = ws.cell(r_idx, dc_col).value
                row_rn  = ws.cell(r_idx, rn_col).value
                row_tn  = ws.cell(r_idx, tn_col).value
                if (abs(float(row_snr) - float(snr)) < 1e-6
                        and float(row_dc) == float(dist_cond)
                        and int(float(str(row_rn))) == int(run_num)
                        and int(float(str(row_tn))) == int(trial_num)):
                    match_row = r_idx
                    break
            except Exception:
                continue

        if match_row is None:
            raise ValueError(
                "No matching row for SNR={} Dist={} Run={} Trial={} in {}".format(
                    snr, dist_cond, run_num, trial_num, excel_path)
            )

        vrt_val = None if (vrt is None or (isinstance(vrt, float) and math.isnan(vrt))) else vrt
        ws.cell(match_row, r3_cols["Reviewer3"]).value  = reviewer_initials
        ws.cell(match_row, r3_cols["VRT3"]).value       = vrt_val
        ws.cell(match_row, r3_cols["RespScore3"]).value = resp_score
        ws.cell(match_row, r3_cols["Recheck3"]).value   = recheck
        ws.cell(match_row, r3_cols["Cutoff3"]).value    = cutoff

        wb.save(excel_path)
        wb.close()
