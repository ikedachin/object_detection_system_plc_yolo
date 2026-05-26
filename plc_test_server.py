import argparse
import html
import sys
from pathlib import Path
from threading import Lock

import uvicorn
import yaml
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel


THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parent
DJANGO_ROOT = PROJECT_ROOT / "yolo_system"
SETTINGS_PATH = PROJECT_ROOT / "settings" / "plc_settings.yaml"

if str(DJANGO_ROOT) not in sys.path:
    sys.path.insert(0, str(DJANGO_ROOT))

app = FastAPI(title="Dummy PLC Test Server")
memory_lock = Lock()
memory = {}


class BitWrite(BaseModel):
    area: str
    word_address: int
    bit: int
    value: int


def load_config(path=SETTINGS_PATH):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def bit_key(area, word_address, bit):
    return f"{area}{int(word_address)}.{int(bit):02d}"


def configured_signals():
    config = load_config()
    signals = []
    monitor = config.get("monitor", {})
    if monitor:
        signals.append(("trigger", monitor))
    result_signal = config.get("result_signal", {})
    for name in ("complete", "ok", "error"):
        signal = result_signal.get(name)
        if signal:
            signals.append((name, signal))
    return signals


def ensure_configured_bits():
    with memory_lock:
        for _, signal in configured_signals():
            memory.setdefault(bit_key(signal["area"], signal["word_address"], signal["bit"]), 0)


@app.on_event("startup")
def startup():
    ensure_configured_bits()


@app.get("/", response_class=HTMLResponse)
def index():
    ensure_configured_bits()
    rows = []
    with memory_lock:
        bits = dict(sorted(memory.items()))
    labels = {bit_key(sig["area"], sig["word_address"], sig["bit"]): name for name, sig in configured_signals()}

    for key, value in bits.items():
        label = labels.get(key, "")
        rows.append(
            "<tr>"
            f"<td>{html.escape(label)}</td>"
            f"<td><code>{html.escape(key)}</code></td>"
            f"<td><strong>{value}</strong></td>"
            "<td>"
            f"<button onclick=\"writeBit('{html.escape(key)}', 1)\">ON</button>"
            f"<button onclick=\"writeBit('{html.escape(key)}', 0)\">OFF</button>"
            "</td>"
            "</tr>"
        )

    return f"""
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dummy PLC</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; background: #f6f8fb; color: #20242a; }}
    header {{ display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 20px; }}
    table {{ border-collapse: collapse; width: 100%; background: white; }}
    th, td {{ border: 1px solid #d8dee9; padding: 10px; text-align: left; }}
    th {{ background: #e9eef5; }}
    button {{ margin-right: 8px; padding: 6px 12px; border: 1px solid #9aa7b8; background: white; cursor: pointer; }}
    button.primary {{ background: #2563eb; border-color: #2563eb; color: white; }}
    button.danger {{ background: #b91c1c; border-color: #b91c1c; color: white; }}
    .actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Dummy PLC Test Server</h1>
      <p>PLC監視スクリプトのテスト用メモリです。</p>
    </div>
    <div class="actions">
      <button class="primary" onclick="setTrigger()">D100.00 Trigger ON</button>
      <button onclick="resetResults()">Result Reset</button>
      <button class="danger" onclick="clearAll()">All OFF</button>
      <button onclick="location.reload()">Reload</button>
    </div>
  </header>
  <table>
    <thead><tr><th>用途</th><th>ビット</th><th>値</th><th>操作</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  <script>
    function splitKey(key) {{
      const match = key.match(/^([A-Za-z]+)(\\d+)\\.(\\d+)$/);
      return {{ area: match[1], word_address: Number(match[2]), bit: Number(match[3]) }};
    }}
    async function writeBit(key, value) {{
      const bit = splitKey(key);
      await fetch('/api/bit', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ ...bit, value }})
      }});
      location.reload();
    }}
    async function setTrigger() {{
      await fetch('/api/trigger', {{ method: 'POST' }});
      location.reload();
    }}
    async function resetResults() {{
      await fetch('/api/reset-results', {{ method: 'POST' }});
      location.reload();
    }}
    async function clearAll() {{
      await fetch('/api/clear-all', {{ method: 'POST' }});
      location.reload();
    }}
  </script>
</body>
</html>
"""


@app.get("/api/bits")
def get_bits():
    ensure_configured_bits()
    with memory_lock:
        return {"bits": dict(sorted(memory.items()))}


@app.get("/api/bit/{area}/{word_address}/{bit}")
def get_bit(area: str, word_address: int, bit: int):
    ensure_configured_bits()
    key = bit_key(area, word_address, bit)
    with memory_lock:
        return {"key": key, "value": int(memory.get(key, 0))}


@app.post("/api/bit")
def set_bit(payload: BitWrite):
    ensure_configured_bits()
    key = bit_key(payload.area, payload.word_address, payload.bit)
    with memory_lock:
        memory[key] = 1 if int(payload.value) else 0
        return {"key": key, "value": memory[key]}


@app.post("/api/trigger")
def set_trigger():
    config = load_config()
    monitor = config["monitor"]
    key = bit_key(monitor["area"], monitor["word_address"], monitor["bit"])
    with memory_lock:
        memory[key] = 1
    return {"key": key, "value": 1}


@app.post("/api/reset-results")
def reset_results():
    config = load_config()
    result_signal = config.get("result_signal", {})
    reset = {}
    with memory_lock:
        for name in ("complete", "ok", "error"):
            signal = result_signal.get(name)
            if not signal:
                continue
            key = bit_key(signal["area"], signal["word_address"], signal["bit"])
            memory[key] = int(signal.get("reset_value", 0))
            reset[key] = memory[key]
    return {"reset": reset}


@app.post("/api/clear-all")
def clear_all():
    ensure_configured_bits()
    with memory_lock:
        for key in list(memory):
            memory[key] = 0
    return {"bits": dict(sorted(memory.items()))}


def main():
    config = load_config()
    server = config.get("test_server", {})
    uvicorn.run(
        "plc_test_server:app",
        host=server.get("host", "127.0.0.1"),
        port=int(server.get("port", 8010)),
        reload=False,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run dummy PLC test server.")
    parser.parse_args()
    main()
