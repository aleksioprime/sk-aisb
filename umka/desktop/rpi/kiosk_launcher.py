#!/usr/bin/env python3
"""Запустить общий киоск UMKA на Raspberry Pi."""

from pathlib import Path
import runpy


if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "kiosk_launcher.py"),
                   run_name="__main__")
