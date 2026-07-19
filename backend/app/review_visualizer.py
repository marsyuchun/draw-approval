from __future__ import annotations

from html import escape
from typing import Any

from .drawing_models import ParsedDrawing


PAGE_WIDTH = 920
HEADER_HEIGHT = 64
LINE_HEIGHT = 30
LEFT_MARGIN = 40
TEXT_TOP = 88
MAX_LINES = 28


class ReviewVisualizer:
    def build(self, parsed: ParsedDrawing, issues: list[dict[str, Any]]) -> dict[str, Any]:
        if parsed.source_format == "dxf":
            return self._build_dxf(parsed, issues)
        return self._build_text(parsed.raw_text, issues)

    def build_pdf_dxf(self, parsed: ParsedDrawing, issues: list[dict[str, Any]], pdf_preview: dict[str, Any]) -> dict[str, Any]:
        if not pdf_preview.get("available"):
            return self._build_dxf(parsed, issues)

        width = int(pdf_preview["width"])
        height = int(pdf_preview["height"])
        located_issues = [
            issue
            for issue in issues
            if any(str(location.get("source", "")).startswith("pdf") for location in issue.get("locations", []))
        ]
        return {
            "available": True,
            "kind": "pdf-dxf-overlay",
            "reason": "" if located_issues else "no_pdf_issue_coordinates",
            "coordinateSource": "pdf-text" if located_issues else "pdf-base-only",
            "baseImage": pdf_preview["dataUrl"],
            "overlaySvg": self._render_pdf_overlay(pdf_preview, located_issues),
            "width": width,
            "height": height,
            "note": "标注框使用 PDF 文本层坐标；未匹配到 PDF 文本证据时不画框，避免错位。",
        }

    def _render_pdf_overlay(self, pdf_preview: dict[str, Any], issues: list[dict[str, Any]]) -> str:
        width = int(pdf_preview["width"])
        height = int(pdf_preview["height"])
        page_width = max(float(pdf_preview.get("pageWidth") or width), 1.0)
        page_height = max(float(pdf_preview.get("pageHeight") or height), 1.0)
        scale_x = width / page_width
        scale_y = height / page_height
        rect_nodes = []

        for issue in issues:
            color = self._severity_color(issue["severity"])
            for location in issue.get("locations", []):
                if not str(location.get("source", "")).startswith("pdf"):
                    continue
                bbox = location.get("bbox")
                if not bbox:
                    continue
                x = float(bbox["x"]) * scale_x
                y = float(bbox["y"]) * scale_y
                rect_width = max(float(bbox["width"]) * scale_x, 22)
                rect_height = max(float(bbox["height"]) * scale_y, 16)
                rect_nodes.append(
                    f'<rect data-issue-code="{escape(issue["code"])}" x="{x - 5:.2f}" y="{y - 5:.2f}" '
                    f'width="{rect_width + 10:.2f}" height="{rect_height + 10:.2f}" rx="4" '
                    f'fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="2" />'
                )

        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" class="review-overlay-svg" aria-hidden="true">'
            "<style>"
            ".review-overlay-svg{pointer-events:none;overflow:visible}"
            "</style>"
            + "".join(rect_nodes)
            + "</svg>"
        )

    def _build_text(self, text: str, issues: list[dict[str, Any]]) -> dict[str, Any]:
        lines = self._visible_lines(text)
        located_issues = [issue for issue in issues if issue.get("locations")]

        if not lines or not located_issues:
            return {
                "available": False,
                "kind": "annotated-svg",
                "reason": "no_text_coordinates",
                "svg": "",
            }

        page_height = max(420, HEADER_HEIGHT + 58 + len(lines) * LINE_HEIGHT)
        issue_rects = self._issue_rects(located_issues)
        svg = self._render_svg(lines, issue_rects, page_height)

        return {
            "available": True,
            "kind": "annotated-svg",
            "reason": "",
            "coordinateSource": "text-layout",
            "svg": svg,
        }

    def _build_dxf(self, parsed: ParsedDrawing, issues: list[dict[str, Any]]) -> dict[str, Any]:
        located_issues = [issue for issue in issues if issue.get("locations")]
        render = parsed.render or {}
        if not render.get("available") and not parsed.texts and not parsed.lines:
            return {
                "available": False,
                "kind": "dxf-overlay",
                "reason": "no_dxf_entities",
                "svg": "",
            }
        if not render.get("available") or not render.get("baseSvg"):
            return {
                "available": False,
                "kind": "dxf-overlay",
                "reason": render.get("reason", "no_dxf_render"),
                "svg": "",
            }

        return {
            "available": True,
            "kind": "dxf-overlay",
            "reason": "" if located_issues else "no_issue_coordinates",
            "coordinateSource": "dxf",
            "baseSvg": render["baseSvg"],
            "overlaySvg": self._render_dxf_overlay(render, located_issues),
            "width": render["width"],
            "height": render["height"],
        }

    def _render_dxf_overlay(self, render: dict[str, Any], issues: list[dict[str, Any]]) -> str:
        width = int(render["width"])
        height = int(render["height"])
        transform = render["transform"]
        scale = float(transform["scale"])
        min_x = float(transform["minX"])
        max_y = float(transform["maxY"])
        offset_x = float(transform.get("offsetX", 0.0))
        offset_y = float(transform.get("offsetY", 0.0))
        rect_nodes = []

        for issue in issues:
            color = self._severity_color(issue["severity"])
            for location in issue.get("locations", []):
                bbox = location.get("bbox")
                if not bbox:
                    continue
                x = offset_x + (float(bbox["x"]) - min_x) * scale
                y_top = offset_y + (max_y - (float(bbox["y"]) + float(bbox["height"]))) * scale
                rect_width = max(float(bbox["width"]) * scale, 28)
                rect_height = max(float(bbox["height"]) * scale, 20)
                rect_nodes.append(
                    f'<rect data-issue-code="{escape(issue["code"])}" x="{x - 6:.2f}" y="{y_top - 6:.2f}" '
                    f'width="{rect_width + 12:.2f}" height="{rect_height + 12:.2f}" rx="4" '
                    f'fill="{color}" fill-opacity="0.08" stroke="{color}" stroke-width="2" '
                    f'vector-effect="non-scaling-stroke" />'
                )

        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" class="review-overlay-svg" aria-hidden="true">'
            "<style>"
            ".review-overlay-svg{pointer-events:none;overflow:visible}"
            "</style>"
            + "".join(rect_nodes)
            + "</svg>"
        )

    def _visible_lines(self, text: str) -> list[str]:
        lines = [line.rstrip() for line in text.splitlines() if line.strip()]
        return lines[:MAX_LINES]

    def _issue_rects(self, issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rects = []
        for issue in issues:
            for location in issue.get("locations", []):
                line = location.get("line", 0)
                if line < 1 or line > MAX_LINES:
                    continue
                rects.append(
                    {
                        "code": issue["code"],
                        "severity": issue["severity"],
                        "title": issue["title"],
                        "x": LEFT_MARGIN - 12,
                        "y": TEXT_TOP + (line - 1) * LINE_HEIGHT - 20,
                        "width": PAGE_WIDTH - LEFT_MARGIN * 2 + 24,
                        "height": 28,
                    }
                )
        return rects

    def _render_svg(self, lines: list[str], rects: list[dict[str, Any]], page_height: int) -> str:
        line_nodes = []
        for index, line in enumerate(lines, start=1):
            y = TEXT_TOP + (index - 1) * LINE_HEIGHT
            line_nodes.append(
                f'<text x="{LEFT_MARGIN}" y="{y}" class="drawing-text">'
                f'<tspan class="line-no">{index:02d}</tspan> {escape(line[:110])}</text>'
            )

        rect_nodes = []
        label_nodes = []
        for index, rect in enumerate(rects, start=1):
            color = self._severity_color(rect["severity"])
            rect_nodes.append(
                f'<rect data-issue-code="{escape(rect["code"])}" x="{rect["x"]}" y="{rect["y"]}" '
                f'width="{rect["width"]}" height="{rect["height"]}" rx="4" '
                f'fill="{color}" fill-opacity="0.14" stroke="{color}" stroke-width="2" />'
            )
            label_nodes.append(
                f'<g transform="translate({rect["x"] + rect["width"] - 114},{rect["y"] - 5})">'
                f'<rect width="108" height="22" rx="4" fill="{color}" />'
                f'<text x="8" y="15" class="issue-label">{index}. {escape(rect["severity"])}</text>'
                f"</g>"
            )

        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {PAGE_WIDTH} {page_height}" '
            f'role="img" aria-label="带审查标注的图纸预览">'
            "<style>"
            ".sheet{fill:#fff;stroke:#cbd5e1;stroke-width:2}"
            ".title{font:700 20px Arial,sans-serif;fill:#172033}"
            ".sub{font:13px Arial,sans-serif;fill:#64748b}"
            ".drawing-text{font:15px Menlo,Consolas,monospace;fill:#1f2937}"
            ".line-no{fill:#94a3b8}"
            ".issue-label{font:700 12px Arial,sans-serif;fill:#fff}"
            "</style>"
            f'<rect class="sheet" x="12" y="12" width="{PAGE_WIDTH - 24}" height="{page_height - 24}" rx="8" />'
            '<text x="40" y="46" class="title">Drawing Review Preview</text>'
            '<text x="40" y="66" class="sub">基于可提取文本生成的行级标注；真实 PDF/CAD 坐标需接入 OCR 或 CAD 解析引擎。</text>'
            + "".join(line_nodes)
            + "".join(rect_nodes)
            + "".join(label_nodes)
            + "</svg>"
        )

    def _severity_color(self, severity: str) -> str:
        return {
            "Critical": "#dc2626",
            "Warning": "#d97706",
            "Notice": "#2563eb",
        }.get(severity, "#64748b")
