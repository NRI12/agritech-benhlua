"""Suy luận (inference) phân loại bệnh lúa bằng model ONNX.

Dùng onnxruntime (CPUExecutionProvider) để chạy nhẹ trên Raspberry Pi 4,
không cần PyTorch/Ultralytics ở môi trường chạy thật.

Tiền xử lý khớp với pipeline classify của Ultralytics YOLO11-cls:
  resize cạnh ngắn -> center crop vuông -> đổi sang RGB -> /255 -> CHW -> batch.
"""
import base64
import os

import numpy as np
import onnxruntime as ort

import config


def _softmax(x):
    x = x - np.max(x)
    e = np.exp(x)
    return e / np.sum(e)


class PaddyClassifier:
    def __init__(self, model_path=config.MODEL_PATH, img_size=config.IMG_SIZE):
        self.img_size = img_size
        self.session = ort.InferenceSession(
            model_path, providers=["CPUExecutionProvider"]
        )
        self.input_name = self.session.get_inputs()[0].name

        # Grad-CAM: cần output "features" (tools/add_cam_output.py) + trọng số lớp cuối (.cam.npy)
        self.cam_weights = None
        cam_path = os.path.splitext(model_path)[0] + ".cam.npy"
        has_features = len(self.session.get_outputs()) > 1
        if has_features and os.path.exists(cam_path):
            self.cam_weights = np.load(cam_path)

        # Ưu tiên tên lớp nhúng trong model; fallback về config nếu không có.
        meta = self.session.get_modelmeta().custom_metadata_map
        names = meta.get("names")
        if names:
            # names lưu dạng "{0: 'bacterial_leaf_blight', ...}" -> dùng eval an toàn
            import ast
            parsed = ast.literal_eval(names)
            self.class_names = [parsed[i] for i in range(len(parsed))]
        else:
            self.class_names = config.CLASS_NAMES

    def preprocess(self, frame_bgr):
        """frame_bgr: numpy array HxWx3 (BGR, như OpenCV). Trả tensor [1,3,S,S]."""
        import cv2

        h, w = frame_bgr.shape[:2]
        s = self.img_size

        # Resize cạnh ngắn về S rồi center-crop SxS
        scale = s / min(h, w)
        nw, nh = int(round(w * scale)), int(round(h * scale))
        resized = cv2.resize(frame_bgr, (nw, nh), interpolation=cv2.INTER_LINEAR)
        x0 = (nw - s) // 2
        y0 = (nh - s) // 2
        crop = resized[y0:y0 + s, x0:x0 + s]

        # BGR -> RGB, /255, HWC -> CHW, thêm batch dim
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        chw = np.transpose(rgb, (2, 0, 1))
        return chw[np.newaxis, ...].astype(np.float32)

    @staticmethod
    def vegetation_ratio(frame_bgr):
        """Tỷ lệ điểm ảnh màu thực vật (hue xanh lá -> vàng, đủ bão hoà/sáng) ở vùng giữa khung."""
        import cv2

        h, w = frame_bgr.shape[:2]
        k = 224 / min(h, w)
        small = cv2.resize(frame_bgr, (max(1, int(round(w * k))), max(1, int(round(h * k)))))
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        return float(((hue >= 15) & (hue <= 95) & (sat >= config.RICE_VEG_MIN_SAT) & (val >= 40)).mean())

    def predict(self, frame_bgr):
        """Trả dict: {class, class_index, confidence, probs, is_rice, reason}.

        Nếu ảnh không giống lúa -> class = "not_rice" (confidence = 0). Lớp "not_rice"
        cũng được chấp nhận nếu sau này model được huấn luyện thêm lớp đó.
        """
        tensor = self.preprocess(frame_bgr)
        outs = self.session.run(None, {self.input_name: tensor})
        out = outs[0][0]
        features = outs[1][0] if len(outs) > 1 else None   # [C, 7, 7]

        # Output ONNX của YOLO-cls thường đã là xác suất; vẫn softmax cho chắc
        probs = out if np.isclose(out.sum(), 1.0, atol=1e-2) else _softmax(out)
        idx = int(np.argmax(probs))
        conf = float(probs[idx])
        entropy = float(-(probs * np.log(probs + 1e-12)).sum() / np.log(len(probs)))
        veg = self.vegetation_ratio(frame_bgr)

        reason = None
        if self.class_names[idx] == config.NOT_RICE:
            reason = "model"
        elif veg < config.RICE_MIN_VEGETATION:
            reason = "no_vegetation"
        elif entropy > config.RICE_MAX_ENTROPY or conf < config.RICE_MIN_CONF:
            reason = "uncertain"
        result = {
            "class": self.class_names[idx],
            "class_index": idx,
            "confidence": conf,
            "probs": [float(p) for p in probs],
            "is_rice": reason is None,
            "reason": reason,
            "vegetation": round(veg, 3),
        }
        if reason:
            result.update({"class": config.NOT_RICE, "confidence": 0.0})
        elif features is not None and self.cam_weights is not None:
            result["gradcam"] = self.gradcam_data_uri(frame_bgr, features, idx)
        return result

    def gradcam_data_uri(self, frame_bgr, features, class_idx):
        """Grad-CAM của lớp class_idx phủ lên vùng ảnh model thực sự nhìn (224x224), dạng data URI JPEG.

        Linear nằm ngay sau avg-pool nên Grad-CAM theo logit = ReLU(sum_k W[c,k] * A_k).
        """
        import cv2

        cam = np.tensordot(self.cam_weights[class_idx], features, axes=(0, 0))   # [7,7]
        cam = np.maximum(cam, 0)
        if cam.max() > 0:
            cam = cam / cam.max()
        # Vẽ ở độ phân giải cao (tối đa 640px) trên đúng vùng vuông trung tâm model đã nhìn,
        # để phóng to vẫn nét. Phép cắt trùng với tiền xử lý nên heatmap khớp từng điểm ảnh.
        h, w = frame_bgr.shape[:2]
        side = min(h, w)
        y0, x0 = (h - side) // 2, (w - side) // 2
        crop = frame_bgr[y0:y0 + side, x0:x0 + side]
        out = min(side, 640)
        crop = cv2.resize(crop, (out, out), interpolation=cv2.INTER_AREA if side > out else cv2.INTER_CUBIC)
        cam = cv2.resize(cam.astype(np.float32), (out, out), interpolation=cv2.INTER_CUBIC)
        cam = np.clip(cam, 0, 1)
        heat = cv2.applyColorMap((cam * 255).astype(np.uint8), cv2.COLORMAP_JET)
        overlay = cv2.addWeighted(crop, 0.55, heat, 0.45, 0)
        ok, buf = cv2.imencode(".jpg", overlay, [cv2.IMWRITE_JPEG_QUALITY, 88])
        return "data:image/jpeg;base64," + base64.b64encode(buf).decode() if ok else None


if __name__ == "__main__":
    # Test nhanh: chạy trên vài ảnh mẫu và in kết quả + nhãn thư mục.
    import os
    import sys
    import cv2

    clf = PaddyClassifier()
    print("Class names:", clf.class_names)

    samples = sys.argv[1:]
    if not samples:
        # Mặc định: lấy 1 ảnh từ mỗi thư mục paddy_images
        img_root = os.path.join(config.BASE_DIR, "paddy_images")
        for cls in ["blast", "normal", "brown_spot", "hispa"]:
            d = os.path.join(img_root, cls)
            if os.path.isdir(d):
                files = [f for f in os.listdir(d) if f.lower().endswith((".jpg", ".png", ".jpeg"))]
                if files:
                    samples.append(os.path.join(d, files[0]))

    correct = 0
    for path in samples:
        frame = cv2.imread(path)
        if frame is None:
            print(f"  [bỏ qua] không đọc được {path}")
            continue
        r = clf.predict(frame)
        truth = os.path.basename(os.path.dirname(path))
        ok = "OK " if r["class"] == truth else "  X"
        correct += r["class"] == truth
        print(f"  {ok} {os.path.basename(path):30s} truth={truth:24s} "
              f"pred={r['class']:24s} conf={r['confidence']:.3f} veg={r['vegetation']:.2f}")
    if samples:
        print(f"Correct: {correct}/{len(samples)}")
