"""Настройки приложения и таблицы соответствия классов секциям."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


# Корень UMKA: на Raspberry Pi обычно /home/umka/app.
BASE_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class AppConfig:
    """Неизменяемая конфигурация всех компонентов UMKA.

    Пути вычисляются от расположения пакета, поэтому приложение можно запускать
    из любого рабочего каталога. Для изменяемых словарей используются фабрики,
    чтобы экземпляры конфигурации не разделяли одно состояние.

    После изменения настроек перезапустите программу. Параметры, передаваемые
    из app.py через replace(), берутся из аргументов командной строки, включая
    их значения по умолчанию в parse_args(). Это относится к камере, серверу,
    драйверу, I2C, порогу уверенности и числу кадров: для них проверяйте и app.py.
    Углы моторов задаются отдельно, в начале sorter/hardware.py.
    """

    # Файлы и каталоги приложения.
    model_path: Path = BASE_DIR / "best.pt"  # Веса обученной модели YOLO.
    stats_path: Path = BASE_DIR / "data" / "sort_stats.json"  # Общие счётчики и масса.
    events_path: Path = BASE_DIR / "data" / "events" / "events.jsonl"  # История операций.
    log_path: Path = BASE_DIR / "data" / "logs" / "umka.log"  # Журнал работы и ошибок.
    static_dir: Path = BASE_DIR / "web"  # HTML, CSS, JavaScript и картинки интерфейса.

    # USB-камера и параметры изображения для YOLO.
    camera_index: int = 0  # Номер /dev/videoN: 0 означает /dev/video0.
    camera_width: int = 640  # Запрашиваемая ширина кадра, пиксели.
    camera_height: int = 480  # Запрашиваемая высота; камера может выбрать другую.
    image_size: int = 416  # Размер входа YOLO (imgsz), пиксели; не размер кадра камеры.
    confidence: float = 0.60  # Минимальная уверенность YOLO: 0.60 = 60%, диапазон 0–1.
    min_box_area: int = 2500  # Минимальная площадь рамки в обрезанном кадре, пиксели².

    # Защита от одиночных ложных распознаваний и повторной обработки предмета.
    stable_frames: int = 5  # Столько результатов подряд с одним классом запускают сброс.
    clear_frames: int = 10  # Столько результатов без объекта разрешают следующий сброс.
    # Считаются обработанные кадры, а не секунды и не все кадры видеопотока.

    # Отступы области площадки от границ исходного кадра, в пикселях.
    crop_top: int = 40  # Убрать сверху.
    crop_bottom: int = 85  # Убрать снизу.
    crop_left: int = 100  # Убрать слева.
    crop_right: int = 66  # Убрать справа.
    # Чем больше отступы, тем меньше область, в которой ищутся предметы.

    # Веб-интерфейс и драйвер физического механизма.
    web_host: str = "0.0.0.0"  # Слушать все IPv4-интерфейсы; 127.0.0.1 — только сам Pi.
    web_port: int = 3000  # Порт страницы и API: http://<IP_RASPBERRY_PI>:3000.
    # console — имитация; pca9685 — моторы через I2C; gpiozero — напрямую через GPIO.
    hardware_driver: str = "console"
    simulate_delay: float = 1.0  # Длительность имитации сброса, секунды; только console.
    pca9685_address: int = 0x40  # I2C-адрес всей платы, а не отдельного мотора.
    tilt_servo_channel: int = 1  # Выход PCA9685 для наклона, номер 0–15.
    rotate_servo_channel: int = 0  # Выход PCA9685 для поворота; отличается от наклона.
    # Эти каналы не являются GPIO-номерами и не меняют проводку драйвера gpiozero.

    # Имена классов модели сначала нормализуются, затем фильтруются и только
    # после этого сопоставляются физической секции и типу для интерфейса.
    # Слева имя из модели, справа внутреннее имя: исправляет papper → paper.
    class_aliases: dict[str, str] = field(default_factory=lambda: {"papper": "paper"})
    ignored_classes: frozenset[str] = frozenset({"empty", "hand"})  # Не запускают сброс.
    # Класс → физический отсек. Чтобы поменять баки местами, меняйте значения здесь.
    # section_1–section_4 соответствуют ключам ACTIONS в hardware.py и командам 1–4
    # в calibrate.py. Неизвестные классы детектор относит к non_recyclable.
    class_to_section: dict[str, str] = field(default_factory=lambda: {
        "paper": "section_4",  # Бумага.
        "plastic": "section_3",  # Пластик.
        "organic": "section_2",  # Органика.
        "non_recyclable": "section_1",  # Неперерабатываемые и неизвестные классы.
    })
    # Класс → категория для интерфейса и статистики. Не определяет движение моторов.
    # plastic_aluminum — имя общей категории «Пластик и алюминий» в интерфейсе.
    class_to_waste_type: dict[str, str] = field(default_factory=lambda: {
        "paper": "paper",
        "plastic": "plastic_aluminum",
        "organic": "organic",
        "non_recyclable": "non_recyclable",
    })
    # Оценочная масса ОДНОГО предмета по классу, кг; не измерение весами.
    # Используется для подсчёта массы в статистике и записи события сортировки.
    estimated_weight_kg: dict[str, float] = field(default_factory=lambda: {
        "paper": 0.05,
        "plastic": 0.03,
        "organic": 0.15,
        "non_recyclable": 0.10,
    })

    def validate(self) -> None:
        """Проверить обязательные файлы и допустимость основных параметров."""
        if not self.model_path.is_file():
            raise FileNotFoundError(f"Модель не найдена: {self.model_path}")
        if not self.static_dir.is_dir():
            raise FileNotFoundError(f"Каталог интерфейса не найден: {self.static_dir}")
        if self.stable_frames < 1 or self.clear_frames < 1:
            raise ValueError("stable_frames и clear_frames должны быть положительными")
        if self.hardware_driver not in {"console", "gpiozero", "pca9685"}:
            raise ValueError(f"Неизвестный драйвер: {self.hardware_driver}")
        if not 0x03 <= self.pca9685_address <= 0x77:
            raise ValueError("Адрес PCA9685 должен находиться в диапазоне 0x03–0x77")
        channels = (self.tilt_servo_channel, self.rotate_servo_channel)
        if any(channel not in range(16) for channel in channels):
            raise ValueError("Каналы PCA9685 должны находиться в диапазоне 0–15")
        if self.tilt_servo_channel == self.rotate_servo_channel:
            raise ValueError("Для наклона и поворота нужны разные каналы PCA9685")

    def normalize_class(self, name: str) -> str:
        """Привести имя класса YOLO к внутреннему каноническому имени."""
        normalized = name.strip().lower()
        return self.class_aliases.get(normalized, normalized)
