from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from .drawing_models import ParsedDrawing
from .dxf_parser import DxfParser
from .pdf_parser import PdfParser


class DrawingParser(ABC):
    kind = "unknown"

    @abstractmethod
    def parse(self, filename: str, content: bytes) -> ParsedDrawing:
        raise NotImplementedError


class UnsupportedDrawingParser(DrawingParser):
    kind = "unsupported"

    def parse(self, filename: str, content: bytes) -> ParsedDrawing:
        return ParsedDrawing(
            source_format="unsupported",
            confidence="none",
            warnings=[
                {
                    "code": "UNSUPPORTED_FORMAT",
                    "severity": "Notice",
                    "title": "文件格式不符合当前上传策略",
                    "description": "当前优先支持 DXF；PDF 仅作为 OCR/文本层兜底输入。",
                    "suggestion": "请从 SolidWorks 导出 DXF 后上传。DWG 建议先转换为 DXF。",
                }
            ],
        )


class ParserFactory:
    def for_file(self, filename: str, content_type: str = "") -> DrawingParser:
        extension = Path(filename).suffix.lower()
        if extension == ".dxf":
            return DxfParser()
        if extension == ".pdf":
            return PdfParser()
        return UnsupportedDrawingParser()
