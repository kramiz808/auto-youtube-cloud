import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parent
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]
creds = Credentials.from_authorized_user_file(str(ROOT / "token.json"), SCOPES)
yt = build("youtube", "v3", credentials=creds)
ch = yt.channels().list(mine=True, part="id").execute()["items"][0]["id"]

desc = ("Ziddi Motivation — roz ek nayi Hindi motivational short. Discipline, self-belief, mehnat, "
        "comeback aur pain-to-power ki cinematic kahaniyan. Subscribe karo aur apne sapno ko zidd bana lo.\n"
        "Hindi motivation | motivational video | mindset | success | discipline | self improvement | "
        "motivational shorts | study motivation | gym motivation | life changing quotes")
channel = {
    "title": "Ziddi Motivation",
    "description": desc,
    "keywords": 'motivation "hindi motivation" "motivational video" mindset success discipline '
                '"self improvement" "study motivation" shorts "life quotes" inspiration',
    "country": "IN",
    "defaultLanguage": "hi",
}

banner_url = None
try:
    up = yt.channelBanners().insert(media_body=MediaFileUpload(str(ROOT / "brand" / "banner.png"),
                                    mimetype="image/png", resumable=True)).execute()
    banner_url = up["url"]
    print("banner uploaded:", banner_url[:60], flush=True)
except Exception as e:
    print("banner insert skip:", e, flush=True)

branding = {"channel": channel}
if banner_url:
    branding["image"] = {"bannerImageUrl": banner_url}
try:
    yt.channels().update(part="brandingSettings", body={"id": ch, "brandingSettings": branding}).execute()
    print("OK: name/description/keywords/country/banner set.", flush=True)
except Exception as e:
    print("branding err:", e, flush=True)

try:
    yt.channels().update(part="status", body={"id": ch, "status": {"madeForKids": False}}).execute()
    print("OK: madeForKids=false.", flush=True)
except Exception as e:
    print("status err:", e, flush=True)

got = yt.channels().list(mine=True, part="brandingSettings,status").execute()["items"][0]
print("VERIFY title:", got["brandingSettings"]["channel"].get("title"), flush=True)
print("VERIFY madeForKids:", got.get("status", {}).get("madeForKids"), flush=True)