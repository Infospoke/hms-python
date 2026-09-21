"""Generate sample answer clips for testing audio/visual proctoring.

Produces a synthetic talking head whose mouth aperture and audio can be
controlled independently, which is exactly what is needed to reproduce the
"someone off-camera is answering" case on demand - the candidate's mouth stays
still while speech is recorded.

The faces are deliberately crude drawings rather than real people: they carry
no biometric data, can be committed to the repo, and MediaPipe tracks their
mouth aperture over a wide enough range (MAR ~0.03 closed to ~0.68 open) to
exercise the detector properly.

Every generated clip is analysed immediately and checked against the verdict it
is supposed to produce, so a sample that stops being valid fails loudly here
rather than quietly misleading whoever is testing.

    python scripts/generate_av_samples.py [--out samples/av] [--keep-going]
"""

import argparse
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

SAMPLE_RATE = 16000
FPS = 15
WIDTH, HEIGHT = 640, 480


# --------------------------------------------------------------------------
# Face rendering
# --------------------------------------------------------------------------

def draw_face(mouth_px: float, dx: float = 0.0, dy: float = 0.0,
              brightness: float = 1.0) -> np.ndarray:
    """One frame of the synthetic head. `mouth_px` is the mouth's vertical
    half-axis in pixels, which is what the detector ultimately measures."""
    img = np.full((HEIGHT, WIDTH, 3), 205, np.uint8)
    cx, cy = int(320 + dx), int(240 + dy)

    cv2.ellipse(img, (cx, cy), (115, 155), 0, 0, 360, (188, 158, 138), -1)
    cv2.ellipse(img, (cx, cy - 130), (115, 60), 0, 0, 360, (60, 45, 38), -1)

    for ex in (cx - 42, cx + 42):
        cv2.ellipse(img, (ex, cy - 35), (24, 13), 0, 0, 360, (250, 250, 250), -1)
        cv2.circle(img, (ex, cy - 35), 9, (45, 32, 28), -1)
        cv2.ellipse(img, (ex, cy - 52), (26, 7), 0, 0, 180, (70, 55, 45), -1)

    cv2.ellipse(img, (cx, cy + 10), (13, 26), 0, 0, 360, (172, 142, 122), -1)
    cv2.ellipse(img, (cx, cy + 15), (16, 10), 0, 0, 360, (160, 130, 112), -1)

    h = max(2, int(round(mouth_px)))
    cv2.ellipse(img, (cx, cy + 80), (46, h), 0, 0, 360, (120, 60, 62), -1)
    if h > 8:  # teeth appear once the mouth is properly open
        cv2.ellipse(img, (cx, cy + 80 - int(h * 0.45)), (40, 4), 0, 0, 360,
                    (240, 235, 230), -1)

    if brightness != 1.0:
        img = np.clip(img.astype(np.float32) * brightness, 0, 255).astype(np.uint8)
    return img


# --------------------------------------------------------------------------
# Audio synthesis
# --------------------------------------------------------------------------

def speech_envelope(duration: float, seed: int, speech_fraction: float = 0.75):
    """A boolean speech/pause mask at audio rate, plus its syllable envelope.

    Real answers are not one continuous burst - they have clause pauses - and
    the detector's VAD smoothing needs those to behave realistically.
    """
    rng = np.random.default_rng(seed)
    n = int(duration * SAMPLE_RATE)
    mask = np.zeros(n, dtype=bool)

    pos = 0.0
    while pos < duration:
        burst = rng.uniform(1.2, 2.6)
        gap = rng.uniform(0.25, 0.6)
        a, b = int(pos * SAMPLE_RATE), int(min(duration, pos + burst) * SAMPLE_RATE)
        mask[a:b] = True
        pos += burst + gap

    # Trim toward the requested talking share so short-answer samples stay short.
    if speech_fraction < 1.0:
        want = int(n * speech_fraction)
        idx = np.flatnonzero(mask)
        if idx.size > want:
            mask[idx[want:]] = False

    t = np.arange(n) / SAMPLE_RATE
    syllable = 0.55 + 0.45 * np.sin(2 * np.pi * 4.2 * t)
    return mask, syllable


def synth_voice(duration: float, f0: float, timbre: float, seed: int,
                mask=None, syllable=None, level: float = 0.28):
    """Harmonic-stack voice. `f0` and `timbre` separate the two speakers."""
    rng = np.random.default_rng(seed)
    n = int(duration * SAMPLE_RATE)
    t = np.arange(n) / SAMPLE_RATE

    if mask is None:
        mask, syllable = speech_envelope(duration, seed)

    # Slight pitch drift so the voice is not a synthetic monotone.
    drift = 1.0 + 0.04 * np.sin(2 * np.pi * 0.35 * t + rng.uniform(0, 6))
    sig = np.zeros(n)
    for k in range(1, 13):
        sig += (timbre ** k) * np.sin(2 * np.pi * f0 * k * drift * t + rng.uniform(0, 6))

    sig *= syllable * mask
    sig += rng.standard_normal(n) * 0.0015            # room tone
    peak = np.max(np.abs(sig))
    if peak > 0:
        sig = sig / peak * level
    return sig.astype(np.float32), mask


def near_silence(duration: float, seed: int = 0):
    rng = np.random.default_rng(seed)
    n = int(duration * SAMPLE_RATE)
    return (rng.standard_normal(n) * 0.0009).astype(np.float32), np.zeros(n, bool)


# --------------------------------------------------------------------------
# Muxing
# --------------------------------------------------------------------------

def find_ffmpeg() -> str:
    from app.services.ai_interviewer.av_analysis import _resolve_ffmpeg
    return _resolve_ffmpeg()


def write_clip(frames, audio, out_path: str, ffmpeg: str) -> None:
    """Encode frames + audio into one WebM, the container a browser produces."""
    import soundfile as sf

    tmp = tempfile.mkdtemp()
    video_tmp = os.path.join(tmp, "v.avi")
    audio_tmp = os.path.join(tmp, "a.wav")

    writer = cv2.VideoWriter(video_tmp, cv2.VideoWriter_fourcc(*"MJPG"),
                             FPS, (WIDTH, HEIGHT))
    for frame in frames:
        writer.write(frame)
    writer.release()

    sf.write(audio_tmp, audio, SAMPLE_RATE)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    proc = subprocess.run(
        [ffmpeg, "-y", "-i", video_tmp, "-i", audio_tmp,
         "-c:v", "libvpx", "-b:v", "600k", "-c:a", "libopus", "-b:a", "48k",
         "-shortest", out_path, "-loglevel", "error"],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode("utf-8", "replace")[-600:])


# --------------------------------------------------------------------------
# Sample definitions
# --------------------------------------------------------------------------

def frames_for(duration, mouth_fn, brightness=1.0, face_visible_fn=None, seed=1):
    """Render the frame sequence, letting each sample drive mouth and visibility."""
    rng = np.random.default_rng(seed)
    out = []
    for i in range(int(duration * FPS)):
        t = i / FPS
        if face_visible_fn is not None and not face_visible_fn(t):
            # Face genuinely absent - the candidate looked away or left frame.
            out.append(np.full((HEIGHT, WIDTH, 3), 205, np.uint8))
            continue
        # Small idle head motion, so a "still mouth" clip is not a frozen frame.
        dx = 3.0 * np.sin(2 * np.pi * 0.23 * t) + rng.normal(0, 0.3)
        dy = 2.0 * np.sin(2 * np.pi * 0.17 * t) + rng.normal(0, 0.3)
        out.append(draw_face(mouth_fn(t), dx, dy, brightness))
    return out


def talking_mouth(mask, syllable):
    """Mouth aperture that follows the speech envelope, as a real mouth does."""
    def fn(t):
        i = int(t * SAMPLE_RATE)
        if i >= mask.size or not mask[i]:
            return 4.0
        return 6.0 + 26.0 * max(0.0, syllable[i] - 0.1)
    return fn


def build_samples(duration=16.0):
    """Each entry: (filename, description, frames, audio, expected_verdict)."""
    samples = []

    # 1. Normal answer. Mouth follows the audio.
    audio, mask = synth_voice(duration, 128, 0.72, seed=11)
    _, syll = speech_envelope(duration, 11)
    samples.append((
        "01_clean_normal_answer.webm",
        "Candidate answers normally - mouth moves in time with their speech.",
        frames_for(duration, talking_mouth(mask, syll), seed=11),
        audio, "clean",
    ))

    # 2. THE REPORTED ATTACK. Full speech recorded, mouth completely still.
    audio, mask = synth_voice(duration, 128, 0.72, seed=22)
    samples.append((
        "02_suspicious_helper_answering.webm",
        "Someone off-camera answers: speech is recorded while the candidate's "
        "mouth stays still and their face is clearly visible.",
        frames_for(duration, lambda t: 5.0, seed=22),
        audio, "suspicious",
    ))

    # 3. Two speakers inside a single answer.
    half = duration / 2
    mask_a, syll_a = speech_envelope(half, 33)
    mask_b, syll_b = speech_envelope(half, 44)
    voice_a, _ = synth_voice(half, 115, 0.70, seed=33, mask=mask_a, syllable=syll_a)
    voice_b, _ = synth_voice(half, 225, 0.42, seed=44, mask=mask_b, syllable=syll_b)
    audio = np.concatenate([voice_a, voice_b])
    mask = np.concatenate([mask_a, mask_b])
    syll = np.concatenate([syll_a, syll_b])
    samples.append((
        "03_clean_two_voices_not_flagged.webm",
        "Two distinct voices within one answer. Reads CLEAN by default: the "
        "voice-cluster signal is too unreliable to flag on (AV_ENABLE_MULTI_"
        "VOICE_FLAG is off), and the candidate's mouth is moving throughout.",
        frames_for(duration, talking_mouth(mask, syll), seed=33),
        audio, "clean",
    ))

    # 4. No face at all in frame.
    audio, _ = synth_voice(duration, 128, 0.72, seed=55)
    samples.append((
        "04_not_measurable_no_face.webm",
        "Speech recorded but no face in frame - must NOT be called suspicious.",
        [np.full((HEIGHT, WIDTH, 3), 205, np.uint8) for _ in range(int(duration * FPS))],
        audio, "not_measurable",
    ))

    # 5. Too dark for landmarks. The fairness case that must never accuse.
    audio, mask = synth_voice(duration, 128, 0.72, seed=66)
    samples.append((
        "05_not_measurable_too_dark.webm",
        "Candidate in near-darkness - a poorly-lit room must read as "
        "unmeasurable, never as cheating.",
        frames_for(duration, lambda t: 5.0, brightness=0.06, seed=66),
        audio, "not_measurable",
    ))

    # 6. Barely any speech to judge.
    short = 6.0
    audio, mask = synth_voice(short, 128, 0.72, seed=77, level=0.28)
    _, syll = speech_envelope(short, 77)
    trimmed = audio.copy()
    trimmed[int(1.8 * SAMPLE_RATE):] *= 0.001   # ~1.8s of speech, then quiet
    samples.append((
        "06_not_measurable_too_short.webm",
        "Very short answer - too little speech for the comparison to mean "
        "anything.",
        frames_for(short, talking_mouth(mask, syll), seed=77),
        trimmed, "not_measurable",
    ))

    # 7. Candidate silent and thinking. The most important non-accusation.
    audio, _ = near_silence(duration, seed=88)
    samples.append((
        "07_not_measurable_silent_thinking.webm",
        "Candidate sits quietly thinking - still mouth AND no speech. Nothing "
        "to judge, so nothing is alleged.",
        frames_for(duration, lambda t: 5.0, seed=88),
        audio, "not_measurable",
    ))

    # 8. Face drops out for most of the answer.
    audio, mask = synth_voice(duration, 128, 0.72, seed=99)
    _, syll = speech_envelope(duration, 99)
    samples.append((
        "08_not_measurable_face_intermittent.webm",
        "Face visible for only part of the answer - below the coverage floor, "
        "so the clip is unmeasurable rather than suspicious.",
        frames_for(duration, talking_mouth(mask, syll),
                   face_visible_fn=lambda t: (t % 5.0) < 1.2, seed=99),
        audio, "not_measurable",
    ))

    return samples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="samples/av")
    ap.add_argument("--duration", type=float, default=16.0)
    ap.add_argument("--keep-going", action="store_true",
                    help="Write all samples even if one fails its expected verdict.")
    args = ap.parse_args()

    ffmpeg = find_ffmpeg()
    print(f"ffmpeg: {ffmpeg}\noutput:  {os.path.abspath(args.out)}\n")

    from app.services.ai_interviewer.av_analysis import AVAnswerAnalyzer
    analyzer = AVAnswerAnalyzer()

    failures = []
    manifest = []

    for name, desc, frames, audio, expected in build_samples(args.duration):
        path = os.path.join(args.out, name)
        print(f"  building {name} ...", end=" ", flush=True)
        write_clip(frames, audio, path, ffmpeg)
        size_kb = os.path.getsize(path) / 1024

        with open(path, "rb") as f:
            result = analyzer.analyze(f.read(), ".webm")

        actual = result["verdict"]
        ok = actual == expected
        if not ok:
            failures.append(f"{name}: expected {expected}, got {actual}")

        print(f"{size_kb:6.0f} KB  ->  {actual:16} {'OK' if ok else 'MISMATCH'}")
        print(f"      speech={result['speech_seconds']}s  face={result['face_coverage']:.0%}"
              f"  mouth/speech={result['mouth_active_ratio_during_speech']:.0%}"
              f"  voices={result['distinct_voice_clusters']}")
        if result["reasons"]:
            for r in result["reasons"]:
                print(f"      - {r}")

        manifest.append({
            "file": name, "description": desc, "expected_verdict": expected,
            "observed_verdict": actual,
            "speech_seconds": result["speech_seconds"],
            "face_coverage": result["face_coverage"],
            "mouth_active_ratio_during_speech": result["mouth_active_ratio_during_speech"],
            "distinct_voice_clusters": result["distinct_voice_clusters"],
            "reasons": result["reasons"],
        })

    import json
    with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n{len(manifest)} samples written to {os.path.abspath(args.out)}")
    if failures:
        print("\nSamples that did not produce their expected verdict:")
        for f in failures:
            print(f"  - {f}")
        if not args.keep_going:
            return 1
    else:
        print("All samples produced their expected verdict.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
