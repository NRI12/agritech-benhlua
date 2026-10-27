# Agritech — Nhận diện & tư vấn bệnh lúa trên Raspberry Pi 4

Chụp (hoặc chọn) ảnh lá lúa → model **YOLO11s-cls** (ONNX, chạy bằng CPU) phân loại 10 lớp
(9 bệnh + khoẻ) → dashboard hiện kết quả, **Grad-CAM** (vùng AI chú ý), biện pháp xử lý và
chatbot tư vấn (ChatGPT). Toàn bộ chạy cục bộ trên Pi, không cần GPU.

Dữ liệu huấn luyện: **Paddy Doctor** (10.407 ảnh, NeurIPS 2022). Kết quả: top-1 ≈ 98%, top-5 ≈ 100%
([results.csv](result_training/results.csv)). Phân tích dataset: [paddy_doctor_report.txt](paddy_analysis_output/paddy_doctor_report.txt).

## Cài trên Raspberry Pi (3 lệnh)

```bash
# copy thư mục deploy_pi/ sang Pi (scp/USB), ví dụ ~/agritech
cd ~/agritech && chmod +x install.sh
./install.sh            # ALL-IN-ONE: apt + venv + pip + kiểm tra phần cứng + bật 4G + khởi động server
```

Mở `http://<ip-pi>:5000`. Hằng ngày dùng `./install.sh --restart` (kiểm tra + bật lại 4G + khởi động lại server);
`--check` chỉ kiểm tra, không đổi gì. Chi tiết các tuỳ chọn (`--apn`, `--tunnel`, `--camera`...) xem [DEPLOY.md](DEPLOY.md).

Chạy thử trên máy dev (không cần Pi/camera): `cd deploy_pi && pip install -r server/requirements.txt && python server/app.py`.

## Dashboard làm được gì

- **Chụp & phân tích** từ camera, hoặc **chọn / kéo thả / dán ảnh**. Camera chỉ để chụp, không suy luận liên tục.
- Kết quả: tên bệnh, độ tin cậy, mức độ, top-3, **Grad-CAM** (bấm vào ảnh để phóng to), biện pháp canh tác / sinh học / hoá học.
- Ảnh không phải lúa → báo "Đây không phải hình ảnh lúa" (lọc theo màu thực vật + độ chắc chắn của model).
- **Chat ChatGPT** có câu hỏi gợi ý; hiểu ngữ cảnh ảnh đang xem; đổi API key ngay trên web (hiệu lực tức thì).
  Mọi câu trả lời kèm lưu ý "chỉ mang tính tham khảo". Chưa có key / lỗi → tự dùng tư vấn có sẵn.
- Trang **Cảnh báo, Lịch sử, Thiết bị, Cài đặt**; lịch sử lưu ở `deploy_pi/data/history.jsonl`.
- Cảm biến: dinh dưỡng đất (N-P-K-pH) hiện là **dữ liệu giả lập**; nhiệt độ/độ ẩm báo "chưa sẵn sàng" cho tới khi cắm thiết bị.

## Cấu trúc

```
deploy_pi/                 ★ thư mục duy nhất cần copy sang Pi (~36 MB)
├── install.sh             ALL-IN-ONE: cài + kiểm tra phần cứng + bật/kiểm tra 4G + khởi động server
├── probe_ads1115.py       đọc điện áp 4 kênh ADS1115 (dò cảm biến analog trên I2C 0x48)
├── server/                Flask backend: app, camera, inference (+Grad-CAM), llm (ChatGPT),
│                          chatbot, sensors, history, config  → xem server/README.md
├── templates/agritech/    dashboard (HTML/CSS/JS thuần)
├── paddy_classify/weights/  best.onnx + best.cam.npy (trọng số Grad-CAM)
├── sample_images/         120 ảnh mẫu để thử
└── data/                  (tạo khi chạy) history.jsonl, openai_api_key — đừng chia sẻ

train.py                   chia dữ liệu → train → xuất ONNX → vá Grad-CAM → copy vào deploy_pi/
tools/add_cam_output.py    thêm output đặc trưng cho Grad-CAM vào ONNX (train.py tự gọi)
tests/chat_eval.py         30 case kiểm tra chất lượng chatbot (gọi OpenAI thật)
paddy_images/              dataset gốc, chỉ để train — không copy sang Pi
paddy_analysis_output/     báo cáo + biểu đồ phân tích dataset
result_training/           kết quả huấn luyện gốc (args.yaml, results.csv, ma trận nhầm lẫn, weights)
```

## Huấn luyện lại

```bash
pip install ultralytics onnx
python train.py                              # mặc định 100 epoch, ảnh 224, chia 85/15
python train.py --epochs 30 --batch 16       # chạy thử nhanh
python train.py --skip-export                # chỉ train, không ghi đè best.onnx đang dùng
```

`train.py` tự dò đường dẫn theo vị trí file. Sau khi train, nó ghi đè `deploy_pi/paddy_classify/weights/best.onnx`
(bản gốc ở `result_training/weights/best.onnx`) rồi tự vá thêm Grad-CAM — nhớ copy cả `best.cam.npy` sang Pi.
Muốn nhận diện ảnh "không phải lúa" chắc chắn hơn: thêm thư mục `paddy_images/not_rice/` rồi train lại (thêm 1 lớp).

## Lưu ý

- Thư mục không dùng git: `deploy_pi/` là bản code duy nhất, nên giữ một bản zip backup (không kèm `data/`).
- Dữ liệu xử lý bệnh trong `server/chatbot.py` (`TREATMENT`) **cần chuyên gia BVTV rà lại** theo danh mục thuốc BVTV hiện hành:
  theo tra cứu, Chlorpyrifos ethyl và Carbendazim (đang có trong dữ liệu) đã bị loại/cấm ở Việt Nam — chưa xác minh với danh mục mới nhất.
- Kết quả AI chỉ mang tính tham khảo, không thay thế đánh giá của chuyên gia.
