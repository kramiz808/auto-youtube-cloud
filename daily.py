import datetime
import json
import re
import sys
import urllib.request
from pathlib import Path

import cinematic
import pipeline

ROOT = Path(__file__).resolve().parent
GEMINI_MODELS = ["gemini-flash-lite-latest", "gemini-flash-latest", "gemini-2.5-flash", "gemini-2.0-flash"]


def gemini_script(topic, api_key):
    prompt = (
        f'Topic: "{topic}"\n'
        "Likho ek 60-second YouTube Shorts motivational script Devanagari Hindi mein. SIRF JSON return karo, koi aur text nahi:\n"
        '{"title": "catchy motivational title <=90 chars, #shorts end mein", "hook": "top-screen bold text <=60 chars, punchy curiosity line",'
        ' "description": "2 lines Hindi + motivational keywords",'
        ' "tags": ["motivation", "hindi", "mindset", "success", "4-6 relevant tags"],'
        ' "scenes": [{"text": "scene ka text"}]}\n'
        "Rules: 9-11 scenes, kul ~190 words. Style: cinematic character dialogue — har scene ki line ek gehri (deep) "
        "boli hui baat ho, jaise movie ka character screen par bol raha ho: chhote dumdaar vaaky, seedha 'tum'/'main' "
        "kehkar, emotional aur jazbaati. Pehla scene strong hook (chaunkane wali baat ya sawaal), "
        "beech mein struggle se rise/comeback ka safar, aakhri scene mein powerful punch + subscribe CTA. "
        "Theme: discipline, self-belief, mehnat, darr pe jeet, pain-to-power, never give up. "
        "Simple bolchaal ki Hindi, original baat, koi jhootha claim nahi. "
        "BAHUT ZAROORI: title, hook aur har scene ka text SIRF Devanagari lipi mein ho (जैसे: 'तुम उठोगे नहीं तो कोई और उठ जाएगा'). "
        "Roman/Hinglish (Latin letters) bilkul mana hai."
    )
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": 0.9, "responseMimeType": "application/json"}}).encode()
    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=60) as r:
                resp = json.loads(r.read())
            text = resp["candidates"][0]["content"]["parts"][0]["text"]
            text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
            data = json.loads(text)
            if data.get("scenes") and data.get("title"):
                joined = data["title"] + data.get("hook", "") + " ".join(s.get("text", "") for s in data["scenes"])
                if not re.search(r"[ऀ-ॿ]", joined):
                    raise ValueError("script not in Devanagari")
                print(f"script: Gemini ({model})")
                return data
        except Exception as e:
            print(f"Gemini {model} failed: {e}")
    return None


def fallback_script(index):
    lib = json.loads((ROOT / "scripts" / "library.json").read_text(encoding="utf-8"))
    print("script: fallback library")
    return lib[index % len(lib)]


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
    topics = json.loads((ROOT / "topics.json").read_text(encoding="utf-8"))["topics"]
    idx = state["next_index"] % len(topics)
    topic = topics[idx]
    today = datetime.date.today().isoformat()

    data = None
    key = os.environ.get("GEMINI_API_KEY")
    if key:
        data = gemini_script(topic, key)
    if data is None:
        data = fallback_script(idx)

    data["slug"] = f"{today}-{idx:02d}"
    data["topic"] = topic
    data.setdefault("privacy", "public")
    (ROOT / "today.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    video = cinematic.build_video(data)
    print(f"VIDEO: {video}")
    vid = pipeline.upload(video, data)

    OUT = ROOT / "output"
    OUT.mkdir(exist_ok=True)
    with (OUT / "log.txt").open("a", encoding="utf-8") as f:
        f.write(f"{today} | topic={topic} | youtube_id={vid} | {video.name}\n")

    if vid:
        state["next_index"] = (idx + 1) % len(topics)
        (ROOT / "state.json").write_text(json.dumps(state), encoding="utf-8")
    else:
        print("Auth missing — state advance nahi hua", file=sys.stderr)
        sys.exit(1)

    if key:
        html = gemini_app(key)
        if html:
            apps = ROOT / "apps-output"
            apps.mkdir(exist_ok=True)
            app_path = apps / f"{today}-tool.html"
            app_path.write_text(html, encoding="utf-8")
            print(f"APP: {app_path}")
            with (OUT / "log.txt").open("a", encoding="utf-8") as f:
                f.write(f"{today} | app={app_path.name}\n")


if __name__ == "__main__":
    main()