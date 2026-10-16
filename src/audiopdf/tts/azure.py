import os
from xml.sax.saxutils import escape

import azure.cognitiveservices.speech as speechsdk


class AzureTTS:
    max_chars = 3000  # folga sob o limite de ~10 min de áudio por requisição
    audio_ext = "mp3"
    default_voice = "pt-BR-FranciscaNeural"

    def __init__(self) -> None:
        self._cfg = speechsdk.SpeechConfig(
            subscription=os.environ["AZURE_SPEECH_KEY"],
            region=os.environ["AZURE_SPEECH_REGION"],
        )
        self._cfg.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Audio48Khz96KBitRateMonoMp3
        )

    def synthesize(self, text: str, voice: str, speed: float = 1.0) -> bytes:
        lang = "-".join(voice.split("-")[:2])
        rate = f"{round((speed - 1) * 100):+d}%"
        ssml = (
            f'<speak version="1.0" xml:lang="{lang}" '
            f'xmlns="http://www.w3.org/2001/10/synthesis">'
            f'<voice name="{voice}"><prosody rate="{rate}">{escape(text)}</prosody></voice>'
            f"</speak>"
        )
        synth = speechsdk.SpeechSynthesizer(speech_config=self._cfg, audio_config=None)
        res = synth.speak_ssml_async(ssml).get()
        if res.reason != speechsdk.ResultReason.SynthesizingAudioCompleted:
            raise RuntimeError(f"Azure TTS falhou: {res.reason} {res.cancellation_details.error_details}")
        return res.audio_data
