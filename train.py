"""Huan luyen model phan loai benh lua (YOLO11-cls).

Tu do duong dan theo vi tri file nay (BASE_DIR = thu muc chua train.py), khong
hardcode duong dan tuyet doi kieu "/workspace/benholua/..." nhu ban ghi cu trong
result_training/args.yaml — nen chay dung tren bat ky may nao clone lai repo,
o bat ky he dieu hanh nao (Windows/Linux/Mac), mien la co dataset paddy_images/.

Cach dung:
    pip install ultralytics
    python train.py                        # dung tham so mac dinh (epochs=100...)
    python train.py --epochs 30 --batch 16  # tuy chinh tham so
    python train.py --skip-export           # chi train, khong xuat ONNX

Cac buoc thuc hien:
  1. Neu chua co dataset_yolo/, tu chia paddy_images/<lop_benh>/*.jpg thanh
     dataset_yolo/{train,val}/<lop_benh>/*.jpg (stratified — giu deu ti le moi
     lop benh o ca 2 phan), theo ti le val_ratio (mac dinh 15%).
  2. Huan luyen bang thu vien Ultralytics (kien truc YOLO11-cls).
  3. Xuat model tot nhat sang dinh dang ONNX va copy vao thu muc trien
     khai (deploy_pi/) de dung ngay tren Raspberry Pi.
"""
import argparse
import random
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SOURCE_IMAGES_DIR = BASE_DIR / "paddy_images"
DATASET_DIR = BASE_DIR / "dataset_yolo"
RUNS_DIR = BASE_DIR / "runs"
DEPLOY_WEIGHT_TARGETS = [
    BASE_DIR / "deploy_pi" / "paddy_classify" / "weights" / "best.onnx",
]

IMAGE_EXTS = (".jpg", ".jpeg", ".png")


def build_dataset_split(source_dir: Path, dataset_dir: Path, val_ratio: float, seed: int) -> None:
    """Chia anh theo tung lop benh thanh 2 phan train/val (copy file, khong sua source_dir)."""
    if dataset_dir.exists():
        print(f"[data] {dataset_dir} da ton tai, bo qua buoc chia lai "
              f"(xoa thu muc nay neu muon chia lai tu dau).")
        return

    class_dirs = sorted(d for d in source_dir.iterdir() if d.is_dir())
    if not class_dirs:
        raise RuntimeError(f"Khong tim thay thu muc lop benh nao trong {source_dir}")

    rng = random.Random(seed)
    for class_dir in class_dirs:
        images = sorted(p for p in class_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
        if not images:
            print(f"[data] CANH BAO: {class_dir} khong co anh, bo qua.")
            continue
        rng.shuffle(images)
        n_val = max(1, round(len(images) * val_ratio))
        val_images, train_images = images[:n_val], images[n_val:]

        for split_name, files in (("train", train_images), ("val", val_images)):
            out_dir = dataset_dir / split_name / class_dir.name
            out_dir.mkdir(parents=True, exist_ok=True)
            for src in files:
                shutil.copy2(src, out_dir / src.name)

        print(f"[data] {class_dir.name}: {len(train_images)} train / {len(val_images)} val")


def train(args: argparse.Namespace) -> Path:
    from ultralytics import YOLO

    model = YOLO(args.model)
    results = model.train(
        data=str(DATASET_DIR),
        project=str(RUNS_DIR),
        name=args.name,
        exist_ok=True,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        patience=args.patience,
        optimizer="AdamW",
        seed=args.seed,
        deterministic=True,
        verbose=True,
    )
    best_pt = Path(results.save_dir) / "weights" / "best.pt"
    print(f"[train] Model tot nhat: {best_pt}")
    return best_pt


def export_and_deploy(best_pt: Path) -> None:
    from ultralytics import YOLO

    best_model = YOLO(str(best_pt))
    onnx_path = Path(best_model.export(format="onnx", simplify=True))
    print(f"[export] Da xuat ONNX: {onnx_path}")

    for target in DEPLOY_WEIGHT_TARGETS:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(onnx_path, target)
        print(f"[export] Da copy sang {target}")
        # Them output dac trung + luu trong so lop cuoi de dashboard ve Grad-CAM tren Pi
        try:
            sys.path.insert(0, str(BASE_DIR / "tools"))
            import add_cam_output
            add_cam_output.patch(str(target))
        except ImportError:
            print("[export] CANH BAO: thieu goi `onnx` -> bo qua Grad-CAM. "
                  "Chay: pip install onnx && python tools/add_cam_output.py " + str(target))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="yolo11s-cls.pt", help="Model goc dung de huan luyen tiep (transfer learning)")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=224)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--patience", type=int, default=10, help="Dung som neu bay nhieu vong khong cai thien")
    parser.add_argument("--val-ratio", type=float, default=0.15, help="Ti le anh danh cho tap kiem dinh (val)")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--name", default="paddy_classify", help="Ten thu muc luu ket qua trong runs/")
    parser.add_argument("--skip-export", action="store_true", help="Chi train, khong xuat ONNX va khong copy sang deploy_pi/")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not SOURCE_IMAGES_DIR.exists():
        raise SystemExit(
            f"Khong thay dataset goc tai {SOURCE_IMAGES_DIR}. "
            f"Xem README.md muc 2.3 de biet cach chuan bi du lieu."
        )

    build_dataset_split(SOURCE_IMAGES_DIR, DATASET_DIR, args.val_ratio, args.seed)
    best_pt = train(args)

    if not args.skip_export:
        export_and_deploy(best_pt)


if __name__ == "__main__":
    main()
