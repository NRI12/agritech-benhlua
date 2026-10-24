# Sơ đồ đơn giản — Paddy Doctor

> Xem trong VS Code: **Ctrl+Shift+V** | Hoặc paste vào **https://mermaid.live**

---

## Sơ đồ 1 — Tại sao cần làm cái này?

```mermaid
flowchart TD
    VDE["😟 VẤN ĐỀ\nNông dân thấy lá lúa bị lạ\nnhưng không biết là bệnh gì\nnên không biết phải làm gì"]

    GIAI["💡 GIẢI PHÁP\nDạy máy tính nhận ra bệnh\ngiống như dạy một người mới\nbằng cách cho xem rất nhiều ảnh ví dụ"]

    KQ["✅ KẾT QUẢ MONG MUỐN\nChụp ảnh lá lúa\n→ Máy nói ngay đây là bệnh gì"]

    VDE --> GIAI --> KQ

    style VDE fill:#FCE4EC,stroke:#C62828
    style GIAI fill:#FFF9C4,stroke:#F9A825
    style KQ fill:#E8F5E9,stroke:#2E7D32
```

---

## Sơ đồ 2 — Xây dựng bộ dữ liệu như thế nào?

```mermaid
flowchart LR
    subgraph THU["📷 THU THẬP"]
        A["Chuyên gia ra đồng\nchụp ảnh lá lúa\nbệnh và khoẻ"]
    end

    subgraph NHAN["🏷️ GÁN NHÃN"]
        B["Chuyên gia xem từng ảnh\nvà ghi rõ\n'ảnh này là bệnh Đạo ôn'\n'ảnh này là Bình thường'..."]
    end

    subgraph BO["📦 BỘ DỮ LIỆU HOÀN CHỈNH"]
        C["10.407 ảnh\nMỗi ảnh đã có nhãn sẵn\n10 loại bệnh khác nhau"]
    end

    subgraph DAY["🎓 DẠY MÁY"]
        D["Cho máy xem toàn bộ\nảnh + nhãn\nMáy tự học cách phân biệt"]
    end

    THU --> NHAN --> BO --> DAY

    style THU fill:#E3F2FD,stroke:#1565C0
    style NHAN fill:#FFF9C4,stroke:#F9A825
    style BO fill:#F3E5F5,stroke:#6A1B9A
    style DAY fill:#E8F5E9,stroke:#2E7D32
```

---

## Sơ đồ 3 — Khi có ảnh mới thì máy làm gì?

```mermaid
flowchart LR
    ANH["📱\nChụp ảnh\nlá lúa"]

    MAY["🤖\nMáy so sánh\nvới những gì\nđã học"]

    KQ["🏷️\nĐây là\nbệnh ĐẠO ÔN\n(82% chắc chắn)"]

    ANH --> MAY --> KQ

    style ANH fill:#FFF9C4,stroke:#F9A825
    style MAY fill:#F3E5F5,stroke:#6A1B9A
    style KQ fill:#E8F5E9,stroke:#2E7D32
```

---

## Sơ đồ 4 — Toàn bộ câu chuyện trong 1 hình

```mermaid
flowchart TD
    subgraph BAITOAN["🌾 BÀI TOÁN"]
        Q["Lá lúa này bị bệnh gì?"]
    end

    subgraph DULIEU["📦 BỘ DỮ LIỆU\n(chuẩn bị 1 lần)"]
        D1["Ảnh lá khoẻ → nhãn: Bình thường"]
        D2["Ảnh lá bệnh → nhãn: Đạo ôn"]
        D3["Ảnh lá bệnh → nhãn: Đốm nâu"]
        D4["... 10.407 ảnh · 10 loại ..."]
    end

    subgraph MAY["🤖 MÁY ĐÃ ĐƯỢC DẠY"]
        M["Đã học xong\nbiết phân biệt 10 loại bệnh"]
    end

    subgraph MOIVAO["📱 KHI CÓ ẢNH MỚI"]
        I["Ảnh lá lúa\nchưa biết bệnh"]
        O["→ Đây là bệnh TIM CHẾT\n→ Mức chắc chắn: 76%"]
        I --> O
    end

    BAITOAN --> DULIEU
    DULIEU --> MAY
    MAY --> MOIVAO

    style BAITOAN fill:#FCE4EC,stroke:#C62828
    style DULIEU fill:#E3F2FD,stroke:#1565C0
    style MAY fill:#F3E5F5,stroke:#6A1B9A
    style MOIVAO fill:#E8F5E9,stroke:#2E7D32
```

---

*Paddy Doctor · 10.407 ảnh lá lúa · 10 loại bệnh · Ấn Độ · NeurIPS 2022*
