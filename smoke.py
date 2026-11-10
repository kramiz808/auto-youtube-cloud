"""Live provider check: text model + active TTS. Prints nothing secret."""
import os
import sys

import story
import voice


def key_shape(name):
    value = os.environ.get(name, "")
    odd = sum(1 for ch in value if ord(ch) > 126 or ch in "\r\n\t")
    print(f"{name} shape: len={len(value)} edge_space={value != value.strip()} "
          f"odd_chars={odd} sk_prefix={value.startswith('sk-') or value.startswith('sk_')}")


def main():
    failures = 0
    for name in ("GEMINI_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY"):
        key_shape(name)
    print(f"text provider: {story.text_provider()} | tts provider: {voice.tts_provider()}")

    try:
        text = story.text_completion("Reply with the single word: ok", temperature=0, json_mode=False)
        print(f"text: ok ({text.strip()[:40]!r})")
    except Exception as exc:
        failures += 1
        print(f"text: FAIL {exc}")

    try:
        voice.preflight(story.CAST)
        print("voices: " + ", ".join(
            str(c.get("edge_voice") or c["voice"]) for c in story.CAST.values()))
    except Exception as exc:
        failures += 1
        print(f"voices: FAIL {exc}")

    try:
        timings = voice.dialogue_audio(
            [{"speaker": "आरव", "text": "सुनो, मुझे तुमसे कुछ ज़रूरी बात कहनी है।", "emotion": "tense"},
             {"speaker": "सावित्री", "text": "अब क्या हुआ? बोलो।", "emotion": "sad"}],
            story.CAST, voice.WORK / "smoke_dialogue.wav")
        print(f"speech: ok {len(timings)} lines {timings[-1][1]:.1f}s")
    except Exception as exc:
        failures += 1
        print(f"speech: FAIL {exc}")

    print(f"smoke failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
