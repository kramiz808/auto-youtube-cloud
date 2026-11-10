"""Daily short = series ka cold-open teaser: hook card, 6-line drama, CTA card.
Profile kholne wala seedha episode playlist ki taraf jaye."""
import json

import voice
from pipeline import FFMPEG, OUT, WORK, media_duration, run
from story import (CARD, TAIL, CAST, SERIES, card_ass, scene_ass, silence, plate_for,
                   scene_video, render_piece, finish, text_completion, as_json, repair)

HOOK, CTA = 4.0, 4.0


def latest_plan():
    caches = sorted(OUT.glob("episode-*.json"))
    if not caches:
        return None
    return json.loads(caches[-1].read_text(encoding="utf-8"))


def episode_link():
    log = OUT / "stories.txt"
    if not log.exists():
        return ""
    eps = [l for l in log.read_text(encoding="utf-8").splitlines() if "| ep" in l]
    return eps[-1].split("youtu.be/")[-1].strip() if eps else ""


def teaser_scene(plan):
    if plan:
        scene = dict(plan["scenes"][0])
        scene["lines"] = scene["lines"][:6]
        scene["episode"] = plan["episode"]
        return repair(scene), plan["episode"], plan.get("next_question", SERIES["tagline"])
    prompt = (
        f"Series \"{SERIES['series']}\" — {SERIES['premise']}\nTone: {SERIES['tone']}\n"
        f"Characters: {', '.join(c['name'] for c in SERIES['cast'])}\n\n"
        "Ek 45-second short ke liye cold-open teaser likho: sirf 2 characters, 6 lines, "
        "kul 380-460 akshar, sabse tense pal beech se shuru. Aakhri line adhoori ho — sawaal khula chhode. "
        "Sirf Devanagari, koi narration nahi.\n"
        'Sirf JSON: {"card":"jagah — samay","setting":"home","speakers":["नाम","नाम"],'
        '"lines":[{"speaker":"...","text":"...","emotion":"..."}]}'
    )
    scene = repair(as_json(text_completion(prompt, 0.95)))
    return scene, 1, SERIES["tagline"]


def build(slug):
    voice.api_key()
    for character in CAST.values():
        voice.resolve_voice_id(character["voice"])
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    plan = latest_plan()
    scene, ep, hook = teaser_scene(plan)
    turns = scene["lines"]
    raw = WORK / "teaser_raw.wav"
    timings = voice.dialogue_audio(turns, CAST, raw)
    dur = media_duration(raw)
    lead = silence(CARD, WORK / "te_lead.wav")
    tail = silence(TAIL, WORK / "te_tail.wav")
    lst = WORK / "te_lst.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in (lead, raw, tail)), encoding="utf-8")
    wav = WORK / "teaser.wav"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", lst,
         "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1", wav])
    total = CARD + dur + TAIL

    hook_ass = card_ass(hook, SERIES["tagline"], HOOK, WORK / "te_hook.ass", big=True)
    pieces = [render_piece(plate_for("home"), silence(HOOK, WORK / "te_hook.wav"), hook_ass,
                           HOOK, WORK / "te_p0.mp4", grain=False)]
    ass = scene_ass(scene, timings, total, WORK / "te_sc.ass")
    sv = scene_video(scene, timings, dur, total, WORK / "te_sv.mp4")
    pieces.append(render_piece(sv, wav, ass, total, WORK / "te_p1.mp4"))
    cta_ass = card_ass("पूरी कहानी चैनल पर", f"{SERIES['series']} — एपिसोड {ep} से शुरू करो",
                       CTA, WORK / "te_cta.ass")
    pieces.append(render_piece(plate_for("city-night"), silence(CTA, WORK / "te_cta.wav"),
                               cta_ass, CTA, WORK / "te_p2.mp4", grain=False))

    plst = WORK / "te_pieces.txt"
    plst.write_text("".join(f"file '{p.as_posix()}'\n" for p in pieces), encoding="utf-8")
    joined = WORK / "te_joined.mp4"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", plst, "-c", "copy", joined])
    video = finish(joined, OUT / f"{slug}.mp4")

    link = episode_link()
    desc = (f"{SERIES['tagline']}\n\n{hook}\n\n"
            f"Poori series ek playlist mein — episode 1 se shuru karo.\n"
            + (f"Is episode ka poora video: https://youtu.be/{link}\n" if link else "")
            + "Har roz naya episode. Subscribe kar lo taaki agla hissa chhoote nahi.\n\n"
            f"#hindikahani #audiodrama #suspense #{SERIES['series'].replace(' ', '')} #shorts")
    data = {
        "title": f"{hook} | {SERIES['series']} #shorts"[:100],
        "description": desc,
        "hashtags": f"#hindikahani #audiodrama #suspensestory #{SERIES['series'].replace(' ', '')} #shorts",
        "tags": ["hindi kahani", "audio drama", "hindi suspense story", SERIES["series"],
                 "kahaniyan", "emotional story", "shorts"],
        "attribution": "Kirdar aur background: AI-generated original art. "
                       "Dialogue performed with ElevenLabs. Story written with AI. "
                       "Sabhi kirdar aur ghatnayein kalpanik hain.",
        "privacy": "public",
    }
    print(f"TEASER: {video.name} {media_duration(video):.1f}s ep{ep}")
    return video, data