# Agritech — Backend (Flask)

Chạy trên Raspberry Pi 4: nhận ảnh (chụp từ camera hoặc tải lên) → model ONNX → kết quả + Grad-CAM,
phục vụ dashboard `../templates/agritech`. **Cài đặt và vận hành: xem [../../DEPLOY.md](../../DEPLOY.md)**
(`./install.sh`, `./install.sh --check`, service `agritech`).

## Chạy tay (dev)

```bash
pip install -r requirements.txt        # picamera2 cài bằng apt, không qua pip
python app.py                          # http://localhost:5000
python inference.py ../sample_images/blast/*.jpg   # thử model không cần camera
```

## API

| Route | Chức năng |
|---|---|
| `GET /video_feed` | MJPEG xem trước camera (chỉ để ngắm khung hình) |
| `POST /api/capture` | Chụp 1 khung từ camera rồi phân tích |
| `POST /api/predict/image` | Phân tích ảnh tải lên (multipart `image`, ≤ 10 MB) |
| `GET /api/treatment/<lớp>` | Biện pháp xử lý theo bệnh |
| `POST /api/chat` | Chat (`message`, `history`, `context`); ChatGPT, rớt về rule-based nếu không có key/lỗi |
| `GET/POST/DELETE /api/settings/api-key` | Xem / đặt / xoá API key (chỉ từ LAN, hoặc kèm `X-Admin-Token`) |
| `GET /api/sensors` | Dinh dưỡng đất (giả lập); nhiệt-ẩm `available=false` khi chưa cắm |
| `GET /api/history`, `/api/alerts` | Lịch sử nhận diện, cảnh báo bệnh Nặng/Trung bình |
| `GET /api/device`, `/api/system`, `/api/health` | Trạng thái Pi, nhiệt độ/RAM, kiểm tra sống |

Phản hồi phân tích: `class`, `class_vi`, `confidence`, `severity`, `top3`, `is_rice`, `gradcam` (data URI).

## Module

```
app.py        routes + _analyze()          llm.py       gọi ChatGPT, đọc key mỗi lần (không cache), audit hoạt chất
camera.py     Pi Cam / USB + CaptureThread  chatbot.py   dữ liệu TREATMENT + tư vấn rule-based dự phòng
inference.py  ONNX, lọc "không phải lúa",   sensors.py   dinh dưỡng đất giả lập; nhiệt-ẩm chờ thiết bị thật
              Grad-CAM                      history.py   lịch sử JSONL
config.py     toàn bộ tham số
```

## Cấu hình (biến môi trường, đặt trong `agritech.env`)

| Biến | Ý nghĩa |
|---|---|
| `CAMERA_SOURCE` `auto`/`picam`/`usb`, `USB_CAMERA_INDEX` | chọn camera |
| `PORT` | cổng web (mặc định 5000) |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | key (file `data/openai_api_key` đặt qua web được ưu tiên) / model (mặc định `gpt-4o-mini`) |
| `ADMIN_TOKEN` | mã bảo vệ đổi key khi truy cập từ xa qua tunnel |
| `SENSORS_MOCK=1` | sinh số giả cho nhiệt-ẩm (chỉ để xem giao diện) |

Ngưỡng lọc ảnh không phải lúa (`RICE_*`), ngưỡng tin cậy, danh sách hoạt chất cần cảnh báo (`RESTRICTED_ACTIVES`): `config.py`.

## Cảm biến thật

`sensors.py` chờ thay bằng code đọc NPK (RS485/Modbus) và nhiệt-ẩm (DHT22/SHT3x). Dashboard và API giữ nguyên.
`./install.sh --check` báo các cổng I/O tương ứng đã sẵn sàng chưa.
