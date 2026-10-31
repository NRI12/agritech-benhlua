# Deploy sang Raspberry Pi

## Bê cái gì sang Pi?
**Chỉ cần copy/zip nguyên thư mục [`deploy_pi/`](deploy_pi/) (~36 MB, không kèm `data/`)** — đã đóng gói
sẵn, tự chứa, chạy được ngay. Không cần thứ gì khác.

```
deploy_pi/                         ← BÊ NGUYÊN FOLDER NÀY SANG PI (~36 MB)
├── install.sh                     ALL-IN-ONE: cài + kiểm tra + 4G + khởi động server
├── probe_ads1115.py               đọc điện áp 4 kênh ADS1115
├── server/                        mã backend (Flask, inference, camera...)
├── templates/agritech/           dashboard (HTML/CSS/JS)
├── paddy_classify/weights/best.onnx + best.cam.npy   model (~21 MB) và trọng số Grad-CAM — không có trong repo, liên hệ tác giả để nhận
└── sample_images/                 120 ảnh mẫu (12 ảnh × 10 loại bệnh) để test/demo
```

## Ảnh mẫu test sẵn (`sample_images/`)
Mỗi loại bệnh có 12 ảnh đa dạng (nhiều giống lúa/độ tuổi). Dùng khi chưa cắm
camera, hoặc để demo nhanh. Chạy thử model trên toàn bộ:
```bash
cd deploy_pi
python server/inference.py sample_images/blast/*.jpg   # test 1 loại
# hoặc không truyền tham số -> tự lấy vài ảnh mỗi loại
```

## Những thứ ở máy này KHÔNG bê sang Pi (chỉ để train/lưu trữ)
| Thư mục | Là gì |
|---------|-------|
| `paddy_images/` | 10.407 ảnh dataset — chỉ để train |
| `result_training/` | Output train gốc: `best.pt`, `results.csv`, biểu đồ... (bản `best.onnx` đã được copy vào `deploy_pi/`) |
| `paddy_analysis_output/` | Báo cáo phân tích dataset |

## Cài tự động trên Pi (khuyến nghị) — một script duy nhất
```bash
# Copy deploy_pi/ sang Pi (scp / git clone / USB), ví dụ ở ~/agritech-benhlua/deploy_pi
cd ~/agritech-benhlua/deploy_pi && chmod +x install.sh
./install.sh                      # cài đủ + kiểm tra phần cứng + bật 4G + khởi động server
./install.sh --apn v-internet     # chỉ định APN SIM 4G (lưu lại cho các lần sau)
./install.sh --camera usb         # ép webcam USB
./install.sh --tunnel             # thêm Cloudflare Tunnel, in URL xem từ xa
./install.sh --restart            # hằng ngày: KHÔNG cài lại, chỉ kiểm tra + bật lại 4G + khởi động lại server
./install.sh --check              # chỉ kiểm tra (không sudo, không đổi gì); thoát mã 2 nếu thiếu camera
./install.sh --uninstall          # gỡ service và kết nối 4G
```
Script chạy lại nhiều lần được. Các bước: cài gói apt (+ `python3-picamera2`, `i2c-tools`) → tạo `.venv`
→ `pip install` → chạy thử model → ghi `agritech.env` → **kiểm tra phần cứng** → **bật & kiểm tra 4G** →
tạo/khởi động lại service `agritech` → kiểm tra `/api/health` → in địa chỉ truy cập và tình trạng 4G.

**Kiểm tra phần cứng** (chỉ đọc):
- **Bắt buộc:** ít nhất 1 camera dùng được — CSI (picamera2/libcamera) hoặc webcam USB (đọc thử 1 khung qua OpenCV, đối chiếu `CAMERA_SOURCE`). Thiếu thì báo `[MISS]` nhưng vẫn cài tiếp; cắm camera rồi `./install.sh --restart`.
- **Cảm biến** (code đọc cảm biến thật chưa viết, `sensors.py` vẫn giả lập): cổng USB-RS485, I2C (nhận diện chip theo địa chỉ, vd `0x48` = ADS1115 → `python3 probe_ads1115.py` để đọc điện áp), GPIO. Các cổng `ttyUSB*` của modem 4G được nhận ra, không bị nhầm là RS485.
- **Bo mạch:** model Pi, OS 64-bit, RAM, dung lượng trống, nguồn điện (`get_throttled` báo sụt áp).

**4G (SIM7600):** script nhận ra 2 kiểu modem và bật đúng cách:
- **RNDIS/ECM** (modem tự tạo giao diện `usb0`/`wwan0`, vd SIM7600 PID `1e0e:9011`): đặt APN bằng lệnh AT (`--apn`), xin IP (DHCP) qua NetworkManager, **không dùng ModemManager**.
- **Không có giao diện mạng sẵn:** cài ModemManager và tạo kết nối `gsm` qua NetworkManager.

Cả hai đều đặt `route-metric 700` nên WiFi/Ethernet vẫn được ưu tiên, 4G là đường dự phòng; không đụng tới kết nối khác.
Sau khi bật, script kiểm chứng ra Internet **bằng đúng giao diện 4G** (`curl --interface`) và báo SIM, nhà mạng, cường độ tín hiệu,
trạng thái đăng ký mạng. Cần Raspberry Pi OS Bookworm (`nmcli`); tắt bằng `--no-4g`.
Nếu không lên mạng: thử `--apn <APN nhà mạng>` (Viettel `v-internet`, Mobifone `m-wap`, Vinaphone `m3-world`).

**Server cũ:** trước khi khởi động lại, script tự dừng mọi server Agritech của thư mục này đang chạy tay hoặc ở port cũ
(chỉ tiến trình python chạy `server/app.py`), rồi chạy lại. Chương trình khác chiếm cổng thì chỉ cảnh báo, không kill.
Các tuỳ chọn `--port`, `--camera`, `--usb-index`, `--apn` được lưu vào `agritech.env` để dùng cho lần sau.
Với `--no-service`, server được chạy nền bằng `nohup` (log: `server.log`).

Sau khi cài:
```bash
systemctl status agritech          # trạng thái
journalctl -u agritech -f          # log realtime
nano ~/agritech-benhlua/deploy_pi/agritech.env && ./install.sh --restart   # đổi camera/port/APN
curl localhost:5000/api/health      # kiểm tra sống
curl localhost:5000/api/system      # nhiệt độ CPU, RAM, load, uptime
journalctl -u agritech-tunnel | grep trycloudflare   # URL tunnel (nếu dùng --tunnel)
```

## Cách dashboard hoạt động
- **Camera chỉ để chụp ảnh**, không suy luận liên tục. Bấm "Chụp & phân tích" hoặc "Chọn ảnh để phân tích" (kéo thả/dán ảnh cũng được).
- Kết quả có **Grad-CAM** (vùng ảnh model chú ý) và nút chuyển sang ảnh gốc. Grad-CAM tính ngay trên ONNX, không cần PyTorch trên Pi — cần `best.onnx` đã được vá bằng `python tools/add_cam_output.py` (train.py tự làm khi export) và file `best.cam.npy` đi kèm.
- **Cảm biến chưa cắm** thì dashboard báo "Thiết bị cảm biến chưa sẵn sàng", không hiện số giả. Muốn xem giao diện với dữ liệu giả lập: `SENSORS_MOCK=1` trong `agritech.env`.
- Mỗi ảnh mới sẽ xoá cuộc trò chuyện cũ; chat dùng kết quả của đúng ảnh đang xem. Có nút "Xoá cuộc trò chuyện".
- Lịch sử/Cảnh báo lưu ở `data/history.jsonl`.

## Chatbot ChatGPT
- Bấm nút chìa khoá cạnh ô chat trên dashboard → dán API key OpenAI (`sk-...`). Key lưu ở
  `data/openai_api_key` (quyền 600) và **áp dụng ngay** cho câu hỏi kế tiếp, không cần restart.
- Key được đọc lại từ đĩa ở mỗi câu hỏi (không cache) và file luôn ưu tiên hơn biến
  `OPENAI_API_KEY` trong `agritech.env` — tránh tình trạng dùng nhầm key cũ.
- Chưa có key hoặc ChatGPT lỗi (hết hạn mức, mất mạng) → tự rớt về tư vấn có sẵn.
- Mọi câu trả lời kết thúc bằng: "Lưu ý: Kết quả AI chỉ mang tính tham khảo, không thay thế đánh giá thực tế từ chuyên gia."
- Đổi key chỉ cho phép từ mạng LAN. Khi dùng tunnel, đặt `ADMIN_TOKEN=...` trong `agritech.env`
  rồi nhập mã đó khi dashboard hỏi. Đổi model: `OPENAI_MODEL=...` (mặc định `gpt-4o-mini`).
- Service tên `agritech`; `install.sh` tự gỡ service `agrismart` cũ và chuyển `agrismart.env` (nếu có).

## Chạy tay (không dùng script)
```bash
cd ~/agritech
python3 -m venv --system-site-packages .venv && source .venv/bin/activate
pip install -r server/requirements.txt
python server/app.py      # mở http://<ip-pi>:5000
```
API và cấu hình: [deploy_pi/server/README.md](deploy_pi/server/README.md).

## Lưu ý
- Thư mục **không dùng git** → xoá là mất. `deploy_pi/` là **bản code duy nhất**; nên giữ zip backup (không kèm `data/` vì chứa API key).
- Muốn sửa code/dashboard: sửa thẳng trong `deploy_pi/server/` hoặc
  `deploy_pi/templates/agritech/` (đó giờ là nơi làm việc chính).

## Cảm biến

- **Nhiệt độ — DS18B20** (1-Wire): DQ → GPIO25 (chân vật lý 22), trở kéo lên 4.7 kΩ giữa DATA và 3.3V. Thêm `dtoverlay=w1-gpio,gpiopin=25` vào `/boot/firmware/config.txt`, reboot. Kiểm tra: `ls /sys/bus/w1/devices/` phải có thư mục `28-…`.
- **Độ ẩm đất — cảm biến điện trở (module LM393)**: chân AO → A0 của ADS1115 (I2C 0x48). Hiệu chuẩn bằng `./install.sh --calib-soil`: làm theo hướng dẫn (để khô ngoài không khí, rồi nhúng hai chân kim loại vào nước), script tự ghi `SOIL_DRY_V`/`SOIL_WET_V` vào `agritech.env` và khởi động lại service. Chưa hiệu chuẩn thì dashboard chỉ báo điện áp thô, không hiển thị %.
- **Độ ẩm không khí**: chưa có cảm biến, dashboard báo chưa sẵn sàng. Dinh dưỡng đất N, P, K, pH vẫn là dữ liệu giả lập.

## WiFi do Pi phát, 4G mặc định, SMS

- **WiFi phát (mạng nội bộ):** `install.sh` tạo kết nối `agritech-ap` (SSID `AGRITECH`, Pi cấp DHCP + NAT ra Internet, IP Pi `10.42.0.1`), tự bật mỗi lần khởi động. Nhập mật khẩu **một lần**: `./install.sh --restart --ap-pass 'MẬT_KHẨU'` — lưu ở `deploy_pi/wifi.conf` (quyền 600, nằm trong `.gitignore`, không vào git). Đổi tên: `--ap-ssid`; bỏ phát: `--no-ap`. Pi dùng card `wlan0` để phát nên **không đồng thời làm client WiFi**; SSH/RustDesk qua WiFi cũ sẽ rớt, vào lại qua mạng AGRITECH (`ssh <user>@10.42.0.1`, web `http://10.42.0.1:5000`).
- **4G làm đường mặc định:** metric 100 (WiFi 600), bỏ DNS do SIM cấp, dùng `1.1.1.1` và `8.8.8.8` (đổi ở biến `FOURG_DNS` đầu `install.sh`).
- **Nối WiFi khác làm client (tuỳ chọn):** `--wifi-ssid TEN --wifi-pass 'MAT_KHAU'` (xung đột với WiFi phát vì cùng `wlan0`).
- **Cảnh báo SMS:** web > Cài đặt > "Cảnh báo SMS": bật, nhập số điện thoại, độ tin cậy tối thiểu, thời gian chờ giữa 2 tin cùng bệnh, tối đa tin/ngày; có nút "Gửi tin thử". Gửi qua modem SIM7600 bằng lệnh AT (cần SIM còn tiền, user trong nhóm `dialout`, ModemManager không giữ cổng AT). Nội dung không dấu, ví dụ: `AGRITECH: Phat hien benh Dao on la tren lua (do tin cay 91.3%, muc do Trung binh). De nghi ra tham dong kiem tra som.`
