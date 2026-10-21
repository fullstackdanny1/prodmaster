"""Transcrierea înregistrărilor: local cu faster-whisper sau prin API (/audio/transcriptions).

Transcrierea prin API nu ține de stratul AI comun: folosește furnizorul din
[transcriere].model_api (doar de tip openai) și cheia lui din ai.toml.
"""
import json
import shutil
import subprocess
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Callable

from .ai import config as aicfg
from .config import CFG

API_LIMIT_BYTES = 25 * 1024 * 1024
SEGMENT_SECONDS = 600
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac", ".aac", ".webm"}
VIDEO_EXT = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}
WHISPER_NATIVE = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}


class TranscriptionError(Exception):
    pass


def ffmpeg_missing_message() -> str:
    from . import system
    distro = system.detect_distro()
    cmd = system.install_command(["ffmpeg"], distro) if distro else None
    return ("Pentru înregistrări video sau formate audio neobișnuite e nevoie de ffmpeg. "
            + (f"Instalează-l cu: {cmd}" if cmd else "Instalează pachetul ffmpeg al distribuției tale."))


def duration_seconds(path: Path) -> float | None:
    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json",
                              str(path)], capture_output=True, text=True, timeout=60, check=True).stdout
        return float(json.loads(out)["format"]["duration"])
    except (subprocess.SubprocessError, ValueError, KeyError, OSError):
        return None


def to_wav(src: Path, dest: Path) -> Path:
    """Audio mono 16 kHz cu ffmpeg."""
    if not shutil.which("ffmpeg"):
        raise TranscriptionError(ffmpeg_missing_message())
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(src), "-vn", "-ac", "1",
                        "-ar", "16000", str(dest)], capture_output=True, text=True)
    if r.returncode != 0:
        raise TranscriptionError(f"ffmpeg nu a putut extrage sunetul: {r.stderr.strip()[:300]}")
    return dest


def needs_conversion(path: Path) -> bool:
    ext = path.suffix.lower()
    return ext in VIDEO_EXT or ext not in WHISPER_NATIVE


def _stamp(seconds: float) -> str:
    s = int(seconds)
    return f"[{s // 60:02d}:{s % 60:02d}]" if s < 3600 else f"[{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}]"


def paragraphs(segments, every: float = 60.0) -> str:
    """Segmente (start, end, text) → paragrafe cu marcaj de timp [mm:ss] la început."""
    out, cur, start = [], [], None
    for seg_start, _end, text in segments:
        text = text.strip()
        if not text:
            continue
        if start is None:
            start = seg_start
        cur.append(text)
        if seg_start - start >= every and text.endswith((".", "?", "!")):
            out.append(f"{_stamp(start)} {' '.join(cur)}")
            cur, start = [], None
    if cur:
        out.append(f"{_stamp(start or 0)} {' '.join(cur)}")
    return "\n\n".join(out) + "\n"


def transcribe_local(path: Path, progress: Callable[[float, str], None]) -> str:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise TranscriptionError(
            "Transcrierea locală nu e instalată. Rulează: ./studiu.sh --instaleaza-transcriere") from e
    progress(0, f"Încarc modelul de transcriere «{CFG.transcription_model}» (prima dată se descarcă)")
    model = WhisperModel(CFG.transcription_model, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(path), language=CFG.transcription_language or None, vad_filter=True)
    total = getattr(info, "duration", 0) or 1
    out = []
    for seg in segments:
        out.append((seg.start, seg.end, seg.text))
        progress(min(99, seg.end / total * 100), f"Transcriu: {_stamp(seg.end)} din {_stamp(total)}")
    return paragraphs(out)


def _multipart(fields: dict, file_field: str, path: Path) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
                 f'filename="{path.name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode())
    parts.append(path.read_bytes())
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _api_settings():
    cfg = aicfg.load()
    try:
        provider, model = aicfg.resolve_ref(cfg, CFG.transcription_api_model)
    except aicfg.ConfigError as e:
        raise TranscriptionError(f"[transcriere].model_api: {e}") from e
    p = cfg.providers[provider]
    if p.tip != "openai":
        raise TranscriptionError(f"Transcrierea prin API cere un furnizor de tip openai (nu «{p.tip}»).")
    key = aicfg.key_value(p, cfg)
    if p.cheie and not key:
        raise TranscriptionError(f"Lipsește cheia {p.cheie} în {cfg.env_path}.")
    return p, model, key


def transcribe_file_api(path: Path) -> list[tuple[float, float, str]]:
    p, model, key = _api_settings()
    body, ctype = _multipart({"model": model, "language": CFG.transcription_language,
                              "response_format": "verbose_json"}, "file", path)
    headers = {"Content-Type": ctype}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(f"{p.base_url}/audio/transcriptions", data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=max(p.timeout_s, 600)) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise TranscriptionError(f"Furnizorul «{p.name}» nu are endpoint /audio/transcriptions. "
                                     "Folosește [transcriere].mod = \"local\".") from e
        raise TranscriptionError(f"Transcrierea a eșuat (HTTP {e.code}): "
                                 f"{e.read().decode(errors='replace')[:300]}") from e
    except urllib.error.URLError as e:
        raise TranscriptionError(f"Nu pot contacta {p.base_url}: {e.reason}") from e
    segs = data.get("segments")
    if segs:
        return [(float(s.get("start", 0)), float(s.get("end", 0)), str(s.get("text", ""))) for s in segs]
    return [(0.0, 0.0, str(data.get("text", "")))]


def split_for_api(path: Path, workdir: Path) -> list[tuple[Path, float]]:
    if path.stat().st_size <= API_LIMIT_BYTES:
        return [(path, 0.0)]
    if not shutil.which("ffmpeg"):
        raise TranscriptionError(ffmpeg_missing_message())
    workdir.mkdir(parents=True, exist_ok=True)
    pattern = workdir / "segment-%03d.mp3"
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(path), "-f", "segment",
                        "-segment_time", str(SEGMENT_SECONDS), "-ac", "1", "-ar", "16000", "-b:a", "48k",
                        str(pattern)], capture_output=True, text=True)
    if r.returncode != 0:
        raise TranscriptionError(f"ffmpeg nu a putut împărți înregistrarea: {r.stderr.strip()[:300]}")
    return [(p, i * SEGMENT_SECONDS) for i, p in enumerate(sorted(workdir.glob("segment-*.mp3")))]


def transcribe_api(path: Path, workdir: Path, progress: Callable[[float, str], None]) -> str:
    parts = split_for_api(path, workdir)
    segments = []
    for k, (part, offset) in enumerate(parts):
        progress(k / len(parts) * 100, f"Transcriu prin API: bucata {k + 1} din {len(parts)}")
        segments += [(s + offset, e + offset, t) for s, e, t in transcribe_file_api(part)]
    return paragraphs(segments)


def transcribe(path: Path, workdir: Path, progress: Callable[[float, str], None]) -> str:
    if CFG.transcription_mode == "dezactivat":
        raise TranscriptionError("Transcrierea e dezactivată ([transcriere].mod = \"dezactivat\").")
    if CFG.transcription_mode == "api":
        return transcribe_api(path, workdir, progress)
    return transcribe_local(path, progress)
