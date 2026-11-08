"""Reference-style movie-scene reel: black canvas, letterboxed film strip, top hook, bottom dialogue subs."""
import json
import shutil
from pathlib import Path

from pipeline import FFMPEG, OUT, WORK, media_duration, run
from voice import make_dub

ROOT = Path(__file__).resolve().parent
SCENES_JSON = ROOT / "scenes.json"
FONT_FILE = ROOT / "assets" / "fonts" / "Mukta-Bold.ttf"
W, H = 1080, 1920
STRIP_W, STRIP_H, STRIP_Y = 1080, 600, 600
HOOK_SIZE, HOOK_Y, HOOK_LH = 52, 300, 68
SUB_SIZE, SUB_Y, SUB_LH = 40, 1245, 56
MARK_Y = 1590


def load_scenes():
    return json.loads(SCENES_JSON.read_text(encoding="utf-8"))["scenes"]


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


def build_scene(scene, hook, slug):
    WORK.mkdir(exist_ok=True)
    OUT.mkdir(exist_ok=True)
    src = ROOT / scene["file"]
    dur = media_duration(src)
    shutil.copy(FONT_FILE, WORK / "cfont.ttf")
    dub = make_dub(scene, dur)

    filters = []

    for j, line in enumerate(wrap(hook, 20)[:3]):
        (WORK / f"rhook_{j}.txt").write_text(line, encoding="utf-8")
        filters.append(_drawtext(f"rhook_{j}", HOOK_SIZE, HOOK_Y + j * HOOK_LH,
                                 alpha="min(1,t/0.5)"))

    for k, sub in enumerate(scene["subs"]):
        start, end = float(sub["start"]), float(sub["end"])
        for j, line in enumerate(wrap(sub["text"], 34)[:2]):
            (WORK / f"rsub_{k}_{j}.txt").write_text(line, encoding="utf-8")
            filters.append(_drawtext(f"rsub_{k}_{j}", SUB_SIZE, SUB_Y + j * SUB_LH,
                                     alpha=f"min(1,(t-{start:.2f})/0.15)",
                                     enable=f"between(t,{start:.2f},{end:.2f})", border=2))

    filters.append(
        f"drawtext=fontfile=cfont.ttf:text='|  Z I D D I  |':fontcolor=0x9A9A9A:fontsize=24:"
        f"x=(w-text_w)/2:y={MARK_Y}")

    strip = (f"[1:v]scale={STRIP_W}:{STRIP_H}:force_original_aspect_ratio=increase,"
             f"crop={STRIP_W}:{STRIP_H},setsar=1,"
             f"eq=contrast=1.06:saturation=1.10:brightness=0.015:gamma=1.08[v0];"
             f"[0:v][v0]overlay=0:{STRIP_Y}[v1];[v1]{','.join(filters)}[v];"
             f"[1:a]aresample=48000,aformat=channel_layouts=stereo,volume=0.55[bg];"
             f"[2:a]highpass=f=85,acompressor=threshold=-18dB:ratio=3:attack=6:release=160,"
             f"aresample=48000,aformat=channel_layouts=stereo,volume=2.0,asplit=2[voc][sc];"
             f"[bg][sc]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck];"
             f"[duck][voc]amix=inputs=2:duration=first:normalize=0,"
             f"alimiter=limit=0.95,loudnorm=I=-14:TP=-1.5:LRA=11[a]")

    out = OUT / f"{slug}.mp4"
    run([FFMPEG, "-y",
         "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r=30:d={dur:.3f}",
         "-i", src,
         "-i", dub,
         "-filter_complex", strip,
         "-map", "[v]", "-map", "[a]",
         "-t", f"{dur:.3f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
         out], cwd=WORK)
    return out
