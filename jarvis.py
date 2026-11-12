#!/usr/bin/env python3
"""
Jarvis: double-clap listener + voice assistant (Windows).

Voice modes:
  "hindi me baat karte hai" / "hindi mode"  -> Jarvis replies in Hindi
  "english" / "english mode"                -> Jarvis replies in English
  "stop"                                    -> stops music, speech, recording, timers
                                               and closes all background apps
                                               (CLOSE_ALL_PROCESSES). Jarvis keeps running.
  "sleep"                                   -> shuts Jarvis itself down

Run:
  python -m pip install -r requirements.txt
  python jarvis.py

Extra pip installs for the new features:
  python -m pip install gTTS soundfile pywin32
"""

from __future__ import annotations

import hashlib
import json
import logging
import operator
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import wave
import webbrowser
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import numpy as np
import sounddevice as sd

# --- tuning knobs -----------------------------------------------------------
SAMPLE_RATE = 44100
BLOCK_MS = 40
CHANNELS = 1

SPIKE_RATIO = 7.0
COOLDOWN_S = 0.45
MIN_DOUBLE_GAP_S = 0.05
MAX_DOUBLE_GAP_S = 0.35
RETRIGGER_RATIO = 0.55
NOISE_FLOOR_ALPHA = 0.992
MIN_RMS = 0.012
QUIET_GATE_MULT = 2.2  # update noise floor only when below floor * this
# Startup mic probe: if default input RMS stays below this, scan for a louder device.
INPUT_PROBE_S = 0.5
INPUT_SILENT_RMS = 0.001

# Spotify URI / URL, or a local audio file path (mp3/wav/flac/ogg).
SONG_URI = "C:\\letscode\\2025code\\jarvis-main\\mysong.mp3.mp3"

# If True, play SONG_URI once immediately when the script starts.
PLAY_SONG_ON_STARTUP = False

# --- startup UI (particle sphere HTML) ---------------------------------
JARVIS_UI_ENABLED = True
JARVIS_UI_HTML_PATH = str(Path(__file__).resolve().parent / "jarvis_ui.html")

# --- voice commands -----------------------------------------------------
VOICE_COMMANDS_ENABLED = True
VOICE_COMMAND_PHRASE_TIME_LIMIT = 4
VOICE_COMMAND_FOLDER_PATH = str(Path(__file__).resolve().parent)
VOICE_COMMAND_YOUTUBE_URL = "https://www.youtube.com"
JARVIS_USER_NAME = "Dhananjay"
WAKE_WORD_PHRASES = ["hello jarvis", "hey jarvis", " jarvis"]
WAKE_WORD_RESPONSE = f"Yes {JARVIS_USER_NAME} sir."

# Speech-recognition language used while listening.
#   "en-IN" understands Hinglish typed in English letters ("hindi me baat karte hai").
#   Change HINDI_LISTEN_LANG to "hi-IN" if you want to speak pure Hindi in Hindi mode.
ENGLISH_LISTEN_LANG = "en-IN"
HINDI_LISTEN_LANG = "en-IN"

WAKE_UP_MUSIC_PHRASES = ["wake up buddy", "wake up", "weycup buddy", "wake buddy"]

USER_IDENTITY_RESPONSE = (
    "Sir, you are Dhananjay Rajesh Sharma, a final-year B.Tech Computer Science "
    "student passionate about software development. You have completed multiple "
    "projects and recently deployed your Notes App by Danny. Currently, you're "
    "learning JavaScript and React dot js while building modern and "
    "user-friendly web applications."
)

SLEEP_RESPONSE = "Going to sleep, sir. Goodbye."

# "close <app>" -> process image name (Windows only).
KNOWN_APP_PROCESSES = {
    "chrome": "chrome.exe",
    "browser": "chrome.exe",
    "youtube": "chrome.exe",
    "notepad": "notepad.exe",
    "spotify": "Spotify.exe",
    "cursor": "Cursor.exe",
    "vs code": "Code.exe",
    "vscode": "Code.exe",
    "code": "Code.exe",
    "camera": "WindowsCamera.exe",
}

# "stop" / "close all" / "close everything" close these (missing ones are skipped).
CLOSE_ALL_PROCESSES = ["chrome.exe", "WindowsCamera.exe", "Code.exe", "Spotify.exe", "Cursor.exe"]

CREATE_FILE_DEFAULT_DRIVE = "D:\\"
CREATE_FILE_DEFAULT_EXTENSION = ".txt"

FILE_SEARCH_ROOTS = [
    VOICE_COMMAND_FOLDER_PATH,
    str(Path.home() / "Desktop"),
    str(Path.home() / "Documents"),
    str(Path.home() / "Downloads"),
    CREATE_FILE_DEFAULT_DRIVE,
]

RUN_FILE_INTERPRETERS = {
    ".py": [sys.executable],
    ".js": ["node"],
    ".bat": [],
    ".cmd": [],
}

KNOWN_APP_LAUNCH = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "camera": "microsoft.windows.camera:",
    "chrome": "chrome.exe",
    "browser": "chrome.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "files": "explorer.exe",
    "task manager": "taskmgr.exe",
    "settings": "ms-settings:",
    "control panel": "control.exe",
    "spotify": "spotify:",
}

CAMERA_INDEX_DEFAULT = 0
CAMERA_SAVE_DIR_DEFAULT = str(Path.home() / "Pictures" / "Jarvis")
VIDEO_SAVE_DIR_DEFAULT = str(Path.home() / "Videos" / "Jarvis")
VIDEO_FPS = 20.0

FOCUS_EXISTING_CURSOR_ON_DOUBLE_CLAP = False
OPEN_NEW_CURSOR_ON_DOUBLE_CLAP = False
CURSOR_OPEN_FULLSCREEN = False

OPEN_VSCODE_ON_DOUBLE_CLAP = False
VSCODE_FOLDER_PATH = VOICE_COMMAND_FOLDER_PATH

OPEN_CLAUDE_CODE_IN_CHROME = False
OPEN_BINANCE_BTC_IN_CHROME = False
OPEN_CHROME_FULLSCREEN = True
CHROME_SEPARATE_SITE_PROFILES = False
CLAUDE_CHROME_MONITOR = 1
BINANCE_CHROME_MONITOR = 3

JARVIS_WELCOME_ENABLED = True
JARVIS_WELCOME_PHRASE = (
    "Welcome home sir. "
    "Congratulations  on the new client for your NoteApp sure to follow up. "
    "If it helps: a short, specific note while the deal is still fresh usually "
    "anchors trust better than a polished deck sent cold a few days later."
    "can we start mark 42 project sir."
)
JARVIS_AFTER_SONG_DELAY_S = 1.0
JARVIS_WELCOME_CACHE_ENABLED = True

load_dotenv(Path(__file__).resolve().parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("clap_listen")


# =============================================================================
# Audio input helpers
# =============================================================================
def block_samples() -> int:
    n = int(SAMPLE_RATE * BLOCK_MS / 1000)
    return max(n, 1)


def rms_mono(block: np.ndarray) -> float:
    if block.ndim > 1:
        block = np.mean(block.astype(np.float64), axis=1)
    else:
        block = block.astype(np.float64)
    if block.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(block**2)))


def _input_devices() -> list[tuple[int, dict]]:
    return [
        (i, dev)
        for i, dev in enumerate(sd.query_devices())
        if dev["max_input_channels"] >= 1
    ]


def _resolve_input_device_index(spec: str) -> int:
    spec = spec.strip()
    if spec.isdigit():
        idx = int(spec)
        sd.query_devices(idx)
        return idx
    needle = spec.lower()
    for idx, dev in _input_devices():
        if needle in dev["name"].lower():
            return idx
    raise ValueError(f"No input device matches {spec!r}")


def _probe_input_max_rms(device: int, blocksize: int) -> float | None:
    try:
        with sd.InputStream(
            device=device,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=blocksize,
        ) as stream:
            peak = 0.0
            deadline = time.monotonic() + INPUT_PROBE_S
            while time.monotonic() < deadline:
                data, _ = stream.read(blocksize)
                peak = max(peak, rms_mono(data))
            return peak
    except sd.PortAudioError:
        return None


def _choose_input_device(blocksize: int) -> int:
    log.info("Audio devices:\n%s", sd.query_devices())

    override = (os.environ.get("JARVIS_INPUT_DEVICE") or "").strip()
    if override:
        try:
            idx = _resolve_input_device_index(override)
        except ValueError as e:
            log.error("%s", e)
            log.error("Set JARVIS_INPUT_DEVICE to a device index or name substring.")
            raise SystemExit(1) from e
        name = sd.query_devices(idx)["name"]
        peak = _probe_input_max_rms(idx, blocksize)
        log.info("Using JARVIS_INPUT_DEVICE [%d]: %s", idx, name)
        if peak is None:
            log.warning("Could not open configured mic; trying anyway.")
        elif peak < INPUT_SILENT_RMS:
            log.warning(
                "Configured mic looks silent (probe rms=%.5f). "
                "Check Windows input level or try another JARVIS_INPUT_DEVICE.",
                peak,
            )
        else:
            log.info("Mic probe OK (rms=%.5f).", peak)
        return idx

    default = sd.default.device[0]
    if default is not None and default >= 0:
        default_name = sd.query_devices(default)["name"]
        peak = _probe_input_max_rms(default, blocksize)
        if peak is not None and peak >= INPUT_SILENT_RMS:
            log.info(
                "Using default microphone [%d]: %s (probe rms=%.5f)",
                default,
                default_name,
                peak,
            )
            return default
        log.warning(
            "Default mic [%d] %s is silent or unavailable (probe rms=%s); "
            "scanning other inputs...",
            default,
            default_name,
            f"{peak:.5f}" if peak is not None else "unopenable",
        )

    best_idx: int | None = None
    best_peak = -1.0
    for idx, dev in _input_devices():
        if default is not None and idx == default:
            continue
        peak = _probe_input_max_rms(idx, blocksize)
        if peak is not None and peak > best_peak:
            best_peak = peak
            best_idx = idx

    if best_idx is not None and best_peak >= INPUT_SILENT_RMS:
        log.info(
            "Auto-selected microphone [%d]: %s (probe rms=%.5f)",
            best_idx,
            sd.query_devices(best_idx)["name"],
            best_peak,
        )
        return best_idx

    if default is not None and default >= 0:
        log.warning("No active mic found; falling back to default [%d].", default)
        return default
    inputs = _input_devices()
    if not inputs:
        log.error("No input devices found.")
        raise SystemExit(1)
    idx, dev = inputs[0]
    log.warning("No active mic found; falling back to [%d] %s.", idx, dev["name"])
    return idx


# =============================================================================
# ElevenLabs + offline speech
# =============================================================================
def _elevenlabs_pcm_sample_rate(output_format: str) -> int:
    override = (os.environ.get("ELEVENLABS_PCM_SAMPLE_RATE") or "").strip()
    if override.isdigit():
        return int(override)
    if output_format.startswith("pcm_"):
        try:
            return int(output_format.split("_", maxsplit=1)[1])
        except (ValueError, IndexError):
            pass
    return 24000


def elevenlabs_env_config() -> tuple[str, str, str, int]:
    """voice_id, model_id, output_format, pcm_sample_rate."""
    voice = (os.environ.get("ELEVENLABS_VOICE_ID") or "").strip()
    model = (os.environ.get("ELEVENLABS_MODEL_ID") or "eleven_multilingual_v2").strip()
    fmt = (os.environ.get("ELEVENLABS_OUTPUT_FORMAT") or "pcm_24000").strip()
    rate = _elevenlabs_pcm_sample_rate(fmt)
    return voice, model, fmt, rate


def _jarvis_welcome_cache_dir() -> Path:
    base = Path(__file__).resolve().parent
    override = (os.environ.get("JARVIS_WELCOME_CACHE_DIR") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return base / ".cache" / "jarvis_welcome"


def _jarvis_welcome_cache_path(
    text: str, voice_id: str, model_id: str, output_format: str
) -> Path:
    key = f"{text}|{voice_id}|{model_id}|{output_format}".encode()
    digest = hashlib.sha256(key).hexdigest()[:24]
    return _jarvis_welcome_cache_dir() / f"{digest}.wav"


def _play_pcm_wav_file(path: Path) -> bool:
    try:
        with wave.open(str(path), "rb") as wf:
            ch = wf.getnchannels()
            sw = wf.getsampwidth()
            rate = wf.getframerate()
            if ch != 1 or sw != 2:
                log.warning("Unsupported cached WAV (channels=%s, width=%s).", ch, sw)
                return False
            raw = wf.readframes(wf.getnframes())
    except (OSError, wave.Error) as e:
        log.warning("Could not read cached welcome audio: %s", e)
        return False
    if not raw:
        return False
    pcm_i16 = np.frombuffer(raw, dtype=np.int16)
    pcm_f = pcm_i16.astype(np.float32) / 32768.0
    try:
        sd.play(pcm_f, rate)
        sd.wait()
    except Exception as e:
        log.warning("Could not play cached welcome audio: %s", e)
        return False
    return True


def _save_pcm_wav_file(path: Path, pcm_bytes: bytes, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with wave.open(str(tmp), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(pcm_bytes)
        tmp.replace(path)
    except OSError:
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        raise


# ---------------------------------------------------------------------------
# Hindi / English mode state (used by the speech code below)
# ---------------------------------------------------------------------------
HINDI_MODE = False
_hindi_cache: dict = {}
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")


def _stt_language() -> str:
    return HINDI_LISTEN_LANG if HINDI_MODE else ENGLISH_LISTEN_LANG


def _translate_to_hindi(text: str) -> str:
    """Free Google Translate endpoint (no key). Falls back to the original text."""
    import urllib.request

    url = (
        "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=hi&dt=t&q="
        + urllib.parse.quote(text)
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "jarvis-voice-assistant"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        out = "".join(part[0] for part in data[0] if part and part[0])
        return out.strip() or text
    except Exception as e:
        log.warning("Hindi translation failed (%s); speaking English.", e)
        return text


def _maybe_hindi(text: str) -> str:
    """In Hindi mode, turn Jarvis's English replies into Hindi before speaking."""
    if not HINDI_MODE or _DEVANAGARI.search(text):
        return text
    if text not in _hindi_cache:
        _hindi_cache[text] = _translate_to_hindi(text)
    return _hindi_cache[text]


def _speak_gtts(text: str, lang: str = "hi") -> bool:
    """Free Hindi voice via Google TTS. Needs: python -m pip install gTTS soundfile"""
    try:
        import io
        from gtts import gTTS
        import soundfile as sf
    except ImportError:
        log.warning("Hindi backup voice needs: python -m pip install gTTS soundfile")
        return False
    try:
        buf = io.BytesIO()
        gTTS(text=text, lang=lang).write_to_fp(buf)
        buf.seek(0)
        data, rate = sf.read(buf, dtype="float32")
        sd.play(data, rate)
        sd.wait()
        return True
    except Exception as e:
        log.warning("gTTS speech failed: %s", e)
        return False


def _speak_offline_powershell(text: str) -> bool:
    """Offline voice using Windows' built-in speech (PowerShell). No pip install needed."""
    if sys.platform != "win32":
        return False
    try:
        env = dict(os.environ, JARVIS_TTS_TEXT=text)
        subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Add-Type -AssemblyName System.Speech; "
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                "$s.Speak($env:JARVIS_TTS_TEXT)",
            ],
            env=env,
            timeout=90,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return True
    except Exception as e:
        log.warning("PowerShell speech fallback failed: %s", e)
        return False


_offline_lock = threading.Lock()


def _speak_offline(text: str) -> bool:
    """Backup voice (used when ElevenLabs fails). One reply speaks at a time.
    Hindi text -> Google TTS; English -> Windows built-in speech."""
    with _offline_lock:
        if _DEVANAGARI.search(text) and _speak_gtts(text):
            return True
        try:
            import pythoncom
            import win32com.client
        except ImportError:
            return _speak_offline_powershell(text)
        pythoncom.CoInitialize()
        try:
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            speaker.Speak(text)
            return True
        except Exception as e:
            log.warning("Offline speech fallback failed: %s", e)
            return _speak_offline_powershell(text)
        finally:
            pythoncom.CoUninitialize()


_speaking_lock = threading.Lock()
_speaking_count = 0


def _speaking_delta(n: int) -> None:
    global _speaking_count
    with _speaking_lock:
        _speaking_count = max(0, _speaking_count + n)


def _is_speaking() -> bool:
    return _speaking_count > 0


def speak_text(text: str, *, use_cache: bool = True) -> None:
    """Speak text via ElevenLabs (cached), falling back to offline speech.
    In Hindi mode the text is translated to Hindi first."""
    text = text.strip()
    if not text:
        return
    _speaking_delta(+1)
    try:
        _speak_text_impl(_maybe_hindi(text), use_cache=use_cache)
    finally:
        _speaking_delta(-1)


def _say(text: str) -> None:
    """Speak in a background thread so the listener never blocks."""
    threading.Thread(
        target=speak_text, args=(text,), kwargs={"use_cache": False}, daemon=True
    ).start()


def _speak_text_impl(text: str, *, use_cache: bool = True) -> None:
    vid, model_id, output_format, pcm_rate = elevenlabs_env_config()
    if not vid:
        log.warning("ELEVENLABS_VOICE_ID not set; using offline voice fallback.")
        _speak_offline(text)
        return

    cache_path = _jarvis_welcome_cache_path(text, vid, model_id, output_format)
    if use_cache and JARVIS_WELCOME_CACHE_ENABLED and cache_path.is_file():
        log.info("Playing speech from cache: %s", cache_path)
        if _play_pcm_wav_file(cache_path):
            return
        log.warning("Cache miss after read failure; fetching from ElevenLabs.")

    api_key = (os.environ.get("ELEVENLABS_API_KEY") or "").strip()
    if not api_key:
        log.warning("ELEVENLABS_API_KEY not set; using offline voice fallback.")
        _speak_offline(text)
        return
    try:
        from elevenlabs.client import ElevenLabs
    except ImportError:
        log.warning("elevenlabs package not installed; using offline voice fallback.")
        _speak_offline(text)
        return
    try:
        client = ElevenLabs(api_key=api_key)
        chunks = client.text_to_speech.convert(
            voice_id=vid,
            text=text,
            model_id=model_id,
            output_format=output_format,
        )
        raw = b"".join(chunks)
    except Exception as e:
        log.warning("ElevenLabs TTS failed (%s); using offline voice fallback.", e)
        _speak_offline(text)
        return
    if not raw:
        log.warning("ElevenLabs returned empty audio; using offline voice fallback.")
        _speak_offline(text)
        return
    if use_cache and JARVIS_WELCOME_CACHE_ENABLED:
        try:
            _save_pcm_wav_file(cache_path, raw, pcm_rate)
            log.info("Saved speech to cache: %s", cache_path)
        except OSError as e:
            log.warning("Could not save speech cache: %s", e)
    pcm_i16 = np.frombuffer(raw, dtype=np.int16)
    pcm_f = pcm_i16.astype(np.float32) / 32768.0
    try:
        sd.play(pcm_f, pcm_rate)
        sd.wait()
    except Exception as e:
        log.warning("Could not play ElevenLabs audio (%s); using offline voice fallback.", e)
        _speak_offline(text)


def say_jarvis_welcome() -> None:
    if not JARVIS_WELCOME_ENABLED or not JARVIS_WELCOME_PHRASE.strip():
        return
    speak_text(JARVIS_WELCOME_PHRASE)


def announce_datetime() -> None:
    now = datetime.now()
    phrase = now.strftime("It's %A, %B %d, %Y, %I:%M %p.")
    log.info("Announcing date/time: %s", phrase)
    speak_text(phrase, use_cache=False)


# =============================================================================
# Music
# =============================================================================
def _play_local_audio_file(path: Path) -> None:
    """Decode and play a local audio file via sounddevice, so sd.stop() can stop it."""
    try:
        import soundfile as sf
    except ImportError:
        log.warning(
            "Local song playback works best with `pip install soundfile` "
            "(lets 'stop the music' actually stop it). Falling back to your default app."
        )
        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            else:
                webbrowser.open(str(path))
        except OSError as e:
            log.warning("Could not open song file: %s", e)
        return
    try:
        data, samplerate = sf.read(str(path), dtype="float32")
    except Exception as e:
        log.warning("Could not decode song file %s: %s", path, e)
        return
    try:
        sd.play(data, samplerate)
        log.info("Playing song (say \"stop the music\" to stop): %s", path)
    except Exception as e:
        log.warning("Could not play song: %s", e)


def play_song(uri: str) -> None:
    u = uri.strip()
    if not u:
        return
    p = Path(u)
    if p.is_file() and p.suffix.lower() in {".mp3", ".wav", ".flac", ".ogg"}:
        _play_local_audio_file(p)
        return
    try:
        if sys.platform == "win32":
            os.startfile(u)
        else:
            webbrowser.open(u)
    except OSError as e:
        log.warning("Could not open SONG_URI: %s", e)


def stop_song() -> None:
    """Stops whatever is currently playing via sounddevice (local songs, TTS)."""
    try:
        sd.stop()
        log.info("Stopped playback.")
    except Exception as e:
        log.warning("Could not stop playback: %s", e)


# =============================================================================
# Closing apps / STOP everything
# =============================================================================
def _close_foreground_window_win32() -> None:
    import ctypes

    user32 = ctypes.windll.user32
    WM_CLOSE = 0x0010
    hwnd = user32.GetForegroundWindow()
    if hwnd:
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        log.info("Closed the active window.")
        speak_text("Closed, sir.", use_cache=False)
    else:
        log.warning("No active window found to close.")
        speak_text("There's nothing active to close, sir.", use_cache=False)


def _taskkill(exe: str) -> bool:
    try:
        result = subprocess.run(
            ["taskkill", "/IM", exe, "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0
    except OSError as e:
        log.warning("Could not run taskkill for %s: %s", exe, e)
        return False


_active_timers: list[threading.Timer] = []


def close_all_known_apps() -> None:
    """Stops audio + recording and closes every app in CLOSE_ALL_PROCESSES."""
    stop_song()
    if _video_state.get("stop_event") is not None:
        stop_video_recording()
    closed: list[str] = []
    for exe in CLOSE_ALL_PROCESSES:
        if _taskkill(exe):
            closed.append(exe)
    if closed:
        log.info("Closed: %s", ", ".join(closed))
    else:
        log.info("Nothing to close (none of the known apps were running).")
    speak_text("Closed everything, sir.", use_cache=False)


def stop_everything() -> None:
    """'stop': music/speech, video recording, timers, and all background apps.
    Jarvis itself keeps running (say 'sleep' to shut Jarvis down)."""
    for tm in list(_active_timers):
        tm.cancel()
    _active_timers.clear()
    if sys.platform == "win32":
        close_all_known_apps()
    else:
        stop_song()
        if _video_state.get("stop_event") is not None:
            stop_video_recording()
    log.info("Stop command: everything stopped.")


def close_app_or_window(target: str) -> None:
    """'close chrome', 'close all', or 'close this' (active window)."""
    target = re.sub(r"^(?:the|my|this|a|an)\s+", "", target.strip().lower())
    if sys.platform != "win32":
        log.warning("Voice-close is only wired up for Windows right now.")
        return
    if target in {"all", "everything", "all apps", "everything open", "all tabs", "all the tabs"}:
        close_all_known_apps()
        return
    if not target or target in {"window", "this", "it", "app", "application"}:
        _close_foreground_window_win32()
        return
    exe = KNOWN_APP_PROCESSES.get(target, target.replace(" ", "") + ".exe")
    if _taskkill(exe):
        log.info("Closed process: %s", exe)
        speak_text(f"Closed {target}, sir.", use_cache=False)
    else:
        log.warning(
            "Could not close %s (not running, or name not recognized). "
            "Add it to KNOWN_APP_PROCESSES if the guess was wrong.",
            exe,
        )
        speak_text(f"I couldn't close {target}, sir. It may not be running.", use_cache=False)


# =============================================================================
# Files / folders / YouTube / camera
# =============================================================================
def create_file_on_drive(filename: str, drive: str = CREATE_FILE_DEFAULT_DRIVE) -> None:
    filename = filename.strip().strip(".")
    if not filename:
        log.warning("No filename heard for the create-file command.")
        speak_text("I didn't catch a file name, sir. Cancelled.", use_cache=False)
        return
    if not os.path.splitext(filename)[1]:
        filename += CREATE_FILE_DEFAULT_EXTENSION
    path = Path(drive) / filename
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        log.info("Created file: %s", path)
        speak_text(f"File {filename} was saved, sir.", use_cache=False)
    except OSError as e:
        log.warning("Could not create file %s: %s", path, e)
        speak_text("Sorry sir, I could not save that file.", use_cache=False)


def create_folder_on_drive(name: str, drive: str = CREATE_FILE_DEFAULT_DRIVE) -> None:
    name = name.strip().strip(".")
    if not name:
        speak_text("I didn't catch a folder name, sir. Cancelled.", use_cache=False)
        return
    path = Path(drive) / name
    try:
        path.mkdir(parents=True, exist_ok=True)
        log.info("Created folder: %s", path)
        speak_text(f"Folder {name} was created, sir.", use_cache=False)
    except OSError as e:
        log.warning("Could not create folder %s: %s", path, e)
        speak_text("Sorry sir, I could not create that folder.", use_cache=False)


def _youtube_search_first_video_id(query: str) -> str | None:
    try:
        import yt_dlp
    except ImportError:
        log.warning("YouTube search needs `pip install yt-dlp`.")
        return None
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": "in_playlist",
        "default_search": "ytsearch1",
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            entries = (info or {}).get("entries") or []
            if entries:
                return entries[0].get("id")
    except Exception as e:
        log.warning("YouTube search failed: %s", e)
    return None


def search_and_play_youtube(query: str) -> None:
    query = query.strip()
    if not query:
        open_youtube()
        return
    video_id = _youtube_search_first_video_id(query)
    if video_id:
        url = f"https://www.youtube.com/watch?v={video_id}&autoplay=1"
    else:
        url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query)
    try:
        if sys.platform == "win32":
            os.startfile(url)
        else:
            webbrowser.open(url)
        log.info("YouTube: %s -> %s", query, url)
        if video_id:
            speak_text(f"Playing {query} on YouTube, sir.", use_cache=False)
        else:
            speak_text(
                f"I couldn't find that exactly, sir, so I opened YouTube search for {query}.",
                use_cache=False,
            )
    except OSError as e:
        log.warning("Could not open YouTube: %s", e)
        speak_text("Sorry sir, I couldn't open YouTube.", use_cache=False)


def open_voice_command_folder() -> None:
    path = VOICE_COMMAND_FOLDER_PATH
    try:
        if sys.platform == "win32":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])
        log.info("Opened folder: %s", path)
        speak_text("Opened the folder, sir.", use_cache=False)
    except OSError as e:
        log.warning("Could not open folder %s: %s", path, e)
        speak_text("Sorry sir, I couldn't open that folder.", use_cache=False)


def open_camera_app() -> None:
    try:
        if sys.platform == "win32":
            os.startfile("microsoft.windows.camera:")
            log.info("Opened Camera app.")
            speak_text("Opening the camera, sir.", use_cache=False)
        else:
            log.warning("Camera app launch is only wired up for Windows right now.")
            speak_text("Sorry sir, camera launch isn't set up on this system.", use_cache=False)
    except OSError as e:
        log.warning("Could not open Camera app: %s", e)
        speak_text("Sorry sir, I couldn't open the camera.", use_cache=False)


def find_file(name: str, *, max_results: int = 1) -> list[Path]:
    """Best-effort search across FILE_SEARCH_ROOTS for a filename or name match."""
    name = name.strip().strip(".")
    if not name:
        return []
    name_lower = name.lower()
    has_ext = bool(os.path.splitext(name)[1])
    exact: list[Path] = []
    partial: list[Path] = []
    seen: set[Path] = set()
    for root_str in FILE_SEARCH_ROOTS:
        root = Path(root_str)
        if not root.exists():
            continue
        try:
            for p in root.rglob("*"):
                if not p.is_file() or p in seen:
                    continue
                seen.add(p)
                fname = p.name.lower()
                stem = p.stem.lower()
                if fname == name_lower or (not has_ext and stem == name_lower):
                    exact.append(p)
                    if len(exact) >= max_results:
                        return exact
                elif name_lower in fname:
                    partial.append(p)
        except OSError:
            continue
    return (exact + partial)[:max_results]


def speak_file_location(name: str) -> None:
    name = name.strip()
    if not name:
        return
    matches = find_file(name, max_results=1)
    if matches:
        path = matches[0]
        log.info("Found %r at: %s", name, path)
        speak_text(f"{name} is saved at {path}, sir.", use_cache=False)
    else:
        log.info("File search: no match for %r", name)
        speak_text(f"I could not find a file named {name}, sir.", use_cache=False)


def open_and_run_file(name: str) -> None:
    """Find a file by name, open it in VS Code, and run it in a new console window."""
    name = name.strip()
    if not name:
        return
    matches = find_file(name, max_results=1)
    if not matches:
        log.warning("Run command: no file found matching %r", name)
        speak_text(f"I could not find {name} to run, sir.", use_cache=False)
        return
    path = matches[0]

    exe = _vscode_executable()
    if exe:
        popen_kw: dict = {
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            subprocess.Popen([exe, str(path)], **popen_kw)
            log.info("Opened in VS Code: %s", path)
        except OSError as e:
            log.warning("Could not open %s in VS Code: %s", path, e)
    else:
        log.warning("VS Code not found; skipping editor open, will still try to run.")

    ext = path.suffix.lower()
    if ext not in RUN_FILE_INTERPRETERS:
        log.warning("Don't know how to run %s (extension %s not in RUN_FILE_INTERPRETERS).", path, ext)
        speak_text(f"I opened {path.name}, but I do not know how to run that file type, sir.", use_cache=False)
        return
    cmd = RUN_FILE_INTERPRETERS[ext] + [str(path)]
    try:
        if sys.platform == "win32":
            subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE, cwd=str(path.parent))
        else:
            subprocess.Popen(cmd, cwd=str(path.parent))
        log.info("Running: %s", " ".join(cmd))
        speak_text(f"Running {path.name}, sir.", use_cache=False)
    except OSError as e:
        log.warning("Could not run %s: %s", path, e)
        speak_text(f"Sorry sir, I could not run {path.name}.", use_cache=False)


def open_recent_picture() -> None:
    """Opens File Explorer with the most recently taken picture selected."""
    _, photo_dir, _ = _camera_env_config()
    photos: list[Path] = []
    if photo_dir.exists():
        photos = sorted(photo_dir.glob("photo_*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not photos:
        log.info("No pictures found in %s", photo_dir)
        speak_text("I could not find any pictures yet, sir.", use_cache=False)
        return
    latest = photos[0]
    try:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(latest)])
        else:
            subprocess.Popen(["xdg-open", str(latest.parent)])
        log.info("Opened location of most recent picture: %s", latest)
        speak_text(f"Here is your most recent picture, {latest.name}.", use_cache=False)
    except OSError as e:
        log.warning("Could not open picture location %s: %s", latest, e)


# --- camera: take a picture / record video (OpenCV) -----------------------------
_camera_lock = threading.Lock()
_video_state: dict = {"writer": None, "cap": None, "stop_event": None, "thread": None, "path": None}


def _camera_env_config() -> tuple[int, Path, Path]:
    idx_raw = (os.environ.get("JARVIS_CAMERA_INDEX") or "").strip()
    idx = int(idx_raw) if idx_raw.isdigit() else CAMERA_INDEX_DEFAULT
    photo_dir = Path((os.environ.get("JARVIS_CAMERA_DIR") or "").strip() or CAMERA_SAVE_DIR_DEFAULT)
    video_dir = Path((os.environ.get("JARVIS_VIDEO_DIR") or "").strip() or VIDEO_SAVE_DIR_DEFAULT)
    return idx, photo_dir, video_dir


def _open_cv2():
    try:
        import cv2
        return cv2
    except ImportError:
        log.warning("Camera features need OpenCV: pip install opencv-python")
        return None


def _open_camera_capture(cv2, index: int):
    backend = cv2.CAP_DSHOW if sys.platform == "win32" else 0
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        log.warning("Could not open camera index %d.", index)
        return None
    return cap


def _release_camera_app() -> None:
    """The Windows Camera app locks the webcam, so close it before OpenCV uses it."""
    if sys.platform == "win32" and _taskkill("WindowsCamera.exe"):
        time.sleep(1.0)  # let Windows release the device


def take_picture() -> None:
    _release_camera_app()
    cv2 = _open_cv2()
    if cv2 is None:
        speak_text("Sorry sir, the camera isn't set up.", use_cache=False)
        return
    index, photo_dir, _ = _camera_env_config()
    with _camera_lock:
        cap = _open_camera_capture(cv2, index)
        if cap is None:
            speak_text("Sorry sir, I couldn't reach the camera.", use_cache=False)
            return
        try:
            for _ in range(5):  # let auto-exposure settle
                cap.read()
            ok, frame = cap.read()
        finally:
            cap.release()
    if not ok or frame is None:
        log.warning("Could not capture a photo.")
        speak_text("Sorry sir, I couldn't capture a photo.", use_cache=False)
        return
    photo_dir.mkdir(parents=True, exist_ok=True)
    path = photo_dir / f"photo_{datetime.now():%Y%m%d_%H%M%S}.jpg"
    cv2.imwrite(str(path), frame)
    log.info("Saved photo: %s", path)
    speak_text("Picture saved, sir.", use_cache=False)


def start_video_recording() -> None:
    _release_camera_app()
    cv2 = _open_cv2()
    if cv2 is None:
        speak_text("Sorry sir, the camera isn't set up.", use_cache=False)
        return
    with _camera_lock:
        if _video_state["writer"] is not None:
            log.info("Already recording video.")
            speak_text("Already recording, sir.", use_cache=False)
            return
        index, _, video_dir = _camera_env_config()
        cap = _open_camera_capture(cv2, index)
        if cap is None:
            speak_text("Sorry sir, I couldn't reach the camera.", use_cache=False)
            return
        video_dir.mkdir(parents=True, exist_ok=True)
        path = video_dir / f"video_{datetime.now():%Y%m%d_%H%M%S}.mp4"
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 480
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(path), fourcc, VIDEO_FPS, (width, height))
        stop_event = threading.Event()

        def _record_loop() -> None:
            frame_interval = 1.0 / VIDEO_FPS
            while not stop_event.is_set():
                ok, frame = cap.read()
                if not ok:
                    break
                writer.write(frame)
                time.sleep(frame_interval)
            cap.release()
            writer.release()

        thread = threading.Thread(target=_record_loop, daemon=True)
        _video_state.update(writer=writer, cap=cap, stop_event=stop_event, thread=thread, path=path)
        thread.start()
        log.info('Recording video to: %s (say "stop recording" to stop)', path)
    speak_text("Recording started, sir.", use_cache=False)


def stop_video_recording() -> None:
    with _camera_lock:
        stop_event = _video_state.get("stop_event")
        if stop_event is None:
            log.info("Not currently recording video.")
            speak_text("I'm not recording anything right now, sir.", use_cache=False)
            return
        stop_event.set()
        thread = _video_state.get("thread")
        path = _video_state.get("path")
        _video_state.update(writer=None, cap=None, stop_event=None, thread=None, path=None)
    if thread is not None:
        thread.join(timeout=5)
    log.info("Stopped video recording: %s", path)
    speak_text("Recording saved, sir.", use_cache=False)


# =============================================================================
# Generic "open <anything>"
# =============================================================================
def _win32_start_app_by_display_name(name: str) -> bool:
    """Best-effort: find an installed/Start Menu app by partial display name and launch it."""
    if sys.platform != "win32":
        return False
    safe_name = name.replace("'", "")
    ps_cmd = (
        "(Get-StartApps | Where-Object { $_.Name -like '*" + safe_name + "*' } "
        "| Select-Object -First 1 -ExpandProperty AppID)"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("Start Menu app search failed: %s", e)
        return False
    app_id = (result.stdout or "").strip()
    if not app_id:
        return False
    try:
        os.startfile(f"shell:AppsFolder\\{app_id}")
        return True
    except OSError as e:
        log.warning("Could not launch %r via Start Menu entry: %s", name, e)
        return False


def open_app_by_name(name: str) -> None:
    name = name.strip()
    if not name:
        log.warning("No app name heard for the open command.")
        speak_text("I didn't catch what to open, sir.", use_cache=False)
        return
    if sys.platform != "win32":
        log.warning("Generic 'open <app>' is only wired up for Windows right now.")
        speak_text("Sorry sir, opening apps isn't set up on this system.", use_cache=False)
        return

    key = name.lower()
    target = KNOWN_APP_LAUNCH.get(key)
    if target:
        try:
            os.startfile(target)
            log.info("Opened app: %s", name)
            speak_text(f"Opening {name}, sir.", use_cache=False)
            return
        except OSError as e:
            log.warning("Could not open %r via %r: %s", name, target, e)

    candidate = key.replace(" ", "")
    for guess in (candidate, candidate + ".exe"):
        try:
            os.startfile(guess)
            log.info("Opened app: %s", name)
            speak_text(f"Opening {name}, sir.", use_cache=False)
            return
        except OSError:
            continue

    if _win32_start_app_by_display_name(name):
        log.info("Opened app via Start Menu search: %s", name)
        speak_text(f"Opening {name}, sir.", use_cache=False)
        return

    log.warning(
        "Could not find or open %r. Add it to KNOWN_APP_LAUNCH (exe name or URI) "
        "if it keeps failing, or make sure it shows up in the Start Menu under that name.",
        name,
    )
    speak_text(f"Sorry sir, I couldn't find {name}.", use_cache=False)


# =============================================================================
# Knowledge: Wikipedia, location, distance, weather
# =============================================================================
def _wikipedia_summary(term: str) -> str | None:
    import urllib.request

    host = "https://hi.wikipedia.org" if _DEVANAGARI.search(term) else "https://en.wikipedia.org"
    url = host + "/api/rest_v1/page/summary/" + urllib.parse.quote(term)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "jarvis-voice-assistant"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.warning("Wikipedia lookup failed for %r: %s", term, e)
        return None
    extract = (data.get("extract") or "").strip()
    return extract or None


def _get_ip_location() -> dict | None:
    import urllib.request

    try:
        req = urllib.request.Request(
            "https://ipinfo.io/json", headers={"User-Agent": "jarvis-voice-assistant"}
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.warning("IP location lookup failed: %s", e)
        return None

    loc = data.get("loc")
    lat = lon = None
    if loc and "," in loc:
        try:
            lat_str, lon_str = loc.split(",", 1)
            lat, lon = float(lat_str), float(lon_str)
        except ValueError:
            pass

    return {
        "city": data.get("city"),
        "region": data.get("region"),
        "country": data.get("country"),
        "lat": lat,
        "lon": lon,
    }


def _geocode(place: str) -> dict | None:
    import urllib.request

    url = "https://geocoding-api.open-meteo.com/v1/search?name=" + urllib.parse.quote(place) + "&count=1"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "jarvis-voice-assistant"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log.warning("Geocoding failed for %r: %s", place, e)
        return None

    results = data.get("results") or []
    if not results:
        return None
    top = results[0]
    name_parts = [top.get("name")]
    if top.get("admin1"):
        name_parts.append(top["admin1"])
    if top.get("country"):
        name_parts.append(top["country"])
    return {
        "name": ", ".join(p for p in name_parts if p),
        "lat": top.get("latitude"),
        "lon": top.get("longitude"),
    }


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math

    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def speak_current_location() -> None:
    loc = _get_ip_location()
    if not loc or not (loc.get("city") or loc.get("country")):
        speak_text("Sorry sir, I couldn't find your current location.", use_cache=False)
        return
    parts = [p for p in (loc.get("city"), loc.get("region"), loc.get("country")) if p]
    speak_text(f"You're currently in {', '.join(parts)}, sir.", use_cache=False)


def speak_distance_between(term: str) -> None:
    term = term.strip()
    patterns = [
        r"^distance\s+(?:between|from)\s+(.+?)\s+(?:and|to)\s+(.+?)$",
        r"^how far is\s+(.+?)\s+from\s+(.+?)$",
        r"^how far from\s+(.+?)\s+to\s+(.+?)$",
        r"^(.+?)\s+to\s+(.+?)\s+distance$",
    ]
    place_a = place_b = None
    for pat in patterns:
        m = re.match(pat, term, re.IGNORECASE)
        if m:
            place_a, place_b = m.group(1).strip(), m.group(2).strip()
            break

    if not place_a or not place_b:
        speak_text("Sorry sir, I couldn't understand which two places to measure.", use_cache=False)
        return

    geo_a, geo_b = _geocode(place_a), _geocode(place_b)
    if not geo_a or not geo_b:
        speak_text("Sorry sir, I couldn't find one of those places.", use_cache=False)
        return

    km = _haversine_km(geo_a["lat"], geo_a["lon"], geo_b["lat"], geo_b["lon"])
    miles = km * 0.621371
    speak_text(
        f"The distance between {geo_a['name']} and {geo_b['name']} is about "
        f"{km:,.0f} kilometers, or {miles:,.0f} miles, sir.",
        use_cache=False,
    )


def speak_temperature(place: str | None) -> None:
    import urllib.request

    lat = lon = None
    location_label = None

    if place:
        geo = _geocode(place)
        if geo:
            lat, lon, location_label = geo["lat"], geo["lon"], geo["name"]
    if lat is None:
        ip_loc = _get_ip_location()
        if ip_loc and ip_loc.get("lat") is not None:
            lat, lon = ip_loc["lat"], ip_loc["lon"]
            location_label = ", ".join(
                p for p in (ip_loc.get("city"), ip_loc.get("country")) if p
            )

    if lat is None or lon is None:
        speak_text("Sorry sir, I couldn't determine the location for the weather.", use_cache=False)
        return

    url = (
        "https://api.open-meteo.com/v1/forecast?latitude=" + str(lat)
        + "&longitude=" + str(lon) + "&current_weather=true"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "jarvis-voice-assistant"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        temp_c = data["current_weather"]["temperature"]
    except Exception as e:
        log.warning("Weather lookup failed: %s", e)
        speak_text("Sorry sir, I couldn't get the temperature right now.", use_cache=False)
        return

    where = f" in {location_label}" if location_label else ""
    speak_text(f"It's currently {temp_c:.0f} degrees Celsius{where}, sir.", use_cache=False)


# =============================================================================
# Study material fallback (PDF / Word / images)
# =============================================================================
STUDY_MATERIAL_DIR = Path(
    os.environ.get("JARVIS_STUDY_PDF_DIR")
    or os.environ.get("JARVIS_STUDY_MATERIAL_DIR")
    or (Path(__file__).resolve().parent / "study_pdfs")
)
STUDY_PDF_CACHE = str(Path(__file__).resolve().parent / ".cache" / "study_pdf_chunks.json")
STUDY_ANSWER_MAX_WORDS = 70
STUDY_STOPWORDS = {
    "what", "is", "the", "a", "an", "of", "in", "on", "to", "and",
    "explain", "define", "who", "are", "for", "with", "sir",
}
STUDY_FILE_EXTS = {".pdf", ".docx", ".txt", ".jpg", ".jpeg", ".png", ".bmp", ".tiff"}
STUDY_MAX_FILE_MB = float(os.environ.get("JARVIS_STUDY_MAX_FILE_MB", "25"))

_study_chunks_cache: list[dict] | None = None


def _group_into_chunks(paragraphs: list[str], page: int) -> list[dict]:
    out = []
    for para in paragraphs:
        para = " ".join(para.split())
        if len(para.split()) >= 8:
            out.append({"page": page, "text": para})
    return out


def _extract_pdf_chunks(path: Path) -> list[dict]:
    from pypdf import PdfReader
    chunks: list[dict] = []
    reader = PdfReader(str(path))
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        chunks.extend(_group_into_chunks(re.split(r"\n\s*\n", text), page_num))
    return chunks


def _extract_docx_chunks(path: Path) -> list[dict]:
    import docx  # python-docx
    document = docx.Document(str(path))
    chunks: list[dict] = []
    buffer: list[str] = []
    page = 1
    for para in document.paragraphs:
        text = para.text.strip()
        if text:
            buffer.append(text)
        else:
            if buffer:
                chunks.extend(_group_into_chunks(["\n".join(buffer)], page))
                buffer = []
    if buffer:
        chunks.extend(_group_into_chunks(["\n".join(buffer)], page))
    return chunks


def _extract_image_chunks(path: Path) -> list[dict]:
    import pytesseract
    from PIL import Image
    with Image.open(path) as img:
        text = pytesseract.image_to_string(img) or ""
    return _group_into_chunks(re.split(r"\n\s*\n", text), 1)


def _extract_txt_chunks(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return _group_into_chunks(re.split(r"\n\s*\n", text), 1)


_STUDY_EXTRACTORS = {
    ".pdf": ("pypdf", _extract_pdf_chunks),
    ".docx": ("python-docx", _extract_docx_chunks),
    ".txt": ("built-in", _extract_txt_chunks),
    ".jpg": ("pytesseract + Pillow (+ Tesseract OCR installed)", _extract_image_chunks),
    ".jpeg": ("pytesseract + Pillow (+ Tesseract OCR installed)", _extract_image_chunks),
    ".png": ("pytesseract + Pillow (+ Tesseract OCR installed)", _extract_image_chunks),
    ".bmp": ("pytesseract + Pillow (+ Tesseract OCR installed)", _extract_image_chunks),
    ".tiff": ("pytesseract + Pillow (+ Tesseract OCR installed)", _extract_image_chunks),
}


def _load_study_chunks() -> list[dict]:
    global _study_chunks_cache
    if _study_chunks_cache is not None:
        return _study_chunks_cache

    cache_path = Path(STUDY_PDF_CACHE)
    cached_files: dict = {}
    if cache_path.exists():
        try:
            loaded = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cached_files = loaded
            else:
                log.info("Old-format study cache found; rebuilding.")
                cached_files = {}
        except Exception as e:
            log.warning("Could not read study material cache, re-indexing: %s", e)
            cached_files = {}

    if not STUDY_MATERIAL_DIR.exists():
        log.warning(
            "Study material folder not found at %s (create it and add "
            ".pdf/.docx/image files, or set JARVIS_STUDY_MATERIAL_DIR).",
            STUDY_MATERIAL_DIR,
        )
        _study_chunks_cache = []
        return _study_chunks_cache

    file_paths = sorted(
        p for p in STUDY_MATERIAL_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in STUDY_FILE_EXTS
    )
    if not file_paths:
        log.warning("No supported study files found in %s.", STUDY_MATERIAL_DIR)
        _study_chunks_cache = []
        return _study_chunks_cache

    all_chunks: list[dict] = []
    updated_files: dict = {}
    changed = False
    warned_missing_libs: set[str] = set()

    for file_path in file_paths:
        ext = file_path.suffix.lower()
        lib_name, extractor = _STUDY_EXTRACTORS[ext]
        stat = file_path.stat()
        fingerprint = f"{stat.st_mtime_ns}:{stat.st_size}"
        key = file_path.name
        cached_entry = cached_files.get(key)

        size_mb = stat.st_size / (1024 * 1024)
        if size_mb > STUDY_MAX_FILE_MB and not (cached_entry and cached_entry.get("fingerprint") == fingerprint):
            log.warning(
                "Skipping %s: %.1f MB exceeds the %.0f MB study-file limit "
                "(raise JARVIS_STUDY_MAX_FILE_MB in .env if you want it indexed).",
                file_path.name, size_mb, STUDY_MAX_FILE_MB,
            )
            continue

        if cached_entry and cached_entry.get("fingerprint") == fingerprint:
            file_chunks = cached_entry["chunks"]
        else:
            log.info("Indexing %s (new or changed)...", file_path.name)
            try:
                file_chunks = extractor(file_path)
            except ImportError:
                if lib_name not in warned_missing_libs:
                    log.warning(
                        "Skipping %s: needs %s (run: python -m pip install ...).",
                        file_path.name, lib_name,
                    )
                    warned_missing_libs.add(lib_name)
                continue
            except Exception as e:
                log.warning("Could not read %s: %s", file_path.name, e)
                continue
            changed = True

        updated_files[key] = {"fingerprint": fingerprint, "chunks": file_chunks}
        for c in file_chunks:
            all_chunks.append({"source": key, "page": c["page"], "text": c["text"]})

    if set(cached_files.keys()) - set(updated_files.keys()):
        changed = True

    if changed:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            cache_path.write_text(json.dumps(updated_files), encoding="utf-8")
        except Exception as e:
            log.warning("Could not write study material cache: %s", e)

    _study_chunks_cache = all_chunks
    log.info(
        "Indexed %d chunks from %d file(s) in %s.",
        len(all_chunks), len(file_paths), STUDY_MATERIAL_DIR,
    )
    return _study_chunks_cache


def _search_study_pdf(term: str) -> str | None:
    chunks = _load_study_chunks()
    if not chunks:
        return None

    query_words = set(re.findall(r"[a-z0-9]+", term.lower())) - STUDY_STOPWORDS
    if not query_words:
        return None

    best_score = 0
    best_text: str | None = None
    best_source: str | None = None
    for chunk in chunks:
        chunk_words = set(re.findall(r"[a-z0-9]+", chunk["text"].lower()))
        score = len(query_words & chunk_words)
        if score > best_score:
            best_score, best_text, best_source = score, chunk["text"], chunk.get("source")

    if best_text and best_source:
        log.info("Best study-PDF match for %r came from %s.", term, best_source)
    return best_text if best_score > 0 else None


def _trim_to_speech_length(text: str, max_words: int = STUDY_ANSWER_MAX_WORDS) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    trimmed = " ".join(words[:max_words])
    last_period = trimmed.rfind(".")
    return trimmed[: last_period + 1] if last_period > 0 else trimmed + "..."


def answer_question_and_search(term: str) -> None:
    """'what is X' etc. Wikipedia first, then study material, else an apology."""
    term = term.strip()
    term = re.sub(r"^(?:the|a|an)\s+", "", term, flags=re.IGNORECASE)
    if not term:
        return

    found_answer = False

    summary = _wikipedia_summary(term)
    if summary:
        sentences = re.split(r"(?<=[.!?।])\s+", summary)
        speak_text(" ".join(sentences[:3]).strip(), use_cache=False)
        found_answer = True
    else:
        pdf_answer = _search_study_pdf(term)
        if pdf_answer:
            log.info("Answering %r from study material.", term)
            speak_text(_trim_to_speech_length(pdf_answer), use_cache=False)
            found_answer = True
        else:
            speak_text(f"Sorry sir, I couldn't find anything related to {term}.", use_cache=False)

    if found_answer:
        search_url = "https://www.google.com/search?q=" + urllib.parse.quote(term)
        _open_url_in_chrome(search_url, new_window=True, label=f"search: {term}")


def open_youtube() -> None:
    url = VOICE_COMMAND_YOUTUBE_URL
    try:
        if sys.platform == "win32":
            os.startfile(url)
        else:
            webbrowser.open(url)
        log.info("Opened YouTube: %s", url)
        speak_text("Opening YouTube, sir.", use_cache=False)
    except OSError as e:
        log.warning("Could not open YouTube: %s", e)
        speak_text("Sorry sir, I couldn't open YouTube.", use_cache=False)


def handle_sleep_command() -> None:
    """'sleep' / 'go to sleep': speaks a farewell and shuts Jarvis down."""
    log.info("Sleep command received - shutting down Jarvis.")
    speak_text(SLEEP_RESPONSE, use_cache=False)
    time.sleep(0.3)
    os._exit(0)


# --- calculator --------------------------------------------------------------
_CALC_PATTERN = re.compile(
    r"(-?\d+(?:\.\d+)?)\s*"
    r"(\+|-|\*|/|x|plus|minus|times|multiplied by|multiply by|divided by|divide by)\s*"
    r"(-?\d+(?:\.\d+)?)"
)
_CALC_OP_FUNCS = {
    "+": operator.add,
    "plus": operator.add,
    "-": operator.sub,
    "minus": operator.sub,
    "*": operator.mul,
    "x": operator.mul,
    "times": operator.mul,
    "multiplied by": operator.mul,
    "multiply by": operator.mul,
    "/": operator.truediv,
    "divided by": operator.truediv,
    "divide by": operator.truediv,
}


def _format_calc_result(result: float) -> str:
    if result == int(result):
        return str(int(result))
    return f"{result:.4f}".rstrip("0").rstrip(".")


def calculate_and_speak(t: str) -> None:
    m = _CALC_PATTERN.search(t)
    if not m:
        speak_text("Sorry sir, I couldn't understand the numbers.", use_cache=False)
        return
    a_str, op, b_str = m.groups()
    try:
        a, b = float(a_str), float(b_str)
        result = _CALC_OP_FUNCS[op](a, b)
    except ZeroDivisionError:
        speak_text("Sorry sir, I can't divide by zero.", use_cache=False)
        return
    except (ValueError, KeyError) as e:
        log.warning("Calculate command failed for %r: %s", t, e)
        speak_text("Sorry sir, I couldn't calculate that.", use_cache=False)
        return
    result_str = _format_calc_result(result)
    log.info("Calculated %s %s %s = %s", a_str, op, b_str, result_str)
    speak_text(f"The answer is {result_str}, sir.", use_cache=False)


def answer_from_study_material_fallback(text: str) -> bool:
    answer = _search_study_pdf(text)
    if not answer:
        return False
    log.info("Fallback: answering %r from study material.", text)
    speak_text(_trim_to_speech_length(answer), use_cache=False)
    return True


# =============================================================================
# Claude chat
# =============================================================================
CLAUDE_MODEL = (os.environ.get("JARVIS_CLAUDE_MODEL") or "claude-sonnet-4-6").strip()
_chat_history: list[dict] = []


def ask_claude(question: str) -> str | None:
    """Conversational reply (Siri-style). Needs ANTHROPIC_API_KEY in .env."""
    import urllib.request

    key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        return None
    _chat_history.append({"role": "user", "content": question})
    body = {
        "model": CLAUDE_MODEL,
        "max_tokens": 200,
        "system": (
            f"You are Jarvis, a calm, witty voice assistant talking to {JARVIS_USER_NAME}. "
            "Reply in one to three short spoken sentences. No markdown, no lists. "
            "Say 'sir' occasionally."
            + (" Always reply in Hindi, written in Devanagari script." if HINDI_MODE else "")
        ),
        "messages": _chat_history[-12:],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode(),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
        answer = "".join(b.get("text", "") for b in data["content"]).strip()
        _chat_history.append({"role": "assistant", "content": answer})
        return answer
    except Exception as e:
        log.warning("Claude request failed: %s", e)
        _chat_history.pop()
        return None


def _study_fallback_or_log(text: str) -> None:
    """Nothing matched a command: chat (if ANTHROPIC_API_KEY set), else study notes."""
    answer = ask_claude(text)
    if answer:
        speak_text(answer, use_cache=False)
        return
    if answer_from_study_material_fallback(text):
        return
    log.info("No matching voice command for: %r", text)
    if not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        speak_text(
            "I heard you, sir, but I can only run commands right now. "
            "Add an ANTHROPIC API key to my env file so I can chat.",
            use_cache=False,
        )


# =============================================================================
# Hindi / English mode switching + Hindi command words
# =============================================================================
def _handle_mode_switch(text: str) -> bool:
    """'hindi me baat karte hai' / 'hindi mode' -> Hindi replies.
    'english' / 'english mode' / 'english me baat' -> English replies."""
    global HINDI_MODE
    t = text.lower().strip()

    wants_hindi = (
        re.search(r"hindi.*(?:ba+a?t|bol|mode|me+in?\b|mai?n\b)", t)
        or re.search(r"हिंदी|हिन्दी", t)
    ) and "play" not in t and "song" not in t
    wants_english = (
        re.match(r"^\W*(?:speak |talk |switch to |communicate in )?english\W*$", t)
        or re.search(r"english\s*(?:mode|me+in?\s*ba+a?t|mai?n\s*ba+a?t)", t)
        or re.search(r"इंग्लिश|अंग्रेजी|अंग्रेज़ी", t)
    )

    if wants_hindi:
        if re.search(r"\b(?:off|disable|band)\b|बंद", t):
            HINDI_MODE = False
            _say("Okay boss, I will speak English now.")
        else:
            HINDI_MODE = True
            _say("ठीक है बॉस, अब मैं हिंदी में बात करूँगा।")
        log.info("Hindi mode: %s", "ON" if HINDI_MODE else "OFF")
        return True
    if wants_english:
        HINDI_MODE = False
        log.info("Hindi mode: OFF (English)")
        _say("Okay boss, I will speak English now.")
        return True
    return False


_STOP_RE = re.compile(
    r"^\W*(?:(?:hey |hello )?jarvis\W*)?(?:st[eo]p|stop all|stop everything|ruko|ruk jao|"
    r"sab band(?: karo)?|रुको|रुक जाओ|सब बंद(?: करो| कर दो)?)\W*$",
    re.I,
)

_JARVIS_VARIANTS = re.compile(r"जार्विस|जारविस|जर्विस|जार्विज़|जार्विज|जरविस")
_CAM = r"(?:कैमरा|कैमेरा|camera|kamera)"
_V_OPEN = r"(?:खोलो|खोल दो|खोल|kholo|khol do|khol)"
_V_PLAY = r"(?:चलाओ|चला दो|चला|बजाओ|बजा दो|chalao|chala do|bajao)"
_APP_NAMES = {
    "नोटपैड": "notepad", "क्रोम": "chrome", "कैलकुलेटर": "calculator",
    "स्पॉटिफाई": "spotify", "पेंट": "paint", "सेटिंग्स": "settings",
    "सेटिंग": "settings", "यूट्यूब": "youtube", "युट्यूब": "youtube",
    "फोल्डर": "folder", "कैमरा": "camera", "कैमेरा": "camera",
    "वीएस कोड": "vs code", "कंट्रोल पैनल": "control panel",
}
_HINDI_ALIASES = [
    (r"^\s*(?:रुको|रुक जाओ|सब बंद(?: करो| कर दो)?|ruko|sab band(?: karo)?)\s*$", lambda m: "stop"),
    (rf"{_CAM}.*(?:बंद|band)", lambda m: "close camera"),
    (rf"{_CAM}.*{_V_OPEN}", lambda m: "open camera"),
    (r"(?:फोटो|फ़ोटो|तस्वीर|photo|tasveer|picture|pic)\s*(?:खींचो|खींच|खीचो|लो|ले|kheencho|kheench|khicho|lo|le)\b",
     lambda m: "take a picture"),
    (r"(?:गाना|गाने|संगीत|म्यूजिक|music|gana|gaana|song).*(?:बंद|रोक|band|rok)",
     lambda m: "stop the music"),
    (rf"^\s*(?:यूट्यूब|युट्यूब|youtube)\s*(?:पर|par|pe)\s+(.+?)\s*{_V_PLAY}\s*$",
     lambda m: f"play {m.group(1).strip()} on youtube"),
    (rf"^\s*(.+?)\s+(?:यूट्यूब|युट्यूब|youtube)\s*(?:पर|par|pe)\s*{_V_PLAY}\s*$",
     lambda m: f"play {m.group(1).strip()} on youtube"),
    (rf"^\s*(.+?)\s*{_V_PLAY}\s*$", lambda m: f"play {m.group(1).strip()} on youtube"),
    (r"(?:समय|टाइम|samay|बजे|baje|time\s*kya|kya\s*time)", lambda m: "what is the time"),
    (r"(?:तारीख|तारिख|tareekh|tarikh)", lambda m: "what is the date"),
    (r"(?:फोल्डर|फ़ोल्डर|folder).*(?:बना|banao|bana)", lambda m: "create a folder"),
    (r"(?:फाइल|फ़ाइल|file).*(?:बना|banao|bana)", lambda m: "create a file"),
    (r"(?:सो\s*जा(?:ओ)?|so\s*ja(?:o)?\b)", lambda m: "go to sleep"),
    (r"(?:मौसम|mausam|तापमान|taapman)", lambda m: "weather today"),
    (r"(?:मैं\s*कौन|मै\s*कौन|main\s*kaun|mai\s*kaun|मेरा\s*नाम)", lambda m: "who am i"),
    (r"^\s*(.+?)\s*(?:के\s*बारे\s*में\s*बताओ|ke\s*bare\s*me(?:in)?\s*batao)\s*$",
     lambda m: f"what is {m.group(1).strip()}"),
    (r"^\s*(.+?)\s*(?:क्या\s*है|क्या\s*होता\s*है|kya\s*hai|kya\s*hota\s*hai)\s*[?।]?\s*$",
     lambda m: f"what is {m.group(1).strip()}"),
    (rf"^\s*(.+?)\s*{_V_OPEN}\s*(?:दो|do|karo|करो)?\s*$",
     lambda m: "open " + _APP_NAMES.get(m.group(1).strip(), m.group(1).strip())),
]


def _hindi_to_command(text: str) -> str:
    """Turn Hindi/Hinglish phrases into the English commands Jarvis knows.
    Only active in Hindi mode or when the text contains Hindi letters."""
    t = _JARVIS_VARIANTS.sub("jarvis", text).strip()
    if not (HINDI_MODE or _DEVANAGARI.search(t)):
        return t
    body = re.sub(r"^\s*(?:hey|hello|ok|okay)?\s*jarvis[,.!]?\s*", "", t, flags=re.I)
    for pattern, build in _HINDI_ALIASES:
        m = re.search(pattern, body, re.I)
        if m:
            cmd = build(m)
            log.info("Hindi/Hinglish command %r -> %r", text, cmd)
            return cmd
    return t


# --- extra commands: volume, screenshot, timer, lock, google, jokes, tufani ---
def _press_media_key(vk: int, times: int = 1) -> None:
    if sys.platform != "win32":
        return
    import ctypes

    user32 = ctypes.windll.user32
    for _ in range(times):
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, 2, 0)


def _take_screenshot() -> None:
    try:
        from PIL import ImageGrab
    except ImportError:
        speak_text("Sorry sir, screenshots need Pillow.", use_cache=False)
        return
    _, photo_dir, _ = _camera_env_config()
    try:
        photo_dir.mkdir(parents=True, exist_ok=True)
        path = photo_dir / f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png"
        try:
            img = ImageGrab.grab(all_screens=True)
        except TypeError:
            img = ImageGrab.grab()
        img.save(path)
        log.info("Saved screenshot: %s", path)
        speak_text("Screenshot saved, sir.", use_cache=False)
    except Exception as e:
        log.warning("Screenshot failed: %s", e)
        speak_text("Sorry sir, I couldn't take a screenshot.", use_cache=False)


_TIMER_RE = re.compile(
    r"(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?|सेकंड|सेकण्ड|मिनट|घंटे|घंटा)", re.I
)


def _start_timer(t: str) -> None:
    m = _TIMER_RE.search(t)
    if not m:
        _say("For how long, sir? Say for example: set a timer for 5 minutes.")
        return
    amount = int(m.group(1))
    unit = m.group(2).lower()
    if unit.startswith(("sec", "सेक")):
        seconds, label = amount, "seconds"
    elif unit.startswith(("min", "मिन")):
        seconds, label = amount * 60, "minutes"
    else:
        seconds, label = amount * 3600, "hours"
    timer = threading.Timer(seconds, lambda: _say("Time is up, sir!"))
    timer.daemon = True
    timer.start()
    _active_timers.append(timer)
    log.info("Timer set for %d %s", amount, label)
    _say(f"Timer set for {amount} {label}, sir.")


def _lock_computer() -> None:
    speak_text("Locking the computer, sir.", use_cache=False)
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.LockWorkStation()


def _tufani_mode() -> None:
    speak_text(
        "All systems at full power, boss. Tufani mode activated. Let's make some noise!",
        use_cache=False,
    )
    play_song(SONG_URI)


_JOKES_EN = [
    "Why do programmers prefer dark mode? Because light attracts bugs.",
    "There are only 10 kinds of people: those who understand binary and those who don't.",
    "A SQL query walks into a bar, walks up to two tables and asks: can I join you?",
]
_BADHA = r"(?:ब[ढ\u095d]\u093c?ा|badha|up)"
_VOL_UP = re.compile(
    rf"(?:volume|आवाज़?|awaz|aawaz)\s*{_BADHA}|(?:increase|raise|turn up)\s+(?:the\s+)?volume|\blouder\b",
    re.I,
)
_VOL_DOWN = re.compile(
    r"(?:volume|आवाज़?|awaz|aawaz)\s*(?:कम|kam|down|घटा|ghata)"
    r"|(?:decrease|lower|reduce|turn down)\s+(?:the\s+)?volume|\bquieter\b",
    re.I,
)


def _handle_extra_commands(t: str) -> bool:
    """Returns True if t was one of the extra commands (and runs it)."""
    if re.search(r"tufani|toofani|tufaani|toofan|तूफानी|तूफ़ानी|तुफानी|तूफान", t):
        threading.Thread(target=_tufani_mode, daemon=True).start()
        return True

    if re.search(r"kya\s*h[ae]l|क्या\s*हाल|kaise\s*ho|कैसे\s*हो|how are you", t):
        _say("All systems at full power, boss. What's the plan?")
        return True

    if re.search(r"\bmute\b|\bunmute\b|म्यूट", t):
        _press_media_key(0xAD)
        _say("Done, sir.")
        return True
    if _VOL_UP.search(t):
        _press_media_key(0xAF, 5)
        _say("Volume up, sir.")
        return True
    if _VOL_DOWN.search(t):
        _press_media_key(0xAE, 5)
        _say("Volume down, sir.")
        return True

    if re.search(r"screen\s*shot|screenshot|स्क्रीन\s*शॉट|स्क्रीनशॉट", t):
        threading.Thread(target=_take_screenshot, daemon=True).start()
        return True

    if re.search(r"\btimer\b|टाइमर|remind me", t):
        _start_timer(t)
        return True

    if re.search(r"lock\s*(?:the\s*)?(?:computer|pc|laptop|screen|system)|कंप्यूटर\s*लॉक", t):
        threading.Thread(target=_lock_computer, daemon=True).start()
        return True

    if "youtube" not in t:
        m = (
            re.match(r"^google\s+(?:for\s+)?(.+)$", t.strip())
            or re.match(r"^search\s+(?:on\s+)?google\s+(?:for\s+)?(.+)$", t.strip())
            or re.match(r"^search\s+(.+?)\s+on\s+google$", t.strip())
        )
        if m:
            query = m.group(1).strip()
            _open_url_in_chrome(
                "https://www.google.com/search?q=" + urllib.parse.quote(query),
                new_window=True,
                label=f"google: {query}",
            )
            _say(f"Searching Google for {query}, sir.")
            return True

    if re.search(r"\bjoke\b|चुटकुला", t):
        _say(random.choice(_JOKES_EN))  # translated automatically in Hindi mode
        return True

    return False


# =============================================================================
# Voice command router
# =============================================================================
def handle_voice_command(text: str) -> bool | tuple[str, str]:
    """Match spoken text to a command.

    Returns True if something was run, False if nothing matched, or
    ("await_filename"/"await_foldername", drive) if a name is needed next.
    """
    t = text.lower()

    # "stop" -> stop everything running (checked first so nothing else grabs it)
    if _STOP_RE.match(t.strip()):
        threading.Thread(target=stop_everything, daemon=True).start()
        return True

    # "hey jarvis <request>" -> handle <request>; bare "hey jarvis" -> reply "Yes sir".
    m_wake = re.match(
        r"^\s*(?:hey|hello|ok|okay)?\s*"
        r"(?:jarvis|jealous|judges|xerox|travis|jervis|javis|garvis|jyada)\b[,.!]?\s*(.*)$",
        t,
    )
    if m_wake:
        rest = m_wake.group(1).strip()
        if not rest:
            try:
                sd.stop()
            except Exception:
                pass
            threading.Thread(target=speak_text, args=(WAKE_WORD_RESPONSE,), daemon=True).start()
            return True
        t = rest
        text = rest
        if _STOP_RE.match(t.strip()):
            threading.Thread(target=stop_everything, daemon=True).start()
            return True

    if _handle_extra_commands(t):
        return True

    if re.search(r"\bsleep\b", t):
        threading.Thread(target=handle_sleep_command, daemon=True).start()
        return True

    if re.search(r"\bwho\s+am\s+i\b", t) or re.search(r"\b(?:what'?s|what is)\s+my\s+name\b", t):
        threading.Thread(
            target=speak_text, args=(USER_IDENTITY_RESPONSE,),
            kwargs={"use_cache": False}, daemon=True,
        ).start()
        return True

    if "calculate" in t or "compute" in t:
        threading.Thread(target=calculate_and_speak, args=(t,), daemon=True).start()
        return True

    if "stop" in t and ("music" in t or "song" in t):
        stop_song()
        return True

    if any(phrase in t for phrase in WAKE_UP_MUSIC_PHRASES):
        log.info("Wake-up-buddy phrase heard - starting music + welcome flow (same as double clap).")
        threading.Thread(target=run_double_clap_actions, daemon=True).start()
        return True

    if any(phrase in t for phrase in WAKE_WORD_PHRASES):
        log.info("Wake word heard - stopping anything running and replying.")
        try:
            sd.stop()
        except Exception:
            pass
        threading.Thread(
            target=speak_text, args=(WAKE_WORD_RESPONSE,), daemon=True
        ).start()
        return True

    # "close chrome" / "close this" / "close window" - Windows only.
    if t.strip().startswith("close ") or t.strip() == "close":
        target = re.sub(r"^(?:the|my|this|a|an)\s+", "", t.strip()[len("close"):].strip())
        close_app_or_window(target)
        return True

    # "create a folder" / "make a new folder in d drive" / "create folder named X"
    if ("create" in t or "make" in t) and "folder" in t:
        drive = CREATE_FILE_DEFAULT_DRIVE
        dm = re.search(r"\b([a-z])\s*drive\b", t)
        if dm:
            drive = f"{dm.group(1).upper()}:\\"
        m = re.search(r"(?:named|name|called|call)\s+([a-z0-9_\-\.]+)", t)
        if m:
            threading.Thread(
                target=create_folder_on_drive, args=(m.group(1), drive), daemon=True
            ).start()
            return True
        return ("await_foldername", drive)

    # "create a file named report on d drive"
    if ("create" in t or "make" in t) and "file" in t:
        drive = CREATE_FILE_DEFAULT_DRIVE
        dm = re.search(r"\b([a-z])\s*drive\b", t)
        if dm:
            drive = f"{dm.group(1).upper()}:\\"
        m = re.search(r"(?:named|name|called|call)\s+([a-z0-9_\-\.]+)", t)
        if m:
            threading.Thread(
                target=create_file_on_drive, args=(m.group(1), drive), daemon=True
            ).start()
            return True
        return ("await_filename", drive)

    # "where is jarvis.py" / "find jarvis.py" / "locate report.txt"
    m_locate = re.match(
        r"^(?:jarvis[,]?\s*)?(?:where is|where's|wheres|find|locate|"
        r"(?:file\s+)?location of)\s+(?:the\s+|my\s+)?(?:file\s+)?([\w\-. ]+?)"
        r"(?:\s+file)?(?:\s+located)?[\.\?]*$",
        t.strip(),
    )
    if m_locate:
        name = m_locate.group(1).strip()
        if name:
            threading.Thread(
                target=speak_file_location, args=(name,), daemon=True
            ).start()
            return True

    # "run jarvis.py" / "open jarvis.py and run it"
    m_run = re.search(r"\b(?:run|execute)\s+(?:the\s+)?(?:file\s+)?([\w\-.]+)", t)
    if not m_run:
        m_run = re.search(r"\bopen\s+([\w\-.]+)\b.*\brun\b", t)
    if m_run:
        filename = m_run.group(1).strip()
        if filename:
            threading.Thread(
                target=open_and_run_file, args=(filename,), daemon=True
            ).start()
            return True

    # "show me my recent picture"
    if ("picture" in t or "photo" in t or "image" in t) and (
        "recent" in t or "last" in t or "latest" in t
    ):
        threading.Thread(target=open_recent_picture, daemon=True).start()
        return True

    # "take a picture" / "take a photo"
    if "picture" in t or "photo" in t:
        threading.Thread(target=take_picture, daemon=True).start()
        return True

    # "start video recording" / "stop recording"
    if "recording" in t or ("video" in t and ("start" in t or "record" in t)):
        if "stop" in t:
            threading.Thread(target=stop_video_recording, daemon=True).start()
        else:
            threading.Thread(target=start_video_recording, daemon=True).start()
        return True

    # "search youtube for shape of you" / "play shape of you on youtube"
    if "youtube" in t and ("search" in t or "play" in t):
        query = t
        for word in ("search", "on youtube", "youtube", "playing", "play", "just", "open", "for"):
            query = query.replace(word, " ")
        query = " ".join(query.split()).strip()
        threading.Thread(
            target=search_and_play_youtube, args=(query,), daemon=True
        ).start()
        return True

    if re.search(r"\b(date|time)\b", t):
        threading.Thread(target=announce_datetime, daemon=True).start()
        return True

    if re.search(r"where am i|my (?:current )?location|current location", t):
        threading.Thread(target=speak_current_location, daemon=True).start()
        return True

    if "distance" in t or "how far" in t:
        threading.Thread(target=speak_distance_between, args=(t,), daemon=True).start()
        return True

    m_weather = re.search(
        r"(?:temperature|weather)(?:\s+(?:today|now|currently))?"
        r"(?:\s+(?:in|at|for)\s+(.+))?$",
        t,
    )
    if "temperature" in t or "weather" in t:
        place = m_weather.group(1).strip() if m_weather and m_weather.group(1) else None
        threading.Thread(target=speak_temperature, args=(place,), daemon=True).start()
        return True

    m_question = re.match(
        r"^(?:jarvis[,]?\s*)?(?:what is|what's|whats|who is|who's|whos|define|"
        r"explain|tell me about|what are|how many|how does|how do|how is|why|"
        r"when|where|list|name the|give me|mention)\s+(.+?)[\.\?]*$",
        t.strip(),
    )
    if m_question and (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        return False  # conversational question -> Claude
    if m_question:
        term = m_question.group(1).strip()
        if term:
            threading.Thread(
                target=answer_question_and_search, args=(term,), daemon=True
            ).start()
            return True

    if "camera" in t:
        open_camera_app()
        return True
    if "folder" in t:
        open_voice_command_folder()
        return True
    if "youtube" in t:
        open_youtube()
        return True

    # Generic fallback: "open <anything>"
    m_open = re.search(r"\bopen\s+(.+)$", t.strip())
    if m_open:
        app_name = m_open.group(1).strip()
        for filler in (" please", " now", " for me"):
            if app_name.endswith(filler):
                app_name = app_name[: -len(filler)].strip()
        if app_name:
            threading.Thread(
                target=open_app_by_name, args=(app_name,), daemon=True
            ).start()
            return True

    return False


def _voice_mic_index() -> int | None:
    raw = (os.environ.get("JARVIS_MIC_INDEX") or "").strip()
    return int(raw) if raw.isdigit() else None


def voice_command_listener() -> None:
    """Runs in a background thread, listening for spoken commands via the mic."""
    try:
        import speech_recognition as sr
    except ImportError:
        log.warning(
            "Voice commands need the SpeechRecognition + pyaudio packages: "
            "pip install SpeechRecognition pyaudio"
        )
        return

    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True
    mic = None
    for attempt in range(1, 6):
        try:
            mic = sr.Microphone(device_index=_voice_mic_index())
            with mic as source:
                recognizer.adjust_for_ambient_noise(source, duration=1)
            break
        except Exception as e:
            log.warning("Voice mic setup failed (try %d/5): %s", attempt, e)
            mic = None
            time.sleep(2.0)
    if mic is None:
        log.error(
            "Voice commands DISABLED: could not open the microphone. "
            "Run: python -c \"import speech_recognition as sr; "
            "print(sr.Microphone.list_microphone_names())\""
        )
        return

    log.info(
        "Voice commands ready - say \"hindi me baat karte hai\" for Hindi, \"english\" for English, "
        "\"stop\" to stop everything, or \"sleep\" to shut Jarvis down."
    )

    awaiting_filename_drive: str | None = None
    awaiting_kind = "file"

    while True:
        try:
            while _is_speaking():  # do not listen to our own voice
                time.sleep(0.1)
            log.info("Listening...")
            with mic as source:
                audio = recognizer.listen(
                    source, phrase_time_limit=VOICE_COMMAND_PHRASE_TIME_LIMIT
                )
            text = recognizer.recognize_google(audio, language=_stt_language())
            log.info("Heard: %r", text)

            if awaiting_filename_drive is not None:
                drive = awaiting_filename_drive
                awaiting_filename_drive = None
                filename = text.strip()
                if filename:
                    threading.Thread(
                        target=(create_folder_on_drive if awaiting_kind == "folder" else create_file_on_drive),
                        args=(filename, drive),
                        daemon=True,
                    ).start()
                else:
                    log.info("No name heard - cancelling create command.")
                continue

            # Hindi / English mode switch
            if _handle_mode_switch(text):
                continue
            text = _hindi_to_command(text)

            result = handle_voice_command(text)
            if isinstance(result, tuple) and result[0] in ("await_filename", "await_foldername"):
                awaiting_kind = "folder" if result[0] == "await_foldername" else "file"
                awaiting_filename_drive = result[1]
                speak_text(
                    "What's the folder name, sir?" if awaiting_kind == "folder"
                    else "What's the file name, sir?"
                )
            elif not result:
                threading.Thread(
                    target=_study_fallback_or_log, args=(text,), daemon=True
                ).start()
        except sr.UnknownValueError:
            continue
        except sr.RequestError as e:
            log.warning("Voice command request failed (check internet): %s", e)
            time.sleep(2.0)
        except Exception as e:
            log.warning("Voice command listener error: %s", e)
            time.sleep(1.0)


# =============================================================================
# Chrome / Cursor / VS Code window helpers
# =============================================================================
def _chrome_executable() -> str | None:
    if sys.platform == "win32":
        for base in (
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        ):
            if not base:
                continue
            p = os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")
            if os.path.isfile(p):
                return p
    return shutil.which("google-chrome") or shutil.which("chrome")


def _win32_sorted_monitor_rects() -> list[tuple[int, int, int, int]]:
    """Each monitor as (left, top, right, bottom), sorted left-to-right then top-to-bottom."""
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", wintypes.LONG),
            ("top", wintypes.LONG),
            ("right", wintypes.LONG),
            ("bottom", wintypes.LONG),
        ]

    collected: list[tuple[int, int, int, int]] = []

    @ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(RECT),
        wintypes.LPARAM,
    )
    def _cb(_hm, _hdc, lprc, _lp):
        r = lprc.contents
        collected.append((int(r.left), int(r.top), int(r.right), int(r.bottom)))
        return True

    ctypes.windll.user32.EnumDisplayMonitors(None, None, _cb, 0)
    collected.sort(key=lambda t: (t[0], t[1]))
    return collected


def _chrome_monitor_top_left(one_based_index: int) -> tuple[int, int]:
    l, t, _, _ = _chrome_monitor_bounds(one_based_index)
    return (l, t)


def _chrome_monitor_bounds(one_based_index: int) -> tuple[int, int, int, int]:
    rects = _win32_sorted_monitor_rects()
    if not rects:
        return (0, 0, 1920, 1080)
    idx = one_based_index - 1
    if idx < 0:
        idx = 0
    if idx >= len(rects):
        log.warning(
            "Monitor %d requested but only %d found; using last monitor.",
            one_based_index,
            len(rects),
        )
        idx = len(rects) - 1
    return rects[idx]


def _chrome_monitor_pixel_size(one_based_index: int) -> tuple[int, int]:
    l, t, r, b = _chrome_monitor_bounds(one_based_index)
    return (max(320, r - l), max(240, b - t))


def _chrome_window_size() -> tuple[int, int]:
    w = (os.environ.get("CHROME_WINDOW_WIDTH") or "1400").strip()
    h = (os.environ.get("CHROME_WINDOW_HEIGHT") or "900").strip()
    try:
        return (max(400, int(w)), max(300, int(h)))
    except ValueError:
        return (1400, 900)


def _chrome_site_user_data_dir(site_key: str) -> str:
    p = Path(tempfile.gettempdir()) / "clap-trigger-chrome" / site_key
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def _chrome_new_window_wait_timeout_s() -> float:
    try:
        return max(3.0, float((os.environ.get("CHROME_NEW_WINDOW_WAIT_S") or "25").strip()))
    except ValueError:
        return 25.0


def _chrome_top_level_browser_hwnds_win32() -> set[int]:
    """HWND ints for visible-or-minimized top-level Chrome browser windows."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    GW_OWNER = 4
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    found: set[int] = set()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd: wintypes.HWND, _lp: wintypes.LPARAM) -> bool:
        if user32.GetWindow(hwnd, GW_OWNER):
            return True
        if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        if not user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return True
        hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not hproc:
            return True
        try:
            buf = ctypes.create_unicode_buffer(4096)
            sz = wintypes.DWORD(len(buf))
            if not kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(sz)):
                return True
            exe_path = buf.value
        finally:
            kernel32.CloseHandle(hproc)
        if os.path.basename(exe_path).lower() != "chrome.exe":
            return True
        r = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return True
        w, h = r.right - r.left, r.bottom - r.top
        if w < 80 or h < 80:
            return True
        found.add(int(hwnd))
        return True

    user32.EnumWindows(_enum, 0)
    return found


def _wait_new_chrome_hwnd_win32(before: set[int], timeout: float) -> int | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.12)
        now = _chrome_top_level_browser_hwnds_win32()
        new = now - before
        if not new:
            continue
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        best: int | None = None
        best_area = 0
        for h in new:
            r = wintypes.RECT()
            if user32.GetWindowRect(h, ctypes.byref(r)):
                a = max(0, r.right - r.left) * max(0, r.bottom - r.top)
                if a > best_area:
                    best_area = a
                    best = h
        if best is not None:
            return best
    return None


def _chrome_snap_window_to_monitor_win32(
    hwnd: int,
    one_based_monitor: int,
    *,
    fullscreen: bool,
    windowed_size: tuple[int, int] | None,
) -> None:
    import ctypes
    from ctypes import wintypes

    ml, mt, mr, mb = _chrome_monitor_bounds(one_based_monitor)
    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    SW_SHOWMAXIMIZED = 3
    HWND_TOP = 0
    SWP_SHOWWINDOW = 0x0040
    SWP_FRAMECHANGED = 0x0020
    flags = SWP_SHOWWINDOW | SWP_FRAMECHANGED

    user32.ShowWindow(hwnd, SW_RESTORE)
    if fullscreen:
        w, h = mr - ml, mb - mt
        x, y = ml, mt
    else:
        ww, wh = windowed_size or _chrome_window_size()
        w, h = ww, wh
        x = ml + max(0, (mr - ml - w) // 2)
        y = mt + max(0, (mb - mt - h) // 2)
    user32.SetWindowPos(hwnd, HWND_TOP, x, y, w, h, flags)

    if fullscreen:
        user32.ShowWindow(hwnd, SW_SHOWMAXIMIZED)
        KEYEVENTF_KEYUP = 0x0002
        VK_F11 = 0x7A
        fg = user32.GetForegroundWindow()
        tid_tgt = user32.GetWindowThreadProcessId(hwnd, None)
        tid_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        if tid_fg and tid_tgt:
            user32.AttachThreadInput(tid_fg, tid_tgt, True)
        user32.SetForegroundWindow(hwnd)
        if tid_fg and tid_tgt:
            user32.AttachThreadInput(tid_fg, tid_tgt, False)
        user32.keybd_event(VK_F11, 0, 0, 0)
        user32.keybd_event(VK_F11, 0, KEYEVENTF_KEYUP, 0)


def _open_url_in_chrome(
    url: str,
    *,
    new_window: bool = True,
    label: str = "URL",
    window_position: tuple[int, int] | None = None,
    window_size: tuple[int, int] | None = None,
    fullscreen: bool = False,
    win32_post_fullscreen_monitor: int | None = None,
    user_data_dir: str | None = None,
) -> None:
    u = url.strip()
    if not u:
        return
    chrome = _chrome_executable()
    try:
        if chrome:
            args = [chrome]
            if user_data_dir:
                args.append(f"--user-data-dir={user_data_dir}")
                args.append("--no-first-run")
            if new_window:
                args.append("--new-window")
            if window_position is not None:
                x, y = window_position
                args.append(f"--window-position={x},{y}")
            if window_size:
                args.append(f"--window-size={window_size[0]},{window_size[1]}")
            if fullscreen and not (
                sys.platform == "win32" and win32_post_fullscreen_monitor is not None
            ):
                args.append("--start-fullscreen")
            args.append(u)
            popen_kw: dict = {
                "args": args,
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if sys.platform == "win32":
                popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
            before: set[int] | None = None
            if sys.platform == "win32" and win32_post_fullscreen_monitor is not None:
                before = _chrome_top_level_browser_hwnds_win32()
            subprocess.Popen(**popen_kw)
            if sys.platform == "win32" and win32_post_fullscreen_monitor is not None:
                mon = win32_post_fullscreen_monitor
                hwnd = _wait_new_chrome_hwnd_win32(before, _chrome_new_window_wait_timeout_s())
                if hwnd is not None:
                    _chrome_snap_window_to_monitor_win32(
                        hwnd,
                        mon,
                        fullscreen=fullscreen,
                        windowed_size=window_size if not fullscreen else None,
                    )
                else:
                    log.warning(
                        "Chrome: timed out waiting for new window (%s); check "
                        "CHROME_NEW_WINDOW_WAIT_S or close extra Chrome instances.",
                        label,
                    )
        else:
            log.warning("Chrome not found; opening %s in default browser.", label)
            webbrowser.open(u)
    except OSError as e:
        log.warning("Could not open %s in Chrome: %s", label, e)


def open_claude_in_chrome() -> None:
    if not OPEN_CLAUDE_CODE_IN_CHROME:
        return
    url = (os.environ.get("CLAUDE_CODE_URL") or "https://claude.ai/new").strip()
    pos: tuple[int, int] | None = None
    size: tuple[int, int] | None = None
    fs = OPEN_CHROME_FULLSCREEN
    post_mon: int | None = None
    user_data: str | None = None
    if sys.platform == "win32":
        post_mon = CLAUDE_CHROME_MONITOR
        pos = _chrome_monitor_top_left(CLAUDE_CHROME_MONITOR)
        if fs:
            size = _chrome_monitor_pixel_size(CLAUDE_CHROME_MONITOR)
        else:
            size = _chrome_window_size()
        if CHROME_SEPARATE_SITE_PROFILES:
            user_data = _chrome_site_user_data_dir("claude")
    elif not fs:
        size = _chrome_window_size()
    _open_url_in_chrome(
        url,
        new_window=True,
        label="Claude",
        window_position=pos,
        window_size=size,
        fullscreen=fs,
        win32_post_fullscreen_monitor=post_mon,
        user_data_dir=user_data,
    )


def open_binance_btc_in_chrome() -> None:
    if not OPEN_BINANCE_BTC_IN_CHROME:
        return
    url = (
        os.environ.get("BINANCE_BTC_URL")
        or "https://www.binance.com/en/trade/BTC_USDT"
    ).strip()
    pos: tuple[int, int] | None = None
    size: tuple[int, int] | None = None
    fs = OPEN_CHROME_FULLSCREEN
    post_mon: int | None = None
    user_data: str | None = None
    if sys.platform == "win32":
        post_mon = BINANCE_CHROME_MONITOR
        pos = _chrome_monitor_top_left(BINANCE_CHROME_MONITOR)
        if fs:
            size = _chrome_monitor_pixel_size(BINANCE_CHROME_MONITOR)
        else:
            size = _chrome_window_size()
        if CHROME_SEPARATE_SITE_PROFILES:
            user_data = _chrome_site_user_data_dir("binance")
    elif not fs:
        size = _chrome_window_size()
    _open_url_in_chrome(
        url,
        new_window=True,
        label="Binance BTC",
        window_position=pos,
        window_size=size,
        fullscreen=fs,
        win32_post_fullscreen_monitor=post_mon,
        user_data_dir=user_data,
    )


def _cursor_executable() -> str | None:
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        for sub in ("Programs\\cursor\\Cursor.exe", "Programs\\Cursor\\Cursor.exe"):
            if local:
                p = os.path.join(local, *sub.split("\\"))
                if os.path.isfile(p):
                    return p
    return shutil.which("cursor")


def _cursor_largest_main_hwnd_win32() -> int | None:
    """Largest top-level Cursor.exe window (visible or minimized)."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    GW_OWNER = 4
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    candidates: list[tuple[int, wintypes.HWND]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd: wintypes.HWND, _lp: wintypes.LPARAM) -> bool:
        if user32.GetWindow(hwnd, GW_OWNER):
            return True
        if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return True
        if not user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return True
        hproc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not hproc:
            return True
        try:
            buf = ctypes.create_unicode_buffer(4096)
            sz = wintypes.DWORD(len(buf))
            if not kernel32.QueryFullProcessImageNameW(hproc, 0, buf, ctypes.byref(sz)):
                return True
            exe_path = buf.value
        finally:
            kernel32.CloseHandle(hproc)
        if os.path.basename(exe_path).lower() != "cursor.exe":
            return True
        r = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
            return True
        w, h = r.right - r.left, r.bottom - r.top
        if w < 200 or h < 200:
            return True
        candidates.append((w * h, hwnd))
        return True

    user32.EnumWindows(_enum, 0)
    if not candidates:
        return None
    return int(max(candidates, key=lambda t: t[0])[1])


def _cursor_foreground_hwnd_win32(hwnd: int) -> None:
    import ctypes

    user32 = ctypes.windll.user32
    SW_RESTORE = 9
    user32.ShowWindow(hwnd, SW_RESTORE)
    fg = user32.GetForegroundWindow()
    tid_tgt = user32.GetWindowThreadProcessId(hwnd, None)
    tid_fg = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    if tid_fg and tid_tgt:
        user32.AttachThreadInput(tid_fg, tid_tgt, True)
    user32.SetForegroundWindow(hwnd)
    if tid_fg and tid_tgt:
        user32.AttachThreadInput(tid_fg, tid_tgt, False)


def _cursor_send_f11_fullscreen_win32(hwnd: int) -> None:
    import ctypes

    user32 = ctypes.windll.user32
    KEYEVENTF_KEYUP = 0x0002
    VK_F11 = 0x7A
    _cursor_foreground_hwnd_win32(hwnd)
    user32.keybd_event(VK_F11, 0, 0, 0)
    user32.keybd_event(VK_F11, 0, KEYEVENTF_KEYUP, 0)


def _focus_existing_cursor_window_win32() -> bool:
    if sys.platform != "win32":
        return False
    hwnd = _cursor_largest_main_hwnd_win32()
    if hwnd is None:
        return False
    _cursor_foreground_hwnd_win32(hwnd)
    return True


def _vscode_executable() -> str | None:
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            p = os.path.join(local, "Programs", "Microsoft VS Code", "Code.exe")
            if os.path.isfile(p):
                return p
    found = shutil.which("code")
    if found:
        return found
    return shutil.which("code.cmd")


def open_vscode_window() -> None:
    if not OPEN_VSCODE_ON_DOUBLE_CLAP:
        return
    exe = _vscode_executable()
    if not exe:
        log.warning(
            "Could not find VS Code (install it, or add `code` to PATH via "
            "'Shell Command: Install code command in PATH' from VS Code's command palette)."
        )
        return
    popen_kw: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        subprocess.Popen([exe, VSCODE_FOLDER_PATH], **popen_kw)
        log.info("Opened VS Code: %s", VSCODE_FOLDER_PATH)
    except OSError as e:
        log.warning("Could not start VS Code: %s", e)


def open_jarvis_ui() -> None:
    """Open the particle-sphere HTML visual in the default browser (startup UI)."""
    if not JARVIS_UI_ENABLED:
        return
    ui_path = Path(JARVIS_UI_HTML_PATH)
    if not ui_path.is_file():
        log.warning(
            "Jarvis UI file not found at %s - skipping (JARVIS_UI_ENABLED=True but "
            "the HTML file is missing; place jarvis_ui.html next to jarvis.py or "
            "update JARVIS_UI_HTML_PATH).",
            ui_path,
        )
        return
    try:
        webbrowser.open(ui_path.resolve().as_uri())
        log.info("Opened Jarvis UI: %s", ui_path)
    except Exception as e:
        log.warning("Could not open Jarvis UI (%s): %s", ui_path, e)


def run_double_clap_actions() -> None:
    """Run outside the mic loop so sleeps do not stall capture."""
    play_song(SONG_URI)
    if JARVIS_WELCOME_ENABLED and JARVIS_WELCOME_PHRASE.strip():
        delay = max(0.0, JARVIS_AFTER_SONG_DELAY_S)
        if delay:
            time.sleep(delay)
        threading.Thread(target=say_jarvis_welcome, daemon=True).start()
    open_vscode_window()


def open_cursor_window() -> None:
    if not FOCUS_EXISTING_CURSOR_ON_DOUBLE_CLAP and not OPEN_NEW_CURSOR_ON_DOUBLE_CLAP:
        return
    exe = _cursor_executable()
    if not exe:
        log.warning(
            "Could not find Cursor (install app or add the `cursor` command to PATH)."
        )
        return
    popen_kw: dict = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        popen_kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        if FOCUS_EXISTING_CURSOR_ON_DOUBLE_CLAP:
            focused = (
                sys.platform == "win32" and _focus_existing_cursor_window_win32()
            )
            if not focused:
                subprocess.Popen([exe], **popen_kw)
        if OPEN_NEW_CURSOR_ON_DOUBLE_CLAP:
            subprocess.Popen([exe, "-n"], **popen_kw)
    except OSError as e:
        log.warning("Could not start or focus Cursor: %s", e)
        return
    if sys.platform == "win32" and CURSOR_OPEN_FULLSCREEN:
        time.sleep(0.5)
        hwnd = _cursor_largest_main_hwnd_win32()
        if hwnd is not None:
            _cursor_send_f11_fullscreen_win32(hwnd)
        else:
            log.warning("Cursor fullscreen: no Cursor window found to send F11.")


# =============================================================================
# Main: double-clap detector
# =============================================================================
def main() -> int:
    blocksize = block_samples()
    noise_floor = 1e-4
    last_logged_double = 0.0
    first_clap_time: float | None = None
    spike_armed = True
    welcome_sequence_done = False

    log.info(
        "Listening (double clap: %.2f-%.2fs apart, rate=%d, block=%d ms, "
        "spike_ratio=%.1f, cooldown=%.2fs). Ctrl+C to stop.",
        MIN_DOUBLE_GAP_S,
        MAX_DOUBLE_GAP_S,
        SAMPLE_RATE,
        BLOCK_MS,
        SPIKE_RATIO,
        COOLDOWN_S,
    )
    open_jarvis_ui()

    if SONG_URI.strip():
        log.info("Double clap opens this track: %s", SONG_URI.strip())
    else:
        log.info("SONG_URI is empty - set it to play one song on each double clap.")
    if PLAY_SONG_ON_STARTUP and SONG_URI.strip():
        log.info("Playing startup song: %s", SONG_URI.strip())
        play_song(SONG_URI)

    if VOICE_COMMANDS_ENABLED:
        threading.Thread(target=voice_command_listener, daemon=True).start()

    if FOCUS_EXISTING_CURSOR_ON_DOUBLE_CLAP:
        log.info(
            "Double clap will foreground an existing Cursor window (Windows API); "
            "falls back to launching Cursor if none is running."
        )
    if OPEN_NEW_CURSOR_ON_DOUBLE_CLAP:
        log.info("Double clap will also open a new Cursor window (-n).")
    if CURSOR_OPEN_FULLSCREEN and sys.platform == "win32":
        log.info("Cursor will be sent F11 for fullscreen after focus/launch.")
    if OPEN_CLAUDE_CODE_IN_CHROME:
        cu = (os.environ.get("CLAUDE_CODE_URL") or "https://claude.ai/new").strip()
        log.info(
            "After Spotify, open Claude in Chrome%s on monitor %d: %s",
            " fullscreen" if OPEN_CHROME_FULLSCREEN else "",
            CLAUDE_CHROME_MONITOR,
            cu,
        )
    if OPEN_BINANCE_BTC_IN_CHROME:
        bu = (
            os.environ.get("BINANCE_BTC_URL")
            or "https://www.binance.com/en/trade/BTC_USDT"
        ).strip()
        log.info(
            "After Spotify, open Binance BTC in Chrome%s on monitor %d: %s",
            " fullscreen" if OPEN_CHROME_FULLSCREEN else "",
            BINANCE_CHROME_MONITOR,
            bu,
        )
    if JARVIS_WELCOME_ENABLED:
        ev, em, ef, er = elevenlabs_env_config()
        log.info(
            "After song + %.2fs: %r (ElevenLabs voice=%s, model=%s, format=%s, pcm_rate=%d)",
            JARVIS_AFTER_SONG_DELAY_S,
            JARVIS_WELCOME_PHRASE.strip(),
            ev or "(unset)",
            em,
            ef,
            er,
        )

    input_idx = _choose_input_device(blocksize)

    try:
        with sd.InputStream(
            device=input_idx,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=blocksize,
        ) as stream:
            while True:
                data, overflowed = stream.read(blocksize)
                if overflowed:
                    log.warning("Input overflow; try a larger BLOCK_MS")

                level = rms_mono(data)

                quiet_gate = noise_floor * QUIET_GATE_MULT
                if level < quiet_gate:
                    noise_floor = NOISE_FLOOR_ALPHA * noise_floor + (
                        1.0 - NOISE_FLOOR_ALPHA
                    ) * level
                    noise_floor = max(noise_floor, 1e-7)

                threshold = max(noise_floor * SPIKE_RATIO, MIN_RMS)
                now = time.monotonic()
                retrigger_level = threshold * RETRIGGER_RATIO

                if level < retrigger_level:
                    spike_armed = True

                if (
                    spike_armed
                    and level >= threshold
                    and (now - last_logged_double) >= COOLDOWN_S
                ):
                    spike_armed = False
                    if first_clap_time is None:
                        first_clap_time = now
                    else:
                        gap = now - first_clap_time
                        if gap < MIN_DOUBLE_GAP_S:
                            pass
                        elif gap <= MAX_DOUBLE_GAP_S:
                            first_clap_time = None
                            last_logged_double = now
                            if not welcome_sequence_done:
                                welcome_sequence_done = True
                                log.info(
                                    "Double clap detected (gap=%.3fs, rms=%.5f, "
                                    "noise_floor=%.5f, threshold=%.5f) - running welcome once",
                                    gap,
                                    level,
                                    noise_floor,
                                    threshold,
                                )
                                threading.Thread(
                                    target=run_double_clap_actions, daemon=True
                                ).start()
                        else:
                            first_clap_time = now

    except KeyboardInterrupt:
        log.info("Stopped.")
        return 0
    except sd.PortAudioError as e:
        log.error("Audio error: %s", e)
        log.error("If PortAudio fails, install/repair drivers or try another SAMPLE_RATE.")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())