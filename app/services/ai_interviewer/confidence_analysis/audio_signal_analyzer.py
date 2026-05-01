import numpy as np
import librosa

from datetime import datetime
import logging
import traceback
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)


class AudioSignalAnalyzer:
    def _load_audio(self, audio_input):
        try:
            return librosa.load(audio_input, sr=None)
        except Exception as e:
            logger.info(
                f"Librosa normal load failed, trying ffmpeg fallback... Error: {e}"
            )

            temp_wav = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                    temp_wav = tf.name

                ffmpeg_path = r"C:\Users\ashth\AppData\Local\bin\ffmpeg.exe"
                cmd = [
                    ffmpeg_path,
                    "-y",
                    "-i",
                    audio_input,
                    "-acodec",
                    "pcm_s16le",
                    "-ac",
                    "1",
                    temp_wav,
                ]

                logger.debug(f"Running ffmpeg command: {' '.join(cmd)}")
                subprocess.run(cmd, check=True, capture_output=True)

                y, sr = librosa.load(temp_wav, sr=None)
                return y, sr

            except subprocess.CalledProcessError as scpe:
                logger.error(f"ffmpeg conversion failed: {scpe.stderr.decode()}")
                raise scpe
            except Exception as fe:
                logger.error(f"Fallback loading failed: {fe}")
                raise fe
            finally:
                if temp_wav and os.path.exists(temp_wav):
                    try:
                        os.remove(temp_wav)
                    except:
                        pass

    def analyze(self, audio_input):
        try:
            start_time = datetime.now()

            y, sr = self._load_audio(audio_input)

            # Volume Consistency
            rms = librosa.feature.rms(y=y)[0]
            if len(rms) == 0:
                return None
            volume_stability = float(1.0 - np.std(rms))

            # Pitch Stability
            zcr = librosa.feature.zero_crossing_rate(y)[0]
            pitch_stability = float(1.0 - np.std(zcr))

            # Pauses & Duration
            total_duration = librosa.get_duration(y=y, sr=sr)
            non_silent_intervals = librosa.effects.split(y, top_db=25)
            speaking_duration = (
                sum(end - start for start, end in non_silent_intervals) / sr
            )
            pause_duration = float(total_duration - speaking_duration)

            # Normalize RMS (0 to 1)
            if np.max(rms) > 0:
                rms = (rms - np.min(rms)) / (np.max(rms) - np.min(rms))

            peaks = librosa.util.peak_pick(
                rms, pre_max=3, post_max=3, pre_avg=3, post_avg=3, delta=0.02, wait=5
            )
            estimated_wpm = (
                int((len(peaks) / total_duration) * 60 * 0.6)
                if total_duration > 0
                else 0
            )

            end_time = datetime.now()

            # print(
            #     f"Time taken for {(endcpu audio analyzer: _time - start_time).total_seconds()}"
            # )

            return {
                "score": int((pitch_stability + volume_stability) / 2 * 100),
                "metrics": {
                    "pitch_stability": round(pitch_stability * 100, 2),
                    "volume_consistency": round(volume_stability * 100, 2),
                    "speech_rate_wpm": estimated_wpm,
                    "pause_duration_sec": round(pause_duration, 2),
                    "total_duration_sec": round(total_duration, 2),
                },
            }
        except Exception as e:
            file_info = ""
            if isinstance(audio_input, str) and os.path.exists(audio_input):
                file_info = f" (File: {audio_input}, Size: {os.path.getsize(audio_input)} bytes)"

            error_details = traceback.format_exc()
            logger.error(f"Audio Error during analysis{file_info}:\n{error_details}")
            return None
