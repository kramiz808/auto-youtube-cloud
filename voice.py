"""Hindi dub track: Gemini TTS per subtitle line, slot-fitted, cached in assets/dub."""
import base64
import json
import re
import subprocess
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


DRAMA_MODELS = ["gemini-3.8-flash-tts", "gemini-3.1-flash-tts-preview",
                "gemini-2.5-flash-preview-tts", "gemini-3.8-flash-lite-tts",
                "gemini-2.5-pro-preview-tts"]


def _dialogue_body(turns, cast, model):
    speakers = list(dict.fromkeys(t["speaker"] for t in turns))
    voices = {s: cast[s]["voice"] for s in speakers}
    if len(speakers) == 1:
        speech = {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voices[speakers[0]]}}}
    else:
        speech = {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": [
            {"speaker": s, "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": v}}}
            for s, v in voices.items()]}}
    if model.startswith("gemini-3.8"):
        parts = [{"text": t["text"],
                  "speechMetadata": {"speaker": t["speaker"],
                                     "style": t.get("emotion") or cast[t["speaker"]]["style"]}}
                 for t in turns]
    else:
        stage = ("Perform this as a Hindi audio drama. Act, do not read. Real emotion, natural "
                 "breaths and pauses, and clearly different voices for each character. ")
        stage += " ".join(f"{s} is {cast[s]['style']}." for s in speakers)
        text = (f"TTS the following conversation between {' and '.join(speakers)}. {stage}\n"
                + "\n".join(f"{t['speaker']}: {t['text']}" for t in turns))
        parts = [{"text": text}]
    return {"contents": [{"parts": parts}],
            "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": speech}}


def dialogue_audio(turns, cast, out, models=None):
    """Ek scene ke 1-2 characters ki expressive audio. Poora video isi ek engine se banta hai."""
    out = Path(out)
    for model in (models or DRAMA_MODELS):
        body = _dialogue_body(turns, cast, model)
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            f"?key={_key()}",
            data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"})
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=420).read())
        except urllib.error.HTTPError as exc:
            detail = exc.read()[:300].decode("utf-8", "replace")
            if exc.code == 429:
                print(f"drama TTS quota full on {model}, next model")
                continue
            if exc.code in (400, 404):
                print(f"drama TTS {exc.code} on {model}: {detail[:160]}")
                continue
            raise RuntimeError(f"drama tts {exc.code}: {detail}")
        except Exception as exc:
            print("drama TTS network retry", model, str(exc)[:120])
            time.sleep(15)
            continue
        cand = resp["candidates"][0]
        blob = next((p.get("inlineData") or p.get("inline_data") for p in cand["content"]["parts"]
                     if p.get("inlineData") or p.get("inline_data")), None)
        if not blob:
            print("drama TTS no audio", model, cand.get("finishReason"))
            continue
        if cand.get("finishReason") not in (None, "STOP"):
            print("drama TTS truncated", model, cand.get("finishReason"))
        WORK.mkdir(exist_ok=True)
        pcm = WORK / "drama.pcm"
        pcm.write_bytes(base64.b64decode(blob["data"]))
        run([FFMPEG, "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", pcm,
             "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", out])
        print(f"drama TTS {model}: {media_duration(out):.1f}s / {len(turns)} lines")
        return out
    raise VoiceUnavailable("saare drama TTS models ka quota full")


def silence_gaps(wav, min_gap=0.20, noise="-32dB"):
    r = subprocess.run([FFMPEG, "-i", str(wav), "-af",
                        f"silencedetect=noise={noise}:d={min_gap}", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace")
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return list(zip(starts, ends))


def align_lines(turns, duration, gaps):
    """Har line ka start/end. Char-weight se estimate, phir asli pause par snap — subtitles
    awaaz ke exact saath chalte hain (lip-sync ka audio equivalent)."""
    weights = [max(4, len(re.sub(r"\s+", "", t["text"]))) for t in turns]
    total = sum(weights)
    bounds, acc = [], 0.0
    for w in weights[:-1]:
        acc += w
        bounds.append(duration * acc / total)
    out, cursor = [], 0.0
    for i, est in enumerate(bounds):
        cands = [g for g in gaps if abs(g[0] - est) <= 1.8 and g[0] > cursor + 0.25]
        if cands:
            gap = min(cands, key=lambda g: abs(g[0] - est))
            end, nxt = gap[0], min(gap[1], duration)
        else:
            end, nxt = est, est
        end = max(end, cursor + 0.2)
        out.append((cursor, end))
        cursor = max(nxt, end)
    out.append((cursor, duration))
    return out


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
