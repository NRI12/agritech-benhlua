# Sơ đồ Mô hình — Paddy Doctor (Dành cho người mới)

> Xem trong VS Code: mở file → **Ctrl+Shift+V**
> Hoặc paste từng block vào **https://mermaid.live**

---

## Sơ đồ 1 — Đưa gì vào, nhận gì ra?

```mermaid
flowchart LR
    subgraph INPUT["📥 ĐƯA VÀO"]
        A1["🖼️ Ảnh lá lúa\nchụp bằng điện thoại"]
        A2["🌾 Tên giống lúa\nvd: ADT45, Ponni..."]
        A3["📅 Cây đang bao nhiêu ngày tuổi\nvd: 60 ngày, 70 ngày..."]
    end

    subgraph MODEL["🤖 MÁY HỌC\n(đã được dạy từ 10.407 ảnh)"]
        B["Nhìn ảnh → Nhận ra đặc điểm\n→ So sánh với những gì đã học"]
    end

    subgraph OUTPUT["📤 KẾT QUẢ"]
        C1["🏷️ Tên bệnh\nvd: Đạo ôn"]
        C2["📊 Mức độ chắc chắn\nvd: 82% chắc là Đạo ôn"]
    end

    A1 --> MODEL
    A2 -.->|thông tin thêm| MODEL
    A3 -.->|thông tin thêm| MODEL
    MODEL --> C1
    MODEL --> C2

    style INPUT fill:#E3F2FD,stroke:#1565C0
    style MODEL fill:#F3E5F5,stroke:#6A1B9A
    style OUTPUT fill:#E8F5E9,stroke:#2E7D32
```

---

## Sơ đồ 2 — Quá trình dạy máy từ đầu đến cuối

```mermaid
flowchart TD
    RAW["📦 Kho ảnh gốc\n10.407 ảnh lá lúa\nđã được chuyên gia gán nhãn sẵn\n'ảnh này là bệnh Đạo ôn'\n'ảnh này là Bình thường'..."]

    subgraph PREPROCESS["⚙️ CHUẨN BỊ ẢNH"]
        P1["Cắt / chỉnh kích thước ảnh về cùng cỡ"]
        P2["Điều chỉnh màu sắc\ncho máy dễ nhận hơn"]
        P3["Tạo thêm ảnh biến thể\nvd: lật ngược, xoay, tối/sáng hơn\nđể máy học được nhiều tình huống hơn"]
        P1 --> P2 --> P3
    end

    subgraph SPLIT["✂️ CHIA ẢNH THÀNH 3 PHẦN\n(chia đều đủ các loại bệnh ở mỗi phần)"]
        S1["🟦 Phần để DẠY máy\n70% ảnh — ~7.285 ảnh\nMáy được xem và học từ đây"]
        S2["🟨 Phần để KIỂM TRA trong lúc học\n15% ảnh — ~1.561 ảnh\nMáy KHÔNG được học từ đây\nChỉ dùng để xem máy học tới đâu"]
        S3["🟥 Phần để THI CUỐI\n15% ảnh — ~1.561 ảnh\n⚠️ Chỉ dùng đúng 1 lần sau cùng\nĐể biết máy thật sự giỏi cỡ nào"]
    end

    subgraph TRAIN["🏋️ QUÁ TRÌNH DẠY MÁY"]
        T1["Máy nhìn ảnh → tự đoán bệnh"]
        T2["So sánh đoán của máy với đáp án đúng\n→ Tính xem sai bao nhiêu"]
        T3["Điều chỉnh lại cách nhìn của máy\nđể lần sau đoán đúng hơn"]
        T1 --> T2 --> T3 --> T1
    end

    subgraph VALIDATE["📐 XEM MÁY HỌC TỚI ĐÂU"]
        V1["Đoán đúng bao nhiêu % tổng thể?"]
        V2["Với từng bệnh cụ thể\nmáy đoán đúng bao nhiêu?"]
        V3["Máy hay nhầm bệnh nào với bệnh nào?"]
    end

    JUDGE{"Máy đoán\nđủ tốt chưa?"}

    TUNE["🔧 Tinh chỉnh lại cách dạy\nvd: dạy chậm hơn, dạy lâu hơn\nchú ý hơn vào các bệnh ít ảnh"]

    FINAL["🧪 THI CUỐI CÙNG\nDùng phần ảnh đã cất riêng từ đầu\nĐây là điểm thật của mô hình"]

    DEPLOY["🚀 Đưa vào sử dụng thực tế\nNông dân chụp ảnh → máy đoán bệnh"]

    RAW --> PREPROCESS
    PREPROCESS --> SPLIT
    S1 --> TRAIN
    S2 --> VALIDATE
    TRAIN --> VALIDATE
    VALIDATE --> JUDGE
    JUDGE -- "❌ Chưa đủ tốt" --> TUNE
    TUNE --> TRAIN
    JUDGE -- "✅ Đạt yêu cầu" --> FINAL
    S3 --> FINAL
    FINAL --> DEPLOY

    style RAW fill:#FFF9C4,stroke:#F9A825
    style PREPROCESS fill:#E3F2FD,stroke:#1565C0
    style SPLIT fill:#E8EAF6,stroke:#3949AB
    style TRAIN fill:#F3E5F5,stroke:#6A1B9A
    style VALIDATE fill:#E8F5E9,stroke:#2E7D32
    style JUDGE fill:#FFF3E0,stroke:#E65100
    style TUNE fill:#FCE4EC,stroke:#C62828
    style FINAL fill:#E0F2F1,stroke:#00695C
    style DEPLOY fill:#1B5E20,color:#fff,stroke:#1B5E20
```

---

## Sơ đồ 3 — Khi nông dân chụp ảnh mới và hỏi máy

```mermaid
flowchart LR
    subgraph NEW["📱 ẢNH MỚI\nNông dân vừa chụp ngoài đồng"]
        N["🖼️ Ảnh lá lúa\nchưa biết bị bệnh gì"]
    end

    subgraph PREP["⚙️ Chuẩn bị ảnh\n(giống hệt lúc dạy máy)"]
        P["Chỉnh kích thước\nĐiều chỉnh màu sắc"]
    end

    subgraph INFER["🤖 Máy nhìn ảnh\n(dùng kiến thức đã học\nkhông học thêm nữa)"]
        F["Tìm đặc điểm\ntrên lá lúa"]
        C["So sánh với\n10 loại bệnh đã biết"]
        F --> C
    end

    subgraph PROB["📊 Máy tính xác suất cho từng bệnh"]
        PR["Bình thường   →  5%\nĐạo ôn        → 82%  ⬅ cao nhất\nĐốm nâu       →  8%\nBọ xít Hispa  →  3%\n...các bệnh còn lại → nhỏ"]
    end

    subgraph RESULT["✅ KẾT QUẢ TRẢ VỀ"]
        R1["🏷️ Bệnh: ĐẠO ÔN"]
        R2["📈 Chắc chắn: 82%"]
        R3["💊 Gợi ý xử lý:\nPhun thuốc Tricyclazole\nGiảm bón phân đạm"]
    end

    NEW --> PREP --> INFER --> PROB --> RESULT

    style NEW fill:#FFF9C4,stroke:#F9A825
    style PREP fill:#E3F2FD,stroke:#1565C0
    style INFER fill:#F3E5F5,stroke:#6A1B9A
    style PROB fill:#E8EAF6,stroke:#3949AB
    style RESULT fill:#E8F5E9,stroke:#2E7D32
```

---

## Sơ đồ 4 — Máy học xong rồi, tốt hay chưa?

```mermaid
flowchart TD
    EVAL["📐 Sau mỗi vòng học\nCho máy đoán trên phần ảnh kiểm tra"]

    subgraph METRICS["Cách đánh giá"]
        M1["Đoán đúng tổng thể bao nhiêu %?\n≥ 90% → 🟢 Tốt\n80–90% → 🟡 Tạm được\n< 80% → 🔴 Cần cải thiện"]
        M2["Với bệnh ÍT ẢNH như Bạc thêu bông\nmáy có đoán được không?\nvì ít ảnh → máy dễ bỏ sót"]
        M3["Sai số lúc kiểm tra có\ncao hơn lúc học nhiều không?\nNếu có → máy học vẹt rồi!"]
    end

    JUDGE2{"Kết quả\nổn không?"}

    subgraph GOOD["🟢 TỐT — tiếp tục"]
        G1["Lưu lại phiên bản máy này"]
        G2["Học thêm vài vòng nữa\nhoặc dừng lại"]
    end

    subgraph BAD["🔴 CHƯA TỐT — cần sửa"]
        B1["Máy học vẹt?\n→ Cho xem thêm ảnh biến thể\n→ Bắt máy 'quên bớt' chi tiết nhỏ"]
        B2["Máy học chưa đủ?\n→ Cho học lâu hơn\n→ Dùng máy to hơn, mạnh hơn"]
        B3["Máy bỏ sót bệnh hiếm?\n→ Nhắc máy chú ý hơn\nvào các bệnh ít ảnh"]
    end

    EVAL --> METRICS
    METRICS --> JUDGE2
    JUDGE2 -- "✅ Đoán tốt\nSai số ổn định" --> GOOD
    JUDGE2 -- "❌ Đoán kém\nhoặc học vẹt" --> BAD

    style EVAL fill:#E3F2FD,stroke:#1565C0
    style METRICS fill:#F3E5F5,stroke:#6A1B9A
    style JUDGE2 fill:#FFF3E0,stroke:#E65100
    style GOOD fill:#E8F5E9,stroke:#2E7D32
    style BAD fill:#FCE4EC,stroke:#C62828
```

---

## Sơ đồ 5 — 10 loại bệnh máy cần phân biệt

```mermaid
mindmap
  root((🌾 Máy cần\nphân biệt\n10 loại))
    🦠 Do vi khuẩn gây ra
      Bạc thêu lá
      Sọc lá vi khuẩn
      Bạc thêu bông
    🍄 Do nấm gây ra
      Đạo ôn
      Đốm nâu
      Sương mai
    🐛 Do sâu bọ gây ra
      Bọ xít Hispa
      Tim chết
    🦠 Do virus gây ra
      Bệnh Tung ro
    ✅ Cây khoẻ mạnh
      Bình thường
```

---

## Sơ đồ 6 — Một vòng học của máy trông như thế nào?

```mermaid
sequenceDiagram
    participant D as 📦 Kho ảnh
    participant A as ⚙️ Chuẩn bị ảnh
    participant M as 🤖 Máy học
    participant L as 📉 Tính độ sai
    participant O as 🔧 Điều chỉnh

    Note over D,O: Mỗi lần lấy 1 lô nhỏ (ví dụ 32 ảnh một lúc)

    loop Lặp lại cho đến hết toàn bộ kho ảnh
        D->>A: Lấy 32 ảnh + đáp án đúng
        A->>M: Ảnh đã chỉnh sửa sẵn
        M->>L: Máy đoán → ra xác suất 10 loại bệnh
        L->>L: So với đáp án thật\n→ Tính máy sai bao nhiêu
        L->>O: Thông báo sai chỗ nào
        O->>M: Sửa lại cách nhìn của máy\ncho đúng hơn một chút
    end

    Note over D,O: Hết toàn bộ kho ảnh = xong 1 vòng học
    Note over M,L: Sau mỗi vòng → kiểm tra xem máy tiến bộ chưa
```

---

*Dữ liệu: Paddy Doctor — 10.407 ảnh lá lúa · 10 loại bệnh · Tamil Nadu, Ấn Độ · NeurIPS 2022*
