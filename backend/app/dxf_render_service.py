from __future__ import annotations

import math
from typing import Any


class DxfRenderService:
    """Render DXF layouts with ezdxf's CAD drawing backend."""

    def render(self, document: Any, layout_entity: Any, semantic_bounds: dict[str, float]) -> dict[str, Any]:
        try:
            from ezdxf import bbox
            from ezdxf.addons.drawing import Frontend, RenderContext, config, layout
            from ezdxf.addons.drawing.svg import SVGBackend
            from ezdxf.math import BoundingBox2d, Vec2
        except ImportError as error:
            return {
                "available": False,
                "reason": "dxf_renderer_dependency_missing",
                "error": str(error),
                "warning": {
                    "code": "DXF_RENDER_DEPENDENCY_MISSING",
                    "severity": "Warning",
                    "title": "DXF 底图渲染依赖缺失",
                    "description": "后端无法导入 ezdxf drawing 渲染依赖，不能生成完整 CAD 底图。",
                    "suggestion": "运行 pip install -r backend/requirements.txt 后重启后端。",
                },
            }

        render_bounds = self._render_bounds(bbox, layout_entity, semantic_bounds)
        content_width = max(render_bounds["max_x"] - render_bounds["min_x"], 1.0)
        content_height = max(render_bounds["max_y"] - render_bounds["min_y"], 1.0)
        output_width = max(720, min(int(math.ceil(content_width * 4)), 1800))
        scale = output_width / content_width
        output_height = max(240, int(math.ceil(content_height * scale)))

        backend = SVGBackend()
        render_config = config.Configuration(
            background_policy=config.BackgroundPolicy.WHITE,
            color_policy=config.ColorPolicy.BLACK,
            lineweight_policy=config.LineweightPolicy.RELATIVE,
        )
        try:
            Frontend(RenderContext(document), backend, config=render_config).draw_layout(layout_entity)
            page = layout.Page(output_width, output_height, units=layout.Units.px)
            settings = layout.Settings(
                fit_page=True,
                output_coordinate_space=output_width,
                crop_at_margins=False,
                output_layers=True,
            )
            render_box = BoundingBox2d(
                [
                    Vec2(render_bounds["min_x"], render_bounds["min_y"]),
                    Vec2(render_bounds["max_x"], render_bounds["max_y"]),
                ]
            )
            svg = backend.get_string(page, settings=settings, render_box=render_box, xml_declaration=False)
        except Exception as error:
            return {
                "available": False,
                "reason": "dxf_renderer_failed",
                "error": str(error),
                "warning": {
                    "code": "DXF_RENDER_FAILED",
                    "severity": "Warning",
                    "title": "DXF 底图渲染失败",
                    "description": f"CAD 渲染器未能生成 SVG 底图：{error}",
                    "suggestion": "检查 DXF 是否包含不兼容图元；仍可使用语义提取结果做文字级审查。",
                },
            }

        return {
            "available": True,
            "kind": "dxf-rendered-svg",
            "baseSvg": svg,
            "width": output_width,
            "height": output_height,
            "cadBox": render_bounds,
            "transform": {
                "scale": scale,
                "minX": render_bounds["min_x"],
                "maxY": render_bounds["max_y"],
                "offsetX": 0.0,
                "offsetY": 0.0,
            },
        }

    def _render_bounds(self, bbox_module: Any, layout_entity: Any, semantic_bounds: dict[str, float]) -> dict[str, float]:
        bounds = self._layout_bounds(bbox_module, layout_entity)
        bounds = self._merge_bounds(bounds, semantic_bounds)
        content_width = max(bounds["max_x"] - bounds["min_x"], 1.0)
        content_height = max(bounds["max_y"] - bounds["min_y"], 1.0)
        padding_x = max(content_width * 0.04, 4.0)
        padding_y = max(content_height * 0.04, 4.0)
        return {
            "min_x": bounds["min_x"] - padding_x,
            "max_x": bounds["max_x"] + padding_x,
            "min_y": bounds["min_y"] - padding_y,
            "max_y": bounds["max_y"] + padding_y,
        }

    def _layout_bounds(self, bbox_module: Any, layout_entity: Any) -> dict[str, float]:
        try:
            layout_box = bbox_module.extents(layout_entity, fast=True)
        except Exception:
            layout_box = None
        if layout_box is None or not getattr(layout_box, "has_data", False):
            return {"min_x": 0.0, "max_x": 100.0, "min_y": 0.0, "max_y": 100.0}
        return {
            "min_x": float(layout_box.extmin.x),
            "max_x": float(layout_box.extmax.x),
            "min_y": float(layout_box.extmin.y),
            "max_y": float(layout_box.extmax.y),
        }

    def _merge_bounds(self, first: dict[str, float], second: dict[str, float]) -> dict[str, float]:
        return {
            "min_x": min(first["min_x"], second["min_x"]),
            "max_x": max(first["max_x"], second["max_x"]),
            "min_y": min(first["min_y"], second["min_y"]),
            "max_y": max(first["max_y"], second["max_y"]),
        }
