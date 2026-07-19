<script setup>
import { computed, onMounted, ref } from "vue";

const apiStatus = ref("检查服务中");
const isApiOnline = ref(false);
const isSubmitting = ref(false);
const pdfFile = ref(null);
const dxfFile = ref(null);
const history = ref([]);
const report = ref(null);
const historyError = ref("");
const actionError = ref("");

const summary = computed(() => report.value?.summary ?? {
  totalIssues: 0,
  critical: 0,
  warning: 0,
  notice: 0,
});

const reportMeta = computed(() => {
  if (!report.value) return "暂无报告";
  const companion = report.value.file.companion ? ` · 底图：${report.value.file.companion.name}` : "";
  return `${report.value.file.name}${companion} · ${formatBytes(report.value.file.size)}`;
});

const parserMeta = computed(() => {
  if (!report.value) return "等待上传 PDF + DXF";
  const engine = report.value.engine;
  return `解析来源：${engine.source} · 置信度：${engine.confidence || "unknown"} · 标注坐标：${report.value.visual.coordinateSource || "none"}`;
});

async function request(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || "服务请求失败");
  return payload;
}

async function checkHealth() {
  try {
    await request("/health");
    apiStatus.value = "后端已连接";
    isApiOnline.value = true;
  } catch {
    apiStatus.value = "后端未连接";
    isApiOnline.value = false;
  }
}

async function loadHistory() {
  historyError.value = "";
  try {
    const payload = await request("/api/reviews");
    history.value = payload.items || [];
  } catch (error) {
    historyError.value = `无法读取记录：${error.message}`;
  }
}

async function submitReview() {
  actionError.value = "";
  if (!pdfFile.value || !dxfFile.value) {
    actionError.value = "请选择 PDF 底图和 DXF 数据文件。";
    return;
  }

  const body = new FormData();
  body.append("pdfFile", pdfFile.value);
  body.append("dxfFile", dxfFile.value);
  isSubmitting.value = true;
  try {
    report.value = await request("/api/reviews", { method: "POST", body });
    await loadHistory();
  } catch (error) {
    actionError.value = `上传失败：${error.message}`;
  } finally {
    isSubmitting.value = false;
  }
}

async function openReport(reviewId) {
  actionError.value = "";
  try {
    report.value = await request(`/api/reviews/${encodeURIComponent(reviewId)}`);
  } catch (error) {
    actionError.value = `无法打开报告：${error.message}`;
  }
}

function updateFile(event, kind) {
  const file = event.target.files?.[0] ?? null;
  if (kind === "pdf") pdfFile.value = file;
  else dxfFile.value = file;
}

function visualMessage(visual) {
  if (!visual) return "当前报告没有可视化标注数据。";
  const messages = {
    no_text_coordinates: "当前文件没有可用坐标，因此不能可靠地在图面中框选问题。请优先上传 DXF；PDF 需要文本层或 OCR 才能定位。",
    no_issue_coordinates: "图纸已解析，但当前问题没有可用坐标。请检查尺寸是否以文本或尺寸实体保留在 DXF 中。",
    no_dxf_entities: "DXF 中没有可渲染的线段或文字实体。请检查导出设置。",
    dxf_renderer_dependency_missing: "DXF 语义已解析，但 CAD 底图渲染依赖缺失。请安装后端依赖后重启服务。",
    dxf_renderer_failed: "DXF 语义已解析，但 CAD 底图渲染失败。请检查 DXF 是否包含不兼容图元。",
    pdf_preview_failed: "PDF 底图渲染失败。请重新从 SolidWorks 导出标准 PDF。",
  };
  return messages[visual.reason] || "当前报告没有可视化标注数据。";
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatTime(value) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  }).format(new Date(value));
}

onMounted(async () => {
  await checkHealth();
  await loadHistory();
});
</script>

<template>
  <main class="app-shell">
    <section class="workspace">
      <header class="topbar">
        <div>
          <p class="eyebrow">SolidWorks 2D Drawing Review</p>
          <h1>机械设计图纸自动审查</h1>
        </div>
        <div class="status-pill" :class="{ offline: !isApiOnline }">{{ apiStatus }}</div>
      </header>

      <section class="review-panel">
        <form class="upload-box" @submit.prevent="submitReview">
          <div>
            <label>上传 PDF + DXF 图纸</label>
            <p>PDF 用作和 SolidWorks 一致的显示底图；DXF 用于提取尺寸、文字和坐标进行审查。</p>
          </div>
          <div class="file-pair">
            <label for="pdfFile">PDF 底图</label>
            <input id="pdfFile" accept=".pdf,application/pdf" type="file" required @change="updateFile($event, 'pdf')" />
          </div>
          <div class="file-pair">
            <label for="dxfFile">DXF 数据</label>
            <input id="dxfFile" accept=".dxf,application/dxf" type="file" required @change="updateFile($event, 'dxf')" />
          </div>
          <button type="submit" :disabled="isSubmitting">
            {{ isSubmitting ? "审查中..." : "开始审查" }}
          </button>
        </form>

        <section class="summary-grid" aria-label="问题统计">
          <article><span>总问题</span><strong>{{ summary.totalIssues }}</strong></article>
          <article><span>Critical</span><strong>{{ summary.critical }}</strong></article>
          <article><span>Warning</span><strong>{{ summary.warning }}</strong></article>
          <article><span>Notice</span><strong>{{ summary.notice }}</strong></article>
        </section>
      </section>

      <p v-if="actionError" class="feedback error">{{ actionError }}</p>

      <section class="content-grid">
        <aside class="history-panel">
          <div class="section-title">
            <h2>审查记录</h2>
            <button type="button" class="secondary-button" @click="loadHistory">刷新</button>
          </div>
          <p v-if="historyError" class="feedback error">{{ historyError }}</p>
          <div v-else class="history-list">
            <button
              v-for="item in history"
              :key="item.id"
              class="history-item"
              type="button"
              @click="openReport(item.id)"
            >
              <strong>{{ item.file.name }}</strong>
              <span>{{ item.summary.totalIssues }} 个问题 · {{ formatTime(item.createdAt) }}</span>
            </button>
            <div v-if="history.length === 0" class="empty-state">暂无审查记录</div>
          </div>
        </aside>

        <section class="report-panel">
          <div class="section-title">
            <h2>报告详情</h2>
            <span>{{ reportMeta }}</span>
          </div>
          <div class="parser-meta">{{ parserMeta }}</div>
          <div class="report-layout">
            <section class="drawing-preview">
              <template v-if="report?.visual?.available && report.visual.baseImage">
                <div class="dxf-overlay-frame" :style="{ width: `${report.visual.width || 960}px`, height: `${report.visual.height || 640}px` }">
                  <img class="pdf-base-image" :src="report.visual.baseImage" alt="PDF 图纸底图" />
                  <div class="dxf-overlay-layer" v-html="report.visual.overlaySvg || ''"></div>
                </div>
              </template>
              <template v-else-if="report?.visual?.available && report.visual.baseSvg">
                <div class="dxf-overlay-frame" :style="{ width: `${report.visual.width || 960}px`, height: `${report.visual.height || 640}px` }">
                  <div class="dxf-base-layer" v-html="report.visual.baseSvg"></div>
                  <div class="dxf-overlay-layer" v-html="report.visual.overlaySvg || ''"></div>
                </div>
              </template>
              <div v-else-if="report" class="visual-warning">{{ visualMessage(report.visual) }}</div>
              <div v-else class="empty-state">上传一张图纸后，这里会显示可定位的图面标注。</div>
            </section>

            <section class="issue-list">
              <template v-if="report?.issues?.length">
                <article v-for="issue in report.issues" :key="issue.id || issue.code" class="issue-card" :class="issue.severity">
                  <div class="issue-heading">
                    <strong>{{ issue.title }}</strong>
                    <span class="badge">{{ issue.severity }}</span>
                  </div>
                  <p>{{ issue.description }}</p>
                  <p class="suggestion">{{ issue.suggestion }}</p>
                  <p v-if="issue.evidence?.length">证据：{{ issue.evidence.join(" / ") }}</p>
                </article>
              </template>
              <div v-else-if="report" class="empty-state">未发现明显尺寸审查问题。</div>
              <div v-else class="empty-state">上传一张图纸后，这里会显示审查问题和修改建议。</div>
            </section>
          </div>
        </section>
      </section>
    </section>
  </main>
</template>
