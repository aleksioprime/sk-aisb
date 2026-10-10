# Программа для захвата стоп-кадров с камеры Raspberry Pi
# и сохранения их в папку "snapshots" в домашней директории пользователя

from picamera2 import Picamera2, Preview
from datetime import datetime
import time
import os
import sys

def main():
    headless = "--headless" in sys.argv

    # Определяем путь к папке
    base_dir = os.path.dirname(os.path.abspath(__file__))
    snapshots_dir = os.path.join(base_dir, "snapshots")
    # Создаём папку, если её нет
    os.makedirs(snapshots_dir, exist_ok=True)

    # Инициализация камеры
    picam2 = Picamera2()
    config = picam2.create_preview_configuration(
        main={"size": (640, 480), "format": "XRGB8888"}
    )
    picam2.configure(config)

    if headless:
        picam2.start_preview(Preview.NULL)
    else:
        picam2.start_preview(Preview.QTGL)

    # Запуск камеры
    picam2.start()
    time.sleep(1.0)

    print("Нажмите Enter, чтобы сделать стоп-кадр. Для выхода нажмите Ctrl+C.")

    try:
        while True:
            input("\nНажмите Enter для захвата кадра...")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filepath = os.path.join(snapshots_dir, f"img_{timestamp}.jpg")
            picam2.capture_file(filepath)
            print(f"Снимок сохранён как {filepath}")
    except KeyboardInterrupt:
        print("\nПрограмма завершена.")
    finally:
        picam2.stop_preview()
        picam2.close()

if __name__ == '__main__':
    main()
