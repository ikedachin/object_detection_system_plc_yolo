import logging
import os
import sys
import time
import json
from pathlib import Path
from urllib import request

import yaml


THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parents[3]
DJANGO_ROOT = THIS_FILE.parents[2]
SETTINGS_PATH = PROJECT_ROOT / "settings" / "plc_settings.yaml"
LOCK_PATH = Path("/tmp/yolo_system_plc_monitor.lock")

if str(DJANGO_ROOT) not in sys.path:
    sys.path.insert(0, str(DJANGO_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "yolo_system.settings")

import django  # noqa: E402

django.setup()

from checker.applications.snap_service import is_snap_running, run_snap_backend_sync  # noqa: E402


logger = logging.getLogger(__name__)


class AlreadyRunningError(RuntimeError):
    pass


class SingleInstanceLock:
    def __init__(self, path=LOCK_PATH):
        self.path = Path(path)
        self.file = None

    def acquire(self):
        import fcntl

        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = open(self.path, "w")
        try:
            fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AlreadyRunningError(f"PLC monitor is already running. lock={self.path}") from exc

        self.file.seek(0)
        self.file.truncate()
        self.file.write(str(os.getpid()))
        self.file.flush()
        return self

    def release(self):
        if self.file is None:
            return
        import fcntl

        try:
            fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        finally:
            self.file.close()
            self.file = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc, tb):
        self.release()


class PlcClient:
    """Small adapter around the installed pyfins implementation."""

    def __init__(self, connection_config):
        try:
            import pyfins
        except ImportError as exc:
            raise RuntimeError("pyfins がインストールされていません。依存関係をインストールしてください。") from exc

        self.pyfins = pyfins
        self.config = connection_config
        self.client = None

    def connect(self):
        host = self.config["host"]
        port = self.config.get("port", 9600)
        timeout = self.config.get("timeout")

        if hasattr(self.pyfins, "FinsClient"):
            self.client = self.pyfins.FinsClient(host=host, port=port)
        elif hasattr(self.pyfins, "UDPFinsConnection"):
            self.client = self.pyfins.UDPFinsConnection()
            self.client.connect(host)
        elif hasattr(self.pyfins, "udp") and hasattr(self.pyfins.udp, "UDPFinsConnection"):
            self.client = self.pyfins.udp.UDPFinsConnection()
            self.client.connect(host)
        else:
            raise RuntimeError("対応している pyfins クライアントAPIが見つかりません。PlcClient adapterを実環境APIに合わせてください。")

        self._set_attr_if_exists(("dest_node_add", "dest_node", "plc_node"), self.config.get("plc_node"))
        self._set_attr_if_exists(("srce_node_add", "src_node", "pc_node"), self.config.get("pc_node"))
        self._set_attr_if_exists(("timeout",), timeout)
        return self

    def close(self):
        if self.client is None:
            return
        close = getattr(self.client, "close", None)
        if callable(close):
            close()

    def read_bit(self, area, word_address, bit):
        address = self._address(area, word_address, bit)

        for method_name in ("memory_area_read", "read_memory", "read_bit", "read"):
            method = getattr(self.client, method_name, None)
            if not callable(method):
                continue
            try:
                response = method(address)
            except TypeError:
                continue
            return self._response_to_bit(response)

        raise RuntimeError("pyfins client に対応する読取メソッドがありません。PlcClient.read_bit を実APIに合わせてください。")

    def write_bit(self, area, word_address, bit, value):
        address = self._address(area, word_address, bit)
        payload = b"\x01" if int(value) else b"\x00"

        for method_name in ("memory_area_write", "write_memory", "write_bit", "write"):
            method = getattr(self.client, method_name, None)
            if not callable(method):
                continue
            try:
                method(address, payload)
                return
            except TypeError:
                try:
                    method(address, int(value))
                    return
                except TypeError:
                    continue

        raise RuntimeError("pyfins client に対応する書込メソッドがありません。PlcClient.write_bit を実APIに合わせてください。")

    def _set_attr_if_exists(self, names, value):
        if value is None or self.client is None:
            return
        for name in names:
            if hasattr(self.client, name):
                setattr(self.client, name, value)

    @staticmethod
    def _address(area, word_address, bit):
        return f"{area}{int(word_address)}.{int(bit):02d}"

    @staticmethod
    def _response_to_bit(response):
        data = getattr(response, "data", response)
        if isinstance(data, (bytes, bytearray)):
            return bool(data[-1])
        if isinstance(data, (list, tuple)):
            return bool(data[-1])
        return bool(data)


class TestServerPlcClient:
    """HTTP client for the root-level plc_test_server.py."""

    def __init__(self, test_server_config):
        self.config = test_server_config
        self.base_url = test_server_config.get("base_url", "http://127.0.0.1:8010").rstrip("/")

    def connect(self):
        return self

    def close(self):
        return None

    def read_bit(self, area, word_address, bit):
        url = f"{self.base_url}/api/bit/{area}/{int(word_address)}/{int(bit)}"
        with request.urlopen(url, timeout=float(self.config.get("timeout", 3.0))) as response:
            data = json.loads(response.read().decode("utf-8"))
        return bool(data["value"])

    def write_bit(self, area, word_address, bit, value):
        url = f"{self.base_url}/api/bit"
        body = json.dumps({
            "area": area,
            "word_address": int(word_address),
            "bit": int(bit),
            "value": int(value),
        }).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=float(self.config.get("timeout", 3.0))) as response:
            response.read()


def load_config(path=SETTINGS_PATH):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def is_plc_enabled(config):
    return bool(config.get("plc", {}).get("enabled", True))


def is_test_server_enabled(config):
    return bool(config.get("test_server", {}).get("enabled", False))


def build_plc_client(config):
    if is_plc_enabled(config):
        return PlcClient(config["connection"]).connect()
    if is_test_server_enabled(config):
        return TestServerPlcClient(config["test_server"]).connect()
    return None


def _signal_address(signal):
    return signal["area"], signal["word_address"], signal["bit"]


def _write_signal(client, signal, value_key, default):
    value = int(signal.get(value_key, default))
    client.write_bit(*_signal_address(signal), value)
    return value


def _result_signals_are_pending(client, result_signal):
    complete_signal = result_signal.get("complete") if result_signal else None
    if not complete_signal:
        return False
    return client.read_bit(*_signal_address(complete_signal))


def write_completed_result_signals(client, result_signal, is_ok):
    if not result_signal:
        return

    ok_signal = result_signal.get("ok")
    error_signal = result_signal.get("error")
    complete_signal = result_signal.get("complete")

    if ok_signal:
        key = "ok_value" if is_ok else "ng_value"
        value = _write_signal(client, ok_signal, key, 1 if is_ok else 0)
        logger.info("PLC result OK/NG signal set: %s%s.%02d=%s", ok_signal["area"], int(ok_signal["word_address"]), int(ok_signal["bit"]), value)
    if error_signal:
        value = _write_signal(client, error_signal, "reset_value", 0)
        logger.info("PLC result error signal reset: %s%s.%02d=%s", error_signal["area"], int(error_signal["word_address"]), int(error_signal["bit"]), value)
    if complete_signal:
        value = _write_signal(client, complete_signal, "on_value", 1)
        logger.info("PLC result complete signal set: %s%s.%02d=%s", complete_signal["area"], int(complete_signal["word_address"]), int(complete_signal["bit"]), value)


def write_error_result_signals(client, result_signal):
    if not result_signal:
        return

    error_signal = result_signal.get("error")
    complete_signal = result_signal.get("complete")

    if error_signal:
        value = _write_signal(client, error_signal, "on_value", 1)
        logger.info("PLC result error signal set: %s%s.%02d=%s", error_signal["area"], int(error_signal["word_address"]), int(error_signal["bit"]), value)
    if complete_signal:
        value = _write_signal(client, complete_signal, "on_value", 1)
        logger.info("PLC result complete signal set after error: %s%s.%02d=%s", complete_signal["area"], int(complete_signal["word_address"]), int(complete_signal["bit"]), value)


def reset_result_signals(config=None):
    config = config or load_config()
    client = build_plc_client(config)
    if client is None:
        logger.info("PLC and test server are disabled by settings. Result signal reset is skipped.")
        return [{
            "name": "plc",
            "skipped": True,
            "reason": "PLC and test server are disabled in settings/plc_settings.yaml",
        }]

    result_signal = config.get("result_signal")
    if not result_signal:
        return []

    reset_targets = []
    try:
        for name in ("complete", "ok", "error"):
            signal = result_signal.get(name)
            if not signal:
                continue
            value = _write_signal(client, signal, "reset_value", 0)
            reset_targets.append({
                "name": name,
                "area": signal["area"],
                "word_address": int(signal["word_address"]),
                "bit": int(signal["bit"]),
                "value": value,
            })
    finally:
        client.close()
    return reset_targets


def run_monitor():
    config = load_config()
    client = build_plc_client(config)
    if client is None:
        logger.info("PLC monitor is disabled. Set plc.enabled=true or test_server.enabled=true in settings/plc_settings.yaml.")
        return

    monitor = config["monitor"]
    result_signal = config.get("result_signal")
    behavior = config.get("behavior", {})
    poll_interval = float(monitor.get("poll_interval_seconds", 1.0))
    reset_on_success = bool(behavior.get("reset_on_success", True))
    reset_value = int(behavior.get("reset_value", 0))

    logger.info(
        "PLC monitor started: %s%s.%02d",
        monitor["area"],
        int(monitor["word_address"]),
        int(monitor["bit"]),
    )

    try:
        while True:
            try:
                if is_snap_running():
                    logger.info("Judgment is already running. PLC polling is paused.")
                    time.sleep(poll_interval)
                    continue

                if _result_signals_are_pending(client, result_signal):
                    logger.warning("PLC result complete signal is still ON. Waiting for equipment or reset button to clear it.")
                    time.sleep(poll_interval)
                    continue

                is_on = client.read_bit(monitor["area"], monitor["word_address"], monitor["bit"])
                if is_on:
                    logger.info("PLC trigger detected. Monitoring is paused while judgment is running.")
                    try:
                        snap_result = run_snap_backend_sync()
                    except Exception:
                        write_error_result_signals(client, result_signal)
                        raise

                    logger.info("Snap backend completed: result=%s result_dict=%s", snap_result.result, snap_result.result_dict)
                    if reset_on_success:
                        client.write_bit(monitor["area"], monitor["word_address"], monitor["bit"], reset_value)
                        logger.info("PLC trigger reset to %s after completed judgment. NG results are retryable.", reset_value)
                    write_completed_result_signals(client, result_signal, snap_result.result)
            except Exception:
                logger.exception("PLC monitor iteration failed. Trigger/result bits were not fully updated.")

            time.sleep(poll_interval)
    finally:
        client.close()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        with SingleInstanceLock():
            run_monitor()
    except AlreadyRunningError as exc:
        logger.error(str(exc))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
