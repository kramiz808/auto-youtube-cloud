"""Dragon-style drama: CC-BY animated footage, original Hindi story, lip-synced dub, film-strip edit."""
import json
import hashlib
import shutil
import subprocess
from pathlib import Path

from pipeline import FFMPEG, OUT, ROOT, WORK, media_duration, run
import voice
from story import text_completion, as_json

FONT_FILE = ROOT / "assets" / "fonts" / "Mukta-Bold.ttf"
SCRIPT_DIR = ROOT / "content" / "drama"
MUSIC = ROOT / "assets" / "music" / "epic.mp3"
W, H = 1080, 1920
STRIP_W, STRIP_H, STRIP_Y = 1080, 600, 600
HOOK_SIZE, HOOK_Y, HOOK_LH = 52, 300, 68
SUB_SIZE, SUB_Y, SUB_LH = 44, 1230, 60
MARK_Y = 1590

CAST = {
    "निशा": {"voice": "hi-IN-SwaraNeural", "rate": "+0%", "pitch": "+0Hz"},
    "वृद्ध": {"voice": "hi-IN-MadhurNeural", "rate": "-4%", "pitch": "-6Hz"},
}

SAGA = {
    "series": "ज़िद की राह",
    "tagline": "जो तय्यार करे, रास्ता ख़ुद बन जाता है",
    "cast": {
        "निशा": "गाँव की लड़की, माँ की आख़िरी दवाई पहाड़ी के पार पहुँचाने निकली है। डरती है पर रुकती नहीं।",
        "वृद्ध": "पहाड़ी का पुराना रक्षक, जो हर आने वाले की हिम्मत परखता है।",
    },
}

CLIPS = {
    "sintel_01": {
        "file": "assets/scenes/sintel_01.mp4",
        "visual": "बर्फीला पहाड़ी, आग की रोशनी वाली पुरानी पनाल, बूढ़ा मास्क-पहने रक्षक और तलवार, और आग के सामने खड़ी लड़की",
        "windows": [
            {"start": 7.25, "end": 9.22, "speaker": "वृद्ध", "visual": "बूढ़े रक्षक का हाथ, आग के पास पुरानी तलवार"},
            {"start": 11.8, "end": 15.8, "speaker": "वृद्ध", "visual": "तलवार की धार और आग की रोशनी, हाथ में तलवार"},
            {"start": 18.0, "end": 21.45, "speaker": "निशा", "visual": "लड़की का गंभीर चेहरा, आग की रोशनी में"},
            {"start": 21.75, "end": 24.8, "speaker": "निशा", "visual": "लड़की हाथ आगे करके ज़ोर से बात कर रही है"},
            {"start": 29.4, "end": 33.8, "speaker": "वृद्ध", "visual": "बूढ़े रक्षक का चेहरा सामने से, मास्क और गहरी आँखें"},
            {"start": 35.0, "end": 37.5, "speaker": "निशा", "visual": "लड़की ऊपर देख रही है, हौसले से"},
            {"start": 38.0, "end": 42.2, "speaker": "वृद्ध", "visual": "लड़की हाथ फैलाकर खड़ी, बूढ़े की आवाज़ चल रही है"},
            {"start": 52.95, "end": 55.87, "speaker": "निशा", "visual": "शहर का दूर का नज़ारा, पहाड़ी से नीचे"},
        ],
    },
    "sintel_02": {
        "file": "assets/scenes/sintel_02.mp4",
        "visual": "खंडहर, एक छोटा ड्रैगन बच्चा, रात का अंधेरा और लड़की का चेहरा",
        "windows": [
            {"start": 12.25, "end": 15.5, "speaker": "निशा", "visual": "लड़की ड्रैगन बच्चे का पट्टी बाँध रही है"},
            {"start": 15.75, "end": 18.5, "speaker": "निशा", "visual": "ड्रैगन बच्चा, लड़की उसके पास"},
            {"start": 33.25, "end": 37.25, "speaker": "निशा", "visual": "रात का अंधेरा खंडहर, लड़की बैठी है"},
            {"start": 55.35, "end": 58.85, "speaker": "निशा", "visual": "लड़की दौड़ते हुए, पीछे ड्रैगन"},
            {"start": 70.25, "end": 73.25, "speaker": "निशा", "visual": "लड़की का चेहरा, आँखें फटी हुई"},
        ],
    },
    "sintel_03": {
        "file": "assets/scenes/sintel_03.mp4",
        "visual": "पहाड़ी का दरवाज़ा, बर्फ और रोशनी, बूढ़ा रक्षक और हारी हुई लड़की",
        "windows": [
            {"start": 20.85, "end": 22.5, "speaker": "निशा", "visual": "लड़की हाथ छोड़ती हुई, हार का इशारा"},
            {"start": 27.8, "end": 31.5, "speaker": "वृद्ध", "visual": "बूढ़ा रक्षक सामने से बात कर रहा है"},
            {"start": 32.8, "end": 35.5, "speaker": "वृद्ध", "visual": "बूढ़ा रक्षक, पहाड़ी की ओर इशारा"},
            {"start": 35.85, "end": 39.0, "speaker": "वृद्ध", "visual": "बूढ़े रक्षक का भरोसेमंद चेहरा"},
        ],
    },
    "sintel_04": {
        "file": "assets/scenes/sintel_04.mp4",
        "visual": "गुफा, ड्रैगन की परछाईं, रोशनी की किरण और लड़की का चेहरा",
        "windows": [
            {"start": 9.6, "end": 11.5, "speaker": "निशा", "visual": "लड़की चिल्लाते हुए, गुफा में"},
            {"start": 13.6, "end": 16.0, "speaker": "वृद्ध", "visual": "गुफा में ड्रैगन की परछाईं"},
            {"start": 18.2, "end": 21.8, "speaker": "निशा", "visual": "लड़की का चेहरा, रोशनी की किरण में"},
        ],
    },
}

ATTRIBUTION = ('Footage: "Sintel" (2010) by Blender Foundation (durian.blender.org), '
               'licensed CC-BY 3.0. Original Hindi dialogue, story and voice by this channel.')

# Normalised (x, y) centre of each speaker in the strip, used to punch-in on whoever is talking.
FOCUS = {
    "sintel_01": {"निशा": (0.30, 0.45), "वृद्ध": (0.80, 0.45)},
    "sintel_02": {"निशा": (0.45, 0.50), "वृद्ध": (0.50, 0.50)},
    "sintel_03": {"निशा": (0.25, 0.50), "वृद्ध": (0.75, 0.45)},
    "sintel_04": {"निशा": (0.45, 0.50), "वृद्ध": (0.60, 0.50)},
}
PUNCH_Z = 1.5


def wrap(text, width):
    lines, cur = [], ""
    for word in text.split():
        if len(cur) + len(word) + 1 > width:
            lines.append(cur)
            cur = word
        else:
            cur = (cur + " " + word).strip()
    if cur:
        lines.append(cur)
    return lines


def _drawtext(name, size, y, color="white", alpha="1", enable=None, border=2):
    f = (f"drawtext=fontfile=cfont.ttf:textfile={name}.txt:fontcolor={color}:fontsize={size}:"
         f"x=(w-text_w)/2:y={y}:borderw={border}:bordercolor=black:"
         f"shadowcolor=black@0.55:shadowx=0:shadowy=3")
    if alpha != "1":
        f += f":alpha='{alpha}'"
    if enable:
        f += f":enable='{enable}'"
    return f


def load_script(clip_key, day=None):
    base = SCRIPT_DIR / day if day else SCRIPT_DIR
    path = base / f"{clip_key}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    script = write_chapter(clip_key, saga_state())
    base.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    return script


def saga_state():
    path = SCRIPT_DIR / "state.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")).get("last", "")
    return ""


def remember(script):
    path = SCRIPT_DIR / "state.json"
    last = script["lines"][-1]["text"] if script.get("lines") else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"last": last}, ensure_ascii=False), encoding="utf-8")


def write_chapter(clip_key, saga_state=""):
    clip = CLIPS[clip_key]
    rows = "\n".join(
        f"{i + 1}. {w['start']}-{w['end']}s | {w['speaker']} | दृश्य: {w['visual']} | "
        f"ज़्यादा से ज़्यादा {max(4, int((w['end'] - w['start']) * 2.4))} शब्द"
        for i, w in enumerate(clip["windows"]))
    prompt = f"""तुम एक हिंदी सीरीज़ "{SAGA['series']}" के लिए नया अध्याय लिख रहे हो।
शीर्षक: {SAGA['tagline']}
किरदार:
- निशा: {SAGA['cast']['निशा']}
- वृद्ध: {SAGA['cast']['वृद्ध']}

एक एनिमेटेड फ़िल्म के इस हिस्से पर हम तुम्हारी कहानी डब करेंगे। किरदारों के होंठ सिर्फ़ इन्हीं समय-खंडों में चलते हैं,
इसलिए हर खंड में ठीक एक लाइन होगी, और वो लाइन उस खंड के समय के भीतर बोली जा सके।

समय-खंड:
{rows}

पिछला अध्याय:
{saga_state or "यह पहला अध्याय है।"}

नियम:
- बिल्कुल नई और मौलिक कहानी, किसी फ़िल्म या किताब की डायलॉग कॉपी नहीं।
- हर लाइन सीधे बोली जाने वाली साधारण हिंदी, बिना नैरेशन, बिना स्टेज डायरेक्शन, बिना नाम दोहराए।
- लाइन का मकसद किरदार की मौजूदा हालत से जुड़ा हो — जैसे वो चेहरा, वो हथियार, वो डर।
- भावनात्मक, कसी हुई, सीधी बात। कोई लंबा भाषण नहीं।
- हर लाइन के लिए "emotion" भी बताओ: calm, sad, nervous, angry, determined या whispers में से एक।
- JSON में लौटाओ: {{"title": "क्लिक-वर्टी हिंदी टाइटल #shorts", "hook": "ऊपर दिखने वाला हुक, अधिकतम 70 अक्षर, 2 लाइन",
"description": "हिंदी में 2 लाइन का description", "hashtags": "#shorts #hindi ...",
"lines": [{{"speaker": "निशा या वृद्ध", "text": "...", "emotion": "..."}}]}}
lines की संख्या और क्रम समय-खंडों के बराबर होना चाहिए।"""
    data = as_json(text_completion(prompt, temperature=1.0, json_mode=True))
    lines = data.get("lines") or []
    if len(lines) != len(clip["windows"]):
        raise RuntimeError(f"chapter lines {len(lines)} != windows {len(clip['windows'])}")
    for line, window in zip(lines, clip["windows"]):
        line["start"], line["end"] = window["start"], window["end"]
        line["speaker"] = window["speaker"]
        line["text"] = str(line.get("text", "")).strip()
        if not line["text"]:
            raise RuntimeError("chapter line khaali hai")
    data["lines"] = lines
    data["attribution"] = ATTRIBUTION
    return data


def _shift(base, delta, suffix):
    b = int(base.replace(suffix, "").replace("+", ""))
    d = int(delta.replace(suffix, "").replace("+", ""))
    return f"{b + d:+d}{suffix}"


def line_audio(index, line):
    cast = CAST[line["speaker"]]
    emotion = line.get("emotion", "")
    tag = voice.mood_tag(emotion)
    rate = _shift(cast["rate"], voice.EDGE_RATE.get(tag, "+0%"), "%")
    pitch = _shift(cast["pitch"], voice.EDGE_PITCH.get(tag, "+0Hz"), "Hz")
    return voice.edge_speech(line["text"], cast["voice"], emotion, rate=rate, pitch=pitch)


def _gemini_dub(clip, script, out):
    """Natural Gemini multi-speaker blob, split on the 1s turn pauses and locked to mouth windows."""
    blob = gemini_dialogue(script, WORK / "drama_gemini.wav")
    n = len(script["lines"])
    total = media_duration(blob)
    segs = _speech_segments(blob, n, total)
    if len(segs) != n:
        raise voice.VoiceUnavailable("gemini line split mismatch")
    parts, labels = [], []
    for i, (line, (s, e)) in enumerate(zip(script["lines"], segs)):
        slot = float(line["end"]) - float(line["start"])
        speed = max(0.85, min((e - s) / max(slot, 0.4), 1.3))
        ms = int(round(float(line["start"]) * 1000))
        parts.append(f"[0:a]atrim={s:.3f}:{e:.3f},asetpts=PTS-STARTPTS,atempo={speed:.3f},"
                     f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                     f"adelay={ms}|{ms}[d{i}]")
        labels.append(f"[d{i}]")
    graph = (";".join(parts) + ";" + "".join(labels)
             + f"amix=inputs={n}:duration=longest:normalize=0[voc]")
    run([FFMPEG, "-y", "-i", blob, "-filter_complex", graph, "-map", "[voc]",
         "-c:a", "pcm_s16le", "-ar", "48000", out], cwd=WORK)
    return out


def build_dub(clip, script, out):
    try:
        return _gemini_dub(clip, script, out), True
    except voice.VoiceUnavailable:
        pass
    parts, labels = [], []
    for index, line in enumerate(script["lines"]):
        mp3 = line_audio(index, line)
        dur = media_duration(mp3)
        slot = float(line["end"]) - float(line["start"])
        # Exact-fit: voice spans the whole mouth-window so lips and audio stay locked.
        speed = max(0.9, min(dur / max(slot, 0.4), 1.3))
        ms = int(round(float(line["start"]) * 1000))
        parts.append(f"[{index}:a]atempo={speed:.3f},aresample=48000,"
                     f"aformat=sample_fmts=fltp:channel_layouts=stereo,adelay={ms}|{ms}[d{index}]")
        labels.append(f"[d{index}]")
    graph = (";".join(parts) + ";" + "".join(labels)
             + f"amix=inputs={len(labels)}:duration=longest:normalize=0[voc]")
    ins = [arg for index in range(len(script["lines"])) for arg in ("-i", line_audio(index, script["lines"][index]))]
    run([FFMPEG, "-y", *ins, "-filter_complex", graph, "-map", "[voc]",
         "-c:a", "pcm_s16le", "-ar", "48000", out], cwd=WORK)
    return out, False


def build(clip_key, slug=None, day=None, out=None):
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    clip = CLIPS[clip_key]
    src = ROOT / clip["file"]
    dur = media_duration(src)
    script = load_script(clip_key, day)
    shutil.copy(FONT_FILE, WORK / "cfont.ttf")
    dub, natural = build_dub(clip, script, WORK / "drama_dub.wav")

    filters = []
    hook = script["hook"]
    if len(hook) > 72:
        hook = hook[:72].rsplit(" ", 1)[0] + "…"
    for j, line in enumerate(wrap(hook, 24)[:3]):
        (WORK / f"dhook_{j}.txt").write_text(line, encoding="utf-8")
        filters.append(_drawtext(f"dhook_{j}", HOOK_SIZE, HOOK_Y + j * HOOK_LH,
                                 alpha="min(1,t/0.5)"))
    for k, line in enumerate(script["lines"]):
        start, end = float(line["start"]), float(line["end"])
        for j, seg in enumerate(wrap(line["text"], 32)[:2]):
            (WORK / f"dsub_{k}_{j}.txt").write_text(seg, encoding="utf-8")
            filters.append(_drawtext(f"dsub_{k}_{j}", SUB_SIZE, SUB_Y + j * SUB_LH,
                                     alpha=f"min(1,(t-{start:.2f})/0.15)",
                                     enable=f"between(t,{start:.2f},{end:.2f})"))
    filters.append(
        f"drawtext=fontfile=cfont.ttf:text='|  Z I D D I  |':fontcolor=0x9A9A9A:fontsize=24:"
        f"x=(w-text_w)/2:y={MARK_Y}")

    focus = FOCUS[clip_key]
    zw, zh = int(STRIP_W * PUNCH_Z), int(STRIP_H * PUNCH_Z)
    grade = "eq=contrast=1.06:saturation=1.10:brightness=0.015:gamma=1.08"

    def punch(src, dst, speaker):
        cx, cy = focus.get(speaker, (0.5, 0.5))
        x = min(max(int(cx * zw - STRIP_W / 2), 0), zw - STRIP_W)
        y = min(max(int(cy * zh - STRIP_H / 2), 0), zh - STRIP_H)
        return (f"[{src}]scale={zw}:{zh}:force_original_aspect_ratio=increase,"
                f"crop={zw}:{zh},crop={STRIP_W}:{STRIP_H}:{x}:{y},setsar=1,{grade}[{dst}]")

    def enable_for(speaker):
        terms = [f"between(t,{l['start']:.2f},{l['end']:.2f})"
                 for l in script["lines"] if l["speaker"] == speaker]
        return "+".join(terms) or "0"

    graph = (
        f"[1:v]split=4[bgsrc][wsrc][nsrc][vsrc];"
        f"[bgsrc]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
        f"boxblur=6:1,scale={W}:{H},eq=brightness=-0.10:saturation=1.20:contrast=1.05[bg];"
        f"[wsrc]scale={STRIP_W}:{STRIP_H}:force_original_aspect_ratio=increase,"
        f"crop={STRIP_W}:{STRIP_H},setsar=1,{grade}[v0];"
        + punch("nsrc", "vn", "निशा") + ";"
        + punch("vsrc", "vv", "वृद्ध") + ";"
        + f"[v0][vn]overlay=0:0:enable='{enable_for('निशा')}'[p1];"
        + f"[p1][vv]overlay=0:0:enable='{enable_for('वृद्ध')}'[vstrip];"
        + f"[bg][vstrip]overlay=0:{STRIP_Y}[v1];[v1]{','.join(filters)}[v2];"
        + "[v2][wv]overlay=(main_w-overlay_w)/2:1440[v3];[v3]vignette=PI/5[v];"
        + "[2:a]aresample=48000,aformat=channel_layouts=stereo,"
        + ("highpass=f=80,acompressor=threshold=0.15:ratio=2.5:attack=10:release=200:makeup=1.2,"
           "aecho=0.8:0.18:30:0.12,volume=1.15," if natural else
           "highpass=f=90,lowpass=f=11000,equalizer=f=200:t=q:w=1:g=1.5,"
           "equalizer=f=3000:t=q:w=1.2:g=2,deesser=i=0.25,vibrato=f=5.5:d=0.02,vibrato=f=0.7:d=0.015,"
           "acompressor=threshold=0.12:ratio=3:attack=8:release=180:makeup=1.3,"
           "aecho=0.8:0.22:35:0.15,volume=1.2,")
        + "asplit=4[voc][scA][scB][wvs];"
        + "[wvs]showwaves=s=440x90:colors=0xFFFFFF:rate=30:scale=sqrt[wv];"
        "[1:a]lowpass=f=900,volume=0.5,aresample=48000,aformat=channel_layouts=stereo[amb];"
        "[amb][scA]sidechaincompress=threshold=0.02:ratio=6:attack=15:release=350[ambduck];"
        "[3:a]volume=0.20,aresample=48000,aformat=channel_layouts=stereo[mus];"
        "[mus][scB]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[musduck];"
        "[ambduck][musduck]amix=inputs=2:duration=first:normalize=0[bed];"
        "[bed][voc]amix=inputs=2:duration=first:normalize=0,"
        "alimiter=limit=0.95,loudnorm=I=-14:TP=-1.5:LRA=11[a]")

    out = Path(out) if out else OUT / f"{slug or clip_key}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    run([FFMPEG, "-y",
         "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r=30:d={dur:.3f}",
         "-i", src,
         "-i", dub,
         "-stream_loop", "-1", "-i", MUSIC,
         "-filter_complex", graph,
         "-map", "[v]", "-map", "[a]",
         "-t", f"{dur:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
         "-movflags", "+faststart", out], cwd=WORK)
    return out, script


def chapter_video(clip_key, day):
    folder = OUT / "drama" / day
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{clip_key}.mp4"
    if path.exists():
        return path, load_script(clip_key, day)
    script = load_script(clip_key, day)
    path, _ = build(clip_key, day=day, out=path)
    remember(script)
    return path, script


def episode(day):
    paths, scripts = [], []
    for key in CLIPS:
        path, script = chapter_video(key, day)
        paths.append(path)
        scripts.append(script)
        print(f"chapter {key}: {path.name}", flush=True)
    lst = WORK / "episode.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in paths), encoding="utf-8")
    joined = OUT / "drama" / day / "episode.mp4"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])
    total = media_duration(joined)
    return joined, total, scripts


def short_data(script):
    return {
        "title": script["title"][:100],
        "description": f"{script['description']}\n\n{script['attribution']}",
        "hashtags": script["hashtags"],
        "tags": ["hindi", "motivation", "mindset", "animation", "sintel", "kahani",
                 SAGA["series"], "emotional"],
        "attribution": script["attribution"],
        "privacy": "public",
    }


def episode_data(day, scripts):
    hooks = "\n".join(f"- {s['hook']}" for s in scripts)
    return {
        "title": f"{SAGA['series']} | पूरा एपिसोड — निशा की पहाड़ी #hindikahani"[:100],
        "description": (f"{SAGA['tagline']}\n\nआज के चार अध्याय:\n{hooks}\n\n"
                        "हर रोज़ नई कहानी, नए अध्याय। Subscribe कर लो।\n\n"
                        + "\n".join(s["attribution"] for s in scripts[:1])),
        "hashtags": "#hindikahani #motivation #animation #sintel #ziddi",
        "tags": ["hindi kahani", "animation", "sintel", "motivation", SAGA["series"]],
        "attribution": scripts[0]["attribution"],
        "privacy": "public",
    }


GEMINI_TTS = "gemini-3.1-flash-tts-preview"
GEMINI_TTS_FALLBACKS = ["gemini-2.5-flash-preview-tts", "gemini-3.8-flash-tts"]
GEMINI_VOICES = {"निशा": "Kore", "वृद्ध": "Charon"}


def gemini_dialogue(script, out):
    """One natural multi-speaker Gemini TTS call for the whole chapter (quota-friendly)."""
    import base64
    import urllib.request
    import urllib.error
    from story import gemini_key
    turns = script["lines"]
    speakers = list(dict.fromkeys(l["speaker"] for l in turns))
    dialog = "\n".join(f"{l['speaker']}: {l['text']}" for l in turns)
    prompt = (
        "TTS the following Hindi conversation between characters. Act it like a real emotional "
        "audio drama: natural human delivery, breath, feeling, varied pace. Leave a full "
        "one-second silence between each turn.\n"
        + "\n".join(f"{name}: {SAGA['cast'].get(name, '')}" for name in speakers)
        + "\n" + dialog
    )
    cache = WORK / "gemini_tts"
    cache.mkdir(parents=True, exist_ok=True)
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                "speechConfig": {"multiSpeakerVoiceConfig": {"speakerVoiceConfigs": [
                    {"speaker": s, "voiceConfig": {"prebuiltVoiceConfig": {
                        "voiceName": GEMINI_VOICES.get(s, "Kore")}}} for s in speakers]}}}}
    pcm = None
    for model in [GEMINI_TTS] + GEMINI_TTS_FALLBACKS:
        cached = cache / f"{hashlib.sha256((model + prompt).encode('utf-8')).hexdigest()}.wav"
        if cached.exists():
            shutil.copy(cached, out)
            return out
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json",
                                              "x-goog-api-key": gemini_key()})
        try:
            resp = json.loads(urllib.request.urlopen(req, timeout=300).read())
            parts = resp["candidates"][0]["content"]["parts"]
            blob = next((p.get("inlineData") or p.get("inline_data") for p in parts
                         if p.get("inlineData") or p.get("inline_data")), None)
            if not blob:
                raise RuntimeError("no audio")
            pcm = base64.b64decode(blob["data"])
            used_cache = cached
            break
        except Exception:
            continue
    if pcm is None:
        raise voice.VoiceUnavailable("Gemini TTS failed on all models")
    subprocess.run([FFMPEG, "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", "-",
                    "-c:a", "pcm_s16le", str(out)], input=pcm, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=WORK)
    shutil.copy(out, cached)
    return out


def _speech_segments(wav, n, total):
    """Per-line timings: the n-1 longest silence gaps are the turn boundaries."""
    wav = Path(wav).resolve()
    proc = subprocess.run([FFMPEG, "-hide_banner", "-i", str(wav), "-af",
                           "silencedetect=noise=-30dB:d=0.3", "-f", "null", "-"],
                          capture_output=True, text=True, cwd=WORK)
    text = proc.stderr or ""
    sil = []
    start = None
    for line in text.splitlines():
        if "silence_start:" in line:
            start = float(line.split("silence_start:")[1].strip())
        elif "silence_end:" in line and start is not None:
            sil.append((start, float(line.split("silence_end:")[1].split("|")[0].strip())))
            start = None
    if n <= 1:
        return [(0.0, total)]
    inner = [g for g in sil if g[0] > 0.3 and g[1] < total - 0.3]
    chosen = sorted(sorted(inner, key=lambda g: g[1] - g[0], reverse=True)[:n - 1])
    segs, cur = [], 0.0
    if sil and sil[0][0] <= 0.3:
        cur = sil[0][1]
    for s, e in chosen:
        if s > cur:
            segs.append((cur, s))
        cur = e
    segs.append((cur, total))
    if len(segs) != n:
        step = total / n
        return [(i * step, (i + 1) * step) for i in range(n)]
    return segs


def build_ref(clip_key, slug=None, day=None, out=None, voice_wav=None, script=None):
    """Reference-style aesthetic short: cinematic stills + Ken Burns, blurred ambient bg,
    top hook, bottom subtitles + live audio waveform, natural multi-speaker voice."""
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    clip = CLIPS[clip_key]
    src = ROOT / clip["file"]
    script = script or load_script(clip_key, day)
    lines = script["lines"]
    n = len(lines)
    if voice_wav is None:
        voice_wav = gemini_dialogue(script, WORK / "ref_voice.wav")
    total = media_duration(voice_wav)
    segs = _speech_segments(voice_wav, n, total)
    shutil.copy(FONT_FILE, WORK / "cfont.ttf")

    stills = []
    for i, line in enumerate(lines):
        st = WORK / f"refstill_{clip_key}_{i}.jpg"
        if not st.exists():
            run([FFMPEG, "-y", "-ss", f"{float(line.get('start', i * 3)):.2f}", "-i", src,
                 "-frames:v", "1", "-vf",
                 f"scale={STRIP_W}:{STRIP_H}:force_original_aspect_ratio=increase,"
                 f"crop={STRIP_W}:{STRIP_H}", "-q:v", "2", st], cwd=WORK)
        stills.append(st)

    inputs = [arg for st in stills for arg in ("-i", str(st))]
    inputs += ["-i", str(voice_wav), "-stream_loop", "-1", "-i", str(MUSIC)]
    na, nm = n, n + 1

    parts = []
    for i, (s, e) in enumerate(segs):
        frames = max(1, int(round((e - s) * 30)))
        parts.append(
            f"[{i}:v]zoompan=z='1.06+0.10*on/{frames}':x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':d={frames}:s={STRIP_W}x{STRIP_H}:fps=30,setsar=1,"
            f"eq=contrast=1.06:saturation=1.10:brightness=0.015:gamma=1.08[s{i}]")
    parts.append("".join(f"[s{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[strip]")
    parts.append("[strip]split=2[st][bgs]")
    parts.append(f"[bgs]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
                 f"boxblur=6:1,scale={W}:{H},eq=brightness=-0.10:saturation=1.20:contrast=1.05[bg]")
    parts.append(f"[bg][st]overlay=0:{STRIP_Y}[v1]")

    filters = []
    hook = script["hook"]
    if len(hook) > 72:
        hook = hook[:72].rsplit(" ", 1)[0] + "…"
    for j, seg in enumerate(wrap(hook, 24)[:3]):
        (WORK / f"rhook_{j}.txt").write_text(seg, encoding="utf-8")
        filters.append(_drawtext(f"rhook_{j}", HOOK_SIZE, HOOK_Y + j * HOOK_LH,
                                 alpha="min(1,t/0.5)"))
    for k, (line, (s, e)) in enumerate(zip(lines, segs)):
        for j, seg in enumerate(wrap(line["text"], 32)[:2]):
            (WORK / f"rsub_{k}_{j}.txt").write_text(seg, encoding="utf-8")
            filters.append(_drawtext(f"rsub_{k}_{j}", SUB_SIZE, SUB_Y + j * SUB_LH,
                                     alpha=f"min(1,(t-{s:.2f})/0.15)",
                                     enable=f"between(t,{s:.2f},{e:.2f})"))
    filters.append(
        f"drawtext=fontfile=cfont.ttf:text='|  Z I D D I  |':fontcolor=0x9A9A9A:fontsize=24:"
        f"x=(w-text_w)/2:y={MARK_Y}")
    parts.append(f"[v1]{','.join(filters)}[v2]")
    parts.append(f"[{na}:a]asplit=2[voc][wvs]")
    parts.append("[wvs]showwaves=s=440x90:colors=0xFFFFFF:rate=30:scale=sqrt[wv]")
    parts.append("[v2][wv]overlay=(main_w-overlay_w)/2:1440[v3]")
    parts.append("[v3]vignette=PI/5[v]")
    parts.append("[voc]highpass=f=80,acompressor=threshold=0.15:ratio=2.5:attack=10:release=200:"
                 "makeup=1.2,aecho=0.8:0.18:30:0.12,volume=1.15,asplit=2[voc1][sc]")
    parts.append(f"[{nm}:a]volume=0.15,aresample=48000,aformat=channel_layouts=stereo[mus]")
    parts.append("[mus][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck]")
    parts.append("[duck][voc1]amix=inputs=2:duration=first:normalize=0,"
                 "alimiter=limit=0.95,loudnorm=I=-14:TP=-1.5:LRA=11[a]")

    out = Path(out) if out else OUT / f"{slug or clip_key}-ref.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    run([FFMPEG, "-y", *inputs, "-filter_complex", ";".join(parts),
         "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
         "-movflags", "+faststart", out], cwd=WORK)
    return out, script


if __name__ == "__main__":
    import sys
    key = sys.argv[1] if len(sys.argv) > 1 else "sintel_01"
    path, script = build(key)
    print("built:", path)
    print("title:", script["title"])
