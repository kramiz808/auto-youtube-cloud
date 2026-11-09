import datetime
import json
import re
import sys
import urllib.request
from pathlib import Path

import pipeline
import reel
import voice

ROOT = Path(__file__).resolve().parent
GEMINI_MODELS = ["gemini-flash-lite-latest", "gemini-3-flash-preview", "gemini-flash-latest"]
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


SLOTS = (("morning", 7 * 60), ("afternoon", 14 * 60), ("evening", 17 * 60))


def due_slots(minutes):
    return [name for name, target in SLOTS if minutes >= target]


def posted_slots(day):
    posts = ROOT / "output" / "posts.txt"
    names = {name for name, _ in SLOTS}
    if not posts.exists():
        return set()
    out = set()
    for line in posts.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) > 1 and parts[0] == day and parts[1] in names:
            out.add(parts[1])
    return out


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


def post_slot(slot, today, state, run_no):
    """Ek slot ka short bana ke upload karo. Video id return, warna None."""
    scene_list = reel.load_scenes()
    scene = scene_list[run_no % len(scene_list)]
    hook = scene["hooks"][(run_no // len(scene_list)) % len(scene["hooks"])]
    titles = scene.get("titles") or [scene["title"]]
    slug = f"{today}-{run_no % len(scene_list):02d}"

    data = {k: scene[k] for k in ("description", "hashtags", "tags", "attribution")}
    data["title"] = titles[(run_no // len(scene_list)) % len(titles)]
    data["privacy"] = "public"
    (ROOT / "today.json").write_text(
        json.dumps({**data, "hook": hook, "file": scene["file"]}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    try:
        video = reel.build_scene(scene, hook, slug)
    except voice.VoiceUnavailable as exc:
        print(f"SKIP: Hindi voice cache incomplete aur Gemini quota khatam ({exc}). "
              f"State advance nahi hua — agla run retry karega.", file=sys.stderr)
        return None
    print(f"VIDEO: {video}")
    try:
        vid = pipeline.upload(video, data)
    except pipeline.UploadLimitReached:
        pipeline.mark_blocked()
        print("SKIP: YouTube ka daily upload limit full hai. Reset ke baad apne aap retry.",
              file=sys.stderr)
        return None
    if not vid:
        print("Auth missing — state advance nahi hua", file=sys.stderr)
        return None

    now = datetime.datetime.now(IST)
    posts = ROOT / "output" / "posts.txt"
    with (ROOT / "output" / "log.txt").open("a", encoding="utf-8") as f:
        f.write(f"{today} | {scene['file']} | hook={hook} | youtube_id={vid} | {video.name}\n")
    with posts.open("a", encoding="utf-8") as f:
        f.write(f"{now.date()} {slot} | {vid} | {scene['file']}\n")
    pipeline.clear_blocked()
    try:
        import ig
        ig.publish(video, f"{data['title']}\n\n{data['hashtags']}\n\n{data['description'][:500]}")
    except Exception as exc:
        print("IG SKIP:", str(exc)[:200])
    return vid


def main():
    import os
    state = json.loads((ROOT / "state.json").read_text(encoding="utf-8"))
    force = os.environ.get("FORCE") == "1"
    now = datetime.datetime.now(IST)
    today = now.date().isoformat()
    if force:
        slots = ["extra"]
    else:
        due = due_slots(now.hour * 60 + now.minute)
        if not due:
            print("SKIP: abhi koi posting slot nahi hua")
            sys.exit(0)
        done = posted_slots(today)
        pending = [name for name in due if name not in done]
        if not pending:
            print("SKIP: aaj ke saare slots post ho chuke")
            sys.exit(0)
        # Aakhri ghante me tick aaya to jitne bache hue slots hain sab post kar do —
        # scheduler kabhi kabhi poora din miss kar deta hai.
        slots = pending if now.hour >= 19 else pending[:1]
    if pipeline.upload_blocked() and not force:
        print("SKIP: YouTube upload quota reset ka intezaar")
        sys.exit(0)

    run_no = state.get("scene_index", 0)
    posted = 0
    for slot in slots:
        if not post_slot(slot, today, state, run_no):
            break
        posted += 1
        run_no += 1
        state["scene_index"] = run_no
        (ROOT / "state.json").write_text(json.dumps(state), encoding="utf-8")
    if not posted:
        sys.exit(0)

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
