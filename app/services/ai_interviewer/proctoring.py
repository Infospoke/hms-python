import cv2
import mediapipe as mp
import numpy as np
import math
import logging
import os
import sys
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
        old_stderr, stderr_fd = suppress_tf_warnings()
        try:
            self.mp_face_mesh = mp.solutions.face_mesh
            self.face_mesh = self.mp_face_mesh.FaceMesh(
                max_num_faces=1,
                refine_landmarks=True,
                min_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self.mp_face_detection = mp.solutions.face_detection
            self.face_detection = self.mp_face_detection.FaceDetection(
                min_detection_confidence=0.5
            )
        finally:
            restore_stderr(old_stderr, stderr_fd)
        self.THRESH_LOOK_RIGHT = 0.4
        self.THRESH_LOOK_LEFT = 0.66
        self.THRESH_HEAD_DOWN = 1.65
        self.THRESH_HEAD_UP = 0.83
        self.THRESH_HEAD_RIGHT = 0.55
        self.THRESH_HEAD_LEFT = 2.5
        logger.info("Loading YOLOv8 model for object detection...")
        old_stderr, stderr_fd = suppress_tf_warnings()
        try:
            self.yolo = YOLO("yolov8n.pt")
        finally:
            restore_stderr(old_stderr, stderr_fd)
        self.COCO_PHONE_CLASS_ID = 67
        ProctoringEngine._initialized = True
        logger.info("ProctoringEngine initialized successfully")

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

    def analyze_frame(self, image_array):
        alerts = []
        results = self.yolo(image_array, verbose=False, stream=True)
        phone_detected = False
        person_count = 0
        for r in results:
            boxes = r.boxes
            for box in boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                if cls_id == self.COCO_PHONE_CLASS_ID and conf > 0.5:
                    phone_detected = True
        if phone_detected:
            alerts.append("Cell Phone Detected")
        if person_count > 1:
            alerts.append("Multiple People Detected")
        rgb = cv2.cvtColor(image_array, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb)
        metrics = {"gaze": "Center", "head": "Forward", "emotion": "Neutral"}
        if not results.multi_face_landmarks:
            return {
                "alerts": ["No Face Detected"],
                "metrics": {"gaze": "N/A", "head": "N/A", "emotion": "N/A"},
            }
        lm = results.multi_face_landmarks[0].landmark
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
