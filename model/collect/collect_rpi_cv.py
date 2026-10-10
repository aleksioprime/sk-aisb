from picamera2 import Picamera2
from datetime import datetime
import time
import os
import sys
import cv2


def main():
    headless = "--headless" in sys.argv

    base_dir = os.path.dirname(os.path.abspath(__file__))
    snapshots_dir = os.path.join(base_dir, "snapshots")
    os.makedirs(snapshots_dir, exist_ok=True)

    picam2 = Picamera2()
    config = picam2.create_preview_configuration(
        main={"size": (640, 480), "format": "RGB888"}
    )
    picam2.configure(config)

    picam2.start()
    time.sleep(1.0)

    if headless:
        print("HEADLESS: Enter в консоли — сделать снимок. Ctrl+C — выход.")
    else:
        print("Enter в окне — сделать снимок, q — выход.")

    try:
        while True:
            frame_rgb = picam2.capture_array()                 # RGB888
            frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)

            if not headless:
                cv2.imshow("Preview", frame_bgr)
                key = cv2.waitKey(1) & 0xFF

                if key == 13:  # Enter
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                    filepath = os.path.join(snapshots_dir, f"img_{ts}.jpg")
                    cv2.imwrite(filepath, frame_bgr)
                    print(f"Снимок сохранён как {filepath}")

                elif key == ord("q"):
                    break

            else:
                input("\nНажмите Enter для захвата кадра...")
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                filepath = os.path.join(snapshots_dir, f"img_{ts}.jpg")
                cv2.imwrite(filepath, frame_bgr)
                print(f"Снимок сохранён как {filepath}")

    except KeyboardInterrupt:
        print("\nПрограмма завершена.")
    finally:
        picam2.close()
        if not headless:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()