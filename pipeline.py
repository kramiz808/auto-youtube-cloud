import asyncio
import json
import os
import platform
import shutil
import subprocess
import textwrap
from pathlib import Path

import edge_tts

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
OUT = ROOT / "output"
VOICE = "hi-IN-MadhurNeural"

if platform.system() == "Windows":
    FONT = "Nirmala UI"
    _FF = Path(r"C:/Users/Windows 10/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.2-full_build/bin/ffmpeg.exe")
else:
    FONT = "Noto Sans Devanagari"
    _FF = Path("/usr/bin/ffmpeg")
FFMPEG = shutil.which("ffmpeg") or str(_FF)
FFPROBE = shutil.which("ffprobe") or str(_FF.with_name("ffprobe.exe" if platform.system() == "Windows" else "ffprobe"))


def run(cmd, cwd=None):
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {cmd}\n{r.stderr[-2000:]}")
    return r.stdout


def mp3_duration(path):
    out = run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", path])
    return float(out.strip())


def srt_time(seconds):
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, milli = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


async def _edge_voice(text, path):
    await edge_tts.Communicate(text, VOICE, rate="+5%").save(str(path))


def make_voice(text, path):
    try:
        asyncio.run(_edge_voice(text, path))
        if path.stat().st_size > 1000:
            return
    except Exception as e:
        print(f"edge-tts failed ({e}), gTTS fallback")
    from gtts import gTTS
    gTTS(text, lang="hi").save(str(path))


def wrap_hi(text, width=26):
    return "\\N".join(textwrap.wrap(text, width=width, break_long_words=False))


def build_video(data):
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    scenes = data["scenes"]
    durations = []
    files = []
    for i, scene in enumerate(scenes):
        p = WORK / f"scene_{i:02d}.mp3"
        make_voice(scene["text"], p)
        durations.append(mp3_duration(p) + 0.25)
        files.append(p)

    concat_list = WORK / "concat.txt"
    concat_list.write_text("\n".join(f"file '{p.as_posix()}'" for p in files), encoding="utf-8")
    voice = WORK / "voice.mp3"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", concat_list, "-c", "copy", voice])

    srt = WORK / "subs.srt"
    lines = []
    t = 0.0
    for i, (scene, dur) in enumerate(zip(scenes, durations), 1):
        lines.append(f"{i}\n{srt_time(t)} --> {srt_time(t + dur - 0.1)}\n{wrap_hi(scene['text'])}\n")
        t += dur
    srt.write_text("\n".join(lines), encoding="utf-8")

    total = mp3_duration(voice) + 0.5
    style = (f"FontName={FONT},Fontsize=21,Bold=1,PrimaryColour=&H00FFFFFF,"
             "OutlineColour=&H00000000,BackColour=&H80000000,BorderStyle=1,Outline=2,"
             "Shadow=0,MarginV=70,MarginL=40,MarginR=40,Alignment=2")
    out = OUT / f"{data.get('slug', 'video')}.mp4"
    run([FFMPEG, "-y", "-f", "lavfi", "-i", f"color=c=0x0F172A:s=720x1280:r=30:d={total:.2f}",
         "-i", voice, "-vf", f"subtitles=subs.srt:force_style='{style}'",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
         "-c:a", "aac", "-b:a", "96k", "-shortest", "-pix_fmt", "yuv420p", out], cwd=WORK)
    return out


def get_creds():
    from google.oauth2.credentials import Credentials
    scopes = ["https://www.googleapis.com/auth/youtube.upload"]
    env = os.environ.get("YOUTUBE_TOKEN")
    if env:
        return Credentials.from_authorized_user_info(json.loads(env), scopes)
    token = ROOT / "token.json"
    if token.exists():
        return Credentials.from_authorized_user_file(str(token), scopes)
    return None


def upload(video_path, data):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    creds = get_creds()
    if creds is None:
        print("UPLOAD SKIPPED: YOUTUBE_TOKEN secret / token.json missing")
        return None
    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": data["title"][:100],
            "description": (data.get("description", "") + "\n\n#shorts #hindi #motivation #mindset"
                            + "\n\nFootage: \"Sintel\" by Blender Foundation (durian.blender.org), licensed CC-BY 3.0"),
            "tags": data.get("tags", ["motivation", "hindi", "mindset"]),
            "categoryId": "27",
        },
        "status": {
            "privacyStatus": data.get("privacy", "public"),
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
    }
    media = MediaFileUpload(str(video_path), chunksize=4 * 1024 * 1024, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        status, resp = req.next_chunk(num_retries=3)
        if status:
            print(f"upload {int(status.progress() * 100)}%")
    print(f"UPLOADED: https://youtu.be/{resp['id']}")
    return resp["id"]