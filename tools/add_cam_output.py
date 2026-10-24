"""Thêm output bản đồ đặc trưng vào model ONNX để tính Grad-CAM ngay trên Pi (không cần PyTorch).

YOLO11-cls kết thúc bằng  Conv(1x1) -> GlobalAvgPool -> Linear -> Softmax.
Vì Linear đứng ngay sau avg-pool nên Grad-CAM theo logit lớp c có dạng đóng:
    CAM_c = ReLU( sum_k  W[c,k] * A_k )        (A = đặc trưng 1280x7x7 trước pool)
Script này (chỉ chạy ở máy dev, cần `pip install onnx numpy`):
  1. thêm output thứ 2 "features" = A vào model,
  2. lưu W (10x1280) ra file <model>.cam.npy cạnh model.

    python tools/add_cam_output.py deploy_pi/paddy_classify/weights/best.onnx
Chạy lại nhiều lần an toàn (model đã vá thì bỏ qua).
"""
import os
import sys

import numpy as np
import onnx
from onnx import numpy_helper


def patch(path):
    m = onnx.load(path)
    g = m.graph
    if len(g.output) > 1 and g.output[1].name == "features":
        print("Model đã có output 'features' — bỏ qua phần vá.")
    else:
        gap = next((n for n in g.node if n.op_type == "GlobalAveragePool"), None)
        if gap is None:
            sys.exit("Không thấy GlobalAveragePool: không phải kiến trúc YOLO-cls như mong đợi.")
        feat = gap.input[0]
        # Identity giữ nguyên graph gốc, chỉ phơi tensor đặc trưng ra làm output thứ 2
        g.node.append(onnx.helper.make_node("Identity", [feat], ["features"], name="cam_features"))
        g.output.append(onnx.helper.make_tensor_value_info(
            "features", onnx.TensorProto.FLOAT, [1, "C", "H", "W"]))
        onnx.checker.check_model(m)
        onnx.save(m, path)
        print("Đã thêm output 'features' vào", path)

    gemm = next(n for n in reversed(g.node) if n.op_type == "Gemm")
    w = next(numpy_helper.to_array(i) for i in g.initializer if i.name == gemm.input[1])
    out = os.path.splitext(path)[0] + ".cam.npy"
    np.save(out, w.astype(np.float32))
    print("Đã lưu trọng số lớp cuối", w.shape, "->", out)


if __name__ == "__main__":
    patch(sys.argv[1] if len(sys.argv) > 1 else "deploy_pi/paddy_classify/weights/best.onnx")
