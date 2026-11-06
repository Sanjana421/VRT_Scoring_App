"""
VRT Scoring App - Configuration

Production (Woody / Buzz): paths point to the lab server via UNC.
Local / laptop testing:    set these env vars before starting the server:

    v5:
    DISTVRT_SCORING_LOG      full path to DistVRT_v5_DataScoringLog.xlsx
    DISTVRT_DATA_FOLDER      folder containing subject sub-folders (e.g. D:\\Data_Scoring\\v5_data)
    DISTVRT_RECHECKS_LOG     full path to v5 Rechecks xlsx

    v4:
    DISTVRT_V4_SCORING_LOG   full path to DistVRT_v4_SF_DataScoringLog.xlsx
    DISTVRT_V4_DATA_FOLDER   folder containing subject sub-folders (e.g. D:\\Data_Scoring\\v4_data)
    DISTVRT_V4_RECHECKS_LOG  full path to v4 Rechecks xlsx
"""

import os

# -- Lab server root paths -----------------------------------------------------
DATA_ROOT_V5 = r"\\bl-sphs-sphs\gustafsonlab\Projects\DistVRT_v5"
DATA_ROOT_V4 = r"\\bl-sphs-sphs\gustafsonlab\Projects\DistVRT_v4_SF"

# -- PI/Admin passcode --------------------------------------------------------
# Required to log in with the PI/Admin role. Change per deployment by setting
# the VRT_PI_PASSCODE environment variable (e.g. in start.bat); otherwise this
# default is used.
PI_PASSCODE = os.environ.get("VRT_PI_PASSCODE") or "CARES_LAB_2026"

# -- Scoring logs (env vars override server paths for local testing) -----------
SCORING_LOG_V5 = (
    os.environ.get("DISTVRT_SCORING_LOG")
    or os.path.join(DATA_ROOT_V5, "DistVRT_v5_DataScoringLog.xlsx")
)
RECHECKS_LOG_V5 = (
    os.environ.get("DISTVRT_RECHECKS_LOG")
    or os.path.join(DATA_ROOT_V5, "DistVRT_v5_Rechecks.xlsx")
)
SCORING_LOG_V4 = (
    os.environ.get("DISTVRT_V4_SCORING_LOG")
    or os.path.join(DATA_ROOT_V4, "DistVRT_v4_SF_DataScoringLog.xlsx")
)
RECHECKS_LOG_V4 = (
    os.environ.get("DISTVRT_V4_RECHECKS_LOG")
    or os.path.join(DATA_ROOT_V4, "DistVRT_v4_SF_Rechecks.xlsx")
)

# -- Data folders (env var overrides for local testing) -----------------------
DATA_FOLDER_V5 = (
    os.environ.get("DISTVRT_DATA_FOLDER")
    or os.path.join(DATA_ROOT_V5, "data")
)
DATA_FOLDER_V4 = (
    os.environ.get("DISTVRT_V4_DATA_FOLDER")
    or os.path.join(DATA_ROOT_V4, "data")
)

# -- Audio ---------------------------------------------------------------------
SRATE = 44100
RESP_WINDOW = 4.0   # seconds of waveform window shown
RESP_MARK_PROP = 0.2   # marker at 20% from left of window

# -- Waveform display ----------------------------------------------------------
WAVEFORM_POINTS = 2000  # samples sent to frontend

# -- Helpers ------------------------------------------------------------------
def _format_snr(snr) -> str:
    """Match MATLAB num2str for SNR values in filenames (e.g. -4.55, 10)."""
    try:
        f = float(snr)
        if f == int(f):
            return str(int(f))
        return f"{f:g}"
    except Exception:
        return str(snr)


def get_data_path(obs_name, visit_num: int, version: str = "v5") -> str:
    root = DATA_FOLDER_V5 if version == "v5" else DATA_FOLDER_V4
    return os.path.join(root, str(obs_name), f"Visit{visit_num}")


def get_wav_path(
    obs_name,
    visit_num: int,
    snr,
    dist_cond: int,
    run_num: int,
    trial_num: int,
    version: str = "v5",
) -> str:
    folder = get_data_path(obs_name, visit_num, version)
    snr_str = _format_snr(snr)
    return os.path.join(
        folder,
        f"{obs_name}_{snr_str}_{dist_cond}_{run_num}_{trial_num}.wav",
    )


def get_subject_data_path(
    obs_name,
    visit_num: int,
    bundle_version: str,
    version: str = "v5",
) -> str:
    folder = get_data_path(obs_name, visit_num, version)
    return os.path.join(folder, f"DistVRT_{bundle_version}_{obs_name}")


def get_excel_path(obs_name, visit_num: int, version: str = "v5") -> str:
    """Path to the scored subject workbook."""
    folder = get_data_path(obs_name, visit_num, version)
    return os.path.join(folder, f"{obs_name}_Visit{visit_num}_DistVRT.xlsx")
