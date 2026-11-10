"""Dialogue TTS with content-keyed caching and measured line timings."""
import asyncio
import hashlib
import json
import os
import re
import time
import wave
import urllib.error
import urllib.request
from functools import lru_cache
from pathlib import Path

from pipeline import FFMPEG, ROOT, WORK, media_duration, run

DEFAULT_VOICE = "CwhRBWXzGAHq8TQ4Fs17"
DUB_DIR = ROOT / "assets" / "dub" / "elevenlabs"
SAMPLE_RATE = 48000
LINE_GAP = 0.16
EDGE_RATE = {"angry": "+12%", "sad": "-10%", "nervous": "+14%", "whispers": "-8%"}
EDGE_PITCH = {"angry": "+8Hz", "sad": "-12Hz", "nervous": "+10Hz", "whispers": "-6Hz"}


class VoiceUnavailable(RuntimeError):
    pass


def tts_provider():
    return os.environ.get("TTS_PROVIDER", "").strip().casefold() or "elevenlabs"


def mood_tag(emotion):
    mood = (emotion or "").casefold()
    for label, words in (
        ("whispers", ("whisper", "secret")),
        ("angry", ("angry", "anger", "furious", "bitter", "taunt", "accus", "defian")),
        ("sad", ("sad", "grief", "tear", "cry", "hurt", "regret", "guilt", "plead")),
        ("nervous", ("fear", "scare", "worry", "anxious", "nervous", "panic", "tense")),
    ):
        if any(word in mood for word in words):
            return label
    return ""


async def _edge_save(edge_tts, text, voice, rate, pitch, path):
    await asyncio.wait_for(edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).save(str(path)),
                           timeout=60)


def edge_speech(text, voice, emotion=""):
    tag = mood_tag(emotion)
    rate = EDGE_RATE.get(tag, "+0%")
    pitch = EDGE_PITCH.get(tag, "+0Hz")
    fingerprint = json.dumps({"voice": voice, "text": text, "rate": rate, "pitch": pitch},
                             ensure_ascii=False, sort_keys=True).encode("utf-8")
    cache = WORK / "edge"
    cache.mkdir(parents=True, exist_ok=True)
    mp3 = cache / f"{hashlib.sha256(fingerprint).hexdigest()}.mp3"
    if mp3.exists():
        return mp3
    try:
        import edge_tts
    except ImportError:
        raise VoiceUnavailable("edge-tts missing; pip install -r requirements.txt") from None
    partial = mp3.with_suffix(".part.mp3")
    failure = None
    for attempt in range(3):
        try:
            asyncio.run(_edge_save(edge_tts, text, voice, rate, pitch, partial))
            break
        except Exception as exc:
            failure = exc
            time.sleep(2 + attempt * 3)
    else:
        raise VoiceUnavailable(f"Edge TTS failed; no alternate voice used ({type(failure).__name__})")
    if partial.stat().st_size < 1000:
        partial.unlink(missing_ok=True)
        raise VoiceUnavailable("Edge TTS returned empty audio")
    partial.replace(mp3)
    return mp3


def preflight(cast):
    if tts_provider() == "edge":
        voices = [c.get("edge_voice", "") for c in cast.values()]
        if not all(voices):
            raise VoiceUnavailable("series.json: har kirdar ke liye edge_voice chahiye")
        if len(set(voices)) != len(voices):
            raise VoiceUnavailable("series.json: har kirdar ki Edge voice alag honi chahiye")
        return
    api_key()
    for character in cast.values():
        resolve_voice_id(character["voice"])


def api_key():
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    path = ROOT / "secrets" / "elevenlabs_key.txt"
    if not key and path.exists():
        key = path.read_text(encoding="utf-8").strip()
    if not key:
        raise VoiceUnavailable("ELEVENLABS_API_KEY missing; alternate voice fallback disabled")
    return key


def _request(path, body=None):
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/{path}",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None,
        headers={"xi-api-key": api_key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            ctype = response.headers.get("Content-Type", "")
            data = response.read()
        if body is not None and not ctype.startswith("audio/"):
            raise VoiceUnavailable(f"ElevenLabs returned non-audio ({ctype or 'no content-type'})")
        if body is None and not ctype.startswith("application/json"):
            raise VoiceUnavailable(f"ElevenLabs returned {ctype or 'no content-type'} instead of JSON; check key permissions")
        return data
    except urllib.error.HTTPError as exc:
        raise VoiceUnavailable(f"ElevenLabs HTTP {exc.code}; check key, voice access and credits") from None
    except (urllib.error.URLError, TimeoutError):
        raise VoiceUnavailable("ElevenLabs connection failed; no alternate voice used") from None


@lru_cache(maxsize=1)
def available_voices():
    raw = _request("voices")
    try:
        data = json.loads(raw)
    except ValueError:
        raise VoiceUnavailable(f"ElevenLabs voices: unreadable response {raw[:120]!r}") from None
    voices = data.get("voices") if isinstance(data, dict) else None
    if not isinstance(voices, list):
        raise VoiceUnavailable(f"ElevenLabs voices: unexpected response {raw[:120]!r}")
    return voices


def resolve_voice_id(name):
    if re.fullmatch(r"[A-Za-z0-9]{20}", name):
        return name
    matches = [v for v in available_voices() if v.get("name", "").casefold() == name.casefold()]
    stock = [v for v in matches if v.get("category") == "premade"]
    matches = stock or matches
    if len(matches) != 1 or not re.fullmatch(r"[A-Za-z0-9]{20}", matches[0].get("voice_id", "")):
        raise VoiceUnavailable(f"ElevenLabs voice '{name}' unavailable or ambiguous; set its ID in series.json")
    return matches[0]["voice_id"]


def speech_body(text, emotion=""):
    tag = mood_tag(emotion)
    return {"text": f"[{tag}] {text}" if tag else text,
            "model_id": "eleven_v3", "voice_settings": {"stability": 0.5}}


def speech_file(text, voice_id, emotion=""):
    if tts_provider() == "edge":
        return edge_speech(text, voice_id, emotion)
    body = speech_body(text, emotion)
    fingerprint = json.dumps({"voice": voice_id, "body": body, "format": "mp3_44100_128"},
                             ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(fingerprint).hexdigest()
    cache = WORK / "elevenlabs"
    cache.mkdir(parents=True, exist_ok=True)
    mp3 = cache / f"{digest}.mp3"
    if not mp3.exists():
        data = _request(f"text-to-speech/{voice_id}?output_format=mp3_44100_128", body)
        if not data:
            raise VoiceUnavailable("ElevenLabs returned empty audio")
        partial = mp3.with_suffix(".part")
        partial.write_bytes(data)
        partial.replace(mp3)
    return mp3


def line_audio(scene, k, sub):
    source = speech_file(sub["text"], DEFAULT_VOICE, sub.get("emotion", ""))
    out = DUB_DIR / f"{Path(scene['file']).stem}_{k}.mp3"
    DUB_DIR.mkdir(parents=True, exist_ok=True)
    out.write_bytes(source.read_bytes())
    return out


def dialogue_audio(turns, cast, out):
    if not turns:
        raise VoiceUnavailable("Dialogue has no lines")
    speakers = dict.fromkeys(t["speaker"] for t in turns)
    if tts_provider() == "edge":
        voices = {s: cast[s]["edge_voice"] for s in speakers}
    else:
        voices = {s: resolve_voice_id(cast[s]["voice"]) for s in speakers}
    if len(set(voices.values())) != len(voices):
        raise VoiceUnavailable("Each dialogue character must have a distinct voice")
    files = []
    for index, turn in enumerate(turns, 1):
        print(f"TTS line {index}/{len(turns)} ({voices[turn['speaker']]})", flush=True)
        mp3 = speech_file(turn["text"], voices[turn["speaker"]], turn.get("emotion", ""))
        wav = mp3.with_suffix(".wav")
        if not wav.exists():
            partial = wav.with_suffix(".tmp.wav")
            run([FFMPEG, "-y", "-i", mp3, "-ar", str(SAMPLE_RATE), "-ac", "1",
                 "-c:a", "pcm_s16le", partial])
            partial.replace(wav)
        files.append(wav)

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_suffix(".tmp.wav")
    gap_frames = round(LINE_GAP * SAMPLE_RATE)
    timings, cursor = [], 0
    with wave.open(str(partial), "wb") as dest:
        dest.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
        for i, wav in enumerate(files):
            with wave.open(str(wav), "rb") as source:
                frames = source.getnframes()
                dest.writeframes(source.readframes(frames))
            timings.append((cursor / SAMPLE_RATE, (cursor + frames) / SAMPLE_RATE))
            cursor += frames
            if i < len(files) - 1:
                dest.writeframes(b"\0\0" * gap_frames)
                cursor += gap_frames
    partial.replace(out)
    print(f"TTS ({tts_provider()}): {cursor / SAMPLE_RATE:.1f}s / {len(turns)} lines")
    return timings


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
