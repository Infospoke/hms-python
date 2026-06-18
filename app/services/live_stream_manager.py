import logging
from typing import Dict, List
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class LiveStreamManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LiveStreamManager, cls).__new__(cls)
            # Maps session_id -> list of active websockets (candidate + recruiters)
            cls._instance.active_connections = {}
            cls._instance.proctoring_states = {}
            cls._instance.last_frame_times = {}
        return cls._instance

    def get_proctoring_state(self, session_id: str) -> dict:
        if session_id not in self.proctoring_states:
            self.proctoring_states[session_id] = {
                "is_processing": False,
                "last_detection_time": 0.0
            }
        return self.proctoring_states[session_id]

    def update_last_frame_time(self, session_id: str):
        import time
        self.last_frame_times[session_id] = time.time()

    def get_active_sessions(self) -> List[str]:
        import time
        current_time = time.time()
        active = []
        for session_id, last_time in list(self.last_frame_times.items()):
            if current_time - last_time < 10.0:
                active.append(session_id)
        return active

    async def connect(self, session_id: str, websocket: WebSocket):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        logger.info(f"WebSocket connected for session: {session_id}. Active connections: {len(self.active_connections[session_id])}")

    def disconnect(self, session_id: str, websocket: WebSocket):
        if session_id in self.active_connections:
            if websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
                if session_id in self.last_frame_times:
                    del self.last_frame_times[session_id]
                logger.info(f"WebSocket disconnected for session: {session_id}. No active connections left.")
            else:
                logger.info(f"WebSocket disconnected for session: {session_id}. Active connections remaining: {len(self.active_connections[session_id])}")

    async def broadcast_frame(self, session_id: str, frame_data: str, sender: WebSocket):
        """Sends the frame data to other listeners of this session (e.g. recruiters)"""
        if session_id in self.active_connections:
            for connection in self.active_connections[session_id]:
                if connection != sender:
                    try:
                        await connection.send_text(frame_data)
                    except Exception as e:
                        logger.error(f"Error sending frame in session {session_id}: {e}")

# Global instance to be imported elsewhere
stream_manager = LiveStreamManager()
