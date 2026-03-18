# Training

Папка для обучения, зависимостей и артефактов модели.

## Файлы

- [yolo_train_pc.ipynb](yolo_train_pc.ipynb)  
  Ноутбук для локального обучения на ПК.
- [yolo_train_colab.ipynb](yolo_train_colab.ipynb)  
  Ноутбук для запуска обучения в Google Colab.
- [requirements.txt](requirements.txt)  
  Зависимости для обучения и инференса.
- [dataset/](dataset/)  
  Экспортированный датасет в формате YOLOv8.
- [artifacts/yolo_export/model.pt](artifacts/yolo_export/model.pt)  
  Один из сохранённых артефактов модели.
- [yolov8n.pt](yolov8n.pt)  
  Базовая модель для старта обучения.

## Установка зависимостей

```bash
pip install -r training/requirements.txt
```

## Датасет

В `training/dataset/` лежит экспорт из Roboflow:

- [README.dataset.txt](dataset/README.dataset.txt)
- [README.roboflow.txt](dataset/README.roboflow.txt)
- [data.yaml](dataset/data.yaml)

## Когда сюда идти

- если нужно обучить новую модель;
- если нужно проверить, на каком датасете обучалась текущая модель;
- если нужно взять зависимости для ноутбука или локального запуска.

## См. также

- [Главный README](../README.md)
- [Collect](../collect/README.md)
- [Prepare](../prepare/README.md)
