import threading
import cv2
import mediapipe as mp
import numpy as np
import math
import logging
import os
import sys
from types import SimpleNamespace
from ultralytics import YOLO

logger = logging.getLogger(__name__)


# --- PROCTORING ENGINE ---


class ProctoringEngine:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProctoringEngine, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if ProctoringEngine._initialized:
            return
        logger.info("Initializing ProctoringEngine...")
        self._local = threading.local()

        self.THRESH_LOOK_RIGHT = 0.4
        self.THRESH_LOOK_LEFT = 0.66
        self.THRESH_HEAD_DOWN = 1.65
        self.THRESH_HEAD_UP = 0.83
        self.THRESH_HEAD_RIGHT = 0.55
        self.THRESH_HEAD_LEFT = 2.5
        self.COCO_PHONE_CLASS_ID = 67
        self.COCO_PERSON_CLASS_ID = 0

        self.LOW_LIGHT_BRIGHTNESS_THRESHOLD = 90
        self.THRESH_LIP_OPEN = 0.12

        # Build (and cache) the model bundle for whichever thread constructs
        # the singleton, so the existing preload-on-startup behavior in
        # run_workers.py still warms up at least one bundle immediately.
        self._get_models()
        ProctoringEngine._initialized = True
        logger.info("ProctoringEngine initialized successfully")

    def _build_models(self):
        old_stderr, stderr_fd = suppress_tf_warnings()
        try:
            mp_face_mesh = mp.solutions.face_mesh
            face_mesh = mp_face_mesh.FaceMesh(
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            mp_face_detection = mp.solutions.face_detection
            face_detection = mp_face_detection.FaceDetection(
                model_selection=0,
                min_detection_confidence=0.4,
            )
        finally:
            restore_stderr(old_stderr, stderr_fd)

        logger.info(
            "Loading YOLOv8 model for object detection (thread=%s)...",
            threading.current_thread().name,
        )
        old_stderr, stderr_fd = suppress_tf_warnings()
        try:
            yolo = YOLO("yolov8n.pt")
        finally:
            restore_stderr(old_stderr, stderr_fd)

        return SimpleNamespace(
            face_mesh=face_mesh, face_detection=face_detection, yolo=yolo
        )

    def _get_models(self):
        """Return this thread's own model bundle, building it on first use."""
        models = getattr(self._local, "models", None)
        if models is None:
            models = self._build_models()
            self._local.models = models
        return models

    def warm_up(self):
        """Force this thread's model bundle to build now instead of on the
        first real frame, so worker-pool threads can be pre-warmed at
        startup rather than paying model-load latency on live traffic."""
        self._get_models()

    def calculate_distance(self, p1, p2):
        return math.hypot(p1.x - p2.x, p1.y - p2.y)

    def get_ratio(self, point, start, end):
        p = np.array([point.x, point.y])
        a = np.array([start.x, start.y])
        b = np.array([end.x, end.y])
        vec_line = b - a
        vec_point = p - a
        line_len_sq = np.dot(vec_line, vec_line)
        if line_len_sq == 0:
            return 0.5
        return np.dot(vec_point, vec_line) / line_len_sq

    def get_eye_aspect_ratio(self, landmarks, indices):
        v_dist = self.calculate_distance(landmarks[indices[0]], landmarks[indices[1]])
        h_dist = self.calculate_distance(landmarks[indices[2]], landmarks[indices[3]])
        return v_dist / h_dist if h_dist > 0 else 0.0

    def get_mouth_aspect_ratio(self, landmarks):
        """
        Calculate the Mouth Aspect Ratio (MAR) using inner lip landmarks.
        Upper inner: 81, 13, 311
        Lower inner: 178, 14, 402
        Corners inner: 78, 308
        """
        v1 = self.calculate_distance(landmarks[81], landmarks[178])
        v2 = self.calculate_distance(landmarks[13], landmarks[14])
        v3 = self.calculate_distance(landmarks[311], landmarks[402])
        h = self.calculate_distance(landmarks[78], landmarks[308])
        if h == 0:
            return 0.0
        return (v1 + v2 + v3) / (3.0 * h)

    def _mean_brightness(self, bgr_image):
        gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
        return float(np.mean(gray))

    def _enhance_low_light(self, bgr_image):
        lab = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        l_eq = clahe.apply(l_channel)
        enhanced_lab = cv2.merge((l_eq, a_channel, b_channel))
        return cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)

    def _detect_face_landmarks(self, models, image_array):
        rgb = cv2.cvtColor(image_array, cv2.COLOR_BGR2RGB)
        results = models.face_mesh.process(rgb)
        if results.multi_face_landmarks:
            return results.multi_face_landmarks, False

        probe_bgr = image_array
        if self._mean_brightness(image_array) < self.LOW_LIGHT_BRIGHTNESS_THRESHOLD:
            probe_bgr = self._enhance_low_light(image_array)
            enhanced_rgb = cv2.cvtColor(probe_bgr, cv2.COLOR_BGR2RGB)
            retry_results = models.face_mesh.process(enhanced_rgb)
            if retry_results.multi_face_landmarks:
                return retry_results.multi_face_landmarks, False

        probe_rgb = cv2.cvtColor(probe_bgr, cv2.COLOR_BGR2RGB)
        fallback = models.face_detection.process(probe_rgb)
        if fallback.detections:
            return None, True

        return None, False

    def analyze_frame(
        self,
        image_array,
        audio_detected: bool = False,
        is_speaking: bool = False,
    ):
        models = self._get_models()
        alerts = []
        has_voice = bool(audio_detected or is_speaking)
        results = models.yolo(image_array, verbose=False, stream=True)
        phone_detected = False
        person_count = 0
        for r in results:
            boxes = r.boxes
            for box in boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                if cls_id == self.COCO_PHONE_CLASS_ID and conf > 0.5:
                    phone_detected = True
                elif cls_id == self.COCO_PERSON_CLASS_ID and conf > 0.5:
                    person_count += 1
        if phone_detected:
            alerts.append("Cell Phone Detected")
        if person_count > 1:
            alerts.append("Multiple People Detected")

        metrics = {
            "gaze": "Center",
            "head": "Forward",
            "emotion": "Neutral",
            "mouth": "Closed",
            "lip_movement": False,
        }

        landmarks_list, face_present_unrefined = self._detect_face_landmarks(
            models, image_array
        )

        if landmarks_list is None:
            if face_present_unrefined:
                return {
                    "alerts": alerts,
                    "metrics": {
                        "gaze": "N/A",
                        "head": "N/A",
                        "emotion": "N/A",
                        "mouth": "N/A",
                        "lip_movement": False,
                    },
                }
            alerts.append("No Face Detected")
            return {
                "alerts": alerts,
                "metrics": {
                    "gaze": "N/A",
                    "head": "N/A",
                    "emotion": "N/A",
                    "mouth": "N/A",
                    "lip_movement": False,
                },
            }

        lm = landmarks_list[0].landmark
        iris, inner, outer = lm[473], lm[362], lm[263]
        gaze_ratio = self.get_ratio(iris, inner, outer)
        if gaze_ratio < self.THRESH_LOOK_RIGHT:
            metrics["gaze"] = "Right"
            alerts.append("Looking Away (Right)")
        elif gaze_ratio > self.THRESH_LOOK_LEFT:
            metrics["gaze"] = "Left"
            alerts.append("Looking Away (Left)")
        nose, chin = lm[1], lm[152]
        left_ear, right_ear = lm[234], lm[454]
        forehead = lm[10]
        pitch_ratio = (nose.y - forehead.y) / (chin.y - nose.y + 1e-06)
        yaw_ratio = abs(nose.x - left_ear.x) / (abs(nose.x - right_ear.x) + 1e-06)
        if pitch_ratio > self.THRESH_HEAD_DOWN:
            metrics["head"] = "Down"
            alerts.append("Head Down")
        elif pitch_ratio < self.THRESH_HEAD_UP:
            metrics["head"] = "Up"
            alerts.append("Head Up")
        elif yaw_ratio < self.THRESH_HEAD_RIGHT:
            metrics["head"] = "Right"
            alerts.append("Turning Head Right")
        elif yaw_ratio > self.THRESH_HEAD_LEFT:
            metrics["head"] = "Left"
            alerts.append("Turning Head Left")

        # Lip Movement / Mouth Aspect Ratio
        mar = self.get_mouth_aspect_ratio(lm)
        metrics["mar"] = round(float(mar), 3)
        is_lip_moving = mar > self.THRESH_LIP_OPEN
        metrics["mouth"] = "Open" if is_lip_moving else "Closed"
        metrics["lip_movement"] = is_lip_moving

        # Check for Voice / Audio without candidate Lip Movement (Proxy Speaking / Someone else speaking)
        if has_voice and not is_lip_moving:
            alerts.append("Voice Detected Without Lip Movement")

        return {"alerts": alerts, "metrics": metrics}

    def analyze_video_answer(self, video_file_path: str, sample_fps: float = 2.0) -> dict:
        """
        Samples frames from a submitted answer video recording to analyze lip tracking,
        face presence, multiple people, phone usage, and gaze/pose violations.
        """
        cap = cv2.VideoCapture(video_file_path)
        if not cap.isOpened():
            return {
                "success": False,
                "error": "Could not open video file",
                "lip_movement_ratio": 0.0,
                "face_detected_ratio": 0.0,
                "is_proxy_speaking": False,
                "no_face_detected": False,
                "multiple_people_detected": False,
                "phone_detected": False,
                "looking_away_detected": False,
                "alerts": [],
                "violations": [],
                "violation_snapshots": {},
            }

        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        sample_interval = max(1, int(round(fps / sample_fps)))

        total_frames_sampled = 0
        lip_movement_frames = 0
        face_detected_frames = 0
        multiple_people_frames = 0
        phone_detected_frames = 0
        looking_away_frames = 0
        mar_values = []
        violation_snapshots = {}
        alerts = set()
        frame_idx = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_interval == 0:
                total_frames_sampled += 1
                result = self.analyze_frame(frame, audio_detected=True)
                frame_alerts = result.get("alerts", [])
                metrics = result.get("metrics", {})
                mar = metrics.get("mar", 0.0)
                is_lip_moving = metrics.get("lip_movement", False)

                # Face Presence
                if "No Face Detected" not in frame_alerts:
                    face_detected_frames += 1
                elif "no_face" not in violation_snapshots:
                    violation_snapshots["no_face"] = frame.copy()

                # Multiple People
                if "Multiple People Detected" in frame_alerts:
                    multiple_people_frames += 1
                    if "multiple_people" not in violation_snapshots:
                        violation_snapshots["multiple_people"] = frame.copy()

                # Phone Detected
                if "Cell Phone Detected" in frame_alerts:
                    phone_detected_frames += 1
                    if "phone" not in violation_snapshots:
                        violation_snapshots["phone"] = frame.copy()

                # Looking Away
                if any("Looking Away" in a or "Turning Head" in a for a in frame_alerts):
                    looking_away_frames += 1
                    if "looking_away" not in violation_snapshots:
                        violation_snapshots["looking_away"] = frame.copy()

                # Lip Aspect Ratio
                if mar > 0:
                    mar_values.append(mar)

                if is_lip_moving:
                    lip_movement_frames += 1
                elif "proxy_speaking" not in violation_snapshots and metrics.get("mouth") == "Closed":
                    violation_snapshots["proxy_speaking"] = frame.copy()

                for a in frame_alerts:
                    if a != "Voice Detected Without Lip Movement":
                        alerts.add(a)

            frame_idx += 1

        cap.release()

        avg_mar = float(np.mean(mar_values)) if mar_values else 0.0
        lip_movement_ratio = (
            float(lip_movement_frames / total_frames_sampled)
            if total_frames_sampled > 0
            else 0.0
        )
        face_detected_ratio = (
            float(face_detected_frames / total_frames_sampled)
            if total_frames_sampled > 0
            else 0.0
        )
        looking_away_ratio = (
            float(looking_away_frames / total_frames_sampled)
            if total_frames_sampled > 0
            else 0.0
        )

        # Flag Evaluation
        is_proxy_speaking = total_frames_sampled >= 4 and lip_movement_ratio < 0.15
        no_face_detected = total_frames_sampled >= 4 and face_detected_ratio < 0.40
        multiple_people_detected = multiple_people_frames >= 2
        phone_detected = phone_detected_frames >= 2
        looking_away_detected = total_frames_sampled >= 4 and looking_away_ratio > 0.60

        violations = []
        if is_proxy_speaking:
            violations.append("Voice Detected Without Lip Movement in Answer Recording")
            alerts.add("Voice Detected Without Lip Movement in Answer Recording")
        if no_face_detected:
            violations.append("Candidate Face Missing / Not Detected in Answer Video")
            alerts.add("No Face Detected in Answer Video")
        if multiple_people_detected:
            violations.append("Multiple People Detected in Answer Video")
            alerts.add("Multiple People Detected in Answer Video")
        if phone_detected:
            violations.append("Cell Phone Detected in Answer Video")
            alerts.add("Cell Phone Detected in Answer Video")
        if looking_away_detected:
            violations.append("Looking Away from Camera Sustained During Answer")
            alerts.add("Looking Away Sustained")

        return {
            "success": True,
            "total_frames_sampled": total_frames_sampled,
            "lip_movement_frames": lip_movement_frames,
            "lip_movement_ratio": round(lip_movement_ratio, 3),
            "face_detected_ratio": round(face_detected_ratio, 3),
            "average_mar": round(avg_mar, 3),
            "is_proxy_speaking": is_proxy_speaking,
            "no_face_detected": no_face_detected,
            "multiple_people_detected": multiple_people_detected,
            "phone_detected": phone_detected,
            "looking_away_detected": looking_away_detected,
            "alerts": list(alerts),
            "violations": violations,
            "violation_snapshots": violation_snapshots,
            "violation_snapshot": violation_snapshots.get("proxy_speaking") if is_proxy_speaking else (
                list(violation_snapshots.values())[0] if violation_snapshots else None
            ),
        }



def suppress_tf_warnings():
    stderr_fd = sys.stderr.fileno()
    old_stderr = os.dup(stderr_fd)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, stderr_fd)
    os.close(devnull)
    return old_stderr, stderr_fd


def restore_stderr(old_stderr, stderr_fd):
    os.dup2(old_stderr, stderr_fd)
    os.close(old_stderr)
