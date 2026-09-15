from TTS.api import TTS
import os

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'voice-samples', 'xtts-v2-model')
CONFIG_PATH = os.path.join(MODEL_PATH, 'config.json')
REFERENCE_VOICE = os.path.join(os.path.dirname(__file__), 'voice-samples', 'reference.wav')

_tts_instance = None


def get_tts():
    global _tts_instance
    if _tts_instance is None:
        _tts_instance = TTS(model_path=MODEL_PATH, config_path=CONFIG_PATH)
    return _tts_instance


def synthesize(text: str, output_path: str):
    tts = get_tts()
    tts.tts_to_file(
        text=text,
        speaker_wav=REFERENCE_VOICE,
        language='en',
        file_path=output_path
    )
    return output_path
