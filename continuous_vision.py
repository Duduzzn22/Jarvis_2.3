"""
J.A.R.V.I.S. — CONTINUOUS VISION SYSTEM v1.0
Iron Man armor vision pipeline:

  Layer 1 — OpenCV + MediaPipe (local, <5ms)
    • Face detection + landmark tracking
    • Pose estimation
    • Hand gesture recognition
    • Motion tracking (optical flow)
    • Background subtraction

  Layer 2 — YOLO (local, ~30ms)
    • Object detection with bounding boxes
    • Scene classification

  Layer 3 — OCR (local, ~50ms)
    • Text reading from camera frames

  Layer 4 — AI Vision (cloud/Groq, async)
    • Scene understanding
    • Emotion estimation
    • Environment description
    • Memory integration

Architecture: background thread producer → frame queue → async consumer
              → WebSocket → frontend HUD (60fps render)
"""

import cv2
import base64
import json
import time
import threading
import queue
import datetime
import numpy as np
from pathlib import Path
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Optional
import logging

log = logging.getLogger('jarvis.vision')

# ─── Optional heavy imports — graceful degradation ──────────────────────────
try:
    import mediapipe as mp
    MP_AVAILABLE = True
    log.info('[VISION] MediaPipe disponível')
except ImportError:
    MP_AVAILABLE = False
    log.warning('[VISION] MediaPipe não instalado — pip install mediapipe')

try:
    from ultralytics import YOLO as _YOLO
    YOLO_AVAILABLE = True
    log.info('[VISION] Ultralytics YOLO disponível')
except ImportError:
    YOLO_AVAILABLE = False
    log.warning('[VISION] YOLO não instalado — pip install ultralytics')

try:
    import pytesseract
    OCR_AVAILABLE = True
    log.info('[VISION] Tesseract OCR disponível')
except ImportError:
    OCR_AVAILABLE = False
    log.warning('[VISION] Tesseract não instalado — pip install pytesseract')

try:
    import requests as _requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


# ─── DATA STRUCTURES ─────────────────────────────────────────────────────────

@dataclass
class Detection:
    """Single detected object/face/text in a frame."""
    id:         str
    type:       str          # face | object | text | gesture | motion | pose
    label:      str
    confidence: float
    x: float; y: float       # normalized [0,1]
    w: float; h: float       # normalized
    color:      str  = '#00e5ff'
    extra:      dict = field(default_factory=dict)


@dataclass
class VisionFrame:
    """Processed frame sent to frontend."""
    timestamp:  float
    jpeg_b64:   str          # compressed frame for HUD preview
    fps:        float
    detections: list         # list of Detection dicts
    scene_desc: str  = ''
    environment:str  = ''
    motion_level: float = 0.0
    alerts:     list = field(default_factory=list)


@dataclass
class FaceMemory:
    """Remembered face entry."""
    face_id:    str
    first_seen: str
    last_seen:  str
    seen_count: int  = 1
    label:      str  = 'Desconhecido'
    notes:      str  = ''


# ─── CONTINUOUS VISION ENGINE ─────────────────────────────────────────────────

class ContinuousVisionEngine:
    """
    Main vision engine. Runs in background thread.
    Produces VisionFrame events via SocketIO.
    """

    # Config
    TARGET_FPS          = 15         # capture rate
    HUD_QUALITY         = 60         # JPEG quality for HUD stream
    HUD_WIDTH           = 640        # HUD feed max width
    AI_ANALYSIS_INTERVAL= 8.0        # seconds between AI cloud calls
    OCR_INTERVAL        = 5.0        # seconds between OCR runs
    MOTION_THRESHOLD    = 0.02       # motion detection sensitivity
    FACE_HISTORY_LEN    = 60         # frames to keep face tracks

    def __init__(self, socketio_emit_fn, groq_client=None, gemini_client=None,
                 gemini_models=None):
        self._emit          = socketio_emit_fn
        self._groq          = groq_client
        self._gemini        = gemini_client
        self._gemini_models = gemini_models or []

        # State
        self._running       = False
        self._paused        = False
        self._cam_index     = 0
        self._cap           = None
        self._thread        = None
        self._ai_thread     = None
        self._lock          = threading.Lock()

        # Metrics
        self._fps_history   = deque(maxlen=30)
        self._frame_count   = 0
        self._last_fps_time = time.time()
        self._current_fps   = 0.0

        # AI analysis
        self._last_ai_time  = 0.0
        self._last_ocr_time = 0.0
        self._ai_queue      = queue.Queue(maxsize=2)  # max 2 pending AI jobs
        self._last_scene    = ''
        self._last_ocr_text = ''

        # Motion tracking
        self._prev_gray     = None
        self._motion_level  = 0.0

        # Memory
        self._face_memory: dict[str, FaceMemory] = {}
        self._env_log: list[str]                  = []

        # MediaPipe modules
        self._mp_face    = None
        self._mp_hands   = None
        self._mp_pose    = None
        self._mp_detect  = None
        self._mp_draw    = None

        # YOLO model
        self._yolo       = None

        # Background subtractor for motion
        self._bg_sub     = cv2.createBackgroundSubtractorMOG2(history=100, varThreshold=25)

        self._init_ml_models()

    # ── Init ML ──────────────────────────────────────────────────────────────

    def _init_ml_models(self):
        """Initialize MediaPipe, YOLO — non-blocking."""
        if MP_AVAILABLE:
            try:
                self._mp_draw    = mp.solutions.drawing_utils
                self._mp_face    = mp.solutions.face_detection.FaceDetection(
                    model_selection=0, min_detection_confidence=0.6)
                self._mp_hands   = mp.solutions.hands.Hands(
                    static_image_mode=False, max_num_hands=2,
                    min_detection_confidence=0.65, min_tracking_confidence=0.5)
                self._mp_pose    = mp.solutions.pose.Pose(
                    static_image_mode=False, min_detection_confidence=0.6,
                    min_tracking_confidence=0.5)
                log.info('[VISION] MediaPipe modules carregados')
            except Exception as e:
                log.warning(f'[VISION] MediaPipe init falhou: {e}')

        if YOLO_AVAILABLE:
            try:
                # yolov8n = nano — mais rápido, bom para tempo real
                self._yolo = _YOLO('yolov8n.pt')
                log.info('[VISION] YOLO yolov8n carregado')
            except Exception as e:
                log.warning(f'[VISION] YOLO init falhou: {e}')

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self, camera_index: int = 0) -> bool:
        """Start the vision engine. Returns True if camera opened OK."""
        if self._running:
            return True

        self._cam_index = camera_index
        self._cap = cv2.VideoCapture(camera_index)
        if not self._cap.isOpened():
            log.error(f'[VISION] Câmera {camera_index} não encontrada')
            return False

        # Camera settings for speed
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT,  720)
        self._cap.set(cv2.CAP_PROP_FPS,           30)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE,     1)  # minimize buffer lag

        self._running = True
        self._paused  = False

        self._thread = threading.Thread(target=self._capture_loop, daemon=True, name='vision-capture')
        self._thread.start()

        self._ai_thread = threading.Thread(target=self._ai_analysis_loop, daemon=True, name='vision-ai')
        self._ai_thread.start()

        log.info(f'[VISION] Engine iniciada — câmera {camera_index}')
        self._emit_event('vision_started', {'camera': camera_index})
        return True

    def stop(self):
        """Gracefully stop the engine."""
        self._running = False
        if self._cap:
            self._cap.release()
            self._cap = None
        self._emit_event('vision_stopped', {})
        log.info('[VISION] Engine parada')

    def pause(self):
        self._paused = True
        self._emit_event('vision_paused', {})

    def resume(self):
        self._paused = False
        self._emit_event('vision_resumed', {})

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused

    def get_status(self) -> dict:
        return {
            'running':     self._running,
            'paused':      self._paused,
            'fps':         round(self._current_fps, 1),
            'frame_count': self._frame_count,
            'faces_known': len(self._face_memory),
            'last_scene':  self._last_scene,
            'last_ocr':    self._last_ocr_text[:200],
            'motion':      round(self._motion_level, 3),
            'ml': {
                'mediapipe': MP_AVAILABLE and self._mp_face is not None,
                'yolo':      YOLO_AVAILABLE and self._yolo is not None,
                'ocr':       OCR_AVAILABLE,
            },
        }

    def analyze_frame_once(self, query: str = '') -> dict:
        """Capture one frame and run full AI analysis. For manual command calls."""
        if not self._running or not self._cap:
            return {'error': 'Vision engine não está ativa'}
        ret, frame = self._cap.read()
        if not ret:
            return {'error': 'Não foi possível capturar frame'}
        detections = self._run_local_ml(frame)
        ai_desc    = self._run_ai_analysis(frame, query or 'Descreva a cena completa')
        ocr_text   = self._run_ocr(frame)
        return {
            'scene':      ai_desc,
            'detections': [asdict(d) for d in detections],
            'ocr':        ocr_text,
            'timestamp':  datetime.datetime.now().isoformat(),
        }

    def get_environment_log(self) -> list:
        return self._env_log[-20:]

    # ── Capture Loop (producer thread) ───────────────────────────────────────

    def _capture_loop(self):
        """Main capture loop — runs at TARGET_FPS, does local ML each frame."""
        frame_interval = 1.0 / self.TARGET_FPS
        last_frame_time = 0.0

        while self._running:
            now = time.time()
            elapsed = now - last_frame_time

            if elapsed < frame_interval:
                time.sleep(frame_interval - elapsed)
                continue

            if self._paused:
                time.sleep(0.1)
                continue

            if not self._cap or not self._cap.isOpened():
                time.sleep(0.5)
                continue

            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            last_frame_time = time.time()
            self._frame_count += 1

            # ── FPS calculation ──
            self._fps_history.append(last_frame_time)
            if len(self._fps_history) >= 2:
                span = self._fps_history[-1] - self._fps_history[0]
                self._current_fps = (len(self._fps_history) - 1) / span if span > 0 else 0

            # ── Local ML (fast) ──
            detections = self._run_local_ml(frame)

            # ── Motion detection ──
            self._motion_level = self._detect_motion(frame)
            if self._motion_level > 0.15:
                detections.append(Detection(
                    id='motion', type='motion', label=f'MOVIMENTO {self._motion_level:.0%}',
                    confidence=self._motion_level, x=0, y=0, w=1, h=1,
                    color='#ff8c00'
                ))

            # ── Queue frame for AI (if interval elapsed) ──
            ai_due  = (now - self._last_ai_time)  >= self.AI_ANALYSIS_INTERVAL
            ocr_due = (now - self._last_ocr_time) >= self.OCR_INTERVAL
            if (ai_due or ocr_due) and not self._ai_queue.full():
                try:
                    self._ai_queue.put_nowait({
                        'frame':    frame.copy(),
                        'ai_due':   ai_due,
                        'ocr_due':  ocr_due,
                    })
                    if ai_due:  self._last_ai_time  = now
                    if ocr_due: self._last_ocr_time = now
                except queue.Full:
                    pass

            # ── Encode HUD frame ──
            hud_b64 = self._encode_hud_frame(frame, detections)

            # ── Emit to frontend ──
            vision_frame = VisionFrame(
                timestamp   = now,
                jpeg_b64    = hud_b64,
                fps         = round(self._current_fps, 1),
                detections  = [asdict(d) for d in detections],
                scene_desc  = self._last_scene,
                environment = self._env_log[-1] if self._env_log else '',
                motion_level= round(self._motion_level, 3),
            )
            self._emit_event('vision_frame', asdict(vision_frame))

    # ── AI Analysis Loop (consumer thread) ───────────────────────────────────

    def _ai_analysis_loop(self):
        """Runs AI analysis on queued frames — separate thread to not block capture."""
        while self._running:
            try:
                job = self._ai_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            frame   = job['frame']
            ai_due  = job['ai_due']
            ocr_due = job['ocr_due']

            if ai_due:
                query = 'Descreva a cena: pessoas, objetos, ambiente. Seja conciso (2 frases).'
                desc  = self._run_ai_analysis(frame, query)
                if desc:
                    self._last_scene = desc
                    ts = datetime.datetime.now().strftime('%H:%M:%S')
                    entry = f'[{ts}] {desc}'
                    self._env_log.append(entry)
                    if len(self._env_log) > 100:
                        self._env_log.pop(0)
                    self._emit_event('vision_scene', {'description': desc, 'timestamp': ts})

            if ocr_due and OCR_AVAILABLE:
                text = self._run_ocr(frame)
                if text and text != self._last_ocr_text:
                    self._last_ocr_text = text
                    self._emit_event('vision_ocr', {'text': text})

    # ── Local ML Pipeline ─────────────────────────────────────────────────────

    def _run_local_ml(self, frame: np.ndarray) -> list:
        """Run all fast local ML. Returns list of Detection."""
        detections = []
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = frame.shape[:2]

        # 1. MediaPipe face detection
        if self._mp_face:
            try:
                results = self._mp_face.process(rgb)
                if results.detections:
                    for i, det in enumerate(results.detections):
                        bb   = det.location_data.relative_bounding_box
                        conf = det.score[0] if det.score else 0.5
                        face_id = f'face_{i}'
                        self._update_face_memory(face_id)
                        mem = self._face_memory.get(face_id)
                        label = mem.label if mem else 'FACE'
                        detections.append(Detection(
                            id=face_id, type='face', label=label,
                            confidence=conf,
                            x=bb.xmin, y=bb.ymin, w=bb.width, h=bb.height,
                            color='#00e5ff',
                            extra={'seen': mem.seen_count if mem else 1}
                        ))
            except Exception as e:
                log.debug(f'Face detection: {e}')

        # 2. MediaPipe hands / gesture
        if self._mp_hands:
            try:
                results = self._mp_hands.process(rgb)
                if results.multi_hand_landmarks:
                    for i, hlm in enumerate(results.multi_hand_landmarks):
                        gesture = self._classify_gesture(hlm)
                        # Bounding box from landmarks
                        xs = [lm.x for lm in hlm.landmark]
                        ys = [lm.y for lm in hlm.landmark]
                        xmin, xmax = min(xs), max(xs)
                        ymin, ymax = min(ys), max(ys)
                        detections.append(Detection(
                            id=f'hand_{i}', type='gesture', label=gesture,
                            confidence=0.85,
                            x=xmin, y=ymin, w=xmax-xmin, h=ymax-ymin,
                            color='#00ff88'
                        ))
            except Exception as e:
                log.debug(f'Hands: {e}')

        # 3. YOLO object detection
        if self._yolo:
            try:
                small = cv2.resize(frame, (320, 320))  # faster inference
                results = self._yolo(small, conf=0.45, verbose=False)
                sx, sy = w / 320, h / 320  # scale back
                for r in results:
                    for box in r.boxes:
                        cls_name = r.names[int(box.cls[0])]
                        conf     = float(box.conf[0])
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        detections.append(Detection(
                            id=f'obj_{cls_name}_{int(x1)}',
                            type='object', label=cls_name.upper(),
                            confidence=conf,
                            x=(x1 * sx) / w, y=(y1 * sy) / h,
                            w=(x2 - x1) * sx / w, h=(y2 - y1) * sy / h,
                            color='#ff8c00'
                        ))
            except Exception as e:
                log.debug(f'YOLO: {e}')

        return detections

    def _classify_gesture(self, hand_landmarks) -> str:
        """Simple rule-based gesture classifier from MediaPipe landmarks."""
        try:
            lm = hand_landmarks.landmark
            # Fingertips: 4=thumb, 8=index, 12=middle, 16=ring, 20=pinky
            # MCP bases: 2, 5, 9, 13, 17
            fingers = []
            # Thumb — horizontal comparison
            fingers.append(1 if lm[4].x < lm[3].x else 0)
            # Other 4 fingers — vertical tip vs pip
            for tip, pip in [(8,6), (12,10), (16,14), (20,18)]:
                fingers.append(1 if lm[tip].y < lm[pip].y else 0)

            total = sum(fingers)
            if total == 0:  return 'PUNHO'
            if total == 5:  return 'MAO ABERTA'
            if fingers == [0,1,0,0,0]: return 'APONTAR'
            if fingers == [0,1,1,0,0]: return 'PEACE'
            if fingers == [1,0,0,0,1]: return 'ROCK'
            if fingers == [1,1,1,1,1]: return 'STOP'
            if total == 1 and fingers[0]: return 'JOINHA'
            return f'GESTO ({total} dedos)'
        except Exception:
            return 'GESTO'

    # ── Motion Detection ──────────────────────────────────────────────────────

    def _detect_motion(self, frame: np.ndarray) -> float:
        """Returns motion level [0,1] using background subtraction."""
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)
            mask = self._bg_sub.apply(gray)
            motion = np.count_nonzero(mask) / mask.size
            return float(np.clip(motion, 0, 1))
        except Exception:
            return 0.0

    # ── OCR ───────────────────────────────────────────────────────────────────

    def _run_ocr(self, frame: np.ndarray) -> str:
        """Extract text from frame using Tesseract."""
        if not OCR_AVAILABLE:
            return ''
        try:
            gray    = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray    = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
            text    = pytesseract.image_to_string(gray, config='--psm 6')
            cleaned = ' '.join(text.split())
            return cleaned[:500] if len(cleaned) > 10 else ''
        except Exception as e:
            log.debug(f'OCR: {e}')
            return ''

    # ── AI Cloud Analysis ─────────────────────────────────────────────────────

    def _run_ai_analysis(self, frame: np.ndarray, query: str) -> str:
        """Send frame to Groq/Gemini vision for scene understanding."""
        try:
            # Encode frame as JPEG
            _, buf  = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            img_b64 = base64.b64encode(buf).decode('utf-8')

            # Try Groq vision first (faster)
            if self._groq:
                try:
                    resp = self._groq.chat.completions.create(
                        model='meta-llama/llama-4-scout-17b-16e-instruct',
                        messages=[{
                            'role': 'user',
                            'content': [
                                {'type': 'text',      'text': query},
                                {'type': 'image_url', 'image_url': {'url': f'data:image/jpeg;base64,{img_b64}'}},
                            ],
                        }],
                        max_tokens=120, temperature=0.1, timeout=8,
                    )
                    return resp.choices[0].message.content.strip()
                except Exception as e:
                    log.debug(f'Groq vision: {e}')

            # Gemini fallback
            if self._gemini and self._gemini_models:
                for model in self._gemini_models[:2]:
                    try:
                        response = self._gemini.models.generate_content(
                            model=model,
                            contents=[{
                                'role': 'user',
                                'parts': [
                                    {'text': query},
                                    {'inline_data': {'mime_type': 'image/jpeg', 'data': img_b64}},
                                ],
                            }]
                        )
                        return response.text.strip()
                    except Exception:
                        continue
        except Exception as e:
            log.debug(f'AI analysis: {e}')
        return ''

    # ── Face Memory ───────────────────────────────────────────────────────────

    def _update_face_memory(self, face_id: str):
        now = datetime.datetime.now().isoformat()
        if face_id not in self._face_memory:
            self._face_memory[face_id] = FaceMemory(
                face_id=face_id, first_seen=now, last_seen=now
            )
        else:
            self._face_memory[face_id].last_seen  = now
            self._face_memory[face_id].seen_count += 1

    def get_face_memory(self) -> list:
        return [asdict(f) for f in self._face_memory.values()]

    # ── HUD Frame Encoder ─────────────────────────────────────────────────────

    def _encode_hud_frame(self, frame: np.ndarray, detections: list) -> str:
        """
        Encodes frame as JPEG for HUD stream.
        Does NOT draw overlays — overlays are drawn in JS on canvas for 60fps.
        """
        try:
            h, w = frame.shape[:2]
            if w > self.HUD_WIDTH:
                ratio = self.HUD_WIDTH / w
                frame = cv2.resize(frame, (self.HUD_WIDTH, int(h * ratio)))
            _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, self.HUD_QUALITY])
            return base64.b64encode(buf).decode('utf-8')
        except Exception:
            return ''

    # ── Utils ─────────────────────────────────────────────────────────────────

    def _emit_event(self, event: str, data: dict):
        """Thread-safe emit to all connected clients."""
        try:
            self._emit(event, data)
        except Exception as e:
            log.debug(f'Emit {event}: {e}')


# ─── SINGLETON ────────────────────────────────────────────────────────────────

_engine: Optional[ContinuousVisionEngine] = None


def get_engine() -> Optional[ContinuousVisionEngine]:
    return _engine


def init_vision_engine(emit_fn, groq_client=None, gemini_client=None, gemini_models=None):
    """Create singleton engine. Call once at Flask startup."""
    global _engine
    _engine = ContinuousVisionEngine(
        socketio_emit_fn=emit_fn,
        groq_client=groq_client,
        gemini_client=gemini_client,
        gemini_models=gemini_models,
    )
    log.info('[VISION] Engine singleton criado')
    return _engine