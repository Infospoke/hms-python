"""Per-answer audio/visual proctoring analysis.

Answers the one question the frame-by-frame proctoring pipeline cannot:
*was the person on camera the one producing the audio we recorded?*

The candidate's browser records one clip per answer from a single MediaStream,
so the audio and video inside it share a container clock and are aligned for
free. That removes the alignment problem entirely - there is no cross-stream
timestamp reconciliation here, because the two signals never travel apart.

Two independent signals are extracted:

  1. Mouth activity vs. speech. For every time bin we ask "was speech being
     captured?" and "was the visible mouth moving?". A long stretch of recorded
     speech with a still, clearly-visible mouth is the signature of someone
     off-camera answering.

  2. Distinct voice count. A coarse check for more than one speaker inside a
     single answer.

These fail in opposite directions, which is the point of running both: if a
helper answers *every* question there is only one voice and (2) sees nothing,
but (1) sees a still mouth. If the helper only chips in occasionally, (1) is
diluted but (2) fires.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
It does not decide whether anyone cheated, and it must not be wired to a score
or an automated rejection. A candidate who repeats aloud what a helper whispers
produces a perfectly clean reading on both signals, as does a candidate reading
prepared answers alone. The output is evidence for a human, nothing more.

Every threshold in `app.core.config` is an untested starting point. They need
to be re-derived from real recorded sessions before anything here is shown to
a recruiter.
"""

import logging
import math
import os
import tempfile

import cv2
import numpy as np

from app.core import config as consts
from app.utils import ffmpeg_utils

logger = logging.getLogger(__name__)


# --- MediaPipe FaceMesh landmark indices (468/478 topology) ---
# Inner lip contour. Three vertical pairs are averaged so a single mistracked
# landmark cannot swing the ratio, and the inner ring is used rather than the
# outer because it tracks aperture rather than lip-pursing.
MOUTH_VERTICAL_PAIRS = ((82, 87), (13, 14), (312, 317))
# Inner mouth corners, used to normalise for face size and camera distance.
MOUTH_HORIZONTAL_PAIR = (78, 308)

# Audio framing for voice activity detection.
VAD_FRAME_SEC = 0.030
VAD_HOP_SEC = 0.010
VAD_MIN_SPEECH_SEC = 0.20
VAD_MIN_SILENCE_SEC = 0.15
# Speech must clear the clip's own noise floor by at least this much.
VAD_MIN_SNR_DB = 6.0
VAD_ABSOLUTE_FLOOR_DB = -55.0

# Speaker clustering. Uncalibrated - see module docstring.
VOICE_WINDOW_SEC = 1.0
VOICE_HOP_SEC = 0.5
VOICE_MIN_WINDOWS = 4
VOICE_CLUSTER_DISTANCE = 0.35

# Below this peak level the clip carries no audio at all. Even a silent room
# records well above it, so this indicates a muted or misrouted microphone
# rather than a quiet candidate.
SILENT_AUDIO_PEAK_DB = -70.0

# Common time grid both timelines are resampled onto before comparison.
BIN_SEC = 0.05


def _resolve_ffmpeg() -> str:
    """Platform-aware ffmpeg lookup, shared with the rest of the project."""
    return ffmpeg_utils.resolve()


def _extract_audio(clip_path: str, out_wav_path: str) -> None:
    """Demux the clip's audio to 16 kHz mono PCM."""
    ffmpeg_utils.run(
        [
            "-y",
            "-i", clip_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            out_wav_path,
        ]
    )
    if not os.path.exists(out_wav_path):
        raise RuntimeError(
            "ffmpeg reported success but produced no audio file - the clip "
            "most likely has no audio stream."
        )


def _load_wav(path: str):
    """Read the extracted PCM. soundfile is already a project dependency."""
    import soundfile as sf

    samples, sample_rate = sf.read(path, dtype="float32", always_2d=False)
    if samples.ndim > 1:
        samples = samples.mean(axis=1)
    return samples, sample_rate


def _frame_db(samples: np.ndarray, sample_rate: int):
    """Per-frame RMS in dBFS, plus each frame's start time."""
    frame_len = max(1, int(VAD_FRAME_SEC * sample_rate))
    hop = max(1, int(VAD_HOP_SEC * sample_rate))
    if samples.size < frame_len:
        return np.array([]), np.array([])

    n_frames = 1 + (samples.size - frame_len) // hop
    idx = np.arange(frame_len)[None, :] + hop * np.arange(n_frames)[:, None]
    frames = samples[idx]
    rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))
    db = 20.0 * np.log10(np.maximum(rms, 1e-10))
    times = np.arange(n_frames) * VAD_HOP_SEC
    return db, times


def _smooth_binary(flags: np.ndarray, min_true_sec: float, min_false_sec: float):
    """Drop speech bursts and silence gaps too short to be real.

    Without this, a single loud keystroke reads as speech and a natural pause
    mid-sentence splits one utterance into two.
    """
    if flags.size == 0:
        return flags

    min_true = max(1, int(round(min_true_sec / VAD_HOP_SEC)))
    min_false = max(1, int(round(min_false_sec / VAD_HOP_SEC)))
    out = flags.copy()

    # Fill short gaps first, so a pause does not fragment one utterance.
    start = None
    for i, v in enumerate(out):
        if not v and start is None:
            start = i
        elif v and start is not None:
            if i - start < min_false:
                out[start:i] = True
            start = None

    # Then drop runs still too short to be speech.
    start = None
    for i, v in enumerate(np.append(out, False)):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start < min_true:
                out[start:i] = False
            start = None
    return out


def _detect_speech(samples: np.ndarray, sample_rate: int):
    """Energy-based voice activity detection, calibrated to each clip.

    Deliberately self-calibrating rather than absolute: laptop microphones,
    room noise and Chrome's automatic gain control vary enormously between
    candidates, so a fixed dB threshold would behave very differently for a
    quiet home office than for a noisy one.
    """
    db, times = _frame_db(samples, sample_rate)
    if db.size == 0:
        return np.array([]), np.array([]), {}

    noise_floor = float(np.percentile(db, 10))
    peak = float(np.percentile(db, 95))
    dynamic_range = peak - noise_floor

    threshold = noise_floor + max(VAD_MIN_SNR_DB, 0.35 * dynamic_range)
    flags = (db > threshold) & (db > VAD_ABSOLUTE_FLOOR_DB)
    flags = _smooth_binary(flags, VAD_MIN_SPEECH_SEC, VAD_MIN_SILENCE_SEC)

    stats = {
        "noise_floor_db": round(noise_floor, 2),
        "peak_db": round(peak, 2),
        "dynamic_range_db": round(dynamic_range, 2),
        "vad_threshold_db": round(threshold, 2),
    }
    return flags, times, stats


def _count_distinct_voices(samples: np.ndarray, sample_rate: int, speech_flags, times):
    """Coarse count of distinct speakers inside one answer.

    MFCC statistics over short windows, agglomeratively clustered. This is a
    long way from proper speaker diarisation (ECAPA-TDNN embeddings would be
    far stronger) and is intended as a cheap first-pass indicator that needs
    no new dependency. Treat a count of 2 as "worth a human listening to the
    clip", never as proof of a second person.
    """
    result = {"clusters": 1, "windows": 0, "cluster_shares": [], "reliable": False}
    if speech_flags.size == 0 or not speech_flags.any():
        result["clusters"] = 0
        return result

    try:
        import librosa
        from sklearn.cluster import AgglomerativeClustering
        from sklearn.preprocessing import StandardScaler
    except Exception as e:
        logger.warning(f"AV: voice clustering unavailable ({e})")
        return result

    win = int(VOICE_WINDOW_SEC * sample_rate)
    hop = int(VOICE_HOP_SEC * sample_rate)
    features = []

    for start in range(0, max(0, samples.size - win + 1), hop):
        t0 = start / sample_rate
        t1 = (start + win) / sample_rate
        # Only use windows that are essentially all speech, so silence and
        # room tone cannot form their own "speaker" cluster.
        mask = (times >= t0) & (times < t1)
        if not mask.any() or speech_flags[mask].mean() < 0.9:
            continue
        chunk = samples[start:start + win]
        mfcc = librosa.feature.mfcc(y=chunk, sr=sample_rate, n_mfcc=20)
        features.append(np.concatenate([mfcc.mean(axis=1), mfcc.std(axis=1)]))

    result["windows"] = len(features)
    if len(features) < VOICE_MIN_WINDOWS:
        return result

    try:
        matrix = StandardScaler().fit_transform(np.asarray(features))

        # Cosine distance is undefined for zero-length vectors, which appear
        # whenever a window is spectrally flat (a held tone, a dead mic, or
        # near-identical windows that scale to the mean). Drop them rather
        # than letting the whole clustering step fail.
        norms = np.linalg.norm(matrix, axis=1)
        keep = norms > 1e-9
        if np.count_nonzero(keep) < VOICE_MIN_WINDOWS:
            logger.debug(
                "AV: too few non-degenerate windows for clustering "
                f"({np.count_nonzero(keep)}/{len(features)})"
            )
            return result
        matrix = matrix[keep]

        labels = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=VOICE_CLUSTER_DISTANCE,
            metric="cosine",
            linkage="average",
        ).fit_predict(matrix)
    except Exception as e:
        logger.warning(f"AV: clustering failed ({e})")
        return result

    total = len(labels)
    shares = sorted(
        (float(np.sum(labels == lab)) / total for lab in set(labels)), reverse=True
    )
    significant = [s for s in shares if s >= consts.AV_VOICE_CLUSTER_MIN_SHARE]

    result["clusters"] = max(1, len(significant))
    result["cluster_shares"] = [round(s, 3) for s in shares[:5]]
    result["reliable"] = True
    return result


def _mouth_aspect_ratio(landmarks, width: int, height: int):
    """Aspect-corrected mouth aspect ratio, or None if degenerate.

    MediaPipe normalises x against image WIDTH and y against HEIGHT
    independently, so treating those coordinates as isotropic injects a
    systematic error equal to the frame's aspect ratio - about 33% at 4:3 and
    44% at 16:9. Since MAR is literally a vertical measurement over a
    horizontal one, that error lands squarely on the signal. Scaling back to
    pixels first removes it.
    """
    def point(i):
        lm = landmarks[i]
        return lm.x * width, lm.y * height

    def dist(a, b):
        (ax, ay), (bx, by) = point(a), point(b)
        return math.hypot(ax - bx, ay - by)

    horizontal = dist(*MOUTH_HORIZONTAL_PAIR)
    if horizontal <= 1e-6:
        return None
    vertical = sum(dist(a, b) for a, b in MOUTH_VERTICAL_PAIRS) / len(
        MOUTH_VERTICAL_PAIRS
    )
    return vertical / horizontal


def _build_face_mesh():
    """A FaceMesh instance dedicated to one clip.

    Video-tracking mode is correct here precisely because a clip is one
    continuous recording of one person - unlike the live frame worker, where a
    single shared instance sees interleaved frames from different candidates.
    The instance is created per clip and closed afterwards so that state can
    never leak between sessions.
    """
    import mediapipe as mp

    return mp.solutions.face_mesh.FaceMesh(
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        static_image_mode=False,
    )


def _analyse_video(clip_path: str):
    """Walk every frame, returning the MAR series and its timestamps."""
    capture = cv2.VideoCapture(clip_path)
    if not capture.isOpened():
        raise RuntimeError("could not open clip for video decoding")

    fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
    mar_values, timestamps = [], []
    face_mesh = _build_face_mesh()

    try:
        index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break

            # Prefer the container's own presentation timestamp; fall back to
            # frame index over fps when the demuxer does not supply one.
            pos_ms = capture.get(cv2.CAP_PROP_POS_MSEC)
            if pos_ms and pos_ms > 0:
                timestamp = pos_ms / 1000.0
            elif fps > 0:
                timestamp = index / fps
            else:
                timestamp = float(index)

            height, width = frame.shape[:2]
            results = face_mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

            mar = None
            if results.multi_face_landmarks:
                mar = _mouth_aspect_ratio(
                    results.multi_face_landmarks[0].landmark, width, height
                )

            mar_values.append(np.nan if mar is None else mar)
            timestamps.append(timestamp)
            index += 1
    finally:
        try:
            face_mesh.close()
        except Exception:
            pass
        capture.release()

    mar_array = np.asarray(mar_values, dtype=np.float64)
    time_array = np.asarray(timestamps, dtype=np.float64)

    if fps <= 0 and time_array.size > 1:
        span = time_array[-1] - time_array[0]
        fps = (time_array.size - 1) / span if span > 0 else 0.0

    return mar_array, time_array, float(fps)


def _mouth_activity(mar: np.ndarray, fps: float):
    """Per-frame mouth motion, as rolling variability of the aspect ratio.

    A single frame's aperture says almost nothing - a resting mouth may sit
    open and a mid-syllable mouth may be closed. What distinguishes speech is
    that the aperture *changes* continuously, so the signal is the rolling
    standard deviation over roughly one syllable's worth of time.

    Returns (active, known): `known` marks frames where the face was visible
    for long enough around this point to judge at all. Frames where the face
    was lost are never counted as a still mouth - that distinction is what
    keeps poor lighting from reading as a violation.
    """
    n = mar.size
    active = np.zeros(n, dtype=bool)
    known = np.zeros(n, dtype=bool)
    if n == 0 or fps <= 0:
        return active, known

    window = max(3, int(round(consts.AV_MOUTH_WINDOW_SEC * fps)))
    half = window // 2

    for i in range(n):
        lo, hi = max(0, i - half), min(n, i + half + 1)
        chunk = mar[lo:hi]
        valid = chunk[~np.isnan(chunk)]
        # Need most of the window to be real observations before judging.
        if valid.size < max(3, int(0.6 * (hi - lo))):
            continue
        known[i] = True
        active[i] = float(np.std(valid)) > consts.AV_MOUTH_ACTIVITY_THRESHOLD

    return active, known


def _to_bins(times: np.ndarray, values: np.ndarray, duration: float):
    """Resample an irregular per-frame series onto the shared time grid."""
    n_bins = max(1, int(math.ceil(duration / BIN_SEC)))
    out = np.zeros(n_bins, dtype=bool)
    if times.size == 0:
        return out
    idx = np.clip((times / BIN_SEC).astype(int), 0, n_bins - 1)
    for i, v in zip(idx, values):
        if v:
            out[i] = True
    return out


class AVAnswerAnalyzer:
    """Analyse one recorded answer clip. Stateless between calls."""

    def analyze(self, clip_bytes: bytes, extension: str = ".webm") -> dict:
        clip_path = wav_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as f:
                f.write(clip_bytes)
                clip_path = f.name
            wav_path = clip_path + ".wav"

            _extract_audio(clip_path, wav_path)
            samples, sample_rate = _load_wav(wav_path)
            speech_flags, audio_times, vad_stats = _detect_speech(samples, sample_rate)
            voices = _count_distinct_voices(
                samples, sample_rate, speech_flags, audio_times
            )

            mar, video_times, fps = _analyse_video(clip_path)
            active, known = _mouth_activity(mar, fps)

            audio_duration = samples.size / float(sample_rate) if sample_rate else 0.0
            video_duration = float(video_times[-1]) if video_times.size else 0.0
            duration = max(audio_duration, video_duration)

            speech_bins = _to_bins(audio_times, speech_flags, duration)
            active_bins = _to_bins(video_times, active, duration)
            known_bins = _to_bins(video_times, known, duration)

            return self._summarise(
                duration=duration,
                fps=fps,
                mar=mar,
                known=known,
                speech_bins=speech_bins,
                active_bins=active_bins,
                known_bins=known_bins,
                vad_stats=vad_stats,
                voices=voices,
            )
        finally:
            for path in (wav_path, clip_path):
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception as e:
                        logger.warning(f"AV: could not remove temp file {path}: {e}")

    def _summarise(
        self, duration, fps, mar, known, speech_bins, active_bins, known_bins,
        vad_stats, voices,
    ):
        frame_count = int(mar.size)
        frames_with_face = int(np.count_nonzero(~np.isnan(mar)))
        face_coverage = frames_with_face / frame_count if frame_count else 0.0

        speech_seconds = float(np.count_nonzero(speech_bins) * BIN_SEC)
        speech_ratio = (speech_seconds / duration) if duration > 0 else 0.0

        # Only bins where the mouth was actually observable can be judged.
        # Everything else is missing data, not a still mouth.
        judgable = speech_bins & known_bins
        judgable_seconds = float(np.count_nonzero(judgable) * BIN_SEC)
        silence_judgable = (~speech_bins) & known_bins

        def ratio(mask):
            total = np.count_nonzero(mask)
            return float(np.count_nonzero(active_bins & mask) / total) if total else 0.0

        during_speech = ratio(judgable)
        during_silence = ratio(silence_judgable)
        overall = ratio(known_bins)

        # Coverage is measured over the speech window specifically - a clip can
        # show the face clearly while idle and lose it entirely while talking.
        speech_face_coverage = (
            judgable_seconds / speech_seconds if speech_seconds > 0 else 0.0
        )

        reasons = []
        blockers = []

        if frame_count == 0:
            blockers.append("no video frames could be decoded")
        if fps < consts.AV_MIN_FPS:
            blockers.append(
                f"video frame rate {fps:.1f}fps is below the {consts.AV_MIN_FPS}fps minimum"
            )

        # A flat waveform is a capture fault, not a quiet candidate. Calling it
        # "too little speech" sends whoever is reading the report looking at the
        # wrong thing, so it gets its own message.
        peak_db = vad_stats.get("peak_db")
        audio_silent = peak_db is not None and peak_db < SILENT_AUDIO_PEAK_DB

        if audio_silent:
            blockers.append(
                f"no audio signal in the clip (peak {peak_db:.0f} dBFS) - the "
                "microphone is muted, the wrong input device is selected, or the "
                "recorder captured no audio track"
            )
        elif speech_seconds < consts.AV_MIN_SPEECH_SECONDS:
            blockers.append(
                f"only {speech_seconds:.1f}s of speech detected, "
                f"below the {consts.AV_MIN_SPEECH_SECONDS}s minimum"
            )

        # Face coverage is measured as a share OF SPEECH, so with no speech it
        # is 0/0 and reporting it would wrongly implicate the camera.
        if speech_seconds > 0 and speech_face_coverage < consts.AV_MIN_FACE_COVERAGE:
            blockers.append(
                f"face visible for only {speech_face_coverage:.0%} of speech, "
                f"below the {consts.AV_MIN_FACE_COVERAGE:.0%} minimum"
            )

        if blockers:
            verdict = "not_measurable"
            reasons = blockers
        else:
            if during_speech < consts.AV_MISMATCH_RATIO_THRESHOLD:
                reasons.append(
                    f"Mouth Moved During Only {during_speech:.0%} Of "
                    f"{speech_seconds:.1f}s Of Recorded Speech"
                )
            if (
                consts.AV_ENABLE_MULTI_VOICE_FLAG
                and voices.get("clusters", 1) >= consts.AV_MULTI_VOICE_MIN_CLUSTERS
            ):
                reasons.append(
                    f"{voices['clusters']} distinct voice clusters detected in a "
                    "single answer (coarse indicator, needs human review)"
                )
            verdict = "suspicious" if reasons else "clean"

        valid_mar = mar[~np.isnan(mar)]
        return {
            "verdict": verdict,
            "reasons": reasons,
            "duration_sec": round(duration, 2),
            "video_fps": round(fps, 2),
            "frame_count": frame_count,
            "frames_with_face": frames_with_face,
            "face_coverage": round(face_coverage, 4),
            "speech_seconds": round(speech_seconds, 2),
            "speech_ratio": round(speech_ratio, 4),
            "distinct_voice_clusters": int(voices.get("clusters", 0)),
            "mouth_active_ratio_during_speech": round(during_speech, 4),
            "mouth_active_ratio_during_silence": round(during_silence, 4),
            "mouth_active_ratio_overall": round(overall, 4),
            "metrics": {
                "speech_face_coverage": round(speech_face_coverage, 4),
                "judgable_speech_seconds": round(judgable_seconds, 2),
                "mar_median": round(float(np.median(valid_mar)), 4)
                if valid_mar.size
                else None,
                "mar_p10": round(float(np.percentile(valid_mar, 10)), 4)
                if valid_mar.size
                else None,
                "mar_p90": round(float(np.percentile(valid_mar, 90)), 4)
                if valid_mar.size
                else None,
                "voice_clustering": voices,
                "vad": vad_stats,
                "multi_voice_flag_enabled": consts.AV_ENABLE_MULTI_VOICE_FLAG,
                "thresholds": {
                    "mouth_activity": consts.AV_MOUTH_ACTIVITY_THRESHOLD,
                    "mismatch_ratio": consts.AV_MISMATCH_RATIO_THRESHOLD,
                    "min_face_coverage": consts.AV_MIN_FACE_COVERAGE,
                    "min_speech_seconds": consts.AV_MIN_SPEECH_SECONDS,
                    "mouth_window_sec": consts.AV_MOUTH_WINDOW_SEC,
                },
            },
        }
