"""Usage-page viewport driver: own headless chromium (CDP 9334), one size per call, screenshots + assertions.

Usage: usage_check.py --size 390x844 --out DIR [--url http://127.0.0.1:4398/usage/] [--scheme dark|light]
Per route: wait for the view, screenshot (viewport + full page), flag console errors, horizontal overflow and
"[object Object]" / undefined / NaN text; on the sessions table also click every th and assert the order changes.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

import websocket
from cdp_driver import capture_exact

CHROMIUM = "/usr/bin/chromium"
PORT = 9334
BAD = re.compile(r"\[object Object\]|\bundefined\b|\bNaN\b")
ROUTES = {
    "overview": "#/overview",
    "sessions": "#/sessions",
    "session": "#/s/__KEY__",
    "items": "#/items",
    "efficiency": "#/efficiency",
    "levers": "#/levers",
    "context": "#/context",
    "file": "#/f/__FILE__",
    "anomalies": "#/anomalies",
    "ab": "#/ab",
    "more": "#/more",
    "hooks": "#/more/hooks",
}
READY = "(() => { const m = document.querySelector('usage-app main'); return !!m && !m.hasAttribute('aria-busy') && m.querySelector('.view,.error') !== null; })()"
FACTS = """(() => ({
  sw: document.documentElement.scrollWidth, iw: innerWidth, ih: innerHeight, sh: document.documentElement.scrollHeight,
  text: (() => { const c = document.body.cloneNode(true); c.querySelectorAll('tbody, pre, .log').forEach((n) => n.remove()); return c.textContent; })(), err: document.querySelector('.error')?.innerText ?? null,
  tables: document.querySelectorAll('usage-table').length, charts: document.querySelectorAll('.chart svg').length,
}))()"""
SORT_ALL = """(() => {
  const t = document.querySelector('usage-table'); const out = [];
  for (const th of t.querySelectorAll('th[data-key]')) {
    const first = () => [...t.querySelectorAll('tbody tr')].slice(0, 8).map((r) => r.innerText).join('|');
    const before = first(); th.querySelector('button').click(); const asc = first(); th.querySelector('button').click();
    const desc = first(); th.querySelector('button').click();
    out.push([th.dataset.key, before !== asc || before !== desc || asc !== desc]);
  }
  return out;
})()"""


class Cdp:
    def __init__(self, ws_url: str) -> None:
        self.ws = websocket.create_connection(ws_url, suppress_origin=True, timeout=30)
        self.next_id = 0
        self.errors: list[str] = []
        self.size: tuple[int, int] = (0, 0)

    def call(self, method: str, **params: Any) -> dict[str, Any]:
        self.next_id += 1
        self.ws.send(json.dumps({"id": self.next_id, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            kind = msg.get("method")
            if kind == "Runtime.exceptionThrown":
                self.errors.append(msg["params"]["exceptionDetails"]["text"])
            elif kind == "Runtime.consoleAPICalled" and msg["params"]["type"] == "error":
                self.errors.append(
                    " ".join(str(a.get("value", a.get("description", ""))) for a in msg["params"]["args"])
                )
            elif kind == "Log.entryAdded" and msg["params"]["entry"]["level"] == "error":
                self.errors.append(
                    f"{msg['params']['entry']['text']} {msg['params']['entry'].get('url', '')}"
                )
            if msg.get("id") == self.next_id:
                return msg.get("result", {})

    def js(self, expr: str) -> Any:
        return (
            self.call("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
            .get("result", {})
            .get("value")
        )

    def shot(self, path: Path, full: bool) -> None:
        params: dict[str, Any] = {"format": "png"}
        if full:
            size = self.call("Page.getLayoutMetrics")["cssContentSize"]
            params.update(
                captureBeyondViewport=True,
                clip={
                    "x": 0,
                    "y": 0,
                    "width": size["width"],
                    "height": min(size["height"], 6000),
                    "scale": 1,
                },
            )
        if full:
            path.write_bytes(base64.b64decode(self.call("Page.captureScreenshot", **params)["data"]))
        else:
            path.write_bytes(capture_exact(self.call, self.size))


def launch(width: int, height: int, profile: str) -> subprocess.Popen[bytes]:
    proc = subprocess.Popen(
        [
            CHROMIUM,
            "--headless=new",
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={profile}",
            "--disable-extensions",
            "--no-first-run",
            "--disable-gpu",
            f"--window-size={width},{height}",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1).read()
            return proc
        except OSError:
            time.sleep(0.2)
    proc.kill()
    raise SystemExit("chromium did not start")


def wait_ready(cdp: Cdp, limit: float = 12.0) -> float:
    start = time.time()
    while time.time() - start < limit:
        if cdp.js(READY):
            return time.time() - start
        time.sleep(0.1)
    return -1.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--size", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--url", default="http://127.0.0.1:4398/usage/")
    parser.add_argument("--scheme", default="dark")
    parser.add_argument("--routes", default=",".join(ROUTES))
    args = parser.parse_args()
    width, height = (int(n) for n in args.size.split("x"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    profile = tempfile.mkdtemp(prefix="usage-chromium-")
    proc = launch(width, height, profile)
    problems: list[str] = []
    try:
        targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=5).read())
        cdp = Cdp(next(t["webSocketDebuggerUrl"] for t in targets if t["type"] == "page"))
        for domain in ("Page", "Runtime", "Log"):
            cdp.call(f"{domain}.enable")
        cdp.call(
            "Emulation.setDeviceMetricsOverride",
            width=width,
            height=height,
            deviceScaleFactor=1,
            mobile=width < 700,
        )
        cdp.size = (width, height)
        cdp.call(
            "Emulation.setEmulatedMedia", features=[{"name": "prefers-color-scheme", "value": args.scheme}]
        )
        keys = {}
        cdp.call("Page.navigate", url=args.url + "#/sessions")
        cdp.js("location.reload()")
        time.sleep(0.5)
        wait_ready(cdp)
        keys["__KEY__"] = cdp.js(
            "document.querySelector('tbody a').getAttribute('href').split('/')[2].split('?')[0]"
        )
        cdp.call("Page.navigate", url=args.url + "#/context")
        cdp.js("location.reload()")
        time.sleep(0.5)
        wait_ready(cdp)
        keys["__FILE__"] = cdp.js(
            "document.querySelector('tbody a').getAttribute('href').split('/')[2].split('?')[0]"
        )
        for name in args.routes.split(","):
            hash_ = ROUTES[name]
            for token, value in keys.items():
                hash_ = hash_.replace(token, str(value))
            cdp.call("Page.navigate", url=args.url + hash_)
            cdp.js("location.reload()")
            took = wait_ready(cdp)
            time.sleep(0.4)
            facts = cdp.js(FACTS)
            tag = f"{args.size}-{name}"
            cdp.shot(out / f"{tag}.png", full=False)
            cdp.shot(out / f"{tag}-full.png", full=True)
            found = [f"{name}: not ready in 12 s"] if took < 0 else []
            if facts["err"]:
                found.append(f"{name}: error banner {facts['err']!r}")
            if facts["sw"] > facts["iw"]:
                found.append(f"{name}: horizontal overflow {facts['sw']}>{facts['iw']}")
            if BAD.search(facts["text"]):
                found.append(f"{name}: bad text {BAD.findall(facts['text'])[:3]}")
            if name == "sessions":
                for key, changed in cdp.js(SORT_ALL):
                    if not changed:
                        found.append(f"sessions: th {key} did not change the order")
            problems += found
            print(
                json.dumps(
                    {
                        "route": name,
                        "ready_s": round(took, 2),
                        "tables": facts["tables"],
                        "charts": facts["charts"],
                        "scroll_h": facts["sh"],
                        "problems": found,
                    }
                )
            )
        problems += [f"console: {e}" for e in cdp.errors]
    finally:
        proc.terminate()
        shutil.rmtree(profile, ignore_errors=True)
    print("PROBLEMS" if problems else "OK", *problems, sep="\n")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
