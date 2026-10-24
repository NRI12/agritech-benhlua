"""Cấu hình trung tâm cho backend Agritech chạy trên Raspberry Pi 4.

Sửa các giá trị ở đây để đổi camera, ngưỡng, chu kỳ inference... mà không
phải đụng vào code logic.
"""
import os

# ── Đường dẫn ──────────────────────────────────────────────────────────────
# Thư mục gốc dự án (cha của server/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Model ONNX đã export (nhẹ, chạy bằng onnxruntime trên Pi)
MODEL_PATH = os.path.join(BASE_DIR, "paddy_classify", "weights", "best.onnx")

# Thư mục dashboard tĩnh (HTML/CSS/JS)
DASHBOARD_DIR = os.path.join(BASE_DIR, "templates", "agritech")

# ── Camera ─────────────────────────────────────────────────────────────────
# "usb"   : webcam Hikvision USB qua OpenCV (cv2.VideoCapture)
# "picam" : camera Pi v2 (CSI) qua picamera2
# "auto"  : thử picam trước, không có thì rớt sang usb
CAMERA_SOURCE = os.environ.get("CAMERA_SOURCE", "auto")

USB_CAMERA_INDEX = int(os.environ.get("USB_CAMERA_INDEX", "0"))
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
JPEG_QUALITY = 70          # chất lượng JPEG cho MJPEG stream (1-100)

# ── Inference ──────────────────────────────────────────────────────────────
IMG_SIZE = 224             # khớp imgsz lúc train
CONF_THRESHOLD = 0.40      # dưới ngưỡng này coi như "không chắc chắn"

# Bộ lọc "không phải ảnh lúa" (model chỉ có 10 lớp nên ảnh lạ vẫn bị gán nhầm thành bệnh).
# Ảnh bị loại nếu vi phạm BẤT KỲ điều kiện nào. Đo trên 400 ảnh lúa: loại nhầm 0.
RICE_MIN_VEGETATION = 0.20   # tỷ lệ điểm ảnh màu thực vật (xanh/vàng) tối thiểu
RICE_VEG_MIN_SAT = 60        # độ bão hoà tối thiểu để tính là "thực vật" (webcam ám xanh có bão hoà thấp)
RICE_MAX_ENTROPY = 0.35      # entropy chuẩn hoá của phân phối xác suất (0..1) tối đa
RICE_MIN_CONF = 0.50         # độ tin cậy lớp cao nhất tối thiểu
NOT_RICE = "not_rice"
NOT_RICE_MESSAGE = "Đây không phải hình ảnh lúa"

# ── Tên lớp (thứ tự khớp metadata model: alphabet theo tên thư mục) ─────────
CLASS_NAMES = [
    "bacterial_leaf_blight",
    "bacterial_leaf_streak",
    "bacterial_panicle_blight",
    "blast",
    "brown_spot",
    "dead_heart",
    "downy_mildew",
    "hispa",
    "normal",
    "tungro",
]

# Map sang tên tiếng Việt + mức độ nghiêm trọng mặc định (hiển thị dashboard)
CLASS_INFO = {
    "not_rice":                 {"vi": "Đây không phải hình ảnh lúa", "severity": "—"},
    "bacterial_leaf_blight":    {"vi": "Bạc lá vi khuẩn",        "severity": "Nặng"},
    "bacterial_leaf_streak":    {"vi": "Sọc lá vi khuẩn",        "severity": "Trung bình"},
    "bacterial_panicle_blight": {"vi": "Thối bông vi khuẩn",     "severity": "Nặng"},
    "blast":                    {"vi": "Đạo ôn lá",              "severity": "Trung bình"},
    "brown_spot":               {"vi": "Đốm nâu",                "severity": "Trung bình"},
    "dead_heart":               {"vi": "Sâu đục thân (nõn héo)", "severity": "Nặng"},
    "downy_mildew":             {"vi": "Sương mai",              "severity": "Trung bình"},
    "hispa":                    {"vi": "Bọ trĩ Hispa",           "severity": "Nhẹ"},
    "normal":                   {"vi": "Bình thường",            "severity": "Không"},
    "tungro":                   {"vi": "Bệnh vàng lùn (Tungro)", "severity": "Nặng"},
}

# ── Server ─────────────────────────────────────────────────────────────────
HOST = "0.0.0.0"           # lắng nghe mọi interface (để máy khác trong LAN xem được)
PORT = int(os.environ.get("PORT", "5000"))

# ── ChatGPT ────────────────────────────────────────────────────────────────
# API key đặt qua web (lưu ở DATA_DIR/openai_api_key) hoặc biến OPENAI_API_KEY.
DATA_DIR = os.path.join(BASE_DIR, "data")
OPENAI_MODEL = "gpt-4o-mini"   # đổi bằng biến môi trường OPENAI_MODEL
# Token bảo vệ API đổi key. Để trống: chỉ cho đổi từ mạng LAN (không qua tunnel).
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")

AI_DISCLAIMER = ("Lưu ý: Kết quả AI chỉ mang tính tham khảo, "
                 "không thay thế đánh giá thực tế từ chuyên gia.")

# ── Kiểm soát độ tin cậy câu trả lời AI ──────────────────────────────────────
# Hoạt chất thường gặp: dùng để phát hiện AI nêu thuốc NGOÀI dữ liệu tham khảo.
KNOWN_ACTIVES = [
    "tricyclazole", "isoprothiolane", "hexaconazole", "mancozeb", "propiconazole", "carbendazim",
    "kasugamycin", "copper", "oxolinic", "cartap", "chlorantraniliprole", "metalaxyl", "chlorpyrifos",
    "quinalphos", "imidacloprid", "buprofezin", "azoxystrobin", "thiamethoxam", "fipronil",
    "abamectin", "validamycin", "difenoconazole", "tebuconazole", "trifloxystrobin", "pymetrozine",
    "dinotefuran", "ddt", "monocrotophos", "methamidophos", "endosulfan", "paraquat",
]
# Hoạt chất có thể đã bị cấm/hạn chế tại Việt Nam -> luôn kèm cảnh báo, AI không được gợi ý.
# CẦN CHUYÊN GIA XÁC MINH và cập nhật theo Thông tư/danh mục thuốc BVTV hiện hành.
RESTRICTED_ACTIVES = ["ddt", "monocrotophos", "methamidophos", "endosulfan", "paraquat",
                      "chlorpyrifos", "fipronil"]
