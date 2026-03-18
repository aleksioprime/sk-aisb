# Prepare

Папка для подготовки и экспорта моделей.

## Файлы

- [export_ncnn.py](export_ncnn.py)  
  Экспорт `.pt` модели YOLO в формат NCNN.
- [yolov8n.pt](yolov8n.pt)  
  Базовая модель Ultralytics YOLOv8n.
- [yolov8n_ncnn_model/](yolov8n_ncnn_model/)  
  Пример экспортированной NCNN-модели и её метаданные.

## Экспорт в NCNN

```bash
python prepare/export_ncnn.py --model prepare/yolov8n.pt --imgsz 320
```

Скрипт создаёт папку вида `<model_name>_ncnn_model`.

## Когда это нужно

- если нужно ускорить инференс на слабом устройстве;
- если модель будет запускаться вне PyTorch;
- если требуется тестировать NCNN-конвейер отдельно от `.pt`.

## См. также

- [Главный README](../README.md)
- [Training](../training/README.md)
- [Detection](../detection/README.md)
