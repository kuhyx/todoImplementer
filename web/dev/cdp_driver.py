"""Chromium CDP plumbing for viewport_check: launch, websocket client, layout probe."""

import base64
import json
import os
import re
import struct
import subprocess
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

import websocket

CHROMIUM = "/usr/bin/chromium"
PORT = int(os.environ.get("CDP_PORT", "9333"))
BAD_TEXT = re.compile(r"\[object Object\]|\bundefined\b|\bNaN\b")

PROBE = """(() => {
  const r = (el) => { const b = el.getBoundingClientRect(); return {l: b.left, r: b.right, t: b.top, b: b.bottom}; };
  const out = {sw: document.documentElement.scrollWidth, iw: innerWidth, ih: innerHeight, bad: [], hit: []};
  const text = document.body.innerText;
  const m = text.match(/\\[object Object\\]|\\bundefined\\b|\\bNaN\\b/g);
  if (m) out.bad = m;
  for (const sel of %s) {
    const el = document.querySelector(sel);
    if (!el || el.offsetParent === null && getComputedStyle(el).position !== 'fixed') { out.hit.push({sel, missing: true}); continue; }
    const b = r(el);
    const top = document.elementFromPoint((b.l + b.r) / 2, (b.t + b.b) / 2);
    out.hit.push({sel, inside: b.b <= innerHeight + 1 && b.r <= innerWidth + 1 && b.l >= -1 && b.t >= -1, reachable: el === top || el.contains(top)});
  }
  return out;
})()"""


def png_size(data: bytes) -> tuple[int, int]:
    """Return (width, height) from a PNG's IHDR chunk."""
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def capture_exact(call: Callable[..., dict[str, Any]], size: tuple[int, int], tries: int = 20) -> bytes:
    """Screenshot the viewport at exactly `size`.

    Right after a fresh headless launch the first capture can come back at the default 640x360 surface even
    though the metrics override is set, so clip explicitly and retry until the PNG has the requested size.
    """
    clip = {"x": 0, "y": 0, "width": size[0], "height": size[1], "scale": 1}
    for _ in range(tries):
        data = base64.b64decode(
            call("Page.captureScreenshot", format="png", captureBeyondViewport=True, clip=clip)["data"]
        )
        if png_size(data) == size:
            return data
        time.sleep(0.25)
    raise SystemExit(f"screenshot is {png_size(data)}, wanted {size}")


class Cdp:
    """Minimal CDP client over one page websocket; collects console errors and exceptions."""

    def __init__(self, ws_url: str) -> None:
        self.ws = websocket.create_connection(ws_url, suppress_origin=True, timeout=20)
        self.next_id = 0
        self.errors: list[str] = []
        self.size: tuple[int, int] | None = None

    def set_viewport(self, width: int, height: int, mobile: bool) -> None:
        """Emulate the viewport and remember it so shots come out at exactly this size."""
        self.call(
            "Emulation.setDeviceMetricsOverride",
            width=width,
            height=height,
            deviceScaleFactor=1,
            mobile=mobile,
        )
        self.size = (width, height)

    def call(self, method: str, **params: Any) -> dict[str, Any]:
        self.next_id += 1
        self.ws.send(json.dumps({"id": self.next_id, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("method") == "Runtime.exceptionThrown":
                self.errors.append(msg["params"]["exceptionDetails"]["text"])
            if msg.get("method") == "Runtime.consoleAPICalled" and msg["params"]["type"] == "error":
                self.errors.append(
                    " ".join(str(a.get("value", a.get("description", ""))) for a in msg["params"]["args"])
                )
            if msg.get("method") == "Log.entryAdded" and msg["params"]["entry"]["level"] == "error":
                self.errors.append(msg["params"]["entry"]["text"])
            if msg.get("id") == self.next_id:
                return msg.get("result", {})

    def js(self, expr: str) -> Any:
        result = self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return result.get("result", {}).get("value")

    def shot(self, path: Path) -> None:
        if self.size is None:
            path.write_bytes(base64.b64decode(self.call("Page.captureScreenshot", format="png")["data"]))
        else:
            path.write_bytes(capture_exact(self.call, self.size))


def launch(width: int, height: int, profile: str) -> subprocess.Popen[bytes]:
    args = [
        CHROMIUM,
        "--headless=new",
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={profile}",
        "--disable-extensions",
        "--no-first-run",
        "--disable-gpu",
        f"--window-size={width},{height}",
        "about:blank",
    ]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1).read()
            return proc
        except OSError:
            time.sleep(0.2)
    proc.kill()
    raise SystemExit("chromium did not start")


def page_ws() -> str:
    targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5).read())
    return str(next(t for t in targets if t["type"] == "page")["webSocketDebuggerUrl"])


def goto(cdp: Cdp, url: str, wait: float = 1.6) -> None:
    cdp.call("Page.navigate", url=url)
    time.sleep(wait)


def probe(cdp: Cdp, selectors: list[str]) -> dict[str, Any]:
    result = cdp.js(PROBE % json.dumps(selectors))
    problems = []
    if result["sw"] > result["iw"]:
        problems.append(f"horizontal overflow {result['sw']}>{result['iw']}")
    if result["bad"]:
        problems.append(f"bad text {result['bad']}")
    problems += [f"{h['sel']}: missing" for h in result["hit"] if h.get("missing")]
    problems += [
        f"{h['sel']}: outside viewport" for h in result["hit"] if not h.get("missing") and not h["inside"]
    ]
    problems += [f"{h['sel']}: covered" for h in result["hit"] if not h.get("missing") and not h["reachable"]]
    return {"problems": problems}
