"""Occasional auto-live: 30 min looped backdrop + music so the channel looks owner-run."""
import datetime
import sys

from pipeline import FFMPEG, ROOT, WORK, run, get_creds
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

BG = ROOT / "assets" / "story" / "bg.mp4"
MUSIC = ROOT / "assets" / "music" / "epic.mp3"
FONT = ROOT / "assets" / "fonts" / "Mukta-Bold.ttf"
MINUTES = 30
TITLE = "Ziddi Motivation | सीधा प्रसारण"


def skip(msg):
    print("LIVE SKIP:", msg)
    sys.exit(0)


def main():
    creds = get_creds(["https://www.googleapis.com/auth/youtube"])
    if creds is None:
        skip("YOUTUBE_TOKEN / token.json missing")
    if not any(s.rstrip("/").endswith("/youtube") for s in (creds.scopes or [])):
        skip("token me live scope nahi hai — YouTube dobara authorize karna padega")

    yt = build("youtube", "v3", credentials=creds)
    start = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    try:
        broadcast = yt.liveBroadcasts().insert(
            part="snippet,status,contentDetails",
            body={
                "snippet": {"title": TITLE, "scheduledStartTime": start.isoformat(),
                            "description": "Roz ki Hindi kahaniyan aur motivation. "
                                           "Ziddi Motivation par."},
                "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
                "contentDetails": {"enableAutoStart": True, "enableAutoStop": True,
                                   "latencyPreference": "normal",
                                   "monitorStream": {"enableMonitorStream": False}},
            }).execute()
        stream = yt.liveStreams().insert(
            part="snippet,cdn,status",
            body={"snippet": {"title": TITLE},
                  "cdn": {"frameRate": "30fps", "ingestionType": "rtmp",
                          "resolution": "1080p"}}).execute()
    except HttpError as exc:
        if "not enabled for live streaming" in str(exc):
            skip("channel par live streaming enable nahi hai (phone verify + 24 ghante)")
        raise
    yt.liveBroadcasts().bind(part="id,contentDetails", id=broadcast["id"],
                             streamId=stream["id"]).execute()

    info = stream["cdn"]["ingestionInfo"]
    url = f"{info['ingestionAddress']}/{info['streamName']}"
    print("LIVE:", broadcast["id"], "| https://youtu.be/" + broadcast["id"])

    WORK.mkdir(exist_ok=True)
    font = FONT.as_posix().replace(":", "\\:")
    graph = (
        "[1:a]volume=0.5,afade=t=in:st=0:d=3[mus];"
        f"[0:v]fps=30,drawtext=fontfile='{font}':text='ZIDDI MOTIVATION':"
        "fontcolor=white@0.92:fontsize=54:x=(w-text_w)/2:y=h*0.08,"
        f"drawtext=fontfile='{font}':text='LIVE':fontcolor=red:fontsize=40:"
        "x=(w-text_w)/2:y=h*0.08+90[v]"
    )
    run([FFMPEG, "-y", "-re", "-stream_loop", "-1", "-i", BG,
         "-stream_loop", "-1", "-i", MUSIC,
         "-filter_complex", graph,
         "-map", "[v]", "-map", "[mus]",
         "-t", str(MINUTES * 60),
         "-c:v", "libx264", "-preset", "veryfast", "-b:v", "2500k", "-g", "60",
         "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
         "-f", "flv", url], cwd=WORK)

    try:
        yt.liveBroadcasts().transition(part="status", broadcastStatus="complete",
                                       id=broadcast["id"]).execute()
    except HttpError as exc:
        print("close skip:", str(exc)[:120])
    print("LIVE DONE")


if __name__ == "__main__":
    main()
