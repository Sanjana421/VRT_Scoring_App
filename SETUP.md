# VRT Scoring App - Setup Guide

## Folder layout (on each desktop)

```
Score_Data\                 <- project root (this folder)
|-- backend\                <- Python/FastAPI code
|-- frontend\               <- React source + built app (dist\)
|-- install.bat             <- run ONCE per desktop
|-- start.bat               <- run every time to start scoring
`-- rebuild_frontend.bat    <- run after UI changes
```

## One-time setup (do this on BOTH Woody and Buzz)

### Prerequisites
- Python 3.10 or newer - https://www.python.org/downloads/
  - During install: check "Add Python to PATH"
- Node.js 18 or newer - https://nodejs.org/
  - During install: check "Add to PATH"

### Steps

1. Copy the `Score_Data` folder to both desktops (same path on each).
2. Double-click `install.bat` - wait for it to finish.
3. Double-click `start.bat`.
4. Chrome opens automatically to `http://localhost:8000`.
5. Enter your full name and role, then start scoring.

---

## Daily use

1. Double-click `start.bat`.
2. Chrome opens to `http://localhost:8000` - or type it manually.
3. Log in with your name and role.
4. Click **Start scoring** - the system auto-assigns your next run.
5. Score all 25 trials.
6. Click **Complete run** when done - your initials are written to the server log.

---

## Two students scoring at once

Both desktops can run simultaneously. The system:
- Uses `.lock` sidecar files on the server (NTFS/SMB atomic create) to prevent two
  scorers from claiming the same run.
- Writes a placeholder `--XX--` to the scoring log the moment a run is claimed,
  so the other desktop never sees it as available.
- Students never see subject ID, SNR, or condition - fully blinded.

---

## R3 (third reviewer) workflow

1. Professor logs in with role **Professor**.
2. Goes to **Recheck / cutoff** - sees all flagged trials from completed R1+R2 runs.
3. Selects which trials to send to R3 -> **Send to R3 log**.
4. A 3rd reviewer logs in with role **3rd reviewer**.
5. Goes to **R3 Scoring** - system auto-assigns one flagged trial at a time.
6. Scores it -> saved to `Reviewer3 / VRT3 / RespScore3 / Recheck3` columns in subject Excel.

---

## Server paths (network)

All data lives on the lab server:

| Item | Path |
|---|---|
| Scoring log | `\\bl-sphs-sphs\gustafsonlab\Projects\DistVRT_v5\DistVRT_v5_DataScoringLog.xlsx` |
| R3 recheck log | `\\bl-sphs-sphs\gustafsonlab\Projects\DistVRT_v5\DistVRT_v5_Rechecks.xlsx` |
| WAV files | `\\bl-sphs-sphs\gustafsonlab\Projects\DistVRT_v5\data\{Subject}\Visit{N}\` |
| Subject Excels | `\\bl-sphs-sphs\gustafsonlab\Projects\DistVRT_v5\data\{Subject}\Visit{N}\{Subject}_Visit{N}_DistVRT.xlsm` |

If the path changes, edit `backend\config.py` - only the top two lines need updating.

---

## Keyboard shortcuts (waveform scorer)

| Key | Action |
|---|---|
| Spacebar | Play / stop audio |
| R | Reset marker to default position |
| 1 | Score: Correct |
| 2 | Score: Incorrect |
| 3 | Score: No response |
| 4 | Score: Not scored |

---

## Troubleshooting

**"Server failed to start"** - Run `install.bat` again. Make sure Python is on PATH.

**"No runs available"** - All runs are claimed or fully scored. Check the scoring log on the server.

**"WAV file not found"** - The server path is not accessible. Make sure you are on Woody or Buzz and the lab server is mounted.

**Waveform shows "Loading waveform..."** - WAV file is missing for that trial. You can still score (enter No Response or Not Scored).

**Port already in use** - Another instance of the server is running. Close that window first, or restart the computer.

---

## Making changes

- **Backend logic** - edit files in `backend\`, then restart `start.bat`.
- **UI changes** - edit `frontend\src\App.jsx`, then run `rebuild_frontend.bat`, then restart `start.bat`.
- **Server paths** - edit `backend\config.py` (top 4 lines).
