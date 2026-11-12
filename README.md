# Desktop clap → Jarvis-style welcome

Python script that listens to your default microphone and runs a **double-clap** welcome flow (Spotify, Chrome windows, ElevenLabs voice, Cursor). See constants at the top of `jarvis.py` for behavior and tuning.

## Setup

From this project directory:

```bash
python -m pip install -r requirements.txt
```

## Environment variables

The script loads a **`.env` file** in the same folder as `jarvis.py` (via `python-dotenv`). You can also set variables in the shell.

### Required (ElevenLabs welcome line)

| Variable | Purpose |
| -------- | ------- |
| `ELEVENLABS_API_KEY` | API key from [ElevenLabs](https://elevenlabs.io). |
| `ELEVENLABS_VOICE_ID` | Voice ID from the ElevenLabs app (My Voices / library). |

Without these, the welcome speech is skipped (other actions may still run).

### Optional

| Variable | Purpose |
| -------- | ------- |
| `ELEVENLABS_MODEL_ID` | TTS model (default in code: `eleven_multilingual_v2`). |
| `ELEVENLABS_OUTPUT_FORMAT` | e.g. `pcm_24000` (must match playback expectations). |
| `ELEVENLABS_PCM_SAMPLE_RATE` | Override PCM sample rate if it differs from the format name. |
| `JARVIS_WELCOME_CACHE_DIR` | Custom folder for cached welcome WAV (default: `.cache/jarvis_welcome/` under the project). |
| `JARVIS_INPUT_DEVICE` | Optional mic override: **integer** index or **substring** of the device name. If unset, the script uses the Windows default; when that mic is silent, it auto-picks the loudest working input. List devices: `python -c "import sounddevice as sd; print(sd.query_devices())"`. |
| `CLAUDE_CODE_URL` | URL opened for Claude in Chrome (default: new chat). |
| `TASARADAR_URL` | URL opened for Tasaradar in Chrome (default: `https://tasaradar.com`). `BINANCE_BTC_URL` is still read as a fallback if set. |
| `CHROME_NEW_WINDOW_WAIT_S` | Seconds to wait for a new Chrome window on Windows (default `25`). |
| `CHROME_WINDOW_WIDTH` / `CHROME_WINDOW_HEIGHT` | Windowed Chrome size when not fullscreen. |

Example `.env`:

```env
ELEVENLABS_API_KEY=your_key_here
ELEVENLABS_VOICE_ID=your_voice_id_here
```

## Run

```bash
python jarvis.py
```

Allow the microphone if Windows prompts you. Stop with **Ctrl+C**.

## Voice commands

Say these any time (the word "jarvis" in the phrase is optional — commands match on
keywords, not a strict wake word). Every command now speaks a short spoken confirmation
(not just a terminal log line) — e.g. "Opening notepad, sir.", "Closed chrome, sir.",
"Picture saved, sir.", "Recording started, sir." If something fails, Jarvis says so
instead of failing silently in the terminal. Saying "jarvis" also interrupts (barges in
on) whatever Jarvis is currently saying or playing, so you don't have to wait for it to
finish before giving the next command.

| Say | What happens |
| --- | --- |
| "open notepad" / "open spotify" / "open \<anything>" | Best-effort launch: known apps first, then a Start Menu search by name (Windows). |
| "open camera" | Opens the Windows Camera app. |
| "take a picture" / "take a photo" | Captures a photo from the webcam via OpenCV (no Camera app needed) and saves it. |
| "start video recording" | Starts recording webcam video via OpenCV. |
| "stop video recording" / "stop recording" | Stops the current recording and saves the file. |
| "create a file on d drive" | Jarvis asks **"What's the file name, sir?"** — say a name, it creates the file and speaks **"File \<name> was saved, sir."** |
| "create a file named notes on d drive" | Creates the file directly, no follow-up question. |
| "run \<file>" / "run the file \<file>" / "open \<file> and run it" | Searches `FILE_SEARCH_ROOTS` for the file, opens it in VS Code, and runs it in a new console window (`.py` via the current Python interpreter, `.js` via `node`, `.bat`/`.cmd` directly — extend `RUN_FILE_INTERPRETERS` for more types). |
| "where is \<file>" / "find \<file>" / "locate \<file>" | Searches `FILE_SEARCH_ROOTS` and speaks the full path if found. |
| "recent picture" / "last photo" / "latest image" | Opens File Explorer with the most recently taken picture selected. |
| "open folder" | Opens the project folder. |
| "search youtube for \<song>" / "play \<song> on youtube" | Plays the first search result. |
| "stop the music" | Stops whatever is currently playing. |
| "close chrome" / "close this" | Closes the named app, or the active window (Windows only). |
| "close all" / "close everything" | Closes Chrome (and YouTube with it), Camera, VS Code, Spotify, and Cursor; also stops music and any in-progress recording. |
| "what is \<X>" / "who is \<X>" / "define \<X>" / "explain \<X>" | Speaks a short definition (from Wikipedia, when reachable) and opens a Google search for it in Chrome. |
| "what's the date" / "what's the time" | Speaks the current date/time. |
| "hey jarvis" / "hello jarvis" | Jarvis replies "Yes \<name> sir." |
| "who am I" / "what's my name" | Jarvis speaks your saved identity line (`USER_IDENTITY_RESPONSE` in `jarvis.py`). |
| "calculate \<a> \<op> \<b>" / "compute \<a> \<op> \<b>" | Speaks the result. Understands `+ - * / x` and the words `plus`, `minus`, `times`, `multiplied by`, `divided by`. E.g. "calculate 10 plus 10". |
| "sleep" / "go to sleep" | Jarvis says goodbye and shuts itself down (equivalent to Ctrl+C). |
| *(anything not matched above)* | Jarvis searches your study material (see below) for a relevant answer before giving up silently. |

### Study material fallback (PDFs / Word docs / images)

Any spoken command that doesn't match a known pattern — not just "what is X" questions —
is now also checked against a folder of your own documents before Jarvis gives up. Put
`.pdf`, `.docx`, `.txt`, or image (`.jpg`/`.png`/etc., via OCR) files in `study_pdfs/`
next to `jarvis.py` (or point `JARVIS_STUDY_MATERIAL_DIR` at another folder), and a
question like "top DSA questions" will be answered from whichever paragraph in those
files best matches, instead of just logging "No matching voice command". This reuses
the same indexing/cache and keyword-overlap search already used for "what is / explain"
questions, so it needs `pypdf` (PDFs), `python-docx` (.docx), and `pytesseract` + Pillow
+ a Tesseract install (images) — all already in `requirements.txt` except the Tesseract
binary itself, which you install separately.

### Camera / video env vars (optional)

| Variable | Purpose |
| -------- | ------- |
| `JARVIS_CAMERA_INDEX` | Webcam index if you have more than one (default `0`). |
| `JARVIS_CAMERA_DIR` | Folder photos are saved to (default: `Pictures\Jarvis`). |
| `JARVIS_VIDEO_DIR` | Folder recordings are saved to (default: `Videos\Jarvis`). |

Photo/video capture needs `opencv-python` (already in `requirements.txt`) and a webcam
Windows will grant to Python — allow camera access if prompted.

### Generic app-open notes

For "open \<anything>", well-known apps (notepad, calculator, paint, chrome, explorer,
task manager, settings, control panel, spotify, camera) launch directly via
`KNOWN_APP_LAUNCH` at the top of `jarvis.py`. Anything else falls back to a couple of
generic guesses, then a Windows Start Menu search by display name — so most installed
apps and Store apps work without extra setup. If a specific app never opens correctly,
add its exe name or URI to `KNOWN_APP_LAUNCH`.

## Tuning

Edit the constants at the top of `jarvis.py`:

| Constant      | Effect                                                            |
| ------------- | ----------------------------------------------------------------- |
| `SPIKE_RATIO` | Increase if you get false triggers; decrease if claps are missed. |
| `COOLDOWN_S`  | Minimum time between two logged claps.                            |
| `BLOCK_MS`    | Larger = slightly less CPU, a bit less precise timing.            |
| `MIN_RMS`     | Floor on how loud a block must be (helps in very quiet rooms).  |
| `SAMPLE_RATE` | Try `48000` if your device does not like `44100`.                 |
| `FILE_SEARCH_ROOTS` | Folders scanned (recursively) for "run \<file>" / "where is \<file>". Keep it to a few folders — large ones slow down lookups. |
| `RUN_FILE_INTERPRETERS` | Maps a file extension to the command used to run it for "run \<file>". |

## Troubleshooting

- **Wrong or quiet mic:** On startup the script probes your default Windows input. If it is silent, it **auto-selects** the loudest working mic. To force a specific device, set `JARVIS_INPUT_DEVICE` in `.env` (index or name substring from `sounddevice.query_devices()`).
- **PortAudio / audio errors:** Update audio drivers or try another `SAMPLE_RATE`.
- **No reaction to claps:** Lower `SPIKE_RATIO` slightly or speak/clap closer to the mic.
- **Spam logs:** Raise `SPIKE_RATIO` or `COOLDOWN_S`.
- **No welcome speech:** Set `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` in `.env` and restart the terminal so variables load.
"# jarvis-inpython" 
