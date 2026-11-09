import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parent
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.force-ssl"]

flow = InstalledAppFlow.from_client_secrets_file(str(ROOT / "client_secret.json"), SCOPES)
print("Browser khulega — kaleemasagar652@gmail.com se sign in kar ke Allow daba (channel manage permission).", flush=True)
creds = flow.run_local_server(port=0, prompt="consent", access_type="offline",
                              authorization_prompt_message="AUTH_URL: {url}",
                              success_message="OK: authorized. Ye tab band kar de.")
(ROOT / "token.json").write_text(creds.to_json(), encoding="utf-8")
print("OK: token.json saved (upload + channel-manage scopes).", flush=True)

yt = build("youtube", "v3", credentials=creds)
ch = yt.channels().list(mine=True, part="id").execute()["items"][0]["id"]
print("channel:", ch, flush=True)

desc = ("Ziddi Motivation — roz ek nayi Hindi motivational short. Discipline, self-belief, mehnat, "
        "comeback aur pain-to-power ki cinematic kahaniyan. Roz subah-sham ek nayi aag. "
        "Subscribe karo aur apne sapno ko zidd bana lo.\n"
        "Hindi motivation | motivational video | mindset | success | discipline | self improvement | "
        "motivational shorts | study motivation | gym motivation | life changing quotes")
body = {
    "id": ch,
    "brandingSettings": {
        "channel": {
            "title": "Ziddi Motivation",
            "description": desc,
            "keywords": 'motivation "hindi motivation" "motivational video" mindset success discipline '
                        '"self improvement" "study motivation" shorts "life quotes" inspiration',
            "country": "IN",
            "defaultLanguage": "hi",
        },
    },
    "status": {"madeForKids": False},
}
try:
    yt.channels().update(part="brandingSettings,status", body=body).execute()
    print("OK: channel name/description/keywords/country/madeForKids set.", flush=True)
except Exception as e:
    print("branding update partial:", e, flush=True)

try:
    up = yt.channelBanners().insert(media_body=MediaFileUpload(str(ROOT / "brand" / "banner.png"),
                                    mimetype="image/png", resumable=True)).execute()
    yt.channels().update(part="brandingSettings",
                         body={"id": ch, "brandingSettings": {"image": {"bannerImageUrl": up["url"]}}}).execute()
    print("OK: banner set.", flush=True)
except Exception as e:
    print("banner skip:", e, flush=True)

print("DONE branding. DP (brand/dp.png) Studio se upload karna hai (API support nahi).", flush=True)