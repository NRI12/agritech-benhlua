"""Trợ lý tư vấn bệnh lúa đơn giản (rule-based).

Trả lời dựa trên:
  - Bệnh model đang phát hiện (truyền vào current_disease).
  - Từ khóa trong câu hỏi của người dùng (thuốc, triệu chứng, phòng ngừa...).

Nội dung khuyến nghị lấy theo kiến thức phổ biến về bệnh lúa, đồng bộ với
tab "Đề xuất xử lý" trên dashboard. Có thể nâng cấp sau bằng cách nối Claude
API để tư vấn ngôn ngữ tự nhiên hơn.
"""
import config

# Khuyến nghị xử lý theo từng lớp bệnh
TREATMENT = {
    "blast": {
        "trieu_chung": "Vết bệnh hình thoi, tâm xám tro, viền nâu; nặng làm cháy lá, gãy cổ bông.",
        "canh_tac": "Vệ sinh đồng ruộng, bón phân cân đối N-P-K, tránh bón thừa đạm, giữ mực nước hợp lý.",
        "sinh_hoc": "Dùng chế phẩm nấm đối kháng Trichoderma spp. và Bacillus subtilis.",
        "hoa_hoc": "Tricyclazole 75WP (0.6–0.8 kg/ha), Isoprothiolane 40EC (0.8–1.0 l/ha), Hexaconazole 5SC (0.5–0.7 l/ha).",
    },
    "brown_spot": {
        "trieu_chung": "Đốm tròn/bầu dục màu nâu, tâm xám, thường do thiếu kali hoặc đất nghèo dinh dưỡng.",
        "canh_tac": "Bón bổ sung kali, cải tạo đất, không để ruộng thiếu nước kéo dài.",
        "sinh_hoc": "Xử lý hạt giống bằng Trichoderma; luân canh cây trồng.",
        "hoa_hoc": "Mancozeb, Propiconazole hoặc Carbendazim theo liều khuyến cáo.",
    },
    "bacterial_leaf_blight": {
        "trieu_chung": "Lá héo, mép lá vàng úa lan dần, có giọt dịch vi khuẩn vào sáng sớm.",
        "canh_tac": "Dùng giống kháng bệnh, thoát nước tốt, tránh bón thừa đạm, vệ sinh tàn dư.",
        "sinh_hoc": "Phun chế phẩm Bacillus subtilis; xử lý hạt giống bằng nước nóng 52-54°C.",
        "hoa_hoc": "Kasugamycin, Copper oxychloride (gốc đồng) theo liều khuyến cáo.",
    },
    "bacterial_leaf_streak": {
        "trieu_chung": "Sọc nhỏ trong mờ chạy dọc gân lá, sau chuyển nâu vàng.",
        "canh_tac": "Giống kháng bệnh, tránh để ruộng ngập úng, bón cân đối.",
        "sinh_hoc": "Bacillus subtilis; vệ sinh tàn dư cây bệnh.",
        "hoa_hoc": "Hợp chất gốc đồng (Copper), Kasugamycin.",
    },
    "bacterial_panicle_blight": {
        "trieu_chung": "Bông lép, hạt biến màu nâu, vi khuẩn gây thối ở giai đoạn trổ.",
        "canh_tac": "Giảm mật độ gieo, tránh thừa đạm giai đoạn trổ, thoát nước tốt.",
        "sinh_hoc": "Bacillus spp.; dùng giống sạch bệnh.",
        "hoa_hoc": "Oxolinic acid hoặc gốc đồng, phun phòng giai đoạn trổ.",
    },
    "dead_heart": {
        "trieu_chung": "Nõn (đọt non) héo khô do sâu đục thân; nhổ lên dễ đứt gốc.",
        "canh_tac": "Ngắt ổ trứng, vệ sinh gốc rạ, gieo cấy đồng loạt né lứa sâu.",
        "sinh_hoc": "Thả ong mắt đỏ Trichogramma; chế phẩm Bt (Bacillus thuringiensis).",
        "hoa_hoc": "Cartap, Chlorantraniliprole khi mật độ sâu cao.",
    },
    "downy_mildew": {
        "trieu_chung": "Lá xoăn, có lớp nấm trắng/xám mặt dưới lá ở điều kiện ẩm.",
        "canh_tac": "Thoát nước, tăng thông thoáng, tránh gieo dày.",
        "sinh_hoc": "Trichoderma; xử lý hạt giống.",
        "hoa_hoc": "Metalaxyl, Mancozeb theo khuyến cáo.",
    },
    "hispa": {
        "trieu_chung": "Bọ trĩ Hispa cạp biểu bì lá tạo vệt trắng dọc, lá xơ xác.",
        "canh_tac": "Vệ sinh cỏ bờ, cắt tỉa lá bị hại nặng, tránh thừa đạm.",
        "sinh_hoc": "Bảo vệ thiên địch; chế phẩm nấm Metarhizium/Beauveria.",
        "hoa_hoc": "Chlorpyrifos hoặc Quinalphos khi mật độ cao (luân phiên hoạt chất).",
    },
    "tungro": {
        "trieu_chung": "Cây lùn, lá vàng cam từ chóp xuống; do virus, lan qua rầy xanh.",
        "canh_tac": "Nhổ bỏ cây bệnh sớm, dùng giống kháng, gieo cấy đồng loạt.",
        "sinh_hoc": "Bảo vệ thiên địch của rầy; bẫy đèn theo dõi rầy.",
        "hoa_hoc": "Diệt môi giới rầy xanh bằng thuốc trừ rầy (Imidacloprid, Buprofezin).",
    },
    "normal": {
        "trieu_chung": "Cây lúa khỏe mạnh, chưa phát hiện dấu hiệu bệnh.",
        "canh_tac": "Duy trì bón cân đối N-P-K, giữ mực nước 5–7 cm, theo dõi định kỳ.",
        "sinh_hoc": "Bổ sung chế phẩm vi sinh có lợi cho đất.",
        "hoa_hoc": "Chưa cần dùng thuốc. Chỉ phun khi xuất hiện bệnh.",
    },
}


def answer(question, current_disease=None):
    """Sinh câu trả lời tư vấn.

    question: câu hỏi người dùng (str)
    current_disease: tên lớp bệnh model đang phát hiện (key trong CLASS_NAMES)
    """
    q = (question or "").lower()
    disease = current_disease if current_disease in TREATMENT else None
    info = TREATMENT.get(disease)
    vi = config.CLASS_INFO.get(disease, {}).get("vi", "") if disease else ""

    # Không xác định được bệnh -> hỏi lại / hướng dẫn
    if info is None or disease == "normal":
        if any(k in q for k in ["thuốc", "phun", "trị", "xử lý"]):
            return ("Chưa có kết quả nhận diện bệnh (hoặc cây có vẻ bình thường). "
                    "Hãy chụp ảnh hoặc chọn ảnh vùng lá nghi nhiễm để tôi tư vấn thuốc cụ thể nhé.")
        if disease == "normal":
            return ("Cây lúa hiện ở trạng thái bình thường. "
                    + TREATMENT["normal"]["canh_tac"])
        return ("Bạn hãy chụp ảnh hoặc chọn ảnh lá lúa để tôi nhận diện bệnh, "
                "sau đó tôi sẽ tư vấn biện pháp xử lý phù hợp.")

    # Theo từ khóa câu hỏi
    if any(k in q for k in ["triệu chứng", "dấu hiệu", "bệnh gì", "là gì", "nhận biết"]):
        return f"Đây là dấu hiệu của bệnh {vi}. {info['trieu_chung']}"

    if any(k in q for k in ["thuốc", "hóa học", "phun gì"]):
        return (f"Với bệnh {vi}, biện pháp hóa học: {info['hoa_hoc']} "
                f"Lưu ý luân phiên hoạt chất và tuân thủ thời gian cách ly.")

    if any(k in q for k in ["sinh học", "vi sinh", "an toàn"]):
        return f"Biện pháp sinh học cho bệnh {vi}: {info['sinh_hoc']}"

    if any(k in q for k in ["canh tác", "phòng", "chăm sóc", "bón"]):
        return f"Biện pháp canh tác với bệnh {vi}: {info['canh_tac']}"

    if any(k in q for k in ["khi nào", "thời điểm", "lúc nào"]):
        return ("Nên phun khi bệnh mới xuất hiện (tỷ lệ < 5%), vào sáng sớm hoặc "
                "chiều mát, tránh phun lúc trời sắp mưa.")

    # Trả lời tổng hợp mặc định
    return (f"Ảnh vừa phân tích cho thấy: {vi}.\n"
            f"• Triệu chứng: {info['trieu_chung']}\n"
            f"• Canh tác: {info['canh_tac']}\n"
            f"• Sinh học: {info['sinh_hoc']}\n"
            f"• Hóa học: {info['hoa_hoc']}")
