import base64
import json
import os
import random
import re
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

import pipeline
from pipeline import FFMPEG, OUT, WORK, run, mp3_duration

ROOT = Path(__file__).resolve().parent
CLIPS = sorted((ROOT / "assets" / "clips").glob("movie_*.mp4"))
MUSIC = ROOT / "assets" / "music" / "epic.mp3"
SOFT_MUSIC = ROOT / "assets" / "music" / "soft.mp3"
FONT_FILE = ROOT / "assets" / "fonts" / "Mukta-Bold.ttf"
W, H = 1080, 1920
STRIP_W, STRIP_H = 1080, 608
STRIP_Y = 600
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Charon"


def _gemini_tts(text, path):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("no key")
    prompt = ("Speak in Hindi with a deep, powerful, dramatic and emotional male motivational-speaker "
              "voice, like a cinematic movie-trailer narration. Begin low and intense, gradually build "
              "passion and energy, pause briefly between sentences for impact, and deliver the final line "
              "with full power. Natural breathing and real feeling, never robotic. Say: " + text)
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"responseModalities": ["AUDIO"],
                                            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": TTS_VOICE}}}}}).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{TTS_MODEL}:generateContent?key={key}"
    resp = None
    for attempt in range(4):
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                resp = json.loads(r.read())
            break
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="ignore") if e.code == 429 else ""
            if e.code == 429 and "per day" in detail.lower():
                raise RuntimeError("daily TTS quota exhausted")
            if e.code in (429, 500, 503) and attempt < 3:
                wait = 25 * (attempt + 1)
                print(f"gemini-tts {e.code}, retry {attempt+1} in {wait}s")
                time.sleep(wait)
                continue
            raise
    if resp is None:
        raise RuntimeError("tts no response")
    part = resp["candidates"][0]["content"]["parts"][0]
    inline = part.get("inlineData") or part.get("inline_data")
    pcm = base64.b64decode(inline["data"])
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
        w.writeframes(pcm)


def scene_voice(text, path):
    try:
        _gemini_tts(text, path)
        if path.stat().st_size > 1000:
            return
    except Exception as e:
        print(f"gemini-tts failed ({e}), edge-tts fallback")
    tmp = path.with_suffix(".mp3")
    pipeline.make_voice(text, tmp)
    run([FFMPEG, "-y", "-i", tmp, "-ar", "24000", "-ac", "1", path])


def _clean(s):
    return re.sub(r"[^ -~ऀ-ॿ।॥]", "", s)


def pick_music(data):
    text = (data.get("topic", "") + " " + data.get("title", "") + " " + data.get("hook", "")).lower()
    if any(k in text for k in ("maa", "baap", "dil", "dard", "akela", "aansu", "garibi", "haar", "parivar",
                               "माँ", "मां", "बाप", "दिल", "दर्द", "अकेला", "आँसू", "गरीबी", "हार", "परिवार")):
        return SOFT_MUSIC
    return MUSIC


def build_video(data):
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    scenes = data["scenes"]
    rng = random.Random(data.get("slug", "x"))

    voice = WORK / "cvoice.wav"
    full_text = " ".join(sc["text"] for sc in scenes)
    scene_voice(full_text, voice)
    usable = mp3_duration(voice)
    weights = [max(1, len(sc["text"])) for sc in scenes]
    sw = sum(weights)
    durations = [usable * w / sw for w in weights]
    total = usable + 0.6

    # center strip: per-scene graded clip segments with zoom variety (xfade overlaps)
    T = 0.5
    segdur = [d + T for d in durations[:-1]] + [durations[-1] + 0.6]
    segs = []
    order = CLIPS[:]
    rng.shuffle(order)
    for i, dur in enumerate(segdur):
        clip = order[i % len(order)]
        seg = WORK / ("cseg_%02d.mp4" % i)
        zoom = ("min(zoom+0.0006,1.18)" if i % 2 == 0 else "max(1.18-0.0006*on,1.0)")
        run([FFMPEG, "-y", "-stream_loop", "-1", "-i", clip, "-t", f"{dur:.2f}",
             "-vf", f"scale={STRIP_W}:{STRIP_H}:force_original_aspect_ratio=increase,crop={STRIP_W}:{STRIP_H},"
                    f"zoompan=z='{zoom}':d=1:s={STRIP_W}x{STRIP_H}:fps=30,"
                    f"eq=contrast=1.06:saturation=1.12:brightness=0.01,vignette=PI/5",
             "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-an", seg])
        segs.append(seg)

    # subtitles: per-line drawtext (bundled font, no fontconfig/newline glyph issues)
    sub_filters = []
    t = 0.0
    for i, (sc, dur) in enumerate(zip(scenes, durations)):
        wrapped, cur = [], ""
        for word in _clean(sc["text"]).split():
            if len(cur) + len(word) + 1 > 32:
                wrapped.append(cur); cur = word
            else:
                cur = (cur + " " + word).strip()
        if cur:
            wrapped.append(cur)
        for j, ln in enumerate(wrapped[:3]):
            (WORK / ("csub_%02d_%d.txt" % (i, j))).write_text(ln, encoding="utf-8")
            sub_filters.append(
                f"drawtext=fontfile=cfont.ttf:textfile=csub_{i:02d}_{j}.txt:fontcolor=white:fontsize=54:"
                f"x=(w-text_w)/2:y={1250+j*70}:borderw=3:bordercolor=black:"
                f"alpha='min(1,(t-{t:.2f})/0.3)':enable='between(t,{t:.2f},{t+dur-0.15:.2f})'")
        t += dur

    hook = _clean((data.get("hook") or data["title"]).replace("#shorts", "")).strip()
    hook_lines = []
    cur = ""
    for word in hook.split():
        if len(cur) + len(word) + 1 > 24:
            hook_lines.append(cur); cur = word
        else:
            cur = (cur + " " + word).strip()
    if cur:
        hook_lines.append(cur)
    hook_filters = []
    for j, ln in enumerate(hook_lines[:3]):
        (WORK / ("chook_%d.txt" % j)).write_text(ln, encoding="utf-8")
        hook_filters.append(
            f"drawtext=fontfile=cfont.ttf:textfile=chook_{j}.txt:fontcolor=white:fontsize=62:"
            f"x=(w-text_w)/2:y={210+j*80}:borderw=3:bordercolor=black:alpha='min(1,t/0.4)'")

    import shutil
    shutil.copy(FONT_FILE, WORK / "cfont.ttf")
    out = OUT / f"{data.get('slug', 'video')}.mp4"
    outro = (
        f"drawtext=fontfile=cfont.ttf:text='SUBSCRIBE':fontcolor=0xFF3B3B:fontsize=66:"
        f"x=(w-text_w)/2:y=1520:borderw=4:bordercolor=black:"
        f"alpha='min(1,(t-{total-2.2:.2f})/0.3)':enable='gte(t,{total-2.2:.2f})',"
        f"drawtext=fontfile=cfont.ttf:text='Roz nayi motivation':fontcolor=white:fontsize=38:"
        f"x=(w-text_w)/2:y=1600:borderw=3:bordercolor=black:"
        f"alpha='min(1,(t-{total-2.2:.2f})/0.3)':enable='gte(t,{total-2.2:.2f})'")
    vf = (f"overlay=0:{STRIP_Y},"
          + ",".join(hook_filters) + ","
          f"drawtext=fontfile=cfont.ttf:text='| ZIDDI |':fontcolor=0xAAAAAA:fontsize=30:"
          f"x=(w-text_w)/2:y=1760,"
          + ",".join(sub_filters) + "," + outro)

    # xfade crossfade chain over graded segments
    n = len(segs)
    trans = ["fade", "smoothleft", "fadeblack"]
    chain, cur = "", "[1:v]"
    off = segdur[0] - T
    for k in range(1, n):
        chain += f"{cur}[{k+1}:v]xfade=transition={trans[(k-1)%3]}:duration={T}:offset={off:.2f}[x{k}];"
        cur = f"[x{k}]"
        off += segdur[k] - T
    inputs = [FFMPEG, "-y", "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r=30:d={total:.2f}"]
    for s in segs:
        inputs += ["-i", s]
    inputs += ["-i", voice, "-i", pick_music(data)]
    run(inputs + ["-filter_complex",
         chain + f"[0:v]{cur}{vf}[v];[{n+1}:a]apad=pad_dur=0.6[voc];"
         f"[{n+2}:a]atrim=0:{total:.2f},volume=0.30,afade=t=in:st=0:d=1.5,afade=t=out:st={total-2.5:.2f}:d=2.5[m];"
         f"[voc][m]amix=inputs=2:duration=longest:dropout_transition=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]",
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
         "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-shortest", "-pix_fmt", "yuv420p", out], cwd=WORK)
    return out