"""Lớp trừu tượng nguồn camera + luồng chụp nền.

Hỗ trợ:
  - Webcam Hikvision USB (OpenCV / V4L2)  -> UsbCvSource
  - Camera Pi v2 (CSI) qua picamera2      -> PiCamera2Source

CaptureThread đọc frame liên tục trong nền, giữ "frame mới nhất" để vừa
phục vụ MJPEG stream (đọc liên tục) vừa cho InferenceWorker lấy mẫu định kỳ
mà không tranh chấp thiết bị camera.
"""
import threading
import time

import cv2
import numpy as np

import config


class FrameSource:
    """Giao diện chung: read() -> (ok, frame_bgr)."""

    def read(self):
        raise NotImplementedError

    def release(self):
        pass


class UsbCvSource(FrameSource):
    """Webcam USB qua OpenCV. Phù hợp Hikvision USB 2.0."""

    def __init__(self, index=config.USB_CAMERA_INDEX):
        self.cap = cv2.VideoCapture(index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.FRAME_HEIGHT)
        if not self.cap.isOpened():
            raise RuntimeError(f"Không mở được webcam USB index={index}")

    def read(self):
        return self.cap.read()

    def release(self):
        self.cap.release()


class PiCamera2Source(FrameSource):
    """Camera Pi v2 (CSI) qua picamera2. Chỉ chạy được trên Raspberry Pi OS."""

    def __init__(self):
        from picamera2 import Picamera2  # import trễ: máy dev không có lib này

        self.picam = Picamera2()
        cfg = self.picam.create_preview_configuration(
            main={"format": "RGB888", "size": (config.FRAME_WIDTH, config.FRAME_HEIGHT)}
        )
        self.picam.configure(cfg)
        self.picam.start()
        time.sleep(0.5)  # chờ cảm biến ổn định

    def read(self):
        frame = self.picam.capture_array()  # RGB
        # Đồng bộ với OpenCV (BGR) để toàn pipeline thống nhất
        return True, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    def release(self):
        self.picam.stop()


def _has_csi_camera():
    """True nếu có camera CSI thật. libcamera cũng liệt kê webcam USB (Id chứa 'usb') nên phải loại ra."""
    from picamera2 import Picamera2  # import trễ: máy dev không có lib này

    return any("usb" not in str(c.get("Id", "")).lower() for c in Picamera2.global_camera_info())


def create_source(kind=config.CAMERA_SOURCE):
    """Tạo nguồn camera theo cấu hình. 'auto' = thử picam trước rồi tới usb."""
    if kind == "usb":
        return UsbCvSource()
    if kind == "picam":
        return PiCamera2Source()
    if kind == "auto":
        try:
            if not _has_csi_camera():
                raise RuntimeError("không có camera CSI (chỉ có webcam USB)")
            return PiCamera2Source()
        except Exception as e:
            print(f"[camera] bỏ qua picamera2 ({e}); dùng webcam USB.")
            return UsbCvSource()
    raise ValueError(f"CAMERA_SOURCE không hợp lệ: {kind}")


class CaptureThread:
    """Đọc frame nền, giữ frame mới nhất (thread-safe)."""

    def __init__(self, source=None):
        self.source = source or create_source()
        self._lock = threading.Lock()
        self._frame = None
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self

    def _loop(self):
        while self._running:
            ok, frame = self.source.read()
            if ok and frame is not None:
                with self._lock:
                    self._frame = frame
            else:
                time.sleep(0.05)

    def get_frame(self):
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def get_jpeg(self, quality=config.JPEG_QUALITY):
        """Trả bytes JPEG của frame mới nhất (None nếu chưa có frame)."""
        frame = self.get_frame()
        if frame is None:
            return None
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return buf.tobytes() if ok else None

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        self.source.release()


def placeholder_jpeg(text="Cho camera...", quality=config.JPEG_QUALITY):
    """Ảnh JPEG dự phòng khi chưa có frame (hiển thị trên dashboard)."""
    img = np.zeros((config.FRAME_HEIGHT, config.FRAME_WIDTH, 3), dtype=np.uint8)
    img[:] = (40, 30, 20)
    cv2.putText(img, text, (40, config.FRAME_HEIGHT // 2),
                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (200, 200, 200), 2)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes()
