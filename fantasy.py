"""Daily AI cinematic fantasy music-videos: random theme, AI images, dreamy original music,
beat-synced cinematic edit, vertical 9:16, waveform + minimal title/credit. SFW throughout."""
import hashlib
import json
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from pipeline import FFMPEG, OUT, ROOT, WORK, media_duration, run

W, H = 1080, 1920
FPS = 30
PROMPT_PICK = (0, 1, 4, 5)
SCENES = len(PROMPT_PICK)
SCENE_S = 8.0
XFADE = 0.6
FONT_FILE = ROOT / "assets" / "fonts" / "Mukta-Bold.ttf"

SFW = ("modest elegant fantasy attire, fully covered torso, family-safe, no nudity, "
       "photorealistic cinematic, ultra detailed, professional movie lighting, ")

THEMES = [
    {
        "key": "mermaid",
        "title": "Samundar Ki Rani",
        "credit": "ZIDDI • Dreamy Ocean Mix",
        "bpm": 100,
        "grade": "eq=saturation=1.15:contrast=1.06:brightness=0.02,colorbalance=bm=0.08:gm=0.04:bs=0.06",
        "char": "the same young mermaid with long dark teal hair, emerald shimmering tail, elegant seashell bodice",
        "prompts": [
            "beautiful tropical beach, green palm trees, crystal-clear turquoise ocean water, wide establishing shot",
            "{char} swimming gracefully near the beach underwater, flowing hair",
            "cinematic close-up of seashells and colorful ocean treasures on the sandy seabed",
            "{char} exploring a mysterious underwater cave, shimmering fantasy tail, floating particles",
            "cinematic close-up of {char} face and eyes, gentle underwater expression, sunlight rays",
            "breathtaking wide underwater shot, sunlight rays through ocean, {char} swimming into the distance, colorful tropical fish",
        ],
    },
    {
        "key": "forest",
        "title": "Jungle Ki Pari",
        "credit": "ZIDDI • Dreamy Forest Mix",
        "bpm": 96,
        "grade": "eq=saturation=1.12:contrast=1.07:brightness=0.01,colorbalance=gm=0.08:gs=0.05:bm=0.02",
        "char": "the same forest spirit girl with long silver hair, glowing green eyes, elegant leaf-woven gown",
        "prompts": [
            "enchanted misty forest at dawn, giant ancient trees, god rays, wide establishing shot",
            "{char} walking gracefully between glowing mushrooms, flowing gown",
            "cinematic close-up of dew drops, glowing flowers and forest treasures",
            "{char} touching a glowing ancient tree, fireflies swirling, floating particles",
            "cinematic close-up of {char} face and eyes, soft magical expression",
            "breathtaking wide forest shot, {char} walking into the light between giant trees, fireflies",
        ],
    },
    {
        "key": "celestial",
        "title": "Aasman Ki Pari",
        "credit": "ZIDDI • Dreamy Sky Mix",
        "bpm": 104,
        "grade": "eq=saturation=1.10:contrast=1.08:brightness=0.02,colorbalance=bm=0.06:rm=0.03:bs=0.05",
        "char": "the same celestial girl with long white-gold hair, starlit eyes, elegant flowing star-silk gown",
        "prompts": [
            "sea of clouds above mountains at golden hour, floating islands, wide establishing shot",
            "{char} floating gracefully among clouds, flowing gown and hair",
            "cinematic close-up of glowing stars, crystals and celestial treasures",
            "{char} walking on a bridge of light between floating islands, stardust particles",
            "cinematic close-up of {char} face and eyes, serene cosmic expression",
            "breathtaking wide sky shot, {char} floating into a galaxy of light, shooting stars",
        ],
    },
    {
        "key": "ice",
        "title": "Barf Ki Rani",
        "credit": "ZIDDI • Dreamy Ice Mix",
        "bpm": 92,
        "grade": "eq=saturation=1.05:contrast=1.10:brightness=0.03,colorbalance=bm=0.10:gm=0.05:bs=0.08",
        "char": "the same ice queen with long pale-blue hair, frost-blue eyes, elegant crystal-ice gown",
        "prompts": [
            "glacier valley with aurora borealis, frozen lake, wide establishing shot",
            "{char} gliding gracefully over a frozen lake, flowing gown",
            "cinematic close-up of ice crystals, snowflakes and frozen treasures",
            "{char} inside a glowing ice cave, snow particles swirling",
            "cinematic close-up of {char} face and eyes, calm frosty expression",
            "breathtaking wide aurora shot, {char} walking into the northern lights, snow sparkles",
        ],
    },
]


def pick_theme(day, slot=""):
    digest = hashlib.sha256(f"{day}:{slot}".encode()).hexdigest()
    return THEMES[int(digest, 16) % len(THEMES)]


def fetch_images(theme, day, slot=""):
    import time
    folder = WORK / "fantasy" / f"{day}-{slot or 'main'}"
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for i, tpl in enumerate([theme["prompts"][k] for k in PROMPT_PICK]):
        path = folder / f"{i}.jpg"
        if not path.exists():
            prompt = SFW + tpl.format(char=theme["char"])
            seed = int(hashlib.sha256(f"{day}{slot}{i}".encode()).hexdigest()[:8], 16)
            data = None
            for model in ("flux", "turbo"):
                url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(prompt)
                       + f"?width={W}&height={H}&nologo=true&model={model}&seed={seed}")
                for attempt in range(5):
                    try:
                        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                        blob = urllib.request.urlopen(req, timeout=120).read()
                        if len(blob) > 20000 and blob[:2] == b"\xff\xd8":
                            data = blob
                            break
                    except Exception:
                        pass
                    time.sleep([5, 15, 30, 45, 60][attempt])
                if data:
                    break
            if not data:
                raise RuntimeError(f"image {i} fetch failed")
            path.write_bytes(data)
            time.sleep(10)
        paths.append(path)
    return paths


def synth_music(out, dur, bpm):
    """Original royalty-free dreamy atmospheric phonk: pad + sub + soft kick + hats."""
    beat = 60.0 / bpm
    pad_freqs = (110.0, 130.81, 164.81, 220.0)
    ins = []
    for f in pad_freqs:
        ins += ["-f", "lavfi", "-i", f"sine=frequency={f}:duration={dur:.2f}"]
    ins += ["-f", "lavfi", "-i",
            f"aevalsrc='sin(2*PI*50*t)*exp(-8*mod(t,{beat:.4f}))*0.5':s=48000:d={dur:.2f}"]
    ins += ["-f", "lavfi", "-i",
            f"aevalsrc='(random(0)-0.5)*exp(-30*mod(t+{beat/2:.4f},{beat:.4f}))*0.05':s=48000:d={dur:.2f}"]
    n = len(pad_freqs) + 2
    graph = ("".join(f"[{i}:a]" for i in range(n))
             + f"amix=inputs={n}:duration=first:normalize=0,"
             + "tremolo=f=0.1:d=0.3,aecho=0.8:0.3:60:0.25,lowpass=f=6500,"
             + "alimiter=limit=0.9,loudnorm=I=-16:TP=-1.5:LRA=11[a]")
    run([FFMPEG, "-y", *ins, "-filter_complex", graph, "-map", "[a]",
         "-c:a", "pcm_s16le", "-ar", "48000", out], cwd=WORK)
    return out


def build(day, slot="", out=None):
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    theme = pick_theme(day, slot)
    images = fetch_images(theme, day, slot)
    total = SCENES * SCENE_S - (SCENES - 1) * XFADE
    music = synth_music(WORK / "fantasy_music.wav", total, theme["bpm"])
    import shutil
    shutil.copy(FONT_FILE, WORK / "cfont.ttf")

    inputs = [arg for p in images for arg in ("-i", str(p))]
    inputs += ["-i", str(music)]
    na = len(images)

    parts = []
    frames = int(SCENE_S * FPS)
    for i in range(SCENES):
        parts.append(
            f"[{i}:v]crop=iw:ih*0.94:0:0,"
            f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"zoompan=z='1.02+0.12*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={W}x{H}:fps={FPS},setsar=1,{theme['grade']}[v{i}]")
    chain = "[v0]"
    for i in range(1, SCENES):
        offset = i * SCENE_S - i * XFADE
        nxt = f"[x{i}]" if i < SCENES - 1 else "[vj]"
        parts.append(f"{chain}[v{i}]xfade=transition=fade:duration={XFADE}:offset={offset:.2f}{nxt}")
        chain = nxt
    parts.append("[vj]noise=alls=4:allf=t,vignette=PI/5[vb]")

    title = theme["title"]
    (WORK / "ftitle.txt").write_text(title, encoding="utf-8")
    (WORK / "fcredit.txt").write_text(theme["credit"], encoding="utf-8")
    parts.append(
        "[vb]drawtext=fontfile=cfont.ttf:textfile=ftitle.txt:fontcolor=white:fontsize=56:"
        "x=(w-text_w)/2:y=120:borderw=2:bordercolor=black@0.6:shadowcolor=black@0.5:shadowy=3:"
        "alpha='min(1,t/0.8)'[vt]")
    parts.append(f"[{na}:a]asplit=2[mus][wvs]")
    parts.append("[wvs]showwaves=s=520x90:colors=0xFFFFFF:rate=30:scale=sqrt[wv]")
    parts.append("[vt][wv]overlay=(main_w-overlay_w)/2:1620[vc]")
    parts.append(
        "[vc]drawtext=fontfile=cfont.ttf:textfile=fcredit.txt:fontcolor=0xDDDDDD:fontsize=30:"
        "x=(w-text_w)/2:y=1760:borderw=1:bordercolor=black@0.6[v]")
    parts.append("[mus]volume=1.0[a]")

    out = Path(out) if out else OUT / f"fantasy-{day}-{slot or 'main'}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    run([FFMPEG, "-y", *inputs, "-filter_complex", ";".join(parts),
         "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
         "-movflags", "+faststart", out], cwd=WORK)
    return out, theme


def video_data(theme):
    return {
        "title": f"{theme['title']} | Dreamy Fantasy Cinematic #shorts"[:100],
        "description": ("AI-generated cinematic fantasy visual with original dreamy atmospheric music. "
                        "Naya theme har roz. Subscribe for daily cinematic dreams.\n\n"
                        "Visuals: AI-generated (Pollinations/FLUX). Music: original synthesized dreamy phonk."),
        "hashtags": "#shorts #cinematic #fantasy #dreamy #phonk #aivideo #relaxing",
        "tags": ["cinematic", "fantasy", "dreamy", "phonk", "ai video", "relaxing", "mermaid"],
        "privacy": "public",
    }


if __name__ == "__main__":
    import sys
    day = sys.argv[1] if len(sys.argv) > 1 else "2026-11-13"
    path, theme = build(day)
    print("built:", path, "| theme:", theme["key"])