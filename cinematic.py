import asyncio
import base64
import json
import os
import random
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

import pipeline
from pipeline import FFMPEG, FONT, OUT, WORK, run, mp3_duration

ROOT = Path(__file__).resolve().parent
CLIPS = sorted((ROOT / "assets" / "clips").glob("*.mp4"))
MUSIC = ROOT / "assets" / "music" / "epic.mp3"
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
              "voice, like a cinematic movie trailer narration. Pace with pauses for impact. Say: " + text)
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


def _ass_time(s):
    ms = int(round(s * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(ms, 60000)
    sec, milli = divmod(rem, 1000)
    return f"{h}:{m:02d}:{sec:02d}.{milli//10:02d}"


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

    # center strip: per-scene zooming clip segments
    segs = []
    for i, dur in enumerate(durations):
        clip = CLIPS[(i + rng.randrange(len(CLIPS))) % len(CLIPS)]
        seg = WORK / ("cseg_%02d.mp4" % i)
        run([FFMPEG, "-y", "-stream_loop", "-1", "-i", clip, "-t", f"{dur:.2f}",
             "-vf", f"scale={STRIP_W}:{STRIP_H}:force_original_aspect_ratio=increase,crop={STRIP_W}:{STRIP_H},"
                    f"zoompan=z='min(zoom+0.0006,1.18)':d=1:s={STRIP_W}x{STRIP_H}:fps=30",
             "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-an", seg])
        segs.append(seg)
    sl = WORK / "csegs.txt"
    sl.write_text("\n".join(f"file '{p.as_posix()}'" for p in segs), encoding="utf-8")
    strip = WORK / "cstrip.mp4"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", sl, "-c", "copy", strip])

    # subtitles (ASS) bottom
    ass = WORK / "csubs.ass"
    header = (f"[Script Info]\nPlayResX: {W}\nPlayResY: {H}\n\n"
              f"[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, "
              f"Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV\n"
              f"Style: Sub,{FONT},54,&H00FFFFFF,&H00000000,&H80000000,-1,0,1,3,0,2,60,60,560\n\n"
              f"[Events]\nFormat: Layer, Start, End, Style, Text\n")
    lines, t = [], 0.0
    for sc, dur in zip(scenes, durations):
        txt = sc["text"].replace("\n", " ")
        lines.append(f"Dialogue: 0,{_ass_time(t)},{_ass_time(t+dur-0.15)},Sub,{txt}")
        t += dur
    ass.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")

    hook = (data.get("hook") or data["title"]).replace("#shorts", "").strip()
    hook_lines = []
    cur = ""
    for word in hook.split():
        if len(cur) + len(word) + 1 > 24:
            hook_lines.append(cur); cur = word
        else:
            cur = (cur + " " + word).strip()
    if cur:
        hook_lines.append(cur)
    hook_text = "\n".join(hook_lines[:3])
    hook_file = WORK / "chook.txt"
    hook_file.write_text(hook_text, encoding="utf-8")

    import shutil
    shutil.copy(_font_path(), WORK / "cfont.ttf")
    out = OUT / f"{data.get('slug', 'video')}.mp4"
    vf = (f"overlay=0:{STRIP_Y},"
          f"drawtext=fontfile=cfont.ttf:textfile=chook.txt:fontcolor=white:fontsize=62:"
          f"line_spacing=14:x=(w-text_w)/2:y=210:borderw=3:bordercolor=black,"
          f"drawtext=fontfile=cfont.ttf:text='| KALEEM ASAGAR |':fontcolor=0xAAAAAA:fontsize=30:"
          f"x=(w-text_w)/2:y=1760,"
          f"ass=csubs.ass")
    run([FFMPEG, "-y", "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r=30:d={total:.2f}",
         "-i", strip, "-i", voice, "-i", MUSIC,
         "-filter_complex", f"[0:v][1:v]{vf}[v];[3:a]atrim=0:{total:.2f},volume=0.22[m];[2:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]",
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "fast", "-crf", "21",
         "-c:a", "aac", "-b:a", "128k", "-shortest", "-pix_fmt", "yuv420p", out], cwd=WORK)
    return out


def _font_path():
    import platform
    import subprocess
    if platform.system() == "Windows":
        p = Path("C:/Windows/Fonts/Nirmala.ttf")
        return str(p) if p.exists() else "C:/Windows/Fonts/arial.ttf"
    try:
        out = subprocess.run(["fc-match", "-f", "%{file}", "Noto Sans Devanagari"],
                             capture_output=True, text=True).stdout.strip()
        if out:
            return out
    except Exception:
        pass
    return "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"