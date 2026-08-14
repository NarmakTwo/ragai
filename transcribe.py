import os
import subprocess
import tempfile
import wave

from dotenv import load_dotenv

load_dotenv()

_AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".webm", ".ogg", ".flac", ".mp4", ".mpeg", ".mpga"}
_MAX_BYTES = 25 * 1024 * 1024
_MAX_SECONDS = 10 * 60
_BOILERPLATE = {"thank you.", "thanks for watching.", "thank you", "you"}
_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3")


class TranscribeError(Exception):
    pass


def is_audio_path(path) -> bool:
    name = str(getattr(path, "name", path) or "")
    return os.path.splitext(name)[1].lower() in _AUDIO_EXTS


def _ffprobe_seconds(path):
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        return float(out.stdout.strip())
    except Exception:
        return None


def _duration_seconds(path):
    try:
        with wave.open(path, "rb") as w:
            rate = w.getframerate()
            if rate:
                return w.getnframes() / float(rate)
    except Exception:
        pass
    return _ffprobe_seconds(path)


def _to_wav(path):
    fd, dest = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-ac", "1", "-ar", "16000", dest],
            check=True,
            capture_output=True,
            timeout=60,
        )
    except FileNotFoundError:
        os.remove(dest)
        raise TranscribeError("ffmpeg is required to convert this audio format.")
    except subprocess.CalledProcessError as e:
        os.remove(dest)
        err = (e.stderr or b"").decode("utf-8", "replace")[-400:]
        raise TranscribeError(f"Could not convert audio.{(' ' + err) if err else ''}")
    return dest


def _check_limits(path):
    try:
        size = os.path.getsize(path)
    except OSError as e:
        raise TranscribeError(f"Could not read audio: {e}") from e
    if size > _MAX_BYTES:
        raise TranscribeError("Audio is larger than 25 MB.")
    if size < 256:
        raise TranscribeError("Audio file is empty or too short.")
    duration = _duration_seconds(path)
    if duration is not None and duration > _MAX_SECONDS:
        raise TranscribeError("Audio is longer than 10 minutes.")


def _looks_empty(text):
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return True
    if len(cleaned) < 3:
        return True
    return cleaned.lower().rstrip(".!") in _BOILERPLATE


def _client():
    from openai import OpenAI

    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise TranscribeError("GROQ_API_KEY is missing.")
    return OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")


def _call(path):
    with open(path, "rb") as f:
        return _client().audio.transcriptions.create(model=_MODEL, file=f)


def transcribe_audio(path: str) -> str:
    path = str(getattr(path, "name", path) or "")
    if not path or not os.path.isfile(path):
        raise TranscribeError("Record or upload audio first.")
    if not is_audio_path(path):
        raise TranscribeError("Not a supported audio file.")
    _check_limits(path)
    converted = None
    try:
        try:
            result = _call(path)
        except Exception as e:
            msg = str(e).lower()
            if "format" in msg or "file" in msg or "unsupported" in msg:
                converted = _to_wav(path)
                _check_limits(converted)
                result = _call(converted)
            else:
                raise TranscribeError(f"Transcription failed: {e}") from e
    finally:
        if converted:
            try:
                os.remove(converted)
            except OSError:
                pass
    text = getattr(result, "text", None) or str(result or "")
    text = text.strip()
    if _looks_empty(text):
        raise TranscribeError("No speech detected.")
    return text
