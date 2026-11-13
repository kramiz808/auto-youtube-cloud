import io
import json
import os
import subprocess
import tempfile
import unittest
import urllib.error
import wave
from pathlib import Path
from unittest.mock import patch

import daily
import story
import teaser
import voice


class Response(io.BytesIO):
    def __init__(self, data, content_type="application/json"):
        super().__init__(json.dumps(data).encode() if isinstance(data, dict) else data)
        self.headers = {"Content-Type": content_type}


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for target, value in (("voice.WORK", self.root / "work"),
                              ("voice.ROOT", self.root), ("story.ROOT", self.root)):
            mock = patch(target, value)
            mock.start()
            self.addCleanup(mock.stop)
        env = patch.dict(os.environ, {"OPENAI_API_KEY": "test-openai", "OPENAI_MODEL": "",
                                      "ELEVENLABS_API_KEY": "test-eleven"})
        env.start()
        self.addCleanup(env.stop)
        network = patch("urllib.request.urlopen", side_effect=AssertionError("Live APIs disabled in tests"))
        self.network = network.start()
        self.addCleanup(network.stop)
        voice.available_voices.cache_clear()
        self.addCleanup(voice.available_voices.cache_clear)

    def completion(self, content='{"title":"test"}', finish="stop", refusal=None):
        return {"choices": [{"finish_reason": finish,
                             "message": {"content": content, "refusal": refusal}}]}

    def test_openai_json_contract(self):
        self.network.side_effect = None
        self.network.return_value = Response(self.completion())
        self.assertEqual(story.as_json(story.text_completion("Write JSON")), {"title": "test"})
        request = self.network.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(request.full_url, "https://api.openai.com/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-openai")
        self.assertEqual(body["model"], "gpt-4o-mini")
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["messages"][-1]["content"], "Write JSON")

    def test_openai_plain_text_and_model_override(self):
        self.network.side_effect = None
        self.network.return_value = Response(self.completion("<html></html>"))
        with patch.dict(os.environ, {"OPENAI_MODEL": "custom-model"}):
            self.assertEqual(story.text_completion("HTML", json_mode=False), "<html></html>")
        body = json.loads(self.network.call_args.args[0].data)
        self.assertNotIn("response_format", body)
        self.assertEqual(body["model"], "custom-model")

    def test_missing_keys_fail_before_network(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "", "ELEVENLABS_API_KEY": ""}):
            with self.assertRaisesRegex(RuntimeError, "missing API key"):
                story.text_completion("test")
            with self.assertRaisesRegex(voice.VoiceUnavailable, "ELEVENLABS_API_KEY missing"):
                voice.speech_file("नमस्ते", voice.DEFAULT_VOICE)
        self.network.assert_not_called()

    def test_ignored_local_key_files(self):
        secrets = self.root / "secrets"
        secrets.mkdir()
        (secrets / "openai_key.txt").write_text("local-openai")
        (secrets / "elevenlabs_key.txt").write_text("local-eleven")
        self.network.side_effect = None
        self.network.return_value = Response(self.completion())
        with patch.dict(os.environ, {"OPENAI_API_KEY": "", "ELEVENLABS_API_KEY": ""}):
            story.text_completion("test")
            self.assertEqual(voice.api_key(), "local-eleven")
        self.assertEqual(self.network.call_args.args[0].get_header("Authorization"), "Bearer local-openai")

    def test_openai_rejects_incomplete_refused_empty_and_invalid(self):
        for response in (self.completion(finish="length"), self.completion(refusal="no"),
                         self.completion(content=""), {"choices": []}, {"choices": [None]}):
            with self.subTest(response=response):
                self.network.side_effect = None
                self.network.return_value = Response(response)
                with self.assertRaises(RuntimeError):
                    story.text_completion("test")

    def test_http_errors_do_not_retry_or_expose_secrets(self):
        for code in (401, 403, 429, 500):
            with self.subTest(code=code):
                self.network.reset_mock()
                self.network.side_effect = urllib.error.HTTPError(
                    "https://example.test", code, "secret-error", {}, io.BytesIO(b"secret-body"))
                with self.assertRaisesRegex(RuntimeError, f"^OpenAI HTTP {code}$"):
                    story.text_completion("test")
                self.assertEqual(self.network.call_count, 1)
                self.network.reset_mock()
                with self.assertRaises(voice.VoiceUnavailable) as error:
                    voice.speech_file("नमस्ते", voice.DEFAULT_VOICE)
                self.assertNotIn("secret", str(error.exception))
                self.assertEqual(self.network.call_count, 1)

    def test_roger_voice_id_needs_no_catalog_request(self):
        self.assertEqual(voice.resolve_voice_id(voice.DEFAULT_VOICE), "CwhRBWXzGAHq8TQ4Fs17")
        self.network.assert_not_called()
        self.assertEqual(story.CAST["आरव"]["voice"], voice.DEFAULT_VOICE)

    def test_stock_voice_resolution_is_cached(self):
        voices = {"voices": [{"name": "Sarah", "category": "premade", "voice_id": "S" * 20},
                             {"name": "Sarah", "category": "cloned", "voice_id": "X" * 20},
                             {"name": "George", "category": "premade", "voice_id": "G" * 20}]}
        with patch("voice._request", return_value=json.dumps(voices).encode()) as request:
            self.assertEqual(voice.resolve_voice_id("Sarah"), "S" * 20)
            self.assertEqual(voice.resolve_voice_id("George"), "G" * 20)
            request.assert_called_once_with("voices")
            with self.assertRaisesRegex(voice.VoiceUnavailable, "unavailable"):
                voice.resolve_voice_id("Laura")

    def test_ambiguous_voices_are_not_selected_randomly(self):
        with patch("voice.available_voices", return_value=[
                {"name": "Sarah", "voice_id": "S" * 20},
                {"name": "Sarah", "voice_id": "T" * 20}]):
            with self.assertRaisesRegex(voice.VoiceUnavailable, "ambiguous"):
                voice.resolve_voice_id("Sarah")

    def test_emotion_tags_stay_out_of_original_dialogue(self):
        for emotion, tag in (("angry", "angry"), ("sadness", "sad"),
                             ("whispering", "whispers"), ("fear", "nervous")):
            body = voice.speech_body("यह सच नहीं है।", emotion)
            self.assertEqual(body["model_id"], "eleven_v3")
            self.assertEqual(body["text"], f"[{tag}] यह सच नहीं है।")
        self.assertEqual(voice.speech_body("नमस्ते", "calm")["text"], "नमस्ते")

    def test_elevenlabs_auth_audio_contract_and_cache(self):
        self.network.side_effect = None
        self.network.return_value = Response(b"audio-payload", "audio/mpeg")
        path = voice.speech_file("नमस्ते", voice.DEFAULT_VOICE, "angry")
        self.assertEqual(path.read_bytes(), b"audio-payload")
        request = self.network.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Xi-api-key"), "test-eleven")
        self.assertNotIn("test-eleven", request.full_url)
        self.assertIn(f"/text-to-speech/{voice.DEFAULT_VOICE}?output_format=mp3_44100_128", request.full_url)
        self.assertEqual(voice.speech_file("नमस्ते", voice.DEFAULT_VOICE, "angry"), path)
        self.assertEqual(self.network.call_count, 1)
        with patch("voice._request", return_value=b"other"):
            self.assertNotEqual(voice.speech_file("नमस्ते", voice.DEFAULT_VOICE, "sad"), path)
            self.assertNotEqual(voice.speech_file("नमस्ते", "S" * 20, "angry"), path)
            self.assertNotEqual(voice.speech_file("अलग बात", voice.DEFAULT_VOICE, "angry"), path)

    def test_non_audio_and_empty_responses_never_enter_cache(self):
        self.network.side_effect = None
        self.network.return_value = Response({"error": "not audio"})
        with self.assertRaisesRegex(voice.VoiceUnavailable, "non-audio"):
            voice.speech_file("नमस्ते", voice.DEFAULT_VOICE)
        self.network.return_value = Response(b"", "audio/mpeg")
        with self.assertRaisesRegex(voice.VoiceUnavailable, "empty"):
            voice.speech_file("नमस्ते", voice.DEFAULT_VOICE)
        self.assertEqual(list((voice.WORK / "elevenlabs").glob("*.mp3")), [])

    def test_dialogue_measured_timing_real_ffmpeg_and_resume(self):
        sample = subprocess.run([voice.FFMPEG, "-v", "error", "-f", "lavfi", "-i",
                                 "sine=frequency=440:duration=0.25", "-f", "mp3", "pipe:1"],
                                check=True, capture_output=True).stdout
        turns = [{"speaker": "A", "text": "नमस्ते", "emotion": "angry"},
                 {"speaker": "B", "text": "बताओ", "emotion": "sad"}]
        cast = {"A": {"voice": voice.DEFAULT_VOICE}, "B": {"voice": "S" * 20}}
        out = self.root / "dialogue.wav"
        with patch("voice._request", side_effect=[sample, voice.VoiceUnavailable("quota")]):
            with self.assertRaisesRegex(voice.VoiceUnavailable, "quota"):
                voice.dialogue_audio(turns, cast, out)
        self.assertFalse(out.exists())
        with patch("voice._request", return_value=sample) as request:
            timings = voice.dialogue_audio(turns, cast, out)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(timings[0][0], 0)
            self.assertAlmostEqual(timings[1][0] - timings[0][1], voice.LINE_GAP)
            with wave.open(str(out)) as wav:
                self.assertEqual(wav.getframerate(), 48000)
                self.assertEqual(wav.getnchannels(), 1)
                self.assertEqual(wav.getsampwidth(), 2)
                self.assertAlmostEqual(wav.getnframes() / 48000, timings[-1][1])
            self.assertEqual(voice.dialogue_audio(turns, cast, out), timings)
            self.assertEqual(request.call_count, 1)
        self.assertEqual(turns[0]["text"], "नमस्ते")

    def test_empty_or_collapsed_cast_is_rejected(self):
        with self.assertRaisesRegex(voice.VoiceUnavailable, "no lines"):
            voice.dialogue_audio([], {}, self.root / "empty.wav")
        turns = [{"speaker": "A", "text": "एक"}, {"speaker": "B", "text": "दो"}]
        cast = {name: {"voice": voice.DEFAULT_VOICE} for name in ("A", "B")}
        with self.assertRaisesRegex(voice.VoiceUnavailable, "distinct"):
            voice.dialogue_audio(turns, cast, self.root / "same.wav")
        self.network.assert_not_called()

    def test_daily_does_not_upload_old_reel_after_build_failure(self):
        state = {"scene_index": 2}
        with patch("daily.fantasy.build", side_effect=RuntimeError("image fetch failed")), \
                patch("daily.pipeline.upload") as upload:
            with self.assertRaises(RuntimeError):
                daily.post_slot("afternoon", "2026-11-10", state, 2)
            upload.assert_not_called()
        self.assertEqual(state, {"scene_index": 2})

    def test_upload_uses_sdk_resumable_transport(self):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build as build_client
        import pipeline
        video = self.root / "video.mp4"
        video.write_bytes(b"test-video")
        clients = []

        def create(*args, **kwargs):
            client = build_client(*args, **kwargs)
            clients.append(client)
            return client

        with patch("pipeline.get_creds", return_value=Credentials(token="test-token")), \
                patch("googleapiclient.discovery.build", side_effect=create), \
                patch("googleapiclient.http.HttpRequest.next_chunk", return_value=(None, {"id": "test-id"})):
            self.assertEqual(pipeline.upload(video, {"title": "test"}), "test-id")
        transport = clients[0]._http.http
        self.assertNotIn(308, transport.redirect_codes)
        self.assertIsNotNone(transport.timeout)

    def test_teaser_generates_todays_plan_once_instead_of_repeating_yesterday(self):
        state = {"episode": 3, "revealed": ["prior reveal"]}
        (self.root / "story_state.json").write_text(json.dumps(state), encoding="utf-8")
        (self.root / "episode-2000-01-01.json").write_text('{"episode":1}', encoding="utf-8")
        with patch("teaser.ROOT", self.root), patch("teaser.OUT", self.root), \
                patch("teaser.write_episode", return_value={"episode": 3}) as generate:
            self.assertEqual(teaser.latest_plan(), {"episode": 3})
            self.assertEqual(teaser.latest_plan(), {"episode": 3})
            generate.assert_called_once_with(3, ["prior reveal"])

    def test_published_teaser_does_not_suppress_full_episode(self):
        with patch("pipeline.get_creds"), patch("googleapiclient.discovery.build") as build:
            yt = build.return_value
            yt.channels.return_value.list.return_value.execute.return_value = {
                "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "uploads"}}}]}
            yt.playlistItems.return_value.list.return_value.execute.return_value = {
                "items": [{"snippet": {"publishedAt": "2026-11-10T08:30:00Z",
                "title": "Series teaser", "resourceId": {"videoId": "video"}}}]}
            videos = yt.videos.return_value.list.return_value.execute
            videos.return_value = {"items": [{"contentDetails": {"duration": "PT1M30S"}}]}
            self.assertFalse(story.already_on_channel("2026-11-10", "Series"))
            videos.return_value = {"items": [{"contentDetails": {"duration": "PT15M"}}]}
            self.assertTrue(story.already_on_channel("2026-11-10", "Series"))

    def test_two_short_slots_leave_room_for_daily_story(self):
        self.assertEqual(daily.due_slots(13 * 60 + 59), [])
        self.assertEqual(daily.due_slots(14 * 60), ["afternoon"])
        self.assertEqual(daily.due_slots(18 * 60), ["afternoon", "evening"])
        self.assertEqual(daily.due_slots(23 * 60), ["afternoon", "evening"])

    def test_scene_manifest_preserves_dialogue_gaps_and_total_duration(self):
        names = list(story.CAST)[:2]
        scene = {"setting": "home", "lines": [
            {"speaker": names[0], "emotion": "sad"},
            {"speaker": names[1], "emotion": "angry"}]}
        target = self.root / "scene.ffconcat"
        with patch("story.WORK", self.root), patch("story.run") as encode:
            result = story.scene_source(scene, [(0, 1), (1.16, 2.5)], 2.5, target)
        self.assertEqual(result, target)
        for call in encode.call_args_list:
            command = call.args[0]
            self.assertEqual(command[command.index("-frames:v") + 1], "1")
        lines = target.read_text(encoding="utf-8").splitlines()
        durations = [float(line.split()[1]) for line in lines if line.startswith("duration ")]
        self.assertEqual(durations, [story.CARD, 1.16, 1.34, story.TAIL])
        self.assertAlmostEqual(sum(durations), story.CARD + 2.5 + story.TAIL)
        self.assertEqual(sum(line.startswith("file ") for line in lines), 5)

    def test_gemini_default_and_json_contract(self):
        self.network.side_effect = None
        self.network.return_value = Response({"candidates": [{"finishReason": "STOP",
            "content": {"parts": [{"text": '{"title":"ok"}'}]}}]})
        with patch.dict(os.environ, {"TEXT_PROVIDER": "gemini", "GEMINI_API_KEY": "test-gemini",
                                     "GEMINI_MODEL": ""}):
            self.assertEqual(story.as_json(story.text_completion("Write JSON")), {"title": "ok"})
        request = self.network.call_args.args[0]
        self.assertIn("gemini-3.1-flash-lite:generateContent", request.full_url)
        self.assertNotIn("test-gemini", request.full_url)
        self.assertEqual(json.loads(request.data)["generationConfig"]["responseMimeType"], "application/json")

    def test_teaser_fails_before_writing_story_when_voice_key_missing(self):
        with patch.dict(os.environ, {"ELEVENLABS_API_KEY": ""}), patch("teaser.latest_plan") as plan:
            with self.assertRaises(voice.VoiceUnavailable):
                teaser.build("unused")
            plan.assert_not_called()
        self.network.assert_not_called()


if __name__ == "__main__":
    unittest.main()
