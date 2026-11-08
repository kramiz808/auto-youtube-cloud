import datetime
import json
import re
import sys
import urllib.request
from pathlib import Path

import pipeline
import reel

ROOT = Path(__file__).resolve().parent
GEMINI_MODELS = ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-2.5-flash", "gemini-2.0-flash"]


def gemini_app(api_key):
    prompt = (
        "Banao ek single-file HTML web tool jo students ke kaam aaye (study timer, quiz, flashcards, "
        "calculator, timetable, notes — har roz alag). Requirements: poora HTML+CSS+JS ek hi file mein, "
        "koi external library/CDN nahi, mobile-friendly, Hindi labels, dark theme, saaf sundar UI, "
        "tool sach mein functional ho. SIRF HTML code return karo — koi explanation nahi, koi markdown fence nahi."
    )
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": 1.0}}).encode()
    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as r:
                resp = json.loads(r.read())
            text = resp["candidates"][0]["content"]["parts"][0]["text"].strip()
            text = re.sub(r"^```(?:html)?|```$", "", text, flags=re.M).strip()
            if "<html" in text.lower() and "</html>" in text.lower():
                print(f"app: Gemini ({model})")
                return text
        except Exception as e:
            print(f"app Gemini {model} failed: {e}")
    return None


def main():
    import os
    state = json.loads((ROOT / "state.json").read_text(encoding="utf-8"))
    scene_list = reel.load_scenes()
    run_no = state.get("scene_index", 0)
    scene = scene_list[run_no % len(scene_list)]
    hook = scene["hooks"][(run_no // len(scene_list)) % len(scene["hooks"])]
    today = datetime.date.today().isoformat()
    slug = f"{today}-{run_no % len(scene_list):02d}"

    data = {k: scene[k] for k in ("title", "description", "hashtags", "tags", "attribution")}
    data["privacy"] = "public"
    (ROOT / "today.json").write_text(
        json.dumps({**data, "hook": hook, "file": scene["file"]}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    video = reel.build_scene(scene, hook, slug)
    print(f"VIDEO: {video}")
    vid = pipeline.upload(video, data)

    with (ROOT / "output" / "log.txt").open("a", encoding="utf-8") as f:
        f.write(f"{today} | {scene['file']} | hook={hook} | youtube_id={vid} | {video.name}\n")

    if not vid:
        print("Auth missing — state advance nahi hua", file=sys.stderr)
        sys.exit(1)
    state["scene_index"] = run_no + 1
    (ROOT / "state.json").write_text(json.dumps(state), encoding="utf-8")

    key = os.environ.get("GEMINI_API_KEY")
    if key:
        html = gemini_app(key)
        if html:
            apps = ROOT / "apps-output"
            apps.mkdir(exist_ok=True)
            app_path = apps / f"{today}-tool.html"
            app_path.write_text(html, encoding="utf-8")
            print(f"APP: {app_path}")


if __name__ == "__main__":
    main()
