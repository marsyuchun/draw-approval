from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import re
from typing import Any

from .drawing_models import DrawingDimension
from .drawing_parser import ParserFactory
from .pdf_parser import PdfParser
from .pdf_preview_service import PdfPreviewService
from .review_visualizer import ReviewVisualizer


PRIMARY_EXTENSION = ".dxf"
FALLBACK_EXTENSIONS = {".pdf"}


class DrawingReviewEngine:
    """Creates a first-pass review report from uploaded drawing bytes."""

    def __init__(self) -> None:
        self.visualizer = ReviewVisualizer()
        self.parser_factory = ParserFactory()
        self.pdf_previewer = PdfPreviewService()

    def review(self, filename: str, content: bytes, content_type: str) -> dict[str, Any]:
        extension = Path(filename).suffix.lower()
        parser = self.parser_factory.for_file(filename, content_type)
        parsed = parser.parse(filename, content)
        issues = [self._issue_from_warning(warning) for warning in parsed.warnings]

        if extension == ".dwg":
            issues.append(
                self._issue(
                    code="DWG_REQUIRES_CONVERSION",
                    severity="Notice",
                    title="DWG 需要先转换为 DXF",
                    description="当前解析层以 DXF 为主输入；DWG 是封闭格式，建议通过 ODA File Converter 或 CAD 软件导出 DXF。",
                    suggestion="请上传 DXF，或先把 DWG 转换为 DXF。",
                    locations=[],
                )
            )

        dimensions = parsed.dimensions
        issues.extend(self._check_duplicate_dimensions(dimensions))
        issues.extend(self._check_invalid_dimensions(dimensions))

        if extension == PRIMARY_EXTENSION and not dimensions and not parsed.warnings:
            issues.append(
                self._issue(
                    code="NO_DIMENSIONS_FOUND",
                    severity="Warning",
                    title="未识别到尺寸标注",
                    description="DXF 中未发现可审查的尺寸文字或 DIMENSION 实体。",
                    suggestion="确认图纸导出时保留尺寸标注，或检查尺寸是否已被转成普通几何线。",
                    locations=[],
                )
            )
        elif extension in FALLBACK_EXTENSIONS and not dimensions and not parsed.warnings:
            issues.append(
                self._issue(
                    code="PDF_LOW_CONFIDENCE_NO_DIMENSIONS",
                    severity="Warning",
                    title="PDF 兜底识别未发现尺寸",
                    description="PDF 不是首选审查格式，当前仅能从文本层或 OCR 结果中兜底识别。",
                    suggestion="请优先上传 DXF；扫描 PDF 需要安装并配置 PaddleOCR。",
                    locations=[],
                )
            )

        return {
            "id": self._make_review_id(filename, content),
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "file": {
                "name": filename,
                "extension": extension or "unknown",
                "size": len(content),
                "contentType": content_type,
            },
            "summary": self._summarize(issues),
            "issues": issues,
            "visual": self.visualizer.build(parsed, issues),
            "engine": {
                "mode": "dxf-first-parser",
                "source": parsed.source_format,
                "confidence": parsed.confidence,
                "checks": [
                    "DXF 矢量解析",
                    "PDF 兜底识别",
                    "重复尺寸标注检查",
                    "非法尺寸值检查",
                    "真实坐标 SVG 标注",
                ],
            },
        }

    def review_pair(
        self,
        dxf_filename: str,
        dxf_content: bytes,
        pdf_filename: str,
        pdf_content: bytes,
        dxf_content_type: str = "application/dxf",
        pdf_content_type: str = "application/pdf",
    ) -> dict[str, Any]:
        parser = self.parser_factory.for_file(dxf_filename, dxf_content_type)
        parsed = parser.parse(dxf_filename, dxf_content)
        pdf_parsed = PdfParser().parse(pdf_filename, pdf_content)
        pdf_preview = self.pdf_previewer.render_first_page(pdf_content)
        issues = [self._issue_from_warning(warning) for warning in parsed.warnings]
        if pdf_preview.get("warning"):
            issues.append(self._issue_from_warning(pdf_preview["warning"]))

        dimensions = parsed.dimensions
        issues.extend(self._check_duplicate_dimensions(dimensions))
        repeated_diameter_issues = self._check_repeated_diameter_dimensions(dimensions)
        issues.extend(repeated_diameter_issues)
        ignored_pdf_values = self._issue_dimension_values(repeated_diameter_issues)
        issues.extend(self._check_nearby_pdf_duplicate_dimensions(pdf_parsed.texts, ignored_values=ignored_pdf_values))
        issues.extend(self._check_invalid_dimensions(dimensions))
        if not dimensions and not parsed.warnings:
            issues.append(
                self._issue(
                    code="NO_DIMENSIONS_FOUND",
                    severity="Warning",
                    title="未识别到尺寸标注",
                    description="DXF 中未发现可审查的尺寸文字或 DIMENSION 实体。",
                    suggestion="确认 SolidWorks 导出 DXF 时保留尺寸标注，且不要把尺寸全部转成普通几何线。",
                    locations=[],
                )
            )
        issues = self._prefer_pdf_locations(issues, pdf_parsed.texts)

        review_id = self._make_review_id(f"{dxf_filename}+{pdf_filename}", dxf_content + pdf_content)
        return {
            "id": review_id,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "file": {
                "name": dxf_filename,
                "extension": ".dxf",
                "size": len(dxf_content),
                "contentType": dxf_content_type,
                "companion": {
                    "name": pdf_filename,
                    "extension": ".pdf",
                    "size": len(pdf_content),
                    "contentType": pdf_content_type,
                    "role": "display-base",
                },
            },
            "summary": self._summarize(issues),
            "issues": issues,
            "visual": self.visualizer.build_pdf_dxf(parsed, issues, pdf_preview),
            "engine": {
                "mode": "pdf-dxf-pair",
                "source": "dxf+pdf",
                "confidence": parsed.confidence,
                "checks": [
                    "PDF 矢量底图显示",
                    "DXF 矢量语义解析",
                    "重复尺寸标注检查",
                    "非法尺寸值检查",
                    "PDF 文本层坐标 overlay 标注",
                ],
            },
        }

    def _check_duplicate_dimensions(self, dimensions: list[DrawingDimension]) -> list[dict[str, Any]]:
        seen: dict[tuple[float, str], DrawingDimension] = {}
        issues = []

        for dimension in dimensions:
            if dimension.value <= 0:
                continue
            key = (dimension.value, dimension.unit)
            previous = seen.get(key)
            if previous is not None and self._same_dimension_location(previous, dimension):
                issues.append(
                    self._issue(
                        code="DUPLICATE_DIMENSION",
                        severity="Warning",
                        title="疑似重复标注实体",
                        description=f"检测到同一位置附近重复出现尺寸 {dimension.value:g}{dimension.unit}，可能是同一标注被重复导出或叠放。",
                        suggestion="检查该位置是否存在重叠尺寸文本或重复 DIMENSION 实体；不同视图、不同特征上的同值尺寸不按冗余处理。",
                        evidence=[previous.raw, dimension.raw],
                        locations=[previous.location.to_dict(), dimension.location.to_dict()],
                    )
                )
            else:
                seen[key] = dimension

        return issues

    def _same_dimension_location(self, first: DrawingDimension, second: DrawingDimension) -> bool:
        first_location = first.location
        second_location = second.location
        if first_location.page != second_location.page or first_location.source != second_location.source:
            return False
        return self._bbox_overlap_ratio(first_location.bbox, second_location.bbox) > 0.45 or self._bbox_centers_close(
            first_location.bbox,
            second_location.bbox,
        )

    def _bbox_overlap_ratio(self, first: dict[str, float], second: dict[str, float]) -> float:
        left = max(float(first["x"]), float(second["x"]))
        top = max(float(first["y"]), float(second["y"]))
        right = min(float(first["x"]) + float(first["width"]), float(second["x"]) + float(second["width"]))
        bottom = min(float(first["y"]) + float(first["height"]), float(second["y"]) + float(second["height"]))
        if right <= left or bottom <= top:
            return 0.0
        overlap = (right - left) * (bottom - top)
        first_area = max(float(first["width"]) * float(first["height"]), 1.0)
        second_area = max(float(second["width"]) * float(second["height"]), 1.0)
        return overlap / min(first_area, second_area)

    def _bbox_centers_close(self, first: dict[str, float], second: dict[str, float]) -> bool:
        first_center = (float(first["x"]) + float(first["width"]) / 2, float(first["y"]) + float(first["height"]) / 2)
        second_center = (float(second["x"]) + float(second["width"]) / 2, float(second["y"]) + float(second["height"]) / 2)
        distance = ((first_center[0] - second_center[0]) ** 2 + (first_center[1] - second_center[1]) ** 2) ** 0.5
        tolerance = max(float(first["width"]), float(first["height"]), float(second["width"]), float(second["height"])) * 0.6
        return distance <= tolerance

    def _check_repeated_diameter_dimensions(self, dimensions: list[DrawingDimension]) -> list[dict[str, Any]]:
        groups: dict[tuple[float, str], list[DrawingDimension]] = {}
        for dimension in dimensions:
            if not self._is_diameter_dimension(dimension.raw) or dimension.value <= 0:
                continue
            groups.setdefault((dimension.value, dimension.unit), []).append(dimension)

        issues = []
        for (value, unit), group in groups.items():
            if len(group) < 2:
                continue
            issues.append(
                self._issue(
                    code="REPEATED_DIAMETER_DIMENSION",
                    severity="Warning",
                    title="重复直径尺寸标注",
                    description=f"检测到同一张图纸中重复出现直径尺寸 Φ{value:g}{unit}，可能是同一特征在多个视图中被重复标注。",
                    suggestion="确认这些 Φ 尺寸是否表达同一特征；如果是同一特征，建议保留一个最清晰、最接近加工基准的标注。",
                    evidence=[f"Φ{dimension.value:g}" for dimension in group],
                    locations=[dimension.location.to_dict() for dimension in group],
                )
            )
        return issues

    def _is_diameter_dimension(self, raw: str) -> bool:
        normalized = str(raw).lower()
        return "%%c" in normalized or "φ" in normalized or "dia" in normalized

    def _prefer_pdf_locations(self, issues: list[dict[str, Any]], pdf_texts: list[Any]) -> list[dict[str, Any]]:
        if not pdf_texts:
            return issues

        used_indexes: set[int] = set()
        for issue in issues:
            matched_locations = []
            for evidence in issue.get("evidence", []):
                match = self._find_pdf_text_location(str(evidence), pdf_texts, used_indexes)
                if match is None:
                    continue
                used_indexes.update(match["indexes"])
                matched_locations.append(match["location"])
            if matched_locations:
                issue["locations"] = matched_locations
        return issues

    def _find_pdf_text_location(self, value: str, pdf_texts: list[Any], used_indexes: set[int]) -> dict[str, Any] | None:
        normalized = self._normalize_dimension_text(value)
        if not normalized:
            return None
        for index, text in enumerate(pdf_texts):
            if index in used_indexes:
                continue
            if self._normalize_dimension_text(text.value) == normalized:
                return {"indexes": [index], "location": text.location.to_dict()}

        for start in range(len(pdf_texts)):
            if start in used_indexes:
                continue
            combined = ""
            indexes = []
            for end in range(start, min(start + 5, len(pdf_texts))):
                if end in used_indexes:
                    break
                if pdf_texts[end].location.page != pdf_texts[start].location.page:
                    break
                combined += self._normalize_dimension_text(pdf_texts[end].value)
                indexes.append(end)
                if combined == normalized:
                    return {"indexes": indexes, "location": self._merge_pdf_locations([pdf_texts[i].location for i in indexes])}
                if len(combined) > len(normalized):
                    break
        return None

    def _merge_pdf_locations(self, locations: list[Any]) -> dict[str, Any]:
        xs = []
        ys = []
        for location in locations:
            bbox = location.bbox
            xs.extend([float(bbox["x"]), float(bbox["x"]) + float(bbox["width"])])
            ys.extend([float(bbox["y"]), float(bbox["y"]) + float(bbox["height"])])
        return {
            "page": locations[0].page,
            "source": locations[0].source,
            "bbox": {
                "x": min(xs),
                "y": min(ys),
                "width": max(xs) - min(xs),
                "height": max(ys) - min(ys),
            },
            "text": " ".join(location.text for location in locations),
        }

    def _normalize_dimension_text(self, value: str) -> str:
        normalized = str(value).upper().replace("%%C", "").replace("Φ", "").replace("φ", "").replace("DIA", "")
        return "".join(normalized.split())

    def _check_invalid_dimensions(self, dimensions: list[DrawingDimension]) -> list[dict[str, Any]]:
        issues = []
        for dimension in dimensions:
            if dimension.value <= 0:
                issues.append(
                    self._issue(
                        code="INVALID_DIMENSION_VALUE",
                        severity="Critical",
                        title="尺寸值不合法",
                        description=f"检测到非正尺寸 {dimension.raw}，机械图纸尺寸应大于 0。",
                        suggestion="检查尺寸录入、比例或 OCR 识别结果，必要时修改源图纸标注。",
                        evidence=[dimension.raw],
                        locations=[dimension.location.to_dict()],
                    )
                )
        return issues

    def _check_nearby_pdf_duplicate_dimensions(self, pdf_texts: list[Any], ignored_values: set[float] | None = None) -> list[dict[str, Any]]:
        ignored_values = ignored_values or set()
        candidates = []
        for text in pdf_texts:
            value = self._pdf_dimension_value(text.value)
            if value is None or value < 10 or value in ignored_values:
                continue
            candidates.append({"value": value, "raw": text.value, "location": text.location})

        issues = []
        for first_index, first in enumerate(candidates):
            for second_index in range(first_index + 1, len(candidates)):
                second = candidates[second_index]
                if first["value"] != second["value"]:
                    continue
                if first["location"].page != second["location"].page:
                    continue
                if not self._pdf_dimension_texts_near(first["location"].bbox, second["location"].bbox):
                    continue
                issues.append(
                    self._issue(
                        code="NEARBY_DUPLICATE_DIMENSION",
                        severity="Warning",
                        title="同一视图附近重复尺寸标注",
                        description=f"PDF 显示层中检测到相近位置重复出现尺寸 {first['value']:g}，可能是同一特征被重复标注。",
                        suggestion="确认这两个标注是否指向同一特征；如果是同一特征，建议保留一个清晰的尺寸标注。",
                        evidence=[str(first["raw"]), str(second["raw"])],
                        locations=[first["location"].to_dict(), second["location"].to_dict()],
                    )
                )
                break
        return issues

    def _issue_dimension_values(self, issues: list[dict[str, Any]]) -> set[float]:
        values = set()
        for issue in issues:
            for evidence in issue.get("evidence", []):
                value = self._pdf_dimension_value(str(evidence))
                if value is not None:
                    values.add(value)
        return values

    def _pdf_dimension_value(self, value: str) -> float | None:
        normalized = str(value).replace("Φ", "").replace("φ", "").replace("%%c", "").strip()
        match = re.fullmatch(r"R?\s*(-?\d+(?:\.\d+)?)", normalized, flags=re.IGNORECASE)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    def _pdf_dimension_texts_near(self, first: dict[str, float], second: dict[str, float]) -> bool:
        first_center = (float(first["x"]) + float(first["width"]) / 2, float(first["y"]) + float(first["height"]) / 2)
        second_center = (float(second["x"]) + float(second["width"]) / 2, float(second["y"]) + float(second["height"]) / 2)
        distance = ((first_center[0] - second_center[0]) ** 2 + (first_center[1] - second_center[1]) ** 2) ** 0.5
        return distance <= 120.0

    def _summarize(self, issues: list[dict[str, Any]]) -> dict[str, int]:
        critical = sum(1 for issue in issues if issue["severity"] == "Critical")
        warning = sum(1 for issue in issues if issue["severity"] == "Warning")
        notice = sum(1 for issue in issues if issue["severity"] == "Notice")
        return {
            "totalIssues": len(issues),
            "critical": critical,
            "warning": warning,
            "notice": notice,
        }

    def _issue(
        self,
        code: str,
        severity: str,
        title: str,
        description: str,
        suggestion: str,
        evidence: list[str] | None = None,
        locations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return {
            "code": code,
            "severity": severity,
            "title": title,
            "description": description,
            "suggestion": suggestion,
            "evidence": evidence or [],
            "locations": locations or [],
        }

    def _issue_from_warning(self, warning: dict[str, Any]) -> dict[str, Any]:
        return self._issue(
            code=warning["code"],
            severity=warning.get("severity", "Warning"),
            title=warning["title"],
            description=warning["description"],
            suggestion=warning["suggestion"],
            locations=[],
        )

    def _make_review_id(self, filename: str, content: bytes) -> str:
        digest = sha256(filename.encode("utf-8") + b"\0" + content).hexdigest()
        return digest[:16]
