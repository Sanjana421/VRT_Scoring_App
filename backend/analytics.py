"""
Analytics for the PI/Admin dashboard.

Aggregates, across every run where BOTH R1 and R2 are complete, the metrics the
study cares about (from the paper's Data Analysis section):

  - how much data is scored (progress)
  - R1 vs R2 accuracy agreement / disagreement rate
  - trials where both coders agree it was a cutoff / no response
  - R1 vs R2 VRT agreement (Pearson r)
  - how many trials need a 3rd coder (per needs_third_coder)

No third-party heavy deps beyond numpy (already required). Each subject workbook
is opened once (grouped by ObsName+Visit) for speed.
"""

import os
import math
import openpyxl
import config
from scoring_log import _is_empty, is_placeholder
from r3_log import needs_third_coder


def _num(v):
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except Exception:
        return None


def _norm(s):
    return str(s or "").strip().lower()


def _meaningful(s):
    return _norm(s) not in ("", "999")


def compute_analytics(log_path=None) -> dict:
    if log_path is None:
        log_path = config.SCORING_LOG_V5

    # -- Pass 1: from the scoring log, group both-complete runs by subject ------
    wb = openpyxl.load_workbook(log_path, read_only=True)
    ws = wb.active
    total_runs = 0
    both_runs = 0
    # (obs, visit) -> set of (snr, dist, run) keys that are both-complete
    by_subject = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if any(_is_empty(row[c]) for c in range(6)):
            continue
        total_runs += 1
        r1, r2 = row[6], row[7]
        r1d = bool(r1) and not is_placeholder(r1) and str(r1).strip() != ""
        r2d = bool(r2) and not is_placeholder(r2) and str(r2).strip() != ""
        if not (r1d and r2d):
            continue
        both_runs += 1
        obs = str(int(row[0])) if isinstance(row[0], (int, float)) else str(row[0])
        visit = int(row[1])
        key = (round(float(row[3]), 4), int(row[4]), int(row[5]))  # snr, dist, run
        by_subject.setdefault((obs, visit), set()).add(key)

    wb.close()

    # -- Pass 2: open each subject workbook once, accumulate trial metrics ------
    total = agree = disagree = both_cutoff = both_noresp = needs_r3 = 0
    v1s, v2s = [], []

    for (obs, visit), run_keys in by_subject.items():
        excel = config.get_excel_path(obs, visit)
        if not os.path.isfile(excel):
            continue
        try:
            wb2 = openpyxl.load_workbook(excel, read_only=True)
            ws2 = wb2.active
            hdr = [str(c.value).strip() if c.value else "" for c in ws2[1]]

            def ci(n):
                return hdr.index(n) if n in hdr else None

            c = {n: ci(n) for n in ("SNR", "DistCond", "RunNum", "RespScore1", "VRT1",
                                     "Recheck1", "Cutoff1", "RespScore2", "VRT2",
                                     "Recheck2", "Cutoff2")}
            if c["SNR"] is None or c["DistCond"] is None or c["RunNum"] is None:
                wb2.close()
                continue

            for vals in ws2.iter_rows(min_row=2, values_only=True):
                try:
                    key = (round(float(vals[c["SNR"]]), 4),
                           int(float(vals[c["DistCond"]])),
                           int(float(str(vals[c["RunNum"]]))))
                except Exception:
                    continue
                if key not in run_keys:
                    continue
                rs1 = vals[c["RespScore1"]] if c["RespScore1"] is not None else None
                rs2 = vals[c["RespScore2"]] if c["RespScore2"] is not None else None
                if not (_meaningful(rs1) and _meaningful(rs2)):
                    continue  # not scored by both - skip
                total += 1
                if _norm(rs1) == _norm(rs2):
                    agree += 1
                    if _norm(rs1) == "no response":
                        both_noresp += 1
                else:
                    disagree += 1
                cf1 = _num(vals[c["Cutoff1"]]) if c["Cutoff1"] is not None else None
                cf2 = _num(vals[c["Cutoff2"]]) if c["Cutoff2"] is not None else None
                if cf1 == 1 and cf2 == 1:
                    both_cutoff += 1
                vt1 = _num(vals[c["VRT1"]]) if c["VRT1"] is not None else None
                vt2 = _num(vals[c["VRT2"]]) if c["VRT2"] is not None else None
                if vt1 is not None and vt2 is not None:
                    v1s.append(vt1); v2s.append(vt2)
                rk1 = vals[c["Recheck1"]] if c["Recheck1"] is not None else None
                rk2 = vals[c["Recheck2"]] if c["Recheck2"] is not None else None
                if needs_third_coder(rk1, rk2, rs1, rs2, vt1, vt2):
                    needs_r3 += 1
            wb2.close()
        except Exception:
            continue

    # Pearson r of R1 vs R2 VRT
    vrt_corr = None
    if len(v1s) >= 2:
        try:
            import numpy as np
            r = np.corrcoef(v1s, v2s)[0, 1]
            vrt_corr = None if (isinstance(r, float) and math.isnan(r)) else round(float(r), 4)
        except Exception:
            vrt_corr = None

    return {
        "total_runs": total_runs,
        "both_complete_runs": both_runs,
        "total_planned_trials": total_runs * 25,
        "total_scored_trials": total,          # scored by BOTH reviewers
        "accuracy_agree": agree,
        "accuracy_disagree": disagree,
        "both_cutoff": both_cutoff,
        "both_no_response": both_noresp,
        "needs_third_coder": needs_r3,
        "vrt_pairs": len(v1s),
        "vrt_correlation": vrt_corr,           # Pearson r (R1 vs R2 VRT)
    }
