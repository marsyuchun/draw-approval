from __future__ import annotations

import re

from .drawing_models import DrawingDimension, DrawingLocation, DrawingText, ParsedDrawing


DIMENSION_PATTERN = re.compile(
    r"\b(?:DIM|R|DIA|DIAMETER|SIZE)\s*(-?\d+(?:\.\d+)?)\s*(mm|cm|m|in)?\b"
    r"|"
    r"\b(-?\d+(?:\.\d+)?)\s*(mm|cm|m|in)\b",
    re.IGNORECASE,
)


class PdfParser:
    kind = "pdf"

    def parse(self, filename: str, content: bytes) -> ParsedDrawing:
        warnings = []
        texts: list[DrawingText] = []

        try:
            import fitz
        except ImportError:
            warnings.append(
                {
                    "code": "PDF_TEXT_DEPENDENCY_MISSING",
                    "severity": "Warning",
                    "title": "缺少 PDF 文本解析依赖",
                    "description": "后端未安装 PyMuPDF，无法读取 PDF 文本层和文字坐标。",
                    "suggestion": "安装 backend/requirements.txt 后重启后端；扫描 PDF 还需要 PaddleOCR。",
                }
            )
            return ParsedDrawing(source_format="pdf", confidence="none", warnings=warnings)

        try:
            document = fitz.open(stream=content, filetype="pdf")
        except Exception:
            warnings.append(
                {
                    "code": "PDF_PARSE_FAILED",
                    "severity": "Warning",
                    "title": "PDF 无法解析",
                    "description": "PyMuPDF 无法打开该 PDF，文件可能不完整、损坏，或不是标准 PDF 数据。",
                    "suggestion": "请重新导出 PDF，或优先上传 DXF 文件。",
                }
            )
            return ParsedDrawing(source_format="pdf", confidence="none", warnings=warnings)

        for page_index, page in enumerate(document, start=1):
            words = page.get_text("words")
            for word in words:
                x0, y0, x1, y1, value = word[:5]
                location = DrawingLocation(
                    page=page_index,
                    source="pdf-text",
                    bbox={"x": float(x0), "y": float(y0), "width": float(x1 - x0), "height": float(y1 - y0)},
                    text=str(value),
                )
                texts.append(DrawingText(value=str(value), location=location))

        if not texts:
            ocr_texts, ocr_warnings = self._ocr_pages(document)
            texts.extend(ocr_texts)
            warnings.extend(ocr_warnings)

        raw_text = "\n".join(text.value for text in texts)
        dimensions = self._extract_dimensions(texts)
        if not texts:
            warnings.append(
                {
                    "code": "PDF_OCR_REQUIRED",
                    "severity": "Warning",
                    "title": "PDF 没有可提取文本层",
                    "description": "该 PDF 可能是扫描图或文字已转曲线，需要 OCR 才能识别尺寸。",
                    "suggestion": "安装并配置 PaddleOCR，或优先上传 DXF。",
                }
            )

        return ParsedDrawing(
            source_format="pdf",
            confidence="low" if dimensions else "none",
            texts=texts,
            dimensions=dimensions,
            warnings=warnings,
            raw_text=raw_text,
        )

    def _extract_dimensions(self, texts: list[DrawingText]) -> list[DrawingDimension]:
        dimensions = []
        for text in texts:
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

    def _ocr_pages(self, document) -> tuple[list[DrawingText], list[dict]]:
        try:
            import numpy as np
            from paddleocr import PaddleOCR
        except ImportError:
            return [], [
                {
                    "code": "PDF_OCR_DEPENDENCY_MISSING",
                    "severity": "Warning",
                    "title": "缺少 OCR 依赖",
                    "description": "该 PDF 没有文本层，且后端未安装 PaddleOCR，无法识别扫描图纸。",
                    "suggestion": "安装 PaddleOCR，或优先上传 DXF。",
                }
            ]

        ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
        texts: list[DrawingText] = []
        for page_index, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=None, alpha=False)
            image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)
            result = ocr.ocr(image, cls=True)
            for line in result or []:
                for item in line or []:
                    points, payload = item
                    value = payload[0]
                    xs = [float(point[0]) for point in points]
                    ys = [float(point[1]) for point in points]
                    location = DrawingLocation(
                        page=page_index,
                        source="pdf-ocr",
                        bbox={
                            "x": min(xs),
                            "y": min(ys),
                            "width": max(xs) - min(xs),
                            "height": max(ys) - min(ys),
                        },
                        text=value,
                    )
                    texts.append(DrawingText(value=value, location=location))
        return texts, []
