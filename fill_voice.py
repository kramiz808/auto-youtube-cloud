"""Pre-generate missing Hindi dub lines with ElevenLabs."""
import json
from pathlib import Path

import reel
import voice


def main():
    state = json.loads((reel.ROOT / "state.json").read_text(encoding="utf-8"))
    scenes = reel.load_scenes()
    start = state.get("scene_index", 0)
    made = 0
    try:
        for i in range(len(scenes)):
            scene = scenes[(start + i) % len(scenes)]
            for k, sub in enumerate(scene["subs"]):
                path = voice.DUB_DIR / f"{Path(scene['file']).stem}_{k}.mp3"
                if path.exists() and path.stat().st_size > 1000:
                    continue
                voice.line_audio(scene, k, sub)
                print("voice:", path.name)
                made += 1
    except voice.VoiceUnavailable as exc:
        print("stop:", exc)
    print(f"new lines: {made}")


if __name__ == "__main__":
    main()
