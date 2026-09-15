"""
VRT Scoring App - FastAPI backend
Runs locally on each lab desktop (Woody / Buzz) at http://localhost:8000
Serves React frontend from ../frontend/dist/
"""

from __future__ import annotations

import os
import io
import json
import logging
import traceback
from typing import Optional

import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from config import (
    SCORING_LOG_V5, RECHECKS_LOG_V5,
    SRATE, RESP_WINDOW, RESP_MARK_PROP, WAVEFORM_POINTS,
    get_wav_path,
)
from scoring_log import (
    claim_scoring_row, write_reviewer_initials, get_completion_status,
    release_scoring_row, compute_initials,
)
from subject_data import get_all_trials, read_trial_info
from audio_handler import get_waveform_data, get_wav_filepath, wav_exists
from excel_writer import save_trial
from r3_log import (
    get_flagged_trials, approve_for_r3,
    claim_r3_trial, write_r3_initials,
    save_r3_trial,
)

# -- Logging ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vrt")

# -- App -----------------------------------------------------------------------
app = FastAPI(
    title="VRT Scoring API",
    description="Backend for the VRT (verbal response time) scoring system",
    version="5.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- In-memory session store (single-user per process) ------------------------
# Each desktop runs its own process, so this is safe.
SESSION: dict = {}

# -- Pydantic models -----------------------------------------------------------

class SessionStartRequest(BaseModel):
    reviewer_name: str          # full name, e.g. "Jane Smith"
    role: str = "scorer"        # "scorer" | "professor" | "r3"
    version: str = "v5"

class SessionStartResponse(BaseModel):
    ok: bool
    reviewer_name: str
    initials: str
    role: str
    message: str = ""

class AssignRunResponse(BaseModel):
    ok: bool
    obs_name: str = ""
    visit_num: int = 0
    snr: float = 0.0
    dist_cond: int = 0
    run_num: int = 0
    rev_num: int = 0
    log_row: int = 0
    total_trials: int = 0
    message: str = ""

class TrialResponse(BaseModel):
    ok: bool
    trial_num: int = 0
    stim_word: str = ""
    stim_talker: str = ""
    wav_exists: bool = False
    waveform: list = []
    window_start: float = 0.0
    window_end: float = 0.0
    duration: float = 0.0
    marker_time: float = 0.0
    message: str = ""

class SaveTrialRequest(BaseModel):
    trial_num: int
    vrt: Optional[float] = None  # seconds; None for No Response (stored as NaN/blank)
    resp_score: str             # "Not Scored" | "Correct" | "Incorrect" | "No Response"
    recheck: int = 0            # 0 or 1
    cutoff: int = 0             # 0 or 1

class SaveTrialResponse(BaseModel):
    ok: bool
    message: str = ""

class CompleteRunRequest(BaseModel):
    pass                        # no body needed; session carries all context

class CompleteRunResponse(BaseModel):
    ok: bool
    message: str = ""

class FlaggedTrial(BaseModel):
    # Subject IDs arrive as numbers (e.g. 2020) from the scoring log; allow
    # numeric values to coerce into the string fields instead of 422-erroring.
    model_config = ConfigDict(coerce_numbers_to_str=True)
    obs_name: str
    visit_num: int
    noise_cond: str = ""          # written to the Rechecks log (col C)
    snr: float
    dist_cond: int
    run_num: int
    trial_num: int
    reviewer1: str = ""
    reviewer2: str = ""
    resp_score1: str = ""
    resp_score2: str = ""
    recheck1: int = 0
    recheck2: int = 0
    cutoff1: int = 0
    cutoff2: int = 0

class ApproveR3Request(BaseModel):
    trials: list[FlaggedTrial]

class ApproveR3Response(BaseModel):
    ok: bool
    added: int = 0
    message: str = ""

class R3TrialResponse(BaseModel):
    ok: bool
    obs_name: str = ""
    visit_num: int = 0
    snr: float = 0.0
    dist_cond: int = 0
    run_num: int = 0
    trial_num: int = 0
    log_row: int = 0
    stim_word: str = ""
    stim_talker: str = ""
    wav_exists: bool = False
    waveform: list = []
    window_start: float = 0.0
    window_end: float = 0.0
    duration: float = 0.0
    marker_time: float = 0.0
    # context - what R1/R2 scored (shown to R3)
    resp_score1: str = ""
    resp_score2: str = ""
    vrt1: float = 0.0
    vrt2: float = 0.0
    message: str = ""

class SaveR3Request(BaseModel):
    vrt: Optional[float] = None
    resp_score: str             # "Not Scored" | "Correct" | "Incorrect" | "No Response"
    recheck: int = 0
    cutoff: int = 0             # MATLAB scoreVRT_v5.m writes Cutoff3 for rev_num==3

class StatusResponse(BaseModel):
    ok: bool
    total_runs: int = 0         # runs
    r1_complete: int = 0        # runs with real R1 initials
    r2_complete: int = 0        # runs with real R2 initials
    both_complete: int = 0      # runs with both (was previously a SUBJECT count)
    subjects_complete: int = 0  # subjects fully scored
    runs_claimed: int = 0       # claimed but unfinished ('--XX--')
    r3_pending: int = 0
    r3_complete: int = 0

# -----------------------------------------------------------------------------
# Helper
# -----------------------------------------------------------------------------

def _require_session():
    if not SESSION.get("reviewer_name"):
        raise HTTPException(status_code=401, detail="No active session. POST /api/session/start first.")

def _require_run():
    _require_session()
    if not SESSION.get("obs_name"):
        raise HTTPException(status_code=400, detail="No run assigned. POST /api/session/assign-run first.")

def _initials_from_name(full_name: str) -> str:
    """Single source of truth - delegates to scoring_log.compute_initials so the
    session layer and the scoring-log writer can never drift on reviewer identity."""
    return compute_initials(full_name)

def _load_waveform(obs_name, visit_num, snr, dist_cond, run_num, trial_num, version="v5"):
    """Return waveform dict or empty-safe fallback."""
    try:
        return get_waveform_data(
            obs_name, visit_num, snr, dist_cond, run_num, trial_num, version
        )
    except Exception as exc:
        logger.warning("Waveform load failed for trial %s: %s", trial_num, exc)
        return {
            "samples": [],
            "window_start": 0.0,
            "window_end": RESP_WINDOW,
            "duration": RESP_WINDOW,
            "marker_time": RESP_WINDOW * RESP_MARK_PROP,
        }

# -----------------------------------------------------------------------------
# Routes - session
# -----------------------------------------------------------------------------

@app.post("/api/session/start", response_model=SessionStartResponse)
def session_start(req: SessionStartRequest):
    """Register reviewer and role for this desktop session."""
    if not req.reviewer_name.strip():
        raise HTTPException(status_code=422, detail="reviewer_name is required")
    if req.role not in ("scorer", "professor", "r3"):
        raise HTTPException(status_code=422, detail="role must be 'scorer', 'professor', or 'r3'")

    SESSION.clear()
    SESSION["reviewer_name"] = req.reviewer_name.strip()
    SESSION["initials"]      = _initials_from_name(req.reviewer_name)
    SESSION["role"]          = req.role
    SESSION["version"]       = req.version
    # run state - cleared on each new assignment
    SESSION["obs_name"]  = None
    SESSION["visit_num"] = None
    SESSION["snr"]       = None
    SESSION["dist_cond"] = None
    SESSION["run_num"]   = None
    SESSION["rev_num"]   = None
    SESSION["log_row"]   = None
    SESSION["trials"]    = []     # list of trial dicts from get_all_trials
    SESSION["current_trial_idx"] = 0

    logger.info("Session started: %s (%s) role=%s",
                SESSION["reviewer_name"], SESSION["initials"], req.role)

    return SessionStartResponse(
        ok=True,
        reviewer_name=SESSION["reviewer_name"],
        initials=SESSION["initials"],
        role=req.role,
        message=f"Welcome, {SESSION['reviewer_name']}!",
    )

# -----------------------------------------------------------------------------
# Routes - run assignment
# -----------------------------------------------------------------------------

@app.post("/api/session/assign-run", response_model=AssignRunResponse)
def assign_run():
    """
    Claim the next available run from the scoring log (R1 or R2, never same as R1).
    Writes placeholder initials immediately to prevent concurrent claim by the other desktop.
    """
    _require_session()

    log_path = SCORING_LOG_V5
    reviewer  = SESSION["reviewer_name"]

    try:
        result = claim_scoring_row(reviewer, log_path)
    except ValueError as exc:
        # Expected end-of-queue condition, not a server fault.
        logger.info("No run available for %s: %s", reviewer, exc)
        return AssignRunResponse(ok=False, message=str(exc))
    except Exception as exc:
        logger.error("claim_scoring_row failed: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to claim run: {exc}")

    if not result:
        return AssignRunResponse(
            ok=False,
            message="No runs available. All runs are either fully scored or already claimed.",
        )

    # result keys: obs_name, visit_num, snr, dist_cond, run_num, rev_num, log_row
    SESSION["obs_name"]  = result["obs_name"]
    SESSION["visit_num"] = result["visit_num"]
    SESSION["snr"]       = result["snr"]
    SESSION["dist_cond"] = result["dist_cond"]
    SESSION["run_num"]   = result["run_num"]
    SESSION["rev_num"]   = result["rev_num"]
    SESSION["log_row"]   = result["log_row"]
    SESSION["current_trial_idx"] = 0

    # Load the 25 trials for this run
    trials = []
    try:
        trials = get_all_trials(
            result["obs_name"], result["visit_num"],
            bundle_version="v5",            # adjust if needed
            snr=result["snr"],
            dist_cond=result["dist_cond"],
            run_num=result["run_num"],
            version=SESSION["version"],
        )
    except FileNotFoundError as exc:
        # Bundle missing entirely - fall back to bare trial numbers so the run
        # is still scoreable (no stim word/talker shown).
        logger.warning("Subject data file missing, using bare trial numbers: %s", exc)
        trials = [{"trial_num": i, "stim_word": "", "stim_talker": ""} for i in range(1, 26)]
    except Exception as exc:
        logger.warning("Could not load trial list: %s", exc)

    if not trials:
        # Bundle exists but has no rows for this SNR/DistCond/RunNum - almost
        # always a metadata mismatch between the scoring log and the recorded
        # data (e.g. log says SNR -11.02, data says -11.2). Release the claim so
        # the row isn't stranded, and report plainly instead of 404-ing.
        release_scoring_row(result["log_row"], result["rev_num"], log_path)
        for key in ("obs_name", "visit_num", "snr", "dist_cond",
                    "run_num", "rev_num", "log_row"):
            SESSION[key] = None
        SESSION["trials"] = []
        msg = (
            f"Run metadata does not match any recorded trials "
            f"(SNR={result['snr']}, DistCond={result['dist_cond']}, "
            f"RunNum={result['run_num']}). The scoring log and the subject data "
            f"file disagree - this run needs a metadata fix before it can be scored. "
            f"The claim has been released; try assigning again."
        )
        logger.error("Unscoreable run released (log row %s): %s", result["log_row"], msg)
        return AssignRunResponse(ok=False, message=msg)

    SESSION["trials"] = trials

    logger.info(
        "Run assigned: %s visit%s SNR=%s Dist=%s Run=%s rev_num=%s",
        result["obs_name"], result["visit_num"],
        result["snr"], result["dist_cond"], result["run_num"], result["rev_num"],
    )

    return AssignRunResponse(
        ok=True,
        obs_name=result["obs_name"],
        visit_num=result["visit_num"],
        snr=result["snr"],
        dist_cond=result["dist_cond"],
        run_num=result["run_num"],
        rev_num=result["rev_num"],
        log_row=result["log_row"],
        total_trials=len(SESSION["trials"]),
        message=f"Reviewer {result['rev_num']} - run assigned",
    )

# -----------------------------------------------------------------------------
# Routes - trial display
# -----------------------------------------------------------------------------

@app.get("/api/trial/{trial_index}", response_model=TrialResponse)
def get_trial(trial_index: int):
    """
    Return waveform + metadata for trial at 0-based index within the assigned run.
    Blinded: subject ID, SNR, condition are NOT returned.
    """
    _require_run()

    trials = SESSION["trials"]
    if trial_index < 0 or trial_index >= len(trials):
        raise HTTPException(status_code=404, detail=f"Trial index {trial_index} out of range (0-{len(trials)-1})")

    SESSION["current_trial_idx"] = trial_index
    t = trials[trial_index]
    # get_all_trials() returns lowercase keys: trial_num, stim_word, stim_talker
    trial_num = t.get("trial_num", trial_index + 1)

    obs   = SESSION["obs_name"]
    vis   = SESSION["visit_num"]
    snr   = SESSION["snr"]
    dist  = SESSION["dist_cond"]
    run   = SESSION["run_num"]
    ver   = SESSION["version"]

    # Stim word / talker (allowed - needed for display)
    stim_word   = t.get("stim_word", "")
    stim_talker = t.get("stim_talker", "")
    if not stim_word:
        try:
            info = read_trial_info(obs, vis, "v5", snr, dist, run, trial_num, ver)
            stim_word   = info.get("stim_word", "")
            stim_talker = info.get("stim_talker", "")
        except Exception:
            pass

    # Waveform
    wav_ok = wav_exists(obs, vis, snr, dist, run, trial_num, ver)
    wf = _load_waveform(obs, vis, snr, dist, run, trial_num, ver)

    return TrialResponse(
        ok=True,
        trial_num=trial_num,
        stim_word=stim_word,
        stim_talker=stim_talker,
        wav_exists=wav_ok,
        waveform=wf["samples"],
        window_start=wf["window_start"],
        window_end=wf["window_end"],
        duration=wf["duration"],
        marker_time=wf["marker_time"],
        message="",
    )

# -----------------------------------------------------------------------------
# Routes - audio streaming (for playback)
# -----------------------------------------------------------------------------

@app.get("/api/audio/{obs_name}/{visit_num}/{snr}/{dist_cond}/{run_num}/{trial_num}")
def stream_audio(
    obs_name: str,
    visit_num: int,
    snr: float,
    dist_cond: int,
    run_num: int,
    trial_num: int,
    version: str = Query("v5"),
):
    """
    Stream the raw WAV file for the given trial.
    Frontend uses Web Audio API to play it.
    """
    _require_session()

    wav_path = get_wav_filepath(obs_name, visit_num, snr, dist_cond, run_num, trial_num, version)
    if not wav_path or not os.path.isfile(wav_path):
        raise HTTPException(status_code=404, detail=f"WAV file not found: {wav_path}")

    def iterfile():
        with open(wav_path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    return StreamingResponse(iterfile(), media_type="audio/wav")

# -----------------------------------------------------------------------------
# Routes - saving
# -----------------------------------------------------------------------------

@app.post("/api/trial/save", response_model=SaveTrialResponse)
def save_trial_route(req: SaveTrialRequest):
    """Save a single scored trial to the subject Excel file (per-trial, not batched)."""
    _require_run()

    obs      = SESSION["obs_name"]
    vis      = SESSION["visit_num"]
    snr      = SESSION["snr"]
    dist     = SESSION["dist_cond"]
    run      = SESSION["run_num"]
    rev_num  = SESSION["rev_num"]
    initials = SESSION["initials"]
    ver      = SESSION["version"]

    # Validate resp_score
    valid_scores = {"Not Scored", "Correct", "Incorrect", "No Response"}
    if req.resp_score not in valid_scores:
        raise HTTPException(status_code=422, detail=f"resp_score must be one of {valid_scores}")

    # NaN VRT for No Response
    vrt = req.vrt if req.vrt is not None else float("nan")

    try:
        save_trial(
            obs_name=obs,
            visit_num=vis,
            snr=snr,
            dist_cond=dist,
            run_num=run,
            trial_num=req.trial_num,
            rev_num=rev_num,
            reviewer_initials=initials,
            vrt=vrt,
            resp_score=req.resp_score,
            recheck=req.recheck,
            cutoff=req.cutoff,
            version=ver,
        )
    except Exception as exc:
        logger.error("save_trial failed for trial %s: %s\n%s", req.trial_num, exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to save trial: {exc}")

    logger.info("Trial saved: obs=%s trial=%s score=%s vrt=%s rev=%s",
                obs, req.trial_num, req.resp_score, vrt, rev_num)

    return SaveTrialResponse(ok=True, message="Trial saved.")

@app.post("/api/run/complete", response_model=CompleteRunResponse)
def complete_run():
    """
    All 25 trials scored. Replace placeholder initials with real initials
    in the scoring log, then clear run state.
    """
    _require_run()

    reviewer = SESSION["reviewer_name"]
    log_row  = SESSION["log_row"]
    rev_num  = SESSION["rev_num"]
    log_path = SCORING_LOG_V5

    try:
        write_reviewer_initials(reviewer, log_row, rev_num, log_path)
    except Exception as exc:
        logger.error("write_reviewer_initials failed: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to write initials: {exc}")

    logger.info("Run complete: %s rev%s row=%s", SESSION["obs_name"], rev_num, log_row)

    # Clear run state (keep session alive for next run)
    for key in ("obs_name", "visit_num", "snr", "dist_cond", "run_num",
                "rev_num", "log_row", "trials"):
        SESSION[key] = None
    SESSION["trials"] = []
    SESSION["current_trial_idx"] = 0

    return CompleteRunResponse(ok=True, message="Run complete. Initials written to scoring log.")

# -----------------------------------------------------------------------------
# Routes - professor / R3 workflow
# -----------------------------------------------------------------------------

@app.get("/api/professor/flagged")
def professor_flagged():
    """
    Return all trials flagged for R3 review (Recheck=1, Cutoff=1, or Not Scored)
    across all subjects that have both R1+R2 complete.
    """
    _require_session()
    if SESSION.get("role") not in ("professor", "r3"):
        raise HTTPException(status_code=403, detail="Only professor or r3 role may access this endpoint.")

    log_path = SCORING_LOG_V5
    try:
        flagged = get_flagged_trials(log_path)
    except Exception as exc:
        logger.error("get_flagged_trials failed: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to load flagged trials: {exc}")

    return JSONResponse(content={"ok": True, "flagged": flagged, "count": len(flagged)})

@app.post("/api/professor/approve-r3", response_model=ApproveR3Response)
def professor_approve_r3(req: ApproveR3Request):
    """
    Professor selects which flagged trials go to R3 review.
    Writes approved trials to the Rechecks log.
    """
    _require_session()
    if SESSION.get("role") != "professor":
        raise HTTPException(status_code=403, detail="Only professor role may approve R3 trials.")

    rechecks_path = RECHECKS_LOG_V5
    trials_dicts  = [t.dict() for t in req.trials]

    try:
        added = approve_for_r3(trials_dicts, rechecks_path)
    except Exception as exc:
        logger.error("approve_for_r3 failed: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to approve R3 trials: {exc}")

    logger.info("Professor approved %d trials for R3", added)
    return ApproveR3Response(ok=True, added=added, message=f"{added} trial(s) added to Rechecks log.")

@app.get("/api/r3/next-trial", response_model=R3TrialResponse)
def r3_next_trial():
    """
    Claim a random unclaimed trial from the Rechecks log for R3 review.
    Returns full waveform + R1/R2 context scores for comparison.
    """
    _require_session()
    if SESSION.get("role") != "r3":
        raise HTTPException(status_code=403, detail="Only r3 role may claim R3 trials.")

    rechecks_path = RECHECKS_LOG_V5
    reviewer      = SESSION["reviewer_name"]

    try:
        result = claim_r3_trial(reviewer, rechecks_path)
    except Exception as exc:
        logger.error("claim_r3_trial failed: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to claim R3 trial: {exc}")

    if not result:
        return R3TrialResponse(ok=False, message="No R3 trials available.")

    # Store in session for save step
    SESSION["r3_current"] = result

    obs      = result["obs_name"]
    vis      = result["visit_num"]
    snr      = result["snr"]
    dist     = result["dist_cond"]
    run      = result["run_num"]
    trial    = result["trial_num"]
    ver      = SESSION["version"]

    # Stim word / talker
    stim_word, stim_talker = "", ""
    try:
        info = read_trial_info(obs, vis, "v5", snr, dist, run, trial, ver)
        stim_word   = info.get("stim_word", "")
        stim_talker = info.get("stim_talker", "")
    except Exception:
        pass

    wav_ok = wav_exists(obs, vis, snr, dist, run, trial, ver)
    wf = _load_waveform(obs, vis, snr, dist, run, trial, ver)

    return R3TrialResponse(
        ok=True,
        obs_name=obs,
        visit_num=vis,
        snr=snr,
        dist_cond=dist,
        run_num=run,
        trial_num=trial,
        log_row=result["log_row"],
        stim_word=stim_word,
        stim_talker=stim_talker,
        wav_exists=wav_ok,
        waveform=wf["samples"],
        window_start=wf["window_start"],
        window_end=wf["window_end"],
        duration=wf["duration"],
        marker_time=wf["marker_time"],
        resp_score1=result.get("resp_score1", ""),
        resp_score2=result.get("resp_score2", ""),
        vrt1=result.get("vrt1", 0.0) or 0.0,
        vrt2=result.get("vrt2", 0.0) or 0.0,
        message="R3 trial loaded",
    )

@app.post("/api/r3/save", response_model=SaveTrialResponse)
def r3_save(req: SaveR3Request):
    """Save R3 score to the subject Excel and write initials to Rechecks log."""
    _require_session()
    if SESSION.get("role") != "r3":
        raise HTTPException(status_code=403, detail="Only r3 role may save R3 scores.")

    r3 = SESSION.get("r3_current")
    if not r3:
        raise HTTPException(status_code=400, detail="No R3 trial in progress. GET /api/r3/next-trial first.")

    valid_scores = {"Not Scored", "Correct", "Incorrect", "No Response"}
    if req.resp_score not in valid_scores:
        raise HTTPException(status_code=422, detail=f"resp_score must be one of {valid_scores}")

    vrt      = req.vrt if req.vrt is not None else float("nan")
    initials = SESSION["initials"]
    reviewer = SESSION["reviewer_name"]
    ver      = SESSION["version"]

    try:
        # Save score to subject Excel (columns: Reviewer3, VRT3, RespScore3, Recheck3)
        save_r3_trial(
            obs_name=r3["obs_name"],
            visit_num=r3["visit_num"],
            snr=r3["snr"],
            dist_cond=r3["dist_cond"],
            run_num=r3["run_num"],
            trial_num=r3["trial_num"],
            reviewer_initials=initials,
            vrt=vrt,
            resp_score=req.resp_score,
            recheck=req.recheck,
            cutoff=req.cutoff,
            version=ver,
        )
        # Write real initials to Rechecks log (replace placeholder)
        write_r3_initials(reviewer, r3["log_row"], RECHECKS_LOG_V5)
    except Exception as exc:
        logger.error("r3 save failed: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to save R3 trial: {exc}")

    logger.info("R3 trial saved: obs=%s trial=%s score=%s", r3["obs_name"], r3["trial_num"], req.resp_score)
    SESSION.pop("r3_current", None)

    return SaveTrialResponse(ok=True, message="R3 score saved.")

# -----------------------------------------------------------------------------
# Routes - status
# -----------------------------------------------------------------------------

@app.get("/api/analytics")
def get_analytics():
    """PI/Admin analytics - aggregate R1/R2 agreement metrics across all
    both-complete runs. Heavier than /api/status (scans subject workbooks)."""
    _require_session()
    if SESSION.get("role") != "professor":
        raise HTTPException(status_code=403, detail="Only PI/Admin may view analytics.")
    try:
        from analytics import compute_analytics
        return JSONResponse(content={"ok": True, **compute_analytics(SCORING_LOG_V5)})
    except Exception as exc:
        logger.error("compute_analytics failed: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to compute analytics: {exc}")


@app.get("/api/status", response_model=StatusResponse)
def get_status():
    """Overall completion status - how many runs have R1, R2, both, and R3 pending/done."""
    _require_session()

    log_path = SCORING_LOG_V5
    rechecks_path = RECHECKS_LOG_V5

    try:
        status = get_completion_status(log_path)
    except Exception as exc:
        logger.error("get_completion_status failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Failed to load status: {exc}")

    # Count R3
    r3_pending = 0
    r3_complete = 0
    try:
        import openpyxl
        if os.path.isfile(rechecks_path):
            wb = openpyxl.load_workbook(rechecks_path, read_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(min_row=2, values_only=True))
            wb.close()
            for row in rows:
                r3_init = row[7] if len(row) > 7 else None  # col H
                if not r3_init or str(r3_init).strip() in ("", "--XX--"):
                    r3_pending += 1
                else:
                    r3_complete += 1
    except Exception:
        pass

    return StatusResponse(
        ok=True,
        total_runs=status.get("total_runs", 0),
        r1_complete=status.get("r1_complete", 0),
        r2_complete=status.get("r2_complete", 0),
        both_complete=status.get("both_complete", 0),
        subjects_complete=status.get("subjects_complete", 0),
        runs_claimed=status.get("runs_claimed", 0),
        r3_pending=r3_pending,
        r3_complete=r3_complete,
    )

# -----------------------------------------------------------------------------
# Routes - session info (lightweight)
# -----------------------------------------------------------------------------

@app.get("/api/session/info")
def session_info():
    """Return current session state (non-sensitive) for UI state restoration."""
    if not SESSION.get("reviewer_name"):
        return JSONResponse(content={"ok": False, "message": "No active session."})
    return JSONResponse(content={
        "ok": True,
        "reviewer_name": SESSION.get("reviewer_name"),
        "initials": SESSION.get("initials"),
        "role": SESSION.get("role"),
        "has_run": SESSION.get("obs_name") is not None,
        "rev_num": SESSION.get("rev_num"),
        "total_trials": len(SESSION.get("trials") or []),
        "current_trial_idx": SESSION.get("current_trial_idx", 0),
    })

@app.delete("/api/session")
def clear_session():
    """Clear session (logout). Run placeholder is NOT removed - use only after a run is complete."""
    SESSION.clear()
    return JSONResponse(content={"ok": True, "message": "Session cleared."})

# -----------------------------------------------------------------------------
# Health check
# -----------------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"ok": True, "version": "5.0.0"}

# -----------------------------------------------------------------------------
# Serve React frontend
# -----------------------------------------------------------------------------

FRONTEND_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")

if os.path.isdir(FRONTEND_DIST):
    # Serve static assets (JS, CSS, fonts)
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        """Catch-all: serve index.html for any non-API route (SPA routing)."""
        # Prevent /api routes from falling through here (should never happen with correct order)
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)

        # Serve real static files at the dist root (favicon.svg, icons.svg);
        # otherwise they fall through and the browser gets HTML for an image.
        if full_path and "/" not in full_path and ".." not in full_path:
            candidate = os.path.join(FRONTEND_DIST, full_path)
            if os.path.isfile(candidate):
                return FileResponse(candidate)

        index = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="Frontend not built. Run `npm run build` in the frontend folder.")

# -----------------------------------------------------------------------------
# Entry point (python main.py)
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info",
    )
