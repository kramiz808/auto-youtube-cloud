"""Rozana Hindi audio-drama: recurring cast, characters aapas mein bolte hain, har scene ka alag footage."""
import datetime
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from pipeline import FFMPEG, OUT, ROOT, WORK, media_duration, run
import voice

SERIES = json.loads((ROOT / "series.json").read_text(encoding="utf-8"))
CAST = {c["name"]: c for c in SERIES["cast"]}
LIBRARY = json.loads((ROOT / "assets" / "library" / "manifest.json").read_text(encoding="utf-8"))
TAGS = {m["tag"]: ROOT / m["file"] for m in LIBRARY}
FACE = {m["tag"] for m in LIBRARY if m.get("face")}

PLAN_MODELS = ["gemini-flash-lite-latest", "gemini-3-flash-preview"]
WRITE_MODELS = ["gemini-3-flash-preview", "gemini-flash-lite-latest"]
MUSIC = ROOT / "assets" / "music" / "soft.mp3"
FONT = ROOT / "assets" / "fonts" / "Mukta-Bold.ttf"
GRAD = ROOT / "assets" / "story" / "grad.png"

W, H, FPS = 1080, 1920, 24
CARD, TAIL = 2.8, 0.8
INTRO, OUTRO = 7.0, 9.0
SCENES = 10
CHARS_PER_SCENE = (780, 1050)


def key():
    path = ROOT / "gemini_key.txt"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    import os
    return os.environ.get("GEMINI_API_KEY", "").strip()


def gemini(prompt, models, temperature=1.0):
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": temperature,
                                            "maxOutputTokens": 16000}}).encode("utf-8")
    last = ""
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key()}"
        for attempt in range(2):
            try:
                req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
                resp = json.loads(urllib.request.urlopen(req, timeout=240).read())
                return resp["candidates"][0]["content"]["parts"][0]["text"]
            except urllib.error.HTTPError as exc:
                last = f"{exc.code} {exc.read()[:160].decode('utf-8', 'replace')}"
                print("gemini", model, last[:140])
                if exc.code in (400, 404):
                    break
                time.sleep(15 * (attempt + 1))
            except Exception as exc:
                last = str(exc)[:160]
                print("gemini retry", model, last)
                time.sleep(15 * (attempt + 1))
    raise RuntimeError(f"story text fail: {last}")


def as_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise RuntimeError("model ne JSON nahi diya")
    return json.loads(text[start:end + 1])


def devanagari_ratio(text):
    letters = re.findall(r"[A-Za-z\u0900-\u097F]", text)
    if not letters:
        return 0.0
    return sum(1 for c in letters if "\u0900" <= c <= "\u097F") / len(letters)


def cast_block():
    return "\n".join(
        f"- {c['name']} ({c['role']}, umr {c['age']}): {c['knows']}" for c in SERIES["cast"])


def plan_episode(ep, revealed):
    beat = SERIES["arc"][(ep - 1) % len(SERIES["arc"])]
    prompt = (
        f"Tum ek professional Hindi audio-drama showrunner ho. Series: \"{SERIES['series']}\".\n"
        f"Premise: {SERIES['premise']}\nTone: {SERIES['tone']}\n\nCharacters:\n{cast_block()}\n\n"
        f"Ab EPISODE {ep} likhna hai. Is episode ka beat: {beat['beat']}\n"
        f"Is episode ke ant mein darshak ke mann mein ye sawaal rehna chahiye: {beat['question']}\n"
        f"Pichhle episodes mein ye sach saamne aa chuke hain (inhein dohrao mat, aage badhao): "
        f"{revealed or 'koi nahi — ye pehla episode hai'}\n\n"
        "Sakht niyam:\n"
        "1. Koi narrator/sutradhar nahi. Sirf characters ke dialogue. Mahaul batane ke liye har scene mein ek chhota 'card' text hoga.\n"
        f"2. Kul {SCENES} scenes. Har scene mein sirf 1 ya 2 characters bolein (teesra kabhi nahi).\n"
        "3. Scene 1 = cold open: kahani ka sabse tense pal, beech se shuru. Baaki scenes chronological.\n"
        f"4. Har scene mein 8 se 14 dialogue lines, kul {CHARS_PER_SCENE[0]}-{CHARS_PER_SCENE[1]} akshar. Chhote vakya, beech mein kaatna, chuppi.\n"
        "5. Aakhri scene cliffhanger ho — koi bada sawaal khula chhodo, jawab mat do.\n"
        "6. Sab kuch shuddh Devanagari Hindi mein. Roman/English akshar bilkul nahi.\n"
        f"7. Har scene ka 'setting' inmein se ek ho: {', '.join(SERIES['settings'])}\n\n"
        "Sirf JSON do:\n"
        '{"title":"...","logline":"...","scenes":[{"card":"jagah — samay","setting":"home","speakers":["आरव","सावित्री"],"beat":"is scene mein kya hota hai"}],'
        '"reveal":"is episode mein kya naya sach saamne aaya","cliffhanger":"aakhri adhoora pal","next_question":"agle episode ka sawaal"}'
    )
    plan = as_json(gemini(prompt, PLAN_MODELS, 1.0))
    plan["scenes"] = plan["scenes"][:SCENES]
    plan["episode"] = ep
    return plan


def write_batch(plan, indices, tail):
    names = [c["name"] for c in SERIES["cast"]]
    wanted = [plan["scenes"][i] for i in indices]
    prompt = (
        f"Series \"{SERIES['series']}\" — {SERIES['premise']}\nTone: {SERIES['tone']}\n"
        f"Characters (naam bilkul yahi rakho): {', '.join(names)}\n{cast_block()}\n\n"
        f"Episode {plan['episode']} ka plan:\n"
        + json.dumps({k: plan[k] for k in ("title", "logline", "reveal", "cliffhanger", "next_question")},
                     ensure_ascii=False)
        + "\n\nAb in scenes ke poore dialogue likho (isi kram mein):\n"
        + json.dumps(wanted, ensure_ascii=False)
        + f"\n\nPichhla scene ka ant (continuity): {tail}\n\n"
        "Sakht niyam:\n"
        "- Sirf wahi 1-2 speakers jo scene ke 'speakers' mein diye hain. Naam ki spelling bilkul waisi hi.\n"
        "- Har line 4 se 22 shabd. Asli bolchaal ki Hindi, kitabi nahi. Taana, chuppi, beech mein kaatna — sab chalega.\n"
        "- Har scene mein 8-14 lines aur kul 780-1050 akshar. Kam mat likho.\n"
        "- Koi narration, koi stage direction bracket mein nahi, koi English shabd nahi. Sirf Devanagari.\n"
        "- Jaankari dialogue se bahar aaye, summary se nahi. Koi kirdar apna parichay nahi dega.\n\n"
        'Sirf JSON do: {"scenes":[{"lines":[{"speaker":"naam","text":"...","emotion":"is line ka bhaav, English mein ek chhota phrase"}]}]}'
    )
    got = as_json(gemini(prompt, WRITE_MODELS, 0.95))["scenes"]
    out = []
    for i, scene in enumerate(wanted):
        lines = got[i]["lines"] if i < len(got) else []
        out.append(dict(scene, lines=lines))
    return out


def repair(scene):
    allowed = [s for s in scene.get("speakers", []) if s in CAST]
    fallback = allowed[0] if allowed else SERIES["cast"][0]["name"]
    lines = []
    for ln in scene.get("lines", []):
        sp = ln.get("speaker", "")
        if sp not in CAST:
            sp = next((a for a in allowed if a[:2] == sp[:2]), fallback)
        text = re.sub(r"\s+", " ", str(ln.get("text", ""))).strip()
        text = re.sub(r"[\(\[].*?[\)\]]", "", text).strip()
        if not text or devanagari_ratio(text) < 0.75:
            continue
        lines.append({"speaker": sp, "text": text, "emotion": str(ln.get("emotion", ""))[:160]})
    speakers = list(dict.fromkeys(l["speaker"] for l in lines))
    if len(speakers) > 2:
        keep = speakers[:2]
        lines = [dict(l, speaker=keep[0]) if l["speaker"] not in keep else l for l in lines]
    scene["lines"] = lines
    scene["speakers"] = list(dict.fromkeys(l["speaker"] for l in lines))
    scene["chars"] = sum(len(re.sub(r"\s+", "", l["text"])) for l in lines)
    return scene


def grow(scene, plan):
    prompt = (
        f"Series \"{SERIES['series']}\". Is scene ke dialogue bahut chhote hain ({scene['chars']} akshar). "
        f"Inhein badhakar 850-1000 akshar karo. Wahi {scene['speakers']} speakers, wahi baat, bas aur gehri behas, "
        "chhote vakya, beech mein kaatna, aur asli bhaav jodo. Naya twist mat jodo. Sirf Devanagari.\n"
        + json.dumps({"scene": scene, "plan_title": plan["title"]}, ensure_ascii=False)
        + '\nSirf JSON: {"lines":[{"speaker":"...","text":"...","emotion":"..."}]}'
    )
    try:
        scene["lines"] = as_json(gemini(prompt, WRITE_MODELS, 0.9))["lines"]
    except Exception as exc:
        print("grow skip:", str(exc)[:100])
    return repair(scene)


def write_episode(ep, revealed):
    plan = plan_episode(ep, revealed)
    print("PLAN:", plan["title"], "|", len(plan["scenes"]), "scenes")
    scenes, tail = [], plan["logline"]
    for start in range(0, len(plan["scenes"]), 3):
        idx = list(range(start, min(start + 3, len(plan["scenes"]))))
        for scene in write_batch(plan, idx, tail[-500:]):
            scene = repair(scene)
            if scene["chars"] < 620:
                scene = grow(scene, plan)
            if not scene["lines"]:
                raise RuntimeError(f"scene {len(scenes) + 1} khaali hai")
            scenes.append(scene)
            tail = scene["lines"][-1]["text"]
        print("scenes written:", len(scenes), "chars:", sum(s["chars"] for s in scenes))
    plan["scenes"] = scenes
    total = sum(s["chars"] for s in scenes)
    print("total chars:", total, "~", round(total / 8.5 / 60, 1), "min dialogue")
    if total < 5200:
        raise RuntimeError(f"episode bahut chhota: {total} akshar")
    return plan


def ass_time(t):
    h, m = int(t // 3600), int(t % 3600 // 60)
    return f"{h}:{m:02d}:{t % 60:05.2f}"


def ass_escape(text):
    return text.replace("{", "(").replace("}", ")")


def ass_lines(text, width, max_lines):
    return "\\N".join(ass_escape(l) for l in wrap(text, width, max_lines))


def wrap(text, width=30, max_lines=3):
    lines, cur = [], ""
    for word in text.split():
        if len(cur) + len(word) + 1 > width:
            lines.append(cur)
            cur = word
        else:
            cur = (cur + " " + word).strip()
    if cur:
        lines.append(cur)
    return lines[:max_lines] or [""]


def ass_color(hex_rgb):
    r, g, b = hex_rgb[0:2], hex_rgb[2:4], hex_rgb[4:6]
    return f"&H00{b}{g}{r}&"


ASS_HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Mukta,60,&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,1,4,2,2,70,70,185,1
Style: Name,Mukta,44,&H00FFFFFF,&H00FFFFFF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,1,3,2,5,60,60,0,1
Style: Card,Mukta,66,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,2,5,80,80,0,1
Style: Big,Mukta,86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,5,2,5,70,70,0,1
Style: Tiny,Mukta,32,&H00C8C8C8,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,1,8,60,60,54,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def series_stamp(episode, total):
    return (f"Dialogue: 2,0:00:00.00,{ass_time(total)},Tiny,,0,0,0,,"
            f"{{\\fad(400,400)}}{ass_escape(SERIES['series'])}  ·  एपिसोड {episode}")


def scene_ass(scene, timings, duration, path):
    lines = [ASS_HEAD, series_stamp(scene.get("episode", 1), duration)]
    card = ass_lines(scene["card"], 22, 2)
    lines.append(f"Dialogue: 1,0:00:00.20,{ass_time(CARD - 0.2)},Card,,0,0,0,,"
                 f"{{\\pos(540,860)\\an5\\fad(350,300)}}{card}")
    for (start, end), ln in zip(timings, scene["lines"]):
        color = ass_color(CAST[ln["speaker"]]["color"])
        body = ass_lines(ln["text"], 30, 3)
        s, e = start + CARD, end + CARD
        lines.append(f"Dialogue: 0,{ass_time(s)},{ass_time(e)},Sub,,0,0,0,,"
                     f"{{\\c{color}\\fad(70,70)}}{body}")
        lines.append(f"Dialogue: 1,{ass_time(s)},{ass_time(e)},Name,,0,0,0,,"
                     f"{{\\pos(540,1452)\\an5\\c{color}\\fad(70,70)}}{ass_escape(ln['speaker'])}")
        lines.append(f"Dialogue: 1,{ass_time(s)},{ass_time(e)},Name,,0,0,0,,"
                     f"{{\\pos(540,1492)\\an5\\c{color}\\fad(70,70)\\p1}}"
                     f"m -70 0 l 70 0 70 5 -70 5{{\\p0}}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def card_ass(title, sub, duration, path, big=False):
    lines = [ASS_HEAD]
    style = "Big" if big else "Card"
    body = ass_lines(title, 18 if big else 22, 3)
    lines.append(f"Dialogue: 1,0:00:00.40,{ass_time(duration - 0.4)},{style},,0,0,0,,"
                 f"{{\\pos(540,880)\\an5\\fad(500,400)}}{body}")
    if sub:
        small = ass_lines(sub, 28, 3)
        lines.append(f"Dialogue: 1,0:00:01.20,{ass_time(duration - 0.4)},Card,,0,0,0,,"
                     f"{{\\pos(540,1120)\\an5\\fad(500,400)\\fs48}}{small}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def silence(seconds, path):
    run([FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
         "-t", f"{seconds:.3f}", "-c:a", "pcm_s16le", path])
    return path


def make_gradient():
    if GRAD.exists():
        return GRAD
    GRAD.parent.mkdir(parents=True, exist_ok=True)
    run([FFMPEG, "-y", "-f", "lavfi", "-i", f"color=c=black@0.0:s={W}x{H},format=rgba",
         "-vf", "geq=r=0:g=0:b=0:a='255*(0.72*max(0,1-Y/430) + 0.80*max(0,(Y-1280)/640))'",
         "-frames:v", "1", GRAD])
    return GRAD


def render_piece(clip, wav, ass, duration, out, face=False, grain=True):
    shutil.copy(FONT, WORK / "dfont.ttf")
    make_gradient()
    blur = ",boxblur=10:2" if face else ""
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps={FPS},"
          "zoompan=z='1.04+0.05*sin(on/240)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=24,"
          f"eq=contrast=1.07:saturation=0.88:brightness=-0.045:gamma=0.98{blur}")
    if grain:
        vf += ",noise=alls=5:allf=t"
    graph = (
        f"[0:v]{vf}[base];"
        "[base][2:v]overlay=0:0:format=auto[g];"
        f"[g]ass={ass.name}:fontsdir=.[v];"
        "[1:a]anull[a]"
    )
    run([FFMPEG, "-y",
         "-stream_loop", "-1", "-i", clip,
         "-i", wav,
         "-i", GRAD,
         "-filter_complex", graph,
         "-map", "[v]", "-map", "[a]",
         "-t", f"{duration:.3f}", "-r", str(FPS),
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
         "-movflags", "+faststart", out], cwd=WORK)
    return out


def pick_clip(setting, used):
    tag = setting if setting in TAGS else None
    if tag is None or tag in used:
        tag = next((t for t in SERIES["settings"] if t in TAGS and t not in used), None)
    if tag is None:
        tag = next((t for t in TAGS if t not in used), next(iter(TAGS)))
    used.add(tag)
    return TAGS[tag], tag in FACE


def build(plan, slug):
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    drama = WORK / "drama"
    drama.mkdir(exist_ok=True)
    used, pieces, timeline = set(), [], []
    models = voice.DRAMA_MODELS

    intro_wav = silence(INTRO, WORK / "intro.wav")
    intro_ass = card_ass(f"{SERIES['series']}\nएपिसोड {plan['episode']}", plan["title"],
                         INTRO, WORK / "intro.ass", big=True)
    clip, face = pick_clip("sunrise", used)
    pieces.append(render_piece(clip, intro_wav, intro_ass, INTRO, WORK / "p_intro.mp4", face, grain=False))

    for i, scene in enumerate(plan["scenes"]):
        scene["episode"] = plan["episode"]
        wav = drama / f"s{i:02d}.wav"
        meta_path = drama / f"s{i:02d}.json"
        if not wav.exists():
            turns = scene["lines"]
            k = i % len(models)
            order = models[k:] + models[:k]
            raw = drama / f"s{i:02d}_raw.wav"
            voice.dialogue_audio(turns, CAST, raw, models=order)
            dur = media_duration(raw)
            timings = voice.align_lines(turns, dur, voice.silence_gaps(raw))
            lead = silence(CARD, WORK / f"lead{i}.wav")
            tail = silence(TAIL, WORK / f"tail{i}.wav")
            lst = WORK / f"lst{i}.txt"
            lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in (lead, raw, tail)), encoding="utf-8")
            run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", lst,
                 "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1", wav])
            meta_path.write_text(json.dumps({"duration": dur, "timings": timings}, ensure_ascii=False),
                                 encoding="utf-8")
        else:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            dur, timings = meta["duration"], [tuple(t) for t in meta["timings"]]
        total = CARD + dur + TAIL
        ass = scene_ass(scene, timings, total, WORK / f"sc{i:02d}.ass")
        clip, face = pick_clip(scene.get("setting", ""), used)
        pieces.append(render_piece(clip, wav, ass, total, WORK / f"p{i:02d}.mp4", face))
        timeline.append({"card": scene["card"], "seconds": round(total, 1), "lines": len(scene["lines"])})
        print(f"scene {i + 1}/{len(plan['scenes'])}: {total:.1f}s, {len(scene['lines'])} lines, {clip.stem}")

    outro_wav = silence(OUTRO, WORK / "outro.wav")
    outro_ass = card_ass(plan["next_question"], "अगला एपिसोड कल — चैनल सब्सक्राइब कर लो",
                         OUTRO, WORK / "outro.ass")
    clip, face = pick_clip("city-night", used)
    pieces.append(render_piece(clip, outro_wav, outro_ass, OUTRO, WORK / "p_outro.mp4", face, grain=False))

    lst = WORK / "pieces.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in pieces), encoding="utf-8")
    joined = WORK / "joined.mp4"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])
    total = media_duration(joined)

    video = OUT / f"{slug}.mp4"
    graph = (
        "[0:a]asplit=2[voc][key];"
        f"[1:a]volume=0.20,afade=t=in:st=0:d=3,afade=t=out:st={max(0, total - 5):.1f}:d=5[mus];"
        "[mus][key]sidechaincompress=threshold=0.02:ratio=10:attack=20:release=500[duck];"
        "[voc][duck]amix=inputs=2:duration=first:normalize=0,"
        "alimiter=limit=0.95,loudnorm=I=-16:TP=-1.5:LRA=11[a]"
    )
    run([FFMPEG, "-y", "-i", joined, "-stream_loop", "-1", "-i", MUSIC,
         "-filter_complex", graph, "-map", "0:v", "-map", "[a]",
         "-t", f"{total:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
         "-ar", "48000", "-movflags", "+faststart", video])
    print("TIMELINE:", json.dumps(timeline, ensure_ascii=False))
    return video, total


def already_on_channel(day, series):
    from googleapiclient.discovery import build
    from pipeline import get_creds
    creds = get_creds()
    if creds is None:
        return False
    yt = build("youtube", "v3", credentials=creds)
    ch = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]
    items = yt.playlistItems().list(
        playlistId=ch["contentDetails"]["relatedPlaylists"]["uploads"],
        part="snippet", maxResults=25).execute().get("items", [])
    for it in items:
        s = it.get("snippet", {})
        if str(s.get("publishedAt", "")).startswith(day) and series in s.get("title", ""):
            return True
    return False


def main():
    from pipeline import mark_blocked, upload, upload_blocked, UploadLimitReached
    today = datetime.date.today().isoformat()
    log = OUT / "stories.txt"
    if log.exists() and any(l.startswith(today) and "| ep" in l
                            for l in log.read_text(encoding="utf-8").splitlines()):
        print("SKIP: aaj ka episode pehle hi upload ho chuka hai")
        sys.exit(0)
    if already_on_channel(today, SERIES["series"]):
        print("SKIP: aaj ka episode channel par pehle se hai")
        sys.exit(0)
    if upload_blocked():
        print("SKIP: YouTube upload quota reset ka intezaar")
        sys.exit(0)

    state_path = ROOT / "story_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    ep = state.get("episode", 1)
    cache = OUT / f"episode-{today}.json"
    if cache.exists():
        plan = json.loads(cache.read_text(encoding="utf-8"))
        print("cached script:", plan["title"])
    else:
        plan = write_episode(ep, state.get("revealed", []))
        cache.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    slug = f"drama-ep{ep:02d}-{today}"
    video, total = build(plan, slug)
    minutes = round(total / 60)
    print("VIDEO:", video, round(video.stat().st_size / 1e6, 1), "MB", f"{minutes} min")

    recap = "\n".join(f"- {r}" for r in state.get("revealed", [])[-4:])
    desc = f"{plan['logline']}\n\n"
    if recap:
        desc += f"Pichhle episodes mein:\n{recap}\n\n"
    desc += (f"Is episode ka sawaal: {plan['next_question']}\n\n"
             "Poori series ek hi playlist mein — episode 1 se shuru karo.\n"
             "Har roz naya episode. Subscribe kar lo taaki agla hissa chhoote nahi.\n\n"
             f"#hindikahani #audiodrama #suspense #{SERIES['series'].replace(' ', '')}")
    data = {
        "title": f"{plan['title']} | {SERIES['series']} एपिसोड {ep}"[:100],
        "description": desc,
        "hashtags": f"#hindikahani #audiodrama #suspensestory #{SERIES['series'].replace(' ', '')}",
        "tags": ["hindi kahani", "audio drama", "hindi suspense story", "family drama",
                 "kahaniyan", "hindi audio story", SERIES["series"], "emotional story"],
        "attribution": "Footage: Mixkit free stock video (mixkit.co), royalty-free licence. "
                       "Dialogue performed with Gemini TTS. Story written with AI. "
                       "Sabhi kirdar aur ghatnayein kalpanik hain.",
        "privacy": "public",
    }
    try:
        vid = upload(video, data)
    except UploadLimitReached as exc:
        mark_blocked()
        print("SKIP: upload limit full —", str(exc)[:80], file=sys.stderr)
        sys.exit(0)
    if not vid:
        print("Auth missing — record nahi bana, agla tick retry karega", file=sys.stderr)
        sys.exit(1)
    with log.open("a", encoding="utf-8") as f:
        f.write(f"{today} | ep{ep} | {plan['title']} | {minutes}min | youtu.be/{vid}\n")
    try:
        import ig
        if ig.token():
            ig.publish(ig.teaser(video, 60),
                       f"{plan['title']} | episode {ep} — poori kahani YouTube par\n\n{data['hashtags']}")
    except Exception as exc:
        print("IG SKIP:", str(exc)[:200])
    state["episode"] = ep + 1
    state.setdefault("revealed", []).append(plan.get("reveal", ""))
    state["revealed"] = state["revealed"][-14:]
    state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()