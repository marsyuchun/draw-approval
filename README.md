# 机械设计图纸自动审查系统

这是一个面向 SolidWorks 机械设计图纸审查的 MVP 项目。当前版本采用 DXF 优先策略：DXF 是主输入格式，后端使用解析层读取线段、文字、尺寸和坐标；PDF 仅作为低可信兜底输入。

## 目录

- `frontend/`：基于 Vue 3 + Vite 的前端服务，提供上传、历史记录和报告展示。
- `backend/`：Python 标准库后端，提供上传接口、审查规则和报告存储。

## 当前能力

- 上传 DXF 图纸文件，PDF 可作为兜底格式。
- 使用 `ezdxf` 提取 DXF 中的线段、文字、尺寸文本和模型坐标。
- 通过 `DrawingParser` 抽象层区分 DXF 主解析和 PDF 兜底解析。
- 检查疑似冗余尺寸标注。
- 检查非正尺寸等明显错误。
- 对暂不支持的文件格式生成 Notice 提示。
- 生成 Critical / Warning / Notice 分级报告。
- 基于真实 DXF 坐标生成 SVG 图纸预览，并把问题框选到对应图面位置。
- 保存审查历史，前端可查看历史报告。

## 可视化标注说明

DXF 标注预览基于模型坐标生成。系统会把 DXF 里的线段和文字渲染为 SVG，再用问题里的 bbox 坐标叠加框选。

PDF 不是主输入格式。当前 `PdfParser` 使用 PyMuPDF 读取文本层；如果 PDF 没有文本层或文件无法解析，系统不会伪造坐标，会提示上传 DXF 或配置 OCR。后续可以在 `backend/app/pdf_parser.py` 中接入 PaddleOCR，把扫描 PDF 渲染成图片后识别文字和 bbox。

## 一键部署与运行

首次运行时，双击或在终端执行：

```bash
./scripts/deploy.sh
```

该脚本会安装前后端依赖并启动两个服务。启动后访问：

```text
http://127.0.0.1:5173
```

日常服务管理：

```bash
./scripts/start.sh
./scripts/stop.sh
./scripts/restart.sh
```

运行日志保存在 `.runtime/backend.log` 和 `.runtime/frontend.log`。前端通过 Vite 代理调用后端 API，因此浏览器不再直接读取本地 HTML 文件。

## 后端依赖

```bash
python3 -m pip install -r backend/requirements.txt
```

当前已接入：

- `ezdxf`：DXF 图元解析。
- `PyMuPDF`：PDF 文本层兜底解析。
- `paddleocr`：预留给扫描 PDF/OCR 兜底，体积较大，可按部署环境单独安装。

## 服务地址

- 前端服务：`http://127.0.0.1:5173`
- 后端 API：`http://127.0.0.1:8000`

## API

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

上传并审查：

```bash
curl -F "file=@sample.pdf" http://127.0.0.1:8000/api/reviews
```

获取历史：

```bash
curl http://127.0.0.1:8000/api/reviews
```

获取单个报告：

```bash
curl http://127.0.0.1:8000/api/reviews/<review_id>
```

## 后续接入点

- 在 `backend/app/dxf_parser.py` 中扩展 DIMENSION 实体解析、块引用递归、图层过滤和单位换算。
- 在 `backend/app/pdf_parser.py` 中接入 PaddleOCR，处理扫描 PDF 或文字转曲线的 PDF。
- 增加尺寸链、视图一致性、公差规则时，优先在 `backend/tests/` 中补测试，再扩展 `DrawingReviewEngine`。
- 如果需要任务队列、数据库或账号权限，可以在保持 API 返回结构稳定的基础上新增模块。

## 测试

```bash
PYTHONPATH=backend python3 -m unittest discover backend/tests
```
