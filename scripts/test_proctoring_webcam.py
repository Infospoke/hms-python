"""
Interactive webcam test for the proctoring pipeline (app/services/ai_interviewer/proctoring.py).

Runs the EXACT same ProctoringEngine().analyze_frame() call that production uses
(app/services/analyze_image_worker.py) against your live webcam feed, overlays the
alerts/metrics, and locally simulates the same consecutive-miss debounce logic
that decides whether a "No Face Detected" would actually get logged as a
violation in production -- so you can sit in front of the camera, lean out of
frame, dim the lights, turn sideways, etc. and see exactly what the system
would and wouldn't flag.

Usage:
    python scripts/test_proctoring_webcam.py
    python scripts/test_proctoring_webcam.py --camera 1
    python scripts/test_proctoring_webcam.py --mimic-prod       # resize/compress like the real capture pipeline
    python scripts/test_proctoring_webcam.py --headless          # no GUI window, console-only status

Keys (GUI mode):
    q / ESC   quit
    d         toggle synthetic darkening (stress-test the low-light retry path
              without needing to physically dim the room)
    s         save the current annotated frame to ./scripts/webcam_test_captures/
"""

import argparse
import os
import sys
import time
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from app.services.ai_interviewer.proctoring import ProctoringEngine

# Mirrors app/services/analyze_image_worker.py's NO_FACE_CONSECUTIVE_THRESHOLD.
# Kept as a local constant (not imported) so this script stays a standalone
# CV-only test tool with no Kafka/DB/MinIO dependencies -- if you change the
# threshold in analyze_image_worker.py, update it here too.
NO_FACE_CONSECUTIVE_THRESHOLD = 3

CAPTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webcam_test_captures")


def mimic_prod_compression(frame_bgr, max_dim=320, quality=55):
    """Reproduce the resolution/JPEG-quality loss the real pipeline applies
    before frames ever reach the model (see candidate_stream.html's 320x240
    capture and interview.py's analyze-image compression)."""
    h, w = frame_bgr.shape[:2]
    scale = max_dim / max(h, w)
    if scale < 1:
        frame_bgr = cv2.resize(frame_bgr, (int(w * scale), int(h * scale)))
    ok, buf = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        return frame_bgr
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


class NoFaceDebounce:
    """Local re-implementation of analyze_image_worker.py's per-session
    consecutive-miss counter, for a single simulated session."""

    def __init__(self, threshold=NO_FACE_CONSECUTIVE_THRESHOLD):
        self.threshold = threshold
        self.count = 0

    def register_miss(self) -> bool:
        self.count += 1
        return self.count >= self.threshold

    def reset(self):
        self.count = 0


class Stats:
    def __init__(self):
        self.frames = 0
        self.face_ok = 0
        self.face_rescued_by_fallback = 0
        self.no_face_transient_suppressed = 0
        self.no_face_logged = 0
        self.phone_alerts = 0
        self.multi_person_alerts = 0
        self.proc_times = deque(maxlen=200)

    def summary(self):
        avg_ms = (sum(self.proc_times) / len(self.proc_times) * 1000) if self.proc_times else 0
        return (
            "\n===== Session summary =====\n"
            f"Frames analyzed:                    {self.frames}\n"
            f"Face detected normally:             {self.face_ok}\n"
            f"Face rescued by fallback detector:   {self.face_rescued_by_fallback}"
            "   <- frames the OLD code would have wrongly flagged 'No Face Detected'\n"
            f"No-face transient (suppressed):     {self.no_face_transient_suppressed}"
            "   <- 1-2 frame blips filtered out by the debounce\n"
            f"No-face genuinely logged:           {self.no_face_logged}"
            "   <- sustained absence, would create a real violation\n"
            f"Cell phone alerts:                  {self.phone_alerts}\n"
            f"Multiple-people alerts:             {self.multi_person_alerts}\n"
            f"Avg analyze_frame() time:           {avg_ms:.1f} ms "
            f"({(1000/avg_ms if avg_ms else 0):.1f} fps ceiling)\n"
            "============================\n"
        )


def draw_status(frame, lines, origin=(10, 24), color=(255, 255, 255), scale=0.55):
    x, y = origin
    for line in lines:
        cv2.putText(frame, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(frame, line, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)
        y += 22
    return y


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--camera", type=int, default=0, help="Webcam index (default: 0)")
    parser.add_argument("--mimic-prod", action="store_true",
                         help="Resize/compress frames like the real capture pipeline (320px, JPEG q55) before analysis")
    parser.add_argument("--headless", action="store_true",
                         help="No GUI window; print status to console instead (use when no display is attached)")
    parser.add_argument("--status-interval", type=float, default=1.0,
                         help="Headless mode: seconds between console status prints (default: 1.0)")
    args = parser.parse_args()

    print("Loading ProctoringEngine (FaceMesh + FaceDetection fallback + YOLOv8n)... this can take a few seconds.")
    engine = ProctoringEngine()
    print("Ready.")

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"ERROR: could not open camera index {args.camera}. Try --camera 1, 2, ...")
        sys.exit(1)

    debounce = NoFaceDebounce()
    stats = Stats()
    darken = False
    last_status_print = 0.0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("WARNING: failed to read frame from camera, retrying...")
                time.sleep(0.1)
                continue

            frame = cv2.flip(frame, 1)  # mirror, like a normal webcam preview

            analysis_frame = frame
            if darken:
                analysis_frame = (analysis_frame.astype(np.float32) * 0.25).astype(np.uint8)
            if args.mimic_prod:
                analysis_frame = mimic_prod_compression(analysis_frame)

            t0 = time.time()
            result = engine.analyze_frame(analysis_frame)
            elapsed = time.time() - t0
            stats.proc_times.append(elapsed)
            stats.frames += 1

            alerts = result.get("alerts", [])
            metrics = result.get("metrics", {})

            if "Cell Phone Detected" in alerts:
                stats.phone_alerts += 1
            if "Multiple People Detected" in alerts:
                stats.multi_person_alerts += 1

            no_face = "No Face Detected" in alerts
            would_log = False
            if no_face:
                would_log = debounce.register_miss()
                if would_log:
                    stats.no_face_logged += 1
                else:
                    stats.no_face_transient_suppressed += 1
            else:
                if debounce.count > 0:
                    debounce.reset()
                if metrics.get("gaze") == "N/A" and metrics.get("head") == "N/A":
                    # face present but FaceMesh couldn't refine landmarks this
                    # frame -- the fallback detector is what saved this frame
                    # from a false "No Face Detected".
                    stats.face_rescued_by_fallback += 1
                else:
                    stats.face_ok += 1

            if args.headless:
                now = time.time()
                if now - last_status_print >= args.status_interval:
                    last_status_print = now
                    status = (
                        "LOGGED-NO-FACE" if would_log else
                        ("suppressed-no-face" if no_face else
                         ("face(fallback)" if metrics.get("gaze") == "N/A" else "face-ok"))
                    )
                    print(
                        f"[{stats.frames:5d}] {elapsed*1000:5.1f}ms  status={status:16s} "
                        f"debounce={debounce.count}/{debounce.threshold}  alerts={alerts}  metrics={metrics}"
                    )
                continue

            # ---- GUI overlay ----
            display = frame.copy()

            if no_face:
                if would_log:
                    banner, banner_color = "NO FACE DETECTED - WOULD LOG VIOLATION", (0, 0, 255)
                else:
                    banner, banner_color = f"No face (transient, {debounce.count}/{debounce.threshold} - suppressed)", (0, 200, 255)
            elif metrics.get("gaze") == "N/A" and metrics.get("head") == "N/A":
                banner, banner_color = "Face present (rescued by fallback detector)", (255, 180, 0)
            else:
                banner, banner_color = "Face detected OK", (0, 200, 0)

            cv2.rectangle(display, (0, 0), (display.shape[1], 34), banner_color, -1)
            cv2.putText(display, banner, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2, cv2.LINE_AA)

            lines = [
                f"gaze={metrics.get('gaze')}  head={metrics.get('head')}",
                f"alerts={alerts if alerts else '[]'}",
                f"analyze_frame: {elapsed*1000:.1f} ms   darken(d): {'ON' if darken else 'off'}"
                f"   mimic-prod: {'ON' if args.mimic_prod else 'off'}",
                f"frames={stats.frames}  ok={stats.face_ok}  rescued={stats.face_rescued_by_fallback}  "
                f"suppressed={stats.no_face_transient_suppressed}  logged={stats.no_face_logged}",
            ]
            draw_status(display, lines, origin=(10, 60))

            cv2.putText(display, "q/ESC quit   d toggle darken   s save frame",
                        (10, display.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(display, "q/ESC quit   d toggle darken   s save frame",
                        (10, display.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

            cv2.imshow("Proctoring pipeline test", display)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            elif key == ord("d"):
                darken = not darken
            elif key == ord("s"):
                os.makedirs(CAPTURE_DIR, exist_ok=True)
                out_path = os.path.join(CAPTURE_DIR, f"capture_{int(time.time()*1000)}.jpg")
                cv2.imwrite(out_path, display)
                print(f"Saved {out_path}")

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print(stats.summary())


if __name__ == "__main__":
    main()
