"""Daily 20-25 min Hindi audio-story video: Gemini script, edge narration, blurred backdrop, burned subs."""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

from pipeline import FFMPEG, ROOT, WORK, OUT, media_duration, run

MODEL = "gemini-flash-lite-latest"
VOICE = "hi-IN-MadhurNeural"
RATE = "-6%"
W, H, FPS = 1080, 1920, 24
INTRO, OUTRO, GAP = 5.0, 6.0, 0.18
CHUNK = 80
BG = ROOT / "assets" / "story" / "bg.mp4"
MUSIC = ROOT / "assets" / "music" / "soft.mp3"
FONT = ROOT / "assets" / "fonts" / "Mukta-Bold.ttf"
PARTS = 3

TOPICS = [
    "maa ka woh jhooth jo sach se bada tha",
    "do bhai aur pitaji ki purani diary",
    "gareebi mein pali behen aur uski padhai",
    "chhoti si dukaan aur zameer ka imtihaan",
    "gaon se shehar aaya ladka aur wada",
    "shaadi ke baad pehli raat ka faisla",
    "purane dost ka dhokha aur maafi",
    "naukri, ijjat aur pitaji ka sapna",
    "ek befikra ladki aur uski maa ki bimari",
    "chachaji ki jaydaad aur bhai ka pyar",
    "gareeb chai wale ka beta aur exam",
    "ek khoya hua bachpan aur purani tasveer",
    "pehla pyaar, pehla intezaar, aakhri faisla",
    "chor ki maa aur uski himmat",
    "zameen ka jhagda aur bhai-behen",
    "hospital ki seedhi aur aadhi raat ka faisla",
    "namaaz kabooliyat aur maafi ka rasta",
    "ek taxiwala aur uski beemar biwi",
    "sacchai bolne wali chhoti behen",
    "retire hote pitaji ka aakhri din",
]


def key():
    path = ROOT / "gemini_key.txt"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    import os
    return os.environ.get("GEMINI_API_KEY", "").strip()


def gemini(prompt, temperature=1.0):
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": temperature}}).encode("utf-8")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key()}"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.loads(resp.read())
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as exc:
            print("gemini text retry", attempt + 1, str(exc)[:120])
            time.sleep(20 * (attempt + 1))
    raise RuntimeError("story text fail")


def as_json(text):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def make_outline(topic):
    prompt = (
        "Tum ek pro Hindi story writer ho. Ek 20-25 minute ki audio story (sunne wali kahani) ka outline banao.\n"
        f"Topic: {topic}\n"
        "Audience: 18-45 saal ke Indian, rishton wali emotional kahaniyan pasand karte hain.\n"
        "Rules: pehle 30 second ka strong hook, 14 chapters, beech mein ek bada twist, climax emotional, "
        "ending sachchai wali (jhoothi khushi nahi), aur ek seedha moral. Kahani believable ho, filmy melodrama nahi.\n"
        "SIRF JSON do: {\"title\":\"...\",\"hook\":\"...\",\"moral\":\"...\",\"chapters\":[{\"name\":\"...\",\"beat\":\"...\"}]}"
    )
    return as_json(gemini(prompt))


def write_part(outline, start, end, tail):
    names = [c["name"] for c in outline["chapters"][start:end]]
    prompt = (
        "Hindi story ka outline:\n" + json.dumps(outline, ensure_ascii=False) + "\n\n"
        f"Ab in chapters ko poora likho: {', '.join(names)}.\n"
        "Har chapter 200-220 shabd, bolne layak natural Hindi, chhote dialogue allowed, "
        "koi heading/numbering text ke andar nahi. Repeat mat karo.\n"
        f"Pichhle chapter ka aakhri hissa (continuity ke liye): {tail}\n"
        "SIRF JSON do: {\"chapters\":[{\"name\":\"...\",\"text\":\"...\"}]}"
    )
    return as_json(gemini(prompt, 0.9))["chapters"]


def word_count(text):
    return len(re.findall(r"\S+", text))


def expand_short(outline, chapters):
    short = [c for c in chapters if word_count(c["text"]) < 180]
    if not short:
        return chapters
    payload = [{"name": c["name"], "text": c["text"]} for c in short[:6]]
    prompt = (
        "Ye Hindi story ke adhoore chapters hain. Har chapter ko 200-220 shabd ka poora karo. "
        "Same kahani, same characters, bas detail aur dialogue add karo. Kuch naya twist mat jodo.\n"
        + json.dumps({"outline": outline, "chapters": payload}, ensure_ascii=False)
        + "\nSIRF JSON do: {\"chapters\":[{\"name\":\"...\",\"text\":\"...\"}]}"
    )
    try:
        fixed = {c["name"]: c["text"] for c in as_json(gemini(prompt, 0.8))["chapters"]}
    except Exception as exc:
        print("expand skip:", str(exc)[:100])
        return chapters
    return [dict(c, text=fixed.get(c["name"], c["text"])) for c in chapters]


def write_story(topic):
    outline = make_outline(topic)
    print("outline:", outline["title"], "|", len(outline["chapters"]), "chapters")
    chapters = []
    per = (len(outline["chapters"]) + PARTS - 1) // PARTS
    for i in range(0, len(outline["chapters"]), per):
        part = write_part(outline, i, min(i + per, len(outline["chapters"])),
                          chapters[-1]["text"][-400:] if chapters else outline["hook"])
        chapters.extend(part)
        print("part", i // per + 1, "->", len(part), "chapters")
    chapters = expand_short(outline, chapters)
    total_words = sum(word_count(c["text"]) for c in chapters)
    print("words:", total_words, "~", round(total_words / 140, 1), "min")
    if total_words < 2200:
        raise RuntimeError(f"story too short: {total_words} words")
    return outline, chapters


def chunks_of(text):
    out = []
    for sentence in re.split(r"(?<=[।?!.])\s+", text.strip()):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= CHUNK:
            out.append(sentence)
            continue
        cur = ""
        for word in sentence.split():
            if len(cur) + len(word) + 1 > CHUNK:
                out.append(cur)
                cur = word
            else:
                cur = (cur + " " + word).strip()
        if cur:
            out.append(cur)
    merged = []
    for piece in out:
        if merged and len(merged[-1]) + len(piece) + 1 <= CHUNK:
            merged[-1] = merged[-1] + " " + piece
        else:
            merged.append(piece)
    return merged


async def _tts(text, path):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(path))


def narrate(chunks):
    import asyncio
    wavs = []
    for i, text in enumerate(chunks):
        mp3 = WORK / f"n_{i:03d}.mp3"
        wav = WORK / f"n_{i:03d}.wav"
        for attempt in range(3):
            try:
                asyncio.run(_tts(text, mp3))
                run([FFMPEG, "-y", "-i", mp3, "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", wav])
                break
            except Exception as exc:
                print("tts retry", i, attempt + 1, str(exc)[:80])
                time.sleep(3)
        else:
            raise RuntimeError(f"tts fail chunk {i}")
        wavs.append(wav)
        if i % 20 == 0:
            print("tts", i, "/", len(chunks))
    return wavs


def silence(seconds, path):
    run([FFMPEG, "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
         "-t", f"{seconds:.3f}", "-c:a", "pcm_s16le", path])
    return path


def ass_time(t):
    h, m = int(t // 3600), int(t % 3600 // 60)
    return f"{h}:{m:02d}:{t % 60:05.2f}"


def ass_text(text):
    return text.replace("{", "(").replace("}", ")")


def wrap_lines(text, width=40, max_lines=3):
    lines, cur = [], ""
    for word in text.split():
        if len(cur) + len(word) + 1 > width:
            lines.append(cur)
            cur = word
        else:
            cur = (cur + " " + word).strip()
    if cur:
        lines.append(cur)
    return lines[:max_lines]


def build_ass(events, title, hook, total, path):
    head = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Mukta,58,&H00FFFFFF,&H00FFFFFF,&H00121212,&H90000000,-1,0,0,0,100,100,0,0,1,4,2,2,60,60,380,1
Style: Card,Mukta,74,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,5,2,5,90,90,0,1
Style: Small,Mukta,46,&HD0D0D0D0,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,4,2,2,80,80,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [head]
    card = "\\N".join(wrap_lines(title, 18, 3))
    lines.append(f"Dialogue: 0,0:00:00.00,0:00:0{int(INTRO)-1}.00,Card,,0,0,0,,{{\\fad(400,300)}}{ass_text(card)}")
    sub = "\\N".join(wrap_lines(hook, 26, 2))
    lines.append(f"Dialogue: 0,0:00:02.00,0:00:0{int(INTRO)}.00,Small,,0,0,0,,{{\\fad(300,200)}}{ass_text(sub)}")
    for start, end, text in events:
        body = "\\N".join(wrap_lines(text, 40, 3))
        lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Sub,,0,0,0,,{ass_text(body)}")
    thanks = "\\N".join(wrap_lines("कल की नई कहानी के लिए सब्सक्राइब करना मत भूलना", 20, 2))
    lines.append(f"Dialogue: 0,{ass_time(total - OUTRO + 1)},{ass_time(total - 0.5)},Card,,0,0,0,,"
                 f"{{\\fad(500,400)}}{ass_text(thanks)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def build(outline, chapters, slug):
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    text = "\n".join(c["text"] for c in chapters)
    chunks = chunks_of(text)
    print("chunks:", len(chunks))
    wavs = narrate(chunks)

    list_file = WORK / "concat.txt"
    gap = silence(GAP, WORK / "gap.wav")
    lead = silence(INTRO, WORK / "lead.wav")
    tail = silence(OUTRO, WORK / "tail.wav")
    entries = [lead]
    for w in wavs:
        entries.extend([w, gap])
    entries.append(tail)
    list_file.write_text("".join(f"file '{p.as_posix()}'\n" for p in entries), encoding="utf-8")
    narration = WORK / "narration.wav"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", list_file,
         "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", narration])

    t = INTRO
    events = []
    for w in wavs:
        d = media_duration(w)
        events.append((t, t + d, chunks[len(events)]))
        t += d + GAP
    total = t - GAP + OUTRO
    print("total:", round(total / 60, 1), "min")

    import shutil
    shutil.copy(FONT, WORK / "subfont.ttf")
    ass = build_ass(events, outline["title"], outline["hook"], total, WORK / "story.ass")

    video = OUT / f"{slug}.mp4"
    graph = (
        "[0:v]fps=24,setsar=1[bg];"
        f"[bg]ass=story.ass:fontsdir=.[v];"
        "[1:a]highpass=f=80,acompressor=threshold=-18dB:ratio=3:attack=6:release=160[voice];"
        f"[2:a]volume=0.16,afade=t=in:st=0:d=2,afade=t=out:st={max(0, total - 4):.1f}:d=4[mus];"
        "[voice][mus]amix=inputs=2:duration=first:normalize=0,"
        "alimiter=limit=0.95,loudnorm=I=-16:TP=-1.5:LRA=11[a]"
    )
    run([FFMPEG, "-y",
         "-stream_loop", "-1", "-i", BG,
         "-i", narration,
         "-stream_loop", "-1", "-i", MUSIC,
         "-filter_complex", graph,
         "-map", "[v]", "-map", "[a]",
         "-t", f"{total:.2f}", "-r", "24",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart",
         video], cwd=WORK)
    return video, total


def split_upload(video, data):
    dur = media_duration(video)
    cut = dur / 2
    first = None
    for i, (ss, span) in enumerate(((0, cut), (cut, dur - cut)), 1):
        part = OUT / f"{video.stem}-part{i}.mp4"
        run([FFMPEG, "-y", "-ss", f"{ss:.2f}", "-i", video, "-t", f"{span:.2f}",
             "-c", "copy", "-avoid_negative_ts", "make_zero", "-movflags", "+faststart", part])
        d = dict(data)
        d["title"] = f"{data['title'][:88]} | Part {i}/2"
        d["description"] = ("Part 1/2.\n\n" if i == 1 else "Part 2/2. Part 1 pehle dekho.\n\n") + data["description"]
        vid = upload(part, d)
        print("PART", i, vid)
        first = first or vid
    return first


def already_on_channel(day):
    """Aaj ki story channel par pehle se hai? Upload log se pata karo (double-post se bachao)."""
    from googleapiclient.discovery import build
    from pipeline import get_creds
    creds = get_creds()
    if creds is None:
        return False
    yt = build("youtube", "v3", credentials=creds)
    ch = yt.channels().list(part="contentDetails", mine=True).execute()["items"][0]
    items = yt.playlistItems().list(
        playlistId=ch["contentDetails"]["relatedPlaylists"]["uploads"],
        part="snippet", maxResults=20).execute().get("items", [])
    for it in items:
        s = it.get("snippet", {})
        if str(s.get("publishedAt", "")).startswith(day) and "Hindi Kahani" in s.get("title", ""):
            return True
    return False


def main():
    import datetime
    from pipeline import mark_blocked, upload_blocked
    today = datetime.date.today().isoformat()
    log = OUT / "stories.txt"
    if log.exists() and any(l.startswith(today) for l in log.read_text(encoding="utf-8").splitlines()):
        print("SKIP: aaj ki story already upload ho chuki hai")
        sys.exit(0)
    if already_on_channel(today):
        print("SKIP: aaj ki story channel par already upload hai")
        sys.exit(0)
    if upload_blocked():
        print("SKIP: YouTube upload quota reset ka intezaar")
        sys.exit(0)
    story_state_path = ROOT / "story_state.json"
    state = json.loads(story_state_path.read_text(encoding="utf-8")) if story_state_path.exists() else {}
    idx = state.get("story_index", 0)
    topic = TOPICS[idx % len(TOPICS)]
    outline, chapters = write_story(topic)
    slug = f"story-{datetime.date.today().isoformat()}"
    video, total = build(outline, chapters, slug)
    minutes = round(total / 60)
    print("VIDEO:", video, round(video.stat().st_size / 1e6, 1), "MB")

    data = {
        "title": f"{outline['title']} | Hindi Kahani"[:100],
        "description": (f"{outline['hook']}\n\n{outline['moral']}\n\n"
                        f"Poori kahani sunne ke liye video chalao — {minutes} minute.\n"
                        "Har roz nayi Hindi kahani.\n\n#kahani #hindikahani #emotionalstory #hindistory"),
        "hashtags": "#kahani #hindikahani #emotionalstory #hindistory",
        "tags": ["hindi kahani", "emotional story", "hindi story", "audio story",
                 "moral story", "family story", "kahaniyan"],
        "attribution": "Background footage: \"Sintel\" (2010) by Blender Foundation (durian.blender.org), CC-BY 3.0. "
                       "Story generated with AI.",
        "privacy": "public",
    }
    from pipeline import upload, UploadLimitReached
    try:
        vid = upload(video, data)
    except UploadLimitReached as exc:
        mark_blocked()
        print("SKIP: upload limit full —", str(exc)[:80], file=sys.stderr)
        sys.exit(0)
    except Exception as exc:
        if "too long" in str(exc).lower():
            print("channel par 15-min limit hai — story 2 parts me upload kar raha hoon", file=sys.stderr)
            vid = split_upload(video, data)
        else:
            raise
    if not vid:
        print("Auth missing — story record nahi bana, agla tick retry karega", file=sys.stderr)
        sys.exit(1)
    with (ROOT / "output" / "stories.txt").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.date.today().isoformat()} | {topic} | {minutes}min | youtu.be/{vid}\n")
    try:
        import ig
        if ig.token():
            ig.publish(ig.teaser(video, 60),
                       f"{outline['title']} | Poori {minutes} min ki kahani YouTube par\n\n"
                       f"{data['hashtags']}")
    except Exception as exc:
        print("IG SKIP:", str(exc)[:200])
    state["story_index"] = idx + 1
    story_state_path.write_text(json.dumps(state), encoding="utf-8")


if __name__ == "__main__":
    main()
