import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
OUT = ROOT / "output"

if platform.system() == "Windows":
    _FF = Path(r"C:/Users/Windows 10/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.2-full_build/bin/ffmpeg.exe")
else:
    _FF = Path("/usr/bin/ffmpeg")
FFMPEG = shutil.which("ffmpeg") or str(_FF)
FFPROBE = shutil.which("ffprobe") or str(_FF.with_name("ffprobe.exe" if platform.system() == "Windows" else "ffprobe"))


def run(cmd, cwd=None):
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"command failed: {cmd}\n{r.stderr[-2000:]}")
    return r.stdout


class UploadLimitReached(RuntimeError):
    pass


def media_duration(path):
    out = run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
               "-of", "default=noprint_wrappers=1:nokey=1", path])
    return float(out.strip())


def get_creds(scopes=None):
    from google.oauth2.credentials import Credentials
    scopes = scopes or ["https://www.googleapis.com/auth/youtube.upload"]
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
            "description": (data.get("description", "")
                            + "\n\n" + data.get("hashtags", "#shorts #movie #emotional")
                            + "\n\n" + data.get("attribution", "")),
            "tags": data.get("tags", ["movie scene", "emotional", "animation"]),
            "categoryId": "24",
        },
        "status": {
            "privacyStatus": data.get("privacy", "public"),
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video_path), chunksize=4 * 1024 * 1024, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        try:
            status, resp = req.next_chunk(num_retries=3)
        except Exception as exc:
            text = str(exc)
            if "uploadLimitExceeded" in text or "exceeded the number of videos" in text:
                raise UploadLimitReached(text[:160])
            raise
        if status:
            print(f"upload {int(status.progress() * 100)}%")
    print(f"UPLOADED: https://youtu.be/{resp['id']}")
    return resp["id"]