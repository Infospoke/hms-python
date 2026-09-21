"""
Real-time Audio & Video Lip-Sync Proctoring Test.
Captures live microphone audio via sounddevice + live webcam frames via OpenCV.
Correlates real-time speech activity with MediaPipe Mouth Aspect Ratio (MAR).

Run command:
    .\\.venv\\Scripts\\python scripts/test_live_voice_violation.py
"""
import sys
import os
import time
import cv2
import numpy as np

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ai_interviewer.proctoring import ProctoringEngine

# Try importing sounddevice for live microphone stream
try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False


class LiveMicrophoneMonitor:
    """Streams live microphone audio in a background thread and tracks RMS audio energy."""
    def __init__(self, sample_rate=16000, block_size=1600):
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.current_rms = 0.0
        self.peak_rms = 0.05
        self.threshold_percent = 15  # Speech detection threshold: 15%
        self.is_running = False
        self.stream = None

    def _audio_callback(self, indata, frames, time_info, status):
        rms = float(np.sqrt(np.mean(indata**2)))
        self.current_rms = 0.7 * self.current_rms + 0.3 * rms
        if self.current_rms > self.peak_rms:
            self.peak_rms = max(0.05, self.current_rms)

    def start(self):
        if not HAS_SOUNDDEVICE:
            return False
        try:
            self.stream = sd.InputStream(
                channels=1,
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                callback=self._audio_callback
            )
            self.stream.start()
            self.is_running = True
            return True
        except Exception as e:
            print(f"Warning: Could not start microphone stream: {e}")
            self.is_running = False
            return False

    def stop(self):
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        self.is_running = False

    @property
    def is_speech_active(self) -> bool:
        return self.audio_level_percent >= self.threshold_percent

    @property
    def audio_level_percent(self) -> int:
        norm = min(1.0, self.current_rms / max(0.02, self.peak_rms))
        return int(norm * 100)



def main():
    print("\n============================================================")
    print("   LIVE AUDIO & VIDEO LIP-SYNC PROCTORING TEST")
    print("============================================================")
    print("Initializing Proctoring Engine...")
    engine = ProctoringEngine()
    print("Engine loaded successfully!\n")

    # Start live microphone
    mic = LiveMicrophoneMonitor()
    mic_active = mic.start()
    if mic_active:
        print("[Microphone] Live audio stream active from default microphone.")
    else:
        print("[Microphone] Sounddevice not available or no mic found. Falling back to simulation mode.")

    camera_index = 0
    cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        print(f"Error: Could not open camera at index {camera_index}.")
        print("Please check your webcam connection.")
        mic.stop()
        return

    # Modes: Real Mic (if available) or Manual Simulation
    use_live_mic = mic_active
    simulated_voice = True
    accumulated_mismatch_time = 0.0
    last_loop_time = time.time()
    legitimate_speaking_time = 0.0
    total_violations = 0
    violation_flash_until = 0.0
    VIOLATION_DURATION_SECONDS = 10.0


    print("Controls:")
    print("  [m]     - Toggle between Live Microphone / Simulated Audio")
    print("  [v]     - Toggle simulated voice ON/OFF (in simulation mode)")
    print("  [r]     - Reset accumulated mismatch timer to 0.0s")
    print("  [+] / [-] - Adjust microphone threshold sensitivity")
    print("  [q/ESC] - Exit test")
    print("\nTest Scenarios:")
    print("  1. Speak sentence with lips moving -> Banner GREEN (OK)")
    print("  2. Speak sentence without moving lips -> Timer accumulates (continues across sentences!)")
    print("  3. Total voice without lip movement reaches 10s -> VIOLATION TRIGGERED (RED)")
    print("------------------------------------------------------------\n")

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                print("Failed to grab frame from camera.")
                time.sleep(0.1)
                continue

            frame = cv2.flip(frame, 1)

            now = time.time()
            dt = max(0.001, min(0.2, now - last_loop_time))
            last_loop_time = now

            # Determine audio status
            if use_live_mic:
                audio_detected = mic.is_speech_active
                mic_level = mic.audio_level_percent
                audio_source_label = f"LIVE MIC: {'SPEAKING' if audio_detected else 'SILENT'} (Level: {mic_level}%, Thresh: {mic.threshold_percent}%)"
            else:
                audio_detected = simulated_voice
                mic_level = 80 if simulated_voice else 0
                audio_source_label = f"SIMULATED VOICE: {'ON (Speech active)' if simulated_voice else 'OFF (Silent)'}"


            t0 = time.time()
            result = engine.analyze_frame(frame, audio_detected=audio_detected)
            elapsed_ms = (time.time() - t0) * 1000

            alerts = result.get("alerts", [])
            metrics = result.get("metrics", {})

            lip_moving = metrics.get("lip_movement", False)
            mar = metrics.get("mar", 0.0)
            mouth_status = metrics.get("mouth", "Closed")

            display = frame.copy()
            h, w = display.shape[:2]

            is_mismatch = audio_detected and not lip_moving
            is_legitimate = audio_detected and lip_moving

            # Cumulative time accumulation logic across sentences
            if is_mismatch:
                accumulated_mismatch_time += dt
                legitimate_speaking_time = 0.0
                if accumulated_mismatch_time >= VIOLATION_DURATION_SECONDS:
                    # Trigger violation, increment counter, flash for 2.5s, and reset accumulator
                    total_violations += 1
                    violation_flash_until = now + 2.5
                    accumulated_mismatch_time = 0.0
                    print(f"--> [VIOLATION #{total_violations} LOGGED] Voice without lip movement exceeded {VIOLATION_DURATION_SECONDS}s! Timer auto-reset to 0.0s.")
            elif is_legitimate:
                legitimate_speaking_time += dt
                # Legitimate speech clears pending mismatch
                if legitimate_speaking_time >= 1.0:
                    accumulated_mismatch_time = 0.0
            else:
                # Silence: keep accumulated mismatch time intact for next sentence
                legitimate_speaking_time = 0.0

            # Determine banner text and colors
            if now < violation_flash_until:
                banner_text = f"VOICE DETECTED WITHOUT LIP MOVEMENT - VIOLATION #{total_violations} LOGGED! (RESET TO 0s)"
                banner_color = (0, 0, 255)  # RED
            elif is_mismatch:
                remaining = VIOLATION_DURATION_SECONDS - accumulated_mismatch_time
                banner_text = f"Voice without lip movement: {accumulated_mismatch_time:.1f}s / {VIOLATION_DURATION_SECONDS:.0f}s (Alert in {remaining:.1f}s) [Accumulating]"
                banner_color = (0, 165, 255)  # ORANGE
            elif is_legitimate:
                banner_text = f"Candidate Speaking OK (Voice + Lips Matched) | Total Violations: {total_violations}"
                banner_color = (0, 200, 0)  # GREEN
            else:
                if accumulated_mismatch_time > 0.0:
                    banner_text = f"Idle / Silent | Stored Mismatch: {accumulated_mismatch_time:.1f}s / {VIOLATION_DURATION_SECONDS:.0f}s [Resumes on voice]"
                    banner_color = (120, 100, 40)  # MUTED AMBER
                else:
                    banner_text = f"Idle / Silent (No speech detected) | Total Violations: {total_violations}"
                    banner_color = (80, 80, 80)  # DARK GRAY

            # Top notification banner
            cv2.rectangle(display, (0, 0), (w, 42), banner_color, -1)
            cv2.putText(
                display,
                banner_text,
                (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 0, 0) if banner_color not in [(0, 0, 255), (80, 80, 80)] else (255, 255, 255),
                2,
                cv2.LINE_AA,
            )


            # Audio volume meter bar
            meter_x, meter_y, meter_w, meter_h = 14, 52, 220, 14
            cv2.rectangle(display, (meter_x, meter_y), (meter_x + meter_w, meter_y + meter_h), (40, 40, 40), -1)
            fill_w = int((mic_level / 100.0) * meter_w)
            meter_color = (0, 220, 0) if mic_level < 60 else ((0, 180, 255) if mic_level < 85 else (0, 0, 255))
            if fill_w > 0:
                cv2.rectangle(display, (meter_x, meter_y), (meter_x + fill_w, meter_y + meter_h), meter_color, -1)
            cv2.rectangle(display, (meter_x, meter_y), (meter_x + meter_w, meter_y + meter_h), (200, 200, 200), 1)

            cv2.putText(
                display,
                f"Audio: {mic_level}%",
                (meter_x + meter_w + 10, meter_y + 11),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (255, 255, 255),
                1,
                cv2.LINE_AA,
            )

            # Metrics and stats overlay
            status_lines = [
                f"Audio Source: {audio_source_label}",
                f"Mouth: {mouth_status}  |  MAR: {mar:.3f} (Threshold: {engine.THRESH_LIP_OPEN})",
                f"Lip Moving: {'YES' if lip_moving else 'NO'}  |  Voice Active: {'YES' if audio_detected else 'NO'}",
                f"Accumulated Mismatch: {accumulated_mismatch_time:.1f}s / {VIOLATION_DURATION_SECONDS:.0f}s (Continues across sentences)",
            ]

            y = 90
            for line in status_lines:
                cv2.putText(display, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(display, line, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 255, 255), 1, cv2.LINE_AA)
                y += 22

            # Footer instructions
            footer_text = "[m]: Live/Sim Mic | [v]: Sim Voice | [r]: Reset Timer | [+/-]: Mic Sens | [q/ESC]: Quit"
            cv2.putText(
                display,
                footer_text,
                (12, h - 12),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (220, 220, 220),
                1,
                cv2.LINE_AA,
            )

            cv2.imshow("Live Audio-Visual Lip Sync Proctoring Test", display)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            elif key == ord("m"):
                if mic_active:
                    use_live_mic = not use_live_mic
                    print(f"Audio mode switched to: {'LIVE MICROPHONE' if use_live_mic else 'SIMULATED'}")
            elif key == ord("v"):
                if not use_live_mic:
                    simulated_voice = not simulated_voice
                    print(f"Simulated voice toggled: {'ON' if simulated_voice else 'OFF'}")
            elif key == ord("r"):
                accumulated_mismatch_time = 0.0
                legitimate_speaking_time = 0.0
                print("Accumulated mismatch timer reset to 0.0s")
            elif key in (ord("+"), ord("=")):
                mic.threshold_percent = min(90, mic.threshold_percent + 2)
                print(f"Microphone threshold increased to: {mic.threshold_percent}%")
            elif key in (ord("-"), ord("_")):
                mic.threshold_percent = max(3, mic.threshold_percent - 2)
                print(f"Microphone threshold decreased to: {mic.threshold_percent}%")



    finally:
        mic.stop()
        cap.release()
        cv2.destroyAllWindows()
        print("\nTest finished.")


if __name__ == "__main__":
    main()
