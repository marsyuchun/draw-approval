from __future__ import annotations

import base64
from typing import Any


class PdfPreviewService:
    def render_first_page(self, content: bytes, max_width: int = 1600) -> dict[str, Any]:
        try:
            import fitz
        except ImportError as error:
            return {
                "available": False,
                "reason": "pdf_preview_dependency_missing",
                "error": str(error),
                "warning": {
                    "code": "PDF_PREVIEW_DEPENDENCY_MISSING",
                    "severity": "Warning",
                    "title": "PDF 底图渲染依赖缺失",
                    "description": "后端未安装 PyMuPDF，不能把 PDF 渲染为预览底图。",
                    "suggestion": "运行 pip install -r backend/requirements.txt 后重启后端。",
                },
            }

        try:
            document = fitz.open(stream=content, filetype="pdf")
            if document.page_count < 1:
                raise ValueError("empty_pdf")
            page = document[0]
            scale = min(max_width / page.rect.width, 3.0)
            matrix = fitz.Matrix(scale, scale)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            payload = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
        except Exception as error:
            return {
                "available": False,
                "reason": "pdf_preview_failed",
                "error": str(error),
                "warning": {
                    "code": "PDF_PREVIEW_FAILED",
                    "severity": "Warning",
                    "title": "PDF 底图渲染失败",
                    "description": f"后端无法把 PDF 渲染为预览底图：{error}",
                    "suggestion": "请重新从 SolidWorks 导出标准 PDF，或单独上传 DXF 做语义审查。",
                },
            }

        return {
            "available": True,
            "kind": "pdf-preview-image",
            "dataUrl": f"data:image/png;base64,{payload}",
            "width": pixmap.width,
            "height": pixmap.height,
            "pageWidth": float(page.rect.width),
            "pageHeight": float(page.rect.height),
            "page": 1,
        }
