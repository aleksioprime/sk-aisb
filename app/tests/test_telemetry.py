"""Проверки телеметрии без брокера MQTT."""

import json
import tempfile
import unittest
from pathlib import Path

from sorter.launch_config import parse_bool
from sorter.telemetry import Telemetry, pending_events


def record(event_id, event="sort", timestamp="2026-10-11T10:00:00+03:00"):
    return {"timestamp": timestamp, "event": event, "event_id": event_id}


def write(path, records):
    path.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")


class FakeInfo:
    def __init__(self, ok):
        self.ok = ok

    def wait_for_publish(self, timeout=None):
        pass

    def is_published(self):
        return self.ok


class FakeClient:
    """Принимает сообщения, пока не «оборвётся связь» после limit штук."""

    def __init__(self, limit=None):
        self.limit = limit
        self.sent = []

    def publish(self, topic, payload, qos=0, retain=False):
        if self.limit is not None and len(self.sent) >= self.limit:
            return FakeInfo(False)
        self.sent.append((topic, json.loads(payload), retain))
        return FakeInfo(True)


class FakeState:
    def snapshot(self):
        return {"camera": {"ok": True}, "stats": {"total_items": 3}, "controllerState": "IDLE", "detection": None}


class PendingEventsTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "events.jsonl"

    def test_without_cursor_everything_in_order_archives_first(self):
        write(self.dir / "events.2026-10-10.jsonl", [record("a"), record("b")])
        write(self.path, [record("c")])
        self.assertEqual([r["event_id"] for r in pending_events(self.path, None)], ["a", "b", "c"])

    def test_cursor_survives_midnight_rotation(self):
        write(self.path, [record("a"), record("b")])
        cursor = {"timestamp": "2026-10-11T10:00:00+03:00", "key": "a:sort"}
        # В полночь активный журнал стал архивом, появился новый файл.
        self.path.rename(self.dir / "events.2026-10-11.jsonl")
        write(self.path, [record("c", timestamp="2026-10-12T09:00:00+03:00")])
        self.assertEqual([r["event_id"] for r in pending_events(self.path, cursor)], ["b", "c"])

    def test_feedback_with_same_event_id_is_a_separate_event(self):
        write(self.path, [record("a"), record("a", event="feedback")])
        cursor = {"timestamp": "2026-10-11T10:00:00+03:00", "key": "a:sort"}
        self.assertEqual([r["event"] for r in pending_events(self.path, cursor)], ["feedback"])

    def test_cursor_from_deleted_archive_falls_back_to_time(self):
        write(self.path, [record("old", timestamp="2026-09-01T10:00:00+03:00"),
                          record("new", timestamp="2026-10-12T10:00:00+03:00")])
        cursor = {"timestamp": "2026-09-05T00:00:00+03:00", "key": "gone:sort"}
        self.assertEqual([r["event_id"] for r in pending_events(self.path, cursor)], ["new"])


class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "events.jsonl"
        write(self.path, [record("a"), record("b"), record("c")])
        settings = {"mqtt_host": "mqtt.example", "mqtt_username": "umka", "device_id": "opi-expo"}
        self.telemetry = Telemetry(settings, FakeState(), self.path, self.dir / "telemetry.json")
        self.telemetry._connected.set()

    def test_disconnect_stops_and_resumes_from_same_place(self):
        self.telemetry.client = FakeClient(limit=2)
        self.assertEqual(self.telemetry.send_events(), 2)
        self.telemetry.client = FakeClient()
        self.assertEqual(self.telemetry.send_events(), 1)
        topic, payload, _ = self.telemetry.client.sent[0]
        self.assertEqual((topic, payload["event_id"]), ("umka/opi-expo/event", "c"))
        self.assertEqual(self.telemetry.send_events(), 0)

    def test_nothing_is_sent_while_offline(self):
        self.telemetry._connected.clear()
        self.telemetry.client = FakeClient()
        self.assertEqual(self.telemetry.send_events(), 0)

    def test_status_has_device_name_and_no_detection(self):
        payload = self.telemetry.status_payload()
        self.assertEqual(payload["name"], "opi-expo")
        self.assertEqual(payload["stats"], {"total_items": 3})
        self.assertNotIn("detection", payload)

    def test_disabled_without_host_or_username(self):
        self.assertFalse(Telemetry({"mqtt_host": "x"}, FakeState(), self.path, self.dir / "t.json").enabled)
        self.assertTrue(self.telemetry.enabled)

    def test_bool_values(self):
        self.assertTrue(parse_bool("Yes"))
        self.assertFalse(parse_bool("off"))
        with self.assertRaises(ValueError):
            parse_bool("maybe")


if __name__ == "__main__":
    unittest.main()
