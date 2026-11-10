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
        for index, person in enumerate(story.CAST.values(), 1):
            mp3 = voice.speech_file("सुनो, अब बोलो।", person.get("edge_voice") or person["voice"], "tense")
            print(f"voice {index}: {mp3.name} {mp3.stat().st_size} bytes")
    except Exception as exc:
        failures += 1
        print(f"voices: FAIL {exc}")

    print(f"smoke failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
