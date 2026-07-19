from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DrawingLocation:
    page: int
    source: str
    bbox: dict[str, float]
    text: str = ""
    line: int | None = None
    column: int | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "page": self.page,
            "source": self.source,
            "bbox": self.bbox,
            "text": self.text,
        }
        if self.line is not None:
            payload["line"] = self.line
        if self.column is not None:
            payload["column"] = self.column
        return payload


@dataclass(frozen=True)
class DrawingText:
    value: str
    location: DrawingLocation


@dataclass(frozen=True)
class DrawingLine:
    start: tuple[float, float]
    end: tuple[float, float]
    layer: str = ""


@dataclass(frozen=True)
class DrawingDimension:
    value: float
    unit: str
    raw: str
    location: DrawingLocation


@dataclass(frozen=True)
class ParsedDrawing:
    source_format: str
    confidence: str
    texts: list[DrawingText] = field(default_factory=list)
    lines: list[DrawingLine] = field(default_factory=list)
    dimensions: list[DrawingDimension] = field(default_factory=list)
    preview_svg: str = ""
    render: dict[str, Any] = field(default_factory=dict)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    raw_text: str = ""
