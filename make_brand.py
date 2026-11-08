import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FF = Path(r"C:/Users/Windows 10/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-9.0.2-full_build/bin/ffmpeg.exe")
FONT = ROOT / "assets" / "fonts" / "Mukta-Bold.ttf"
BRAND = ROOT / "brand"
BRAND.mkdir(exist_ok=True)
shutil.copy(FONT, BRAND / "bfont.ttf")


def run(args):
    r = subprocess.run([str(a) for a in args], cwd=BRAND, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-1500:])


# DP / avatar 800x800: black + gold monogram Z
run([FF, "-y", "-f", "lavfi", "-i", "color=c=0x0A0A0A:s=800x800",
     "-vf", "drawtext=fontfile=bfont.ttf:text='Z':fontcolor=0xFFC53D:fontsize=430:"
            "x=(w-text_w)/2:y=(h-text_h)/2-70,"
            "drawtext=fontfile=bfont.ttf:text='MOTIVATION':fontcolor=0xFFFFFF:fontsize=58:"
            "x=(w-text_w)/2:y=620",
     "-frames:v", "1", "dp.png"])

# Banner 2048x1152 (safe center band)
run([FF, "-y", "-f", "lavfi", "-i", "color=c=0x0A0A0A:s=2048x1152",
     "-vf", "drawtext=fontfile=bfont.ttf:text='ZIDDI MOTIVATION':fontcolor=0xFFC53D:fontsize=130:"
            "x=(w-text_w)/2:y=430,"
            "drawtext=fontfile=bfont.ttf:text='Roz ek nayi aag. Hindi Motivation.':fontcolor=0xDDDDDD:fontsize=52:"
            "x=(w-text_w)/2:y=610",
     "-frames:v", "1", "banner.png"])

print("BRAND images:", (BRAND / "dp.png").stat().st_size, (BRAND / "banner.png").stat().st_size)