# Экспорт модели YOLOv8 в формат ncnn
# Пример использования:
# cd prepare
# python export_ncnn.py --model yolov8n.pt --imgsz 320

import argparse
from ultralytics import YOLO

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True, help="Путь к .pt (например yolov8n.pt)")
    p.add_argument("--imgsz", type=int, default=320, help="imgsz для экспорта (320/416/640)")
    args = p.parse_args()

    model = YOLO(args.model)

    # Экспорт создаст папку вида: <name>_ncnn_model
    out = model.export(format="ncnn", imgsz=args.imgsz)
    print("Exported to:", out)

if __name__ == "__main__":
    main()