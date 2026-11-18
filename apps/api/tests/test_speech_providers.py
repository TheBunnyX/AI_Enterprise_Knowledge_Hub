"""OpenRouter text-to-speech: every provider wants a different voice name and audio format."""
import io, wave
from hub import google_audio


def test_gemini_tts_asks_for_pcm_with_a_gemini_voice_and_returns_wav():
    body, mime, convert = google_audio.openrouter_speech('google/gemini-3.8-flash-tts', 'สวัสดี', 'alloy')
    assert body == {'model': 'google/gemini-3.8-flash-tts', 'input': 'สวัสดี', 'voice': 'Kore', 'response_format': 'pcm'}  # an OpenAI voice name falls back to Kore
    assert mime == 'audio/wav'
    wav = convert(b'\x00\x00' * 2400)
    with wave.open(io.BytesIO(wav)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 24000, 2400)
    assert google_audio.openrouter_speech('google/gemini-3.8-flash-lite-tts', 'x', 'Puck')[0]['voice'] == 'Puck'


def test_grok_tts_uses_its_own_voices():
    body, mime, convert = google_audio.openrouter_speech('x-ai/grok-voice-tts-1.0', 'x', 'alloy')
    assert body['voice'] == 'eve' and body['response_format'] == 'mp3' and mime == 'audio/mpeg' and convert is None
    assert google_audio.openrouter_speech('x-ai/grok-voice-tts-1.0', 'x', 'Rex')[0]['voice'] == 'rex'


def test_other_providers_keep_the_openai_style_request():
    body, mime, convert = google_audio.openrouter_speech('fish-audio/s2.1-pro', 'x', '', 1.25)
    assert body == {'model': 'fish-audio/s2.1-pro', 'input': 'x', 'voice': 'alloy', 'response_format': 'mp3', 'speed': 1.25}
    assert mime == 'audio/mpeg' and convert is None
