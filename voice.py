"""Hindi dub track: Gemini TTS per subtitle line, slot-fitted, cached in assets/dub."""
import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from pipeline import FFMPEG, ROOT, WORK, media_duration, run

MODEL = "gemini-2.5-flash-preview-tts"
MODELS = ["gemini-2.5-flash-preview-tts", "gemini-3.1-flash-tts-preview",
          "gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"]
DEFAULT_VOICE = "Kore"
DUB_DIR = ROOT / "assets" / "dub"
STYLE = ("Say this line like a Hindi film dubbing artist: warm, emotional, cinematic, "
         "natural, never robotic. Say only the line:")


class VoiceUnavailable(RuntimeError):
    pass


def _key():
    path = ROOT / "gemini_key.txt"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    import os
    return os.environ.get("GEMINI_API_KEY", "").strip()


def gemini_line(text, voice_name, out):
    body = {"contents": [{"parts": [{"text": f"{STYLE} {text}"}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {"voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice_name}}}}}
    data = json.dumps(body).encode("utf-8")
    for model in MODELS:
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            f"?key={_key()}",
            data=data, headers={"Content-Type": "application/json"})
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=180).read())
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:200].decode("utf-8", "replace")
            if exc.code == 429:
                print(f"TTS quota full on {model}, switching model")
                continue
            raise RuntimeError(f"gemini tts {exc.code}: {detail}")
        for part in resp["candidates"][0]["content"]["parts"]:
            blob = part.get("inlineData") or part.get("inline_data")
            if blob:
                pcm = WORK / "line.pcm"
                pcm.write_bytes(base64.b64decode(blob["data"]))
                run([FFMPEG, "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", pcm,
                     "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "24000", "-ac", "1", out])
                return out
        raise RuntimeError(f"gemini tts: no audio in response ({model})")
    raise VoiceUnavailable("all tts models quota full")


def line_audio(scene, k, sub):
    out = DUB_DIR / f"{Path(scene['file']).stem}_{k}.mp3"
    if out.exists() and out.stat().st_size > 1000:
        return out
    DUB_DIR.mkdir(parents=True, exist_ok=True)
    voice = sub.get("voice", DEFAULT_VOICE)
    for attempt in range(4):
        try:
            return gemini_line(sub["text"], voice, out)
        except VoiceUnavailable:
            raise
        except Exception as exc:
            print("GEMINI TTS retry", attempt + 1, exc)
            time.sleep(25 * (attempt + 1))
    raise VoiceUnavailable(sub["text"])


def make_dub(scene, dur):
    WORK.mkdir(exist_ok=True)
    files = [(line_audio(scene, k, sub), float(sub["start"]), float(sub["end"]))
             for k, sub in enumerate(scene["subs"])]
    parts, labels = [], []
    for k, (mp3, start, end) in enumerate(files):
        speed = max(1.0, min(media_duration(mp3) / max(end - start, 0.4), 2.0))
        ms = int(round(start * 1000))
        parts.append(f"[{k}:a]atempo={speed:.3f},aresample=48000,"
                     f"aformat=sample_fmts=fltp:channel_layouts=stereo,"
                     f"adelay={ms}|{ms}[l{k}]")
        labels.append(f"[l{k}]")
    graph = (";".join(parts)
             + f";{''.join(labels)}amix=inputs={len(files)}:duration=longest:normalize=0[voc]")
    out = WORK / "dub.wav"
    ins = [a for mp3, _, _ in files for a in ("-i", mp3)]
    run([FFMPEG, "-y", *ins, "-filter_complex", graph, "-map", "[voc]",
         "-c:a", "pcm_s16le", "-ar", "48000", out], cwd=WORK)
    return out
