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

    def analyze_frame(self, image_array):
        models = self._get_models()
        alerts = []
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

        metrics = {"gaze": "Center", "head": "Forward", "emotion": "Neutral"}

        landmarks_list, face_present_unrefined = self._detect_face_landmarks(
            models, image_array
        )

        if landmarks_list is None:
            if face_present_unrefined:
                return {
                    "alerts": alerts,
                    "metrics": {"gaze": "N/A", "head": "N/A", "emotion": "N/A"},
                }
            alerts.append("No Face Detected")
            return {
                "alerts": alerts,
                "metrics": {"gaze": "N/A", "head": "N/A", "emotion": "N/A"},
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

        return {"alerts": alerts, "metrics": metrics}


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
