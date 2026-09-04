# -*- coding: utf-8 -*-
"""错题本服务：本地或网站部署。"""
from __future__ import annotations

import json
import mimetypes
import os
import socket
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import bank

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8765"))
WEB = Path(__file__).resolve().parent / "web"
MAX_BODY = 12 * 1024 * 1024
MAX_IMAGE = 8 * 1024 * 1024


def decode_data_url(data_url: str) -> tuple[bytes, str]:
    if not data_url:
        return b"", ""
    header, _, body = data_url.partition(",")
    ext = "jpg"
    if "image/png" in header:
        ext = "png"
    elif "image/webp" in header:
        ext = "webp"
    elif "image/jpeg" in header or "image/jpg" in header:
        ext = "jpg"
    raw = base64_decode(body)
    return raw, ext


def base64_decode(body: str) -> bytes:
    import base64
    return base64.b64decode(body)


def parse_notebook_api(path: str) -> tuple[str, str] | None:
    """返回 (notebook_id, rest)。rest 如 bank、items、items/xxx/review、images/a.jpg"""
    prefix = "/api/n/"
    if not path.startswith(prefix):
        return None
    rest = path[len(prefix):]
    nb, _, tail = rest.partition("/")
    if not nb:
        return None
    return nb, tail


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print("[%s] %s" % (self.log_date_time_string(), fmt % args), flush=True)

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(code, data, "application/json; charset=utf-8")

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("内容过大")
        raw = self.rfile.read(length) if length else b"{}"
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        parsed_nb = parse_notebook_api(path)
        if parsed_nb:
            try:
                nb, tail = parsed_nb
                bank.validate_notebook(nb)
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            qs = parse_qs(parsed.query)
            if tail == "bank":
                b = bank.load_bank(nb)
                self._json(200, {"ok": True, "notebook": nb, "stats": bank.stats(b, nb), "items": b.get("items", [])})
                return
            if tail == "stats":
                self._json(200, {"ok": True, "notebook": nb, **bank.stats(notebook_id=nb)})
                return
            if tail == "quiz":
                n = int((qs.get("n") or ["8"])[0])
                subject = (qs.get("subject") or [""])[0]
                items = bank.quiz_items(n=n, subject=subject, notebook_id=nb)
                self._json(200, {"ok": True, "items": items})
                return
            if tail.startswith("images/"):
                name = Path(tail[len("images/"):]).name
                file_path = bank.image_dir(nb) / name
                if not file_path.exists():
                    self._json(404, {"ok": False, "error": "图片不存在"})
                    return
                ctype = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
                self._send(200, file_path.read_bytes(), ctype)
                return
            self._json(404, {"ok": False, "error": "接口不存在"})
            return
        if path == "/api/health":
            self._json(200, {"ok": True})
            return
        if path == "/" or path == "/index.html":
            target = WEB / "index.html"
        else:
            rel = path.lstrip("/").replace("\\", "/")
            target = (WEB / rel).resolve()
            try:
                target.relative_to(WEB.resolve())
            except ValueError:
                self._json(403, {"ok": False, "error": "禁止访问"})
                return
        if not target.exists() or not target.is_file():
            self._json(404, {"ok": False, "error": "页面不存在"})
            return
        ctype = mimetypes.guess_type(str(target))[0] or "text/plain"
        if ctype.startswith("text/"):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            payload = self._read_json()
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return
        except json.JSONDecodeError:
            self._json(400, {"ok": False, "error": "JSON 无效"})
            return
        if path == "/api/notebooks":
            nb = bank.create_notebook()
            self._json(200, {"ok": True, "id": nb})
            return
        parsed_nb = parse_notebook_api(path)
        if not parsed_nb:
            self._json(404, {"ok": False, "error": "接口不存在"})
            return
        try:
            nb, tail = parsed_nb
            bank.validate_notebook(nb)
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return
        if tail == "items":
            image_file = payload.get("imageFile") or ""
            data_url = payload.get("imageData") or ""
            if data_url:
                raw, ext = decode_data_url(data_url)
                if len(raw) > MAX_IMAGE:
                    self._json(400, {"ok": False, "error": "图片太大，请压缩后再传"})
                    return
                name = "%s.%s" % (uuid.uuid4().hex, ext)
                bank.ensure_dirs(nb)
                (bank.image_dir(nb) / name).write_bytes(raw)
                image_file = name
            item_payload = {k: v for k, v in payload.items() if k != "imageData"}
            if image_file:
                item_payload["imageFile"] = image_file
            item = bank.upsert_item(item_payload, nb)
            self._json(200, {"ok": True, "item": item, "stats": bank.stats(notebook_id=nb)})
            return
        if tail.startswith("items/") and tail.endswith("/review"):
            item_id = tail[len("items/"):-len("/review")]
            result = payload.get("result")
            try:
                item = bank.review_item(item_id, result, nb)
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            if not item:
                self._json(404, {"ok": False, "error": "未找到该错题"})
                return
            self._json(200, {"ok": True, "item": item, "stats": bank.stats(notebook_id=nb)})
            return
        self._json(404, {"ok": False, "error": "接口不存在"})

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        parsed_nb = parse_notebook_api(path)
        if not parsed_nb:
            self._json(404, {"ok": False, "error": "接口不存在"})
            return
        try:
            nb, tail = parsed_nb
            bank.validate_notebook(nb)
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return
        if tail.startswith("items/"):
            item_id = tail[len("items/"):]
            ok = bank.delete_item(item_id, nb)
            if not ok:
                self._json(404, {"ok": False, "error": "未找到该错题"})
                return
            self._json(200, {"ok": True, "stats": bank.stats(notebook_id=nb)})
            return
        self._json(404, {"ok": False, "error": "接口不存在"})


def lan_urls(port: int) -> list[str]:
    urls = ["http://127.0.0.1:%s" % port]
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                urls.append("http://%s:%s" % (ip, port))
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("223.5.5.5", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            urls.append("http://%s:%s" % (ip, port))
    except OSError:
        pass
    seen = []
    for u in urls:
        if u not in seen:
            seen.append(u)
    return seen


def main() -> None:
    bank.ensure_dirs("local")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print("错题本已启动。本机打开：", flush=True)
    for url in lan_urls(PORT):
        print("  %s" % url, flush=True)
    print("网站部署时平台会提供 https 地址；每人打开会生成专属错题本链接。", flush=True)
    print("按 Ctrl+C 结束。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止", flush=True)


if __name__ == "__main__":
    main()
