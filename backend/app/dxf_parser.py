from __future__ import annotations

import io
import math
import re
from typing import Any

from .drawing_models import DrawingDimension, DrawingLine, DrawingLocation, DrawingText, ParsedDrawing
from .dxf_render_service import DxfRenderService


DIMENSION_PATTERN = re.compile(
    r"\b(?:DIM|R|DIA|DIAMETER|SIZE)\s*(-?\d+(?:\.\d+)?)\s*(mm|cm|m|in)?\b"
    r"|"
    r"\b(-?\d+(?:\.\d+)?)\s*(mm|cm|m|in)\b",
    re.IGNORECASE,
)
DIAMETER_PATTERN = re.compile(r"(?:%%c|[Φφ])\s*(-?\d+(?:\.\d+)?)\s*(mm|cm|m|in)?", re.IGNORECASE)


class DxfParser:
    kind = "dxf"

    def parse(self, filename: str, content: bytes) -> ParsedDrawing:
        try:
            import ezdxf
        except ImportError:
            return ParsedDrawing(
                source_format="dxf",
                confidence="none",
                warnings=[
                    {
                        "code": "DXF_DEPENDENCY_MISSING",
                        "severity": "Critical",
                        "title": "缺少 DXF 解析依赖",
                        "description": "后端未安装 ezdxf，无法读取 DXF 图元和真实坐标。",
                        "suggestion": "运行 pip install -r backend/requirements.txt 后重启后端。",
                    }
                ],
            )

        text = self._decode_content(content)
        document = ezdxf.read(io.StringIO(text))
        drawing_layout = self._select_layout(document)
        texts: list[DrawingText] = []
        dimension_texts: list[DrawingText] = []
        dimensions: list[DrawingDimension] = []
        lines: list[DrawingLine] = []
        warnings: list[dict[str, Any]] = []

        for entity in self._iter_semantic_entities(drawing_layout):
            entity_type = entity.dxftype()
            if entity_type == "LINE":
                start = entity.dxf.start
                end = entity.dxf.end
                lines.append(
                    DrawingLine(
                        start=(float(start.x), float(start.y)),
                        end=(float(end.x), float(end.y)),
                        layer=getattr(entity.dxf, "layer", ""),
                    )
                )
            elif entity_type == "ARC":
                lines.extend(self._arc_lines(entity))
            elif entity_type == "LWPOLYLINE":
                lines.extend(self._lwpolyline_lines(entity))
            elif entity_type in {"TEXT", "MTEXT"}:
                value = self._entity_text(entity)
                insert = self._entity_insert(entity)
                height = self._entity_text_height(entity)
                bbox = self._text_bbox(value, insert, height)
                location = DrawingLocation(page=1, source="dxf", bbox=bbox, text=value)
                texts.append(DrawingText(value=value, location=location))
            elif entity_type == "DIMENSION":
                dimension = self._dimension_entity(entity, document)
                if dimension is not None:
                    dimensions.append(dimension)
                    dimension_texts.append(DrawingText(value=dimension.raw, location=dimension.location))

        dimensions.extend(self._extract_dimensions(texts))
        texts.extend(dimension_texts)
        render = DxfRenderService().render(document, drawing_layout, self._bounds(lines, texts))
        if render.get("warning"):
            warnings.append(render["warning"])
        return ParsedDrawing(
            source_format="dxf",
            confidence="high",
            texts=texts,
            lines=lines,
            dimensions=dimensions,
            preview_svg=render.get("baseSvg", ""),
            render=render,
            warnings=warnings,
            raw_text="\n".join(text.value for text in texts),
        )

    def _decode_content(self, content: bytes) -> str:
        probe = content[:4096].decode("ascii", errors="ignore")
        encoding = "gbk" if "ANSI_936" in probe else "utf-8-sig"
        text = content.decode(encoding, errors="ignore")
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def _entity_text(self, entity: Any) -> str:
        if entity.dxftype() == "MTEXT":
            value = entity.text
        else:
            value = entity.dxf.text
        return self._decode_dxf_unicode(value)

    def _decode_dxf_unicode(self, value: str) -> str:
        return re.sub(
            r"\\U\+([0-9A-Fa-f]{4})",
            lambda match: chr(int(match.group(1), 16)),
            value,
        )

    def _entity_insert(self, entity: Any) -> tuple[float, float]:
        insert = entity.dxf.insert
        return float(insert.x), float(insert.y)

    def _entity_text_height(self, entity: Any) -> float:
        for attribute in ("height", "char_height"):
            try:
                value = getattr(entity.dxf, attribute)
            except Exception:
                continue
            if value:
                return float(value)
        return 2.5

    def _select_layout(self, document: Any) -> Any:
        modelspace = document.modelspace()
        if self._has_entities(modelspace):
            return modelspace

        for layout_entity in document.layouts:
            if getattr(layout_entity, "name", "") == getattr(modelspace, "name", ""):
                continue
            if self._has_entities(layout_entity):
                return layout_entity

        return modelspace

    def _has_entities(self, layout_entity: Any) -> bool:
        try:
            return len(layout_entity) > 0
        except Exception:
            return any(True for _ in layout_entity)

    def _iter_semantic_entities(self, entities: Any, depth: int = 0) -> list[Any]:
        resolved = []
        for entity in entities:
            if entity.dxftype() == "INSERT" and depth < 8:
                try:
                    virtual_entities = list(entity.virtual_entities())
                except Exception:
                    virtual_entities = []
                resolved.extend(self._iter_semantic_entities(virtual_entities, depth + 1))
            else:
                resolved.append(entity)
        return resolved

    def _arc_lines(self, entity: Any) -> list[DrawingLine]:
        center = entity.dxf.center
        radius = float(entity.dxf.radius)
        start_angle = math.radians(float(entity.dxf.start_angle))
        end_angle = math.radians(float(entity.dxf.end_angle))
        if end_angle < start_angle:
            end_angle += math.tau

        segments = max(8, int(abs(end_angle - start_angle) / (math.pi / 18)))
        points = []
        for index in range(segments + 1):
            angle = start_angle + (end_angle - start_angle) * index / segments
            points.append((float(center.x) + radius * math.cos(angle), float(center.y) + radius * math.sin(angle)))
        return [
            DrawingLine(start=points[index], end=points[index + 1], layer=getattr(entity.dxf, "layer", ""))
            for index in range(len(points) - 1)
        ]

    def _lwpolyline_lines(self, entity: Any) -> list[DrawingLine]:
        points = [(float(point[0]), float(point[1])) for point in entity.get_points()]
        lines = [
            DrawingLine(start=points[index], end=points[index + 1], layer=getattr(entity.dxf, "layer", ""))
            for index in range(len(points) - 1)
        ]
        if getattr(entity, "closed", False) and len(points) > 2:
            lines.append(DrawingLine(start=points[-1], end=points[0], layer=getattr(entity.dxf, "layer", "")))
        return lines

    def _text_bbox(self, value: str, insert: tuple[float, float], height: float) -> dict[str, float]:
        width = max(len(value) * height * 0.62, height * 2)
        return {
            "x": insert[0],
            "y": insert[1],
            "width": width,
            "height": height,
        }

    def _extract_dimensions(self, texts: list[DrawingText]) -> list[DrawingDimension]:
        dimensions = []
        for text in texts:
            for match in DIAMETER_PATTERN.finditer(text.value):
                unit_text = match.group(2)
                dimensions.append(
                    DrawingDimension(
                        value=float(match.group(1)),
                        unit=(unit_text or "mm").lower(),
                        raw=match.group(0).strip(),
                        location=text.location,
                    )
                )
            for match in DIMENSION_PATTERN.finditer(text.value):
                value_text = match.group(1) or match.group(3)
                unit_text = match.group(2) or match.group(4)
                dimensions.append(
                    DrawingDimension(
                        value=float(value_text),
                        unit=(unit_text or "mm").lower(),
                        raw=match.group(0).strip(),
                        location=text.location,
                    )
                )
        return dimensions

    def _dimension_entity(self, entity: Any, document: Any) -> DrawingDimension | None:
        try:
            fallback_value = float(entity.get_measurement())
        except Exception:
            return None

        displayed = self._dimension_display_text(entity, document)
        raw_text = displayed["text"] or getattr(entity.dxf, "text", "") or f"DIM {fallback_value:g} mm"
        value = self._parse_dimension_value(raw_text, fallback_value)
        insert = displayed["insert"] or self._dimension_insert(entity)
        if insert is None:
            return None
        height = displayed["height"] or 2.5
        bbox = self._text_bbox(raw_text, insert, height)
        location = DrawingLocation(page=1, source="dxf", bbox=bbox, text=raw_text)
        return DrawingDimension(value=value, unit="mm", raw=raw_text, location=location)

    def _dimension_display_text(self, entity: Any, document: Any) -> dict[str, Any]:
        block_name = getattr(entity.dxf, "geometry", "")
        if not block_name:
            return {"text": "", "insert": None, "height": None}
        try:
            block = document.blocks.get(block_name)
        except Exception:
            return {"text": "", "insert": None, "height": None}

        text_parts = []
        first_insert = None
        first_height = None
        for block_entity in block:
            if block_entity.dxftype() not in {"TEXT", "MTEXT"}:
                continue
            value = self._entity_text(block_entity)
            insert = self._entity_insert(block_entity)
            if first_insert is None:
                first_insert = insert
                first_height = self._entity_text_height(block_entity)
            text_parts.append((insert[0], value))
        if not text_parts:
            return {"text": "", "insert": None, "height": None}
        text = "".join(part for _, part in sorted(text_parts, key=lambda item: item[0]))
        return {"text": text, "insert": first_insert, "height": first_height}

    def _dimension_insert(self, entity: Any) -> tuple[float, float] | None:
        for attribute in ("text_midpoint", "defpoint"):
            try:
                point = getattr(entity.dxf, attribute)
            except Exception:
                continue
            if point is not None:
                return float(point.x), float(point.y)
        return None

    def _parse_dimension_value(self, raw_text: str, fallback_value: float) -> float:
        match = re.search(r"-?\d+(?:\.\d+)?", raw_text)
        if not match:
            return fallback_value
        return float(match.group(0))

    def _bounds(self, lines: list[DrawingLine], texts: list[DrawingText]) -> dict[str, float]:
        xs: list[float] = []
        ys: list[float] = []
        for line in lines:
            xs.extend([line.start[0], line.end[0]])
            ys.extend([line.start[1], line.end[1]])
        for text in texts:
            bbox = text.location.bbox
            xs.extend([bbox["x"], bbox["x"] + bbox["width"]])
            ys.extend([bbox["y"], bbox["y"] + bbox["height"]])
        if not xs or not ys:
            return {"min_x": 0.0, "max_x": 100.0, "min_y": 0.0, "max_y": 100.0}
        return {
            "min_x": min(xs),
            "max_x": max(xs),
            "min_y": min(ys),
            "max_y": max(ys),
        }
