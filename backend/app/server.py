from __future__ import annotations

import cgi
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .review_engine import DrawingReviewEngine
from .review_store import ReviewStore


DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class ReviewRequestHandler(BaseHTTPRequestHandler):
    engine = DrawingReviewEngine()
    store = ReviewStore(DATA_DIR)

    def do_OPTIONS(self) -> None:
        self._send_empty(204)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json({"status": "ok"})
            return
        if path == "/api/reviews":
            reports = self.store.list_reports()
            self._send_json({"items": [self._compact_report(report) for report in reports]})
            return
        if path.startswith("/api/reviews/"):
            review_id = path.rsplit("/", 1)[-1]
            try:
                self._send_json(self.store.get_report(review_id))
            except FileNotFoundError:
                self._send_json({"error": "review_not_found"}, 404)
            return
        self._send_json({"error": "not_found"}, 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/reviews":
            self._send_json({"error": "not_found"}, 404)
            return

        try:
            upload = self._read_multipart_upload()
        except ValueError as exc:
            self._send_json({"error": str(exc)}, 400)
            return

        if upload["mode"] == "pair":
            dxf = upload["dxf"]
            pdf = upload["pdf"]
            report = self.engine.review_pair(
                dxf_filename=dxf["filename"],
                dxf_content=dxf["content"],
                pdf_filename=pdf["filename"],
                pdf_content=pdf["content"],
                dxf_content_type=dxf["content_type"],
                pdf_content_type=pdf["content_type"],
            )
            self.store.save_upload(dxf["filename"], dxf["content"], report["id"])
            self.store.save_upload(pdf["filename"], pdf["content"], report["id"])
        else:
            file_upload = upload["file"]
            report = self.engine.review(
                filename=file_upload["filename"],
                content=file_upload["content"],
                content_type=file_upload["content_type"],
            )
            self.store.save_upload(file_upload["filename"], file_upload["content"], report["id"])
        self.store.save_report(report)
        self._send_json(report, 201)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if not path.startswith("/api/reviews/"):
            self._send_json({"error": "not_found"}, 404)
            return

        review_id = path.rsplit("/", 1)[-1]
        try:
            self.store.delete_report(review_id)
        except FileNotFoundError:
            self._send_json({"error": "review_not_found"}, 404)
            return
        self._send_empty(204)

    def _read_multipart_upload(self) -> dict[str, Any]:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            raise ValueError("multipart_form_required")

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
            },
        )
        dxf_field = self._single_form_file(form, "dxfFile")
        pdf_field = self._single_form_file(form, "pdfFile")
        if dxf_field is not None or pdf_field is not None:
            if dxf_field is None:
                raise ValueError("dxf_file_required")
            if pdf_field is None:
                raise ValueError("pdf_file_required")
            dxf = self._read_form_file(dxf_field)
            pdf = self._read_form_file(pdf_field)
            if Path(dxf["filename"]).suffix.lower() != ".dxf":
                raise ValueError("dxf_file_must_be_dxf")
            if Path(pdf["filename"]).suffix.lower() != ".pdf":
                raise ValueError("pdf_file_must_be_pdf")
            return {"mode": "pair", "dxf": dxf, "pdf": pdf}

        field = self._single_form_file(form, "file")
        if field is None:
            raise ValueError("file_required")
        return {"mode": "single", "file": self._read_form_file(field)}

    def _single_form_file(self, form: cgi.FieldStorage, name: str) -> Any | None:
        if name not in form:
            return None
        field = form[name]
        if isinstance(field, list):
            field = field[0] if field else None
        if field is None or not getattr(field, "filename", ""):
            return None
        return field

    def _read_form_file(self, field: Any) -> dict[str, Any]:
        content = field.file.read()
        if not content:
            raise ValueError("empty_file")

        return {
            "filename": Path(field.filename).name,
            "content": content,
            "content_type": field.type or "application/octet-stream",
        }

    def _compact_report(self, report: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": report["id"],
            "createdAt": report["createdAt"],
            "file": report["file"],
            "summary": report["summary"],
        }

    def _send_empty(self, status: int) -> None:
        self.send_response(status)
        self._send_cors_headers()
        self.end_headers()

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[backend] {self.address_string()} - {format % args}")


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), ReviewRequestHandler)
    print(f"Backend running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run()
