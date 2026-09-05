"""Настройки приложения и таблицы соответствия классов секциям."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class AppConfig:
    """Неизменяемая конфигурация всех компонентов UMKA.

    Пути вычисляются от расположения пакета, поэтому приложение можно запускать
    из любого рабочего каталога. Для изменяемых словарей используются фабрики,
    чтобы экземпляры конфигурации не разделяли одно состояние.
    """

    # Файлы и каталоги приложения.
    model_path: Path = BASE_DIR / "best.pt"
    stats_path: Path = BASE_DIR / "data" / "sort_stats.json"
    events_path: Path = BASE_DIR / "data" / "events" / "events.jsonl"
    log_path: Path = BASE_DIR / "data" / "logs" / "umka.log"
    static_dir: Path = BASE_DIR / "web"
    # USB-камера и параметры изображения для YOLO.
    camera_index: int = 0
    camera_width: int = 640
    camera_height: int = 480
    image_size: int = 416
    confidence: float = 0.60
    min_box_area: int = 2500
    # Защита от одиночных ложных распознаваний и повторной обработки предмета.
    stable_frames: int = 5
    clear_frames: int = 10
    # Отступы области площадки от границ исходного кадра, в пикселях.
    crop_top: int = 40
    crop_bottom: int = 85
    crop_left: int = 100
    crop_right: int = 66
    # Веб-интерфейс и драйвер физического механизма.
    web_host: str = "0.0.0.0"
    web_port: int = 3000
    hardware_driver: str = "console"
    simulate_delay: float = 1.0
    pca9685_address: int = 0x40
    tilt_servo_channel: int = 0
    rotate_servo_channel: int = 1
    # Имена классов модели сначала нормализуются, затем фильтруются и только
    # после этого сопоставляются физической секции и типу для интерфейса.
    class_aliases: dict[str, str] = field(default_factory=lambda: {"papper": "paper"})
    ignored_classes: frozenset[str] = frozenset({"empty", "hand"})
    class_to_section: dict[str, str] = field(default_factory=lambda: {
        "paper": "section_1",
        "plastic": "section_2",
        "organic": "section_3",
        "non_recyclable": "section_4",
    })
    class_to_waste_type: dict[str, str] = field(default_factory=lambda: {
        "paper": "paper",
        "plastic": "plastic_aluminum",
        "organic": "organic",
        "non_recyclable": "non_recyclable",
    })
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
