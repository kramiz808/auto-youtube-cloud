"""Instagram Reels publishing (same reel that goes to YouTube)."""
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

from pipeline import FFMPEG, ROOT, WORK

GRAPH = "https://graph.facebook.com/v21.0"
UPLOAD_HOST = "https://catbox.moe/user/api.php"
TOKEN_FILE = ROOT / "ig_token.txt"


def token():
    env = os.environ.get("IG_TOKEN", "").strip()
    if env:
        return env
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    return ""


def ig_account(tok):
    """Page-linked professional IG account id + username."""
    pages = requests.get(f"{GRAPH}/me/accounts",
                         params={"fields": "id,name,access_token,instagram_business_account{id,username}",
                                 "access_token": tok}, timeout=60).json()
    for page in pages.get("data", []):
        ig = page.get("instagram_business_account")
        if ig and ig.get("id"):
            return ig["id"], ig.get("username"), page.get("access_token") or tok
    return None, None, None


def public_url(video):
    with open(video, "rb") as fh:
        r = requests.post(UPLOAD_HOST,
                          data={"reqtype": "fileupload"},
                          files={"fileToUpload": (Path(video).name, fh, "video/mp4")},
                          timeout=900)
    url = r.text.strip()
    if not r.ok or not url.startswith("http"):
        raise RuntimeError(f"public upload fail: {r.text[:120]}")
    return url


def publish(video, caption):
    tok = token()
    if not tok:
        return None
    ig_id, username, page_tok = ig_account(tok)
    if not ig_id:
        print("IG SKIP: token se koi Instagram professional account nahi mila")
        return None
    url = public_url(video)
    print("IG public url:", url)
    body = {"media_type": "REELS", "video_url": url, "caption": caption[:2200],
            "access_token": page_tok}
    cont = requests.post(f"{GRAPH}/{ig_id}/media", data=body, timeout=120).json()
    if "id" not in cont:
        print("IG SKIP: container nahi bana —", str(cont)[:200])
        return None
    cid = cont["id"]
    for _ in range(30):
        st = requests.get(f"{GRAPH}/{cid}", params={"fields": "status_code,status", "access_token": page_tok},
                          timeout=60).json()
        code = st.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED", "PUBLISH_FAILED"):
            print("IG SKIP: container status", str(st)[:200])
            return None
        time.sleep(10)
    pub = requests.post(f"{GRAPH}/{ig_id}/media_publish",
                        data={"creation_id": cid, "access_token": page_tok}, timeout=120).json()
    if "id" not in pub:
        print("IG SKIP: publish fail —", str(pub)[:200])
        return None
    link = f"https://www.instagram.com/reel/{pub['id']}/"
    print("IG POSTED:", link)
    return link


def teaser(video, seconds=60):
    """Chhoti clip bana kar Reel ki tarah post karne ke liye."""
    out = WORK / f"{Path(video).stem}-teaser.mp4"
    subprocess.run([str(FFMPEG), "-y", "-i", str(video), "-t", str(seconds), "-c", "copy", str(out)],
                   check=True, capture_output=True)
    return out


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        tok = token()
        if not tok:
            print("IG token missing (ig_token.txt / IG_TOKEN secret)")
            return
        ig_id, username, _ = ig_account(tok)
        print("IG account:", username, ig_id)
        return
    if len(sys.argv) < 2:
        print("usage: python ig.py <video> [caption]")
        sys.exit(1)
    video = sys.argv[1]
    caption = sys.argv[2] if len(sys.argv) > 2 else Path(video).stem
    print(publish(video, caption))


if __name__ == "__main__":
    main()
