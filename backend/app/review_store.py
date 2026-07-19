from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SavedUpload:
    review_id: str
    path: Path


class ReviewStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.upload_dir = base_dir / "uploads"
        self.report_dir = base_dir / "reviews"
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(self, filename: str, content: bytes, review_id: str | None = None) -> SavedUpload:
        safe_name = self._safe_filename(filename)
        resolved_review_id = review_id or self._safe_filename(Path(filename).stem or "drawing")
        path = self.upload_dir / f"{resolved_review_id}-{safe_name}"
        path.write_bytes(content)
        return SavedUpload(review_id=resolved_review_id, path=path)

    def save_report(self, report: dict) -> None:
        path = self.report_dir / f"{report['id']}.json"
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_report(self, review_id: str) -> dict:
        path = self.report_dir / f"{review_id}.json"
        if not path.exists():
            raise FileNotFoundError(review_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def list_reports(self) -> list[dict]:
        reports = []
        for path in sorted(self.report_dir.glob("*.json"), reverse=True):
            reports.append(json.loads(path.read_text(encoding="utf-8")))
        return reports

    def delete_report(self, review_id: str) -> None:
        report_path = self.report_dir / f"{review_id}.json"
        if not report_path.exists():
            raise FileNotFoundError(review_id)

        report_path.unlink()
        for upload_path in self.upload_dir.glob(f"{review_id}-*"):
            upload_path.unlink()

    def _safe_filename(self, filename: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", filename).strip("._")
        return cleaned or "drawing"
