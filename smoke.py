"""Live key check: OpenAI text + ElevenLabs voices/credits/one Hindi line. Prints nothing secret."""
import json
import sys

import story
import voice


def main():
    failures = 0

    try:
        text = story.text_completion("Reply with the single word: ok", temperature=0, json_mode=False)
        print(f"openai: ok ({len(text)} chars)")
    except Exception as exc:
        failures += 1
        print(f"openai: FAIL {exc}")

    try:
        sub = json.loads(voice._request("user/subscription"))
        print(f"elevenlabs plan: {sub.get('tier')} credits {sub.get('character_count')}/{sub.get('character_limit')}")
    except Exception as exc:
        failures += 1
        print(f"elevenlabs: FAIL {exc}")
        print(f"smoke failures: {failures}")
        return 1

    for name, person in story.CAST.items():
        try:
            print(f"voice {name}: {person['voice']} -> {voice.resolve_voice_id(person['voice'])}")
        except Exception as exc:
            failures += 1
            print(f"voice {name}: FAIL {exc}")

    try:
        mp3 = voice.speech_file("सुनो, मुझे तुमसे कुछ ज़रूरी बात कहनी है।", voice.DEFAULT_VOICE, "nervous")
        try:
            seconds = f"{story.media_duration(mp3):.1f}s"
        except Exception:
            seconds = "duration n/a"
        print(f"speech: {mp3.name} {mp3.stat().st_size} bytes {seconds}")
    except Exception as exc:
        failures += 1
        print(f"speech: FAIL {exc}")

    print(f"smoke failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
