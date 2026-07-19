<script setup>
import { computed, onMounted, ref } from "vue";

const LOGIN_USERNAME = "zhaoyali998";
const LOGIN_PASSWORD = "naura999";

const apiStatus = ref("系统状态检查中");
const isApiOnline = ref(false);
const isAuthenticated = ref(sessionStorage.getItem("draw-approval-authenticated") === "true");
const loginUsername = ref("");
const loginPassword = ref("");
const loginError = ref("");
const isSubmitting = ref(false);
const pdfFile = ref(null);
const dxfFile = ref(null);
const history = ref([]);
const report = ref(null);
const activeView = ref("history");
const historyError = ref("");
const actionError = ref("");

const summary = computed(() => report.value?.summary ?? { totalIssues: 0, critical: 0, warning: 0, notice: 0 });
const reportMeta = computed(() => {
  if (!report.value) return "";
  const companion = report.value.file.companion ? ` · 底图：${report.value.file.companion.name}` : "";
  return `${report.value.file.name}${companion} · ${formatBytes(report.value.file.size)}`;
});
const parserMeta = computed(() => {
  if (!report.value) return "";
  const engine = report.value.engine;
  return `解析来源：${engine.source} · 置信度：${engine.confidence || "unknown"} · 标注坐标：${report.value.visual.coordinateSource || "none"}`;
});

async function request(path, options) {
  const response = await fetch(path, options);
  const payload = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload?.error || "服务请求失败");
  return payload;
}

async function signIn() {
  loginError.value = "";
  if (loginUsername.value !== LOGIN_USERNAME || loginPassword.value !== LOGIN_PASSWORD) {
    loginError.value = "账号或密码不正确，请重新输入。";
    return;
  }
  sessionStorage.setItem("draw-approval-authenticated", "true");
  isAuthenticated.value = true;
  await initializeWorkspace();
}

function signOut() {
  sessionStorage.removeItem("draw-approval-authenticated");
  isAuthenticated.value = false;
  loginPassword.value = "";
  activeView.value = "history";
}

async function checkHealth() {
  try {
    await request("/health");
    apiStatus.value = "系统运行正常";
    isApiOnline.value = true;
  } catch {
    apiStatus.value = "系统服务异常";
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
    activeView.value = "detail";
    await loadHistory();
  } catch (error) {
    actionError.value = `审查失败：${error.message}`;
  } finally {
    isSubmitting.value = false;
  }
}

async function openReport(reviewId) {
  actionError.value = "";
  try {
    report.value = await request(`/api/reviews/${encodeURIComponent(reviewId)}`);
    activeView.value = "detail";
  } catch (error) {
    actionError.value = `无法打开报告：${error.message}`;
  }
}

async function deleteReview(reviewId) {
  actionError.value = "";
  try {
    await request(`/api/reviews/${encodeURIComponent(reviewId)}`, { method: "DELETE" });
    if (report.value?.id === reviewId) report.value = null;
    activeView.value = "history";
    await loadHistory();
  } catch (error) {
    actionError.value = `删除失败：${error.message}`;
  }
}

function updateFile(event, kind) {
  const file = event.target.files?.[0] ?? null;
  if (kind === "pdf") pdfFile.value = file;
  else dxfFile.value = file;
}

function visualMessage(visual) {
  const messages = {
    no_text_coordinates: "当前文件没有可用坐标，无法可靠地在图面中框选问题。",
    no_issue_coordinates: "图纸已解析，但当前问题没有可用坐标。",
    no_dxf_entities: "DXF 中没有可渲染的线段或文字实体。",
    dxf_renderer_dependency_missing: "CAD 底图渲染依赖缺失。",
    dxf_renderer_failed: "CAD 底图渲染失败。",
    pdf_preview_failed: "PDF 底图渲染失败。",
  };
  return messages[visual?.reason] || "当前报告没有可视化标注数据。";
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatTime(value) {
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

async function initializeWorkspace() {
  await checkHealth();
  await loadHistory();
}

onMounted(async () => {
  if (isAuthenticated.value) await initializeWorkspace();
});
</script>

<template>
  <main v-if="!isAuthenticated" class="login-page">
    <div class="login-backdrop" aria-hidden="true"></div>
    <div class="login-grid" aria-hidden="true"></div>
    <section class="login-shell" aria-label="系统登录">
      <div class="login-brand">
        <img class="naura-logo" src="/images/naura-logo.png" alt="北方华创 NAURA" />
        <div class="brand-divider"></div>
        <p class="brand-eyebrow">DRAWING INTELLIGENCE PLATFORM</p>
        <h1>智审图</h1>
        <p class="brand-description">AI辅助机械设计图纸自动审查系统</p>
        <div class="brand-signal"><span></span> SYSTEM READY</div>
      </div>
      <form class="login-card" @submit.prevent="signIn">
        <div class="login-heading"><p>WELCOME BACK</p><h2>账号登录</h2></div>
        <label class="login-field" for="loginUsername"><span>账号</span><input id="loginUsername" v-model.trim="loginUsername" autocomplete="username" placeholder="请输入账号" required /></label>
        <label class="login-field" for="loginPassword"><span>密码</span><input id="loginPassword" v-model="loginPassword" autocomplete="current-password" placeholder="请输入密码" required type="password" /></label>
        <p v-if="loginError" class="login-error" role="alert">{{ loginError }}</p>
        <button class="login-button" type="submit">进入系统</button>
        <p class="login-note">NAURA DIGITAL MANUFACTURING</p>
      </form>
    </section>
  </main>

  <main v-else class="app-shell">
    <section class="workspace">
      <header class="topbar">
        <div class="product-identity">
          <img src="/images/naura-logo.png" alt="北方华创 NAURA" />
          <div><h1>智审图</h1><p>AI辅助机械设计图纸自动审查系统</p></div>
        </div>
        <div class="topbar-actions">
          <div class="system-status" :class="{ offline: !isApiOnline }"><span></span>{{ apiStatus }}</div>
          <button class="logout-button" type="button" @click="signOut">退出登录</button>
        </div>
      </header>

      <p v-if="actionError" class="feedback error">{{ actionError }}</p>

      <template v-if="activeView === 'history'">
        <section class="upload-panel">
          <div class="panel-heading"><div><p class="eyebrow">NEW REVIEW</p><h2>创建审查任务</h2></div><span>上传 PDF 与 DXF 后生成审查报告</span></div>
          <form class="upload-box" @submit.prevent="submitReview">
            <label class="file-pair" for="pdfFile"><span>PDF 底图</span><input id="pdfFile" accept=".pdf,application/pdf" type="file" required @change="updateFile($event, 'pdf')" /></label>
            <label class="file-pair" for="dxfFile"><span>DXF 数据</span><input id="dxfFile" accept=".dxf,application/dxf" type="file" required @change="updateFile($event, 'dxf')" /></label>
            <button class="review-button" type="submit" :disabled="isSubmitting">{{ isSubmitting ? "审查中..." : "审查" }}</button>
          </form>
        </section>

        <section class="history-panel">
          <div class="panel-heading"><div><p class="eyebrow">REVIEW HISTORY</p><h2>审查记录</h2></div><span>{{ history.length }} 条记录</span></div>
          <p v-if="historyError" class="feedback error">{{ historyError }}</p>
          <div v-else class="history-table">
            <div class="history-table-header"><span>图纸文件</span><span>审查时间</span><span>审查问题</span><span>操作</span></div>
            <article v-for="item in history" :key="item.id" class="history-row">
              <button class="history-main" type="button" @click="openReport(item.id)"><strong>{{ item.file.name }}</strong><span>查看报告详情</span></button>
              <time>{{ formatTime(item.createdAt) }}</time>
              <span class="issue-count">{{ item.summary.totalIssues }} 个</span>
              <button class="delete-button" type="button" @click="deleteReview(item.id)">删除</button>
            </article>
            <div v-if="history.length === 0" class="empty-state">暂无审查记录</div>
          </div>
        </section>
      </template>

      <template v-else>
        <div class="detail-nav"><button class="back-button" type="button" @click="activeView = 'history'">返回审查记录</button></div>
        <section v-if="report" class="report-panel">
          <div class="panel-heading"><div><p class="eyebrow">REVIEW REPORT</p><h2>报告详情</h2></div><span>{{ reportMeta }}</span></div>
          <div class="report-summary">
            <article><span>总问题</span><strong>{{ summary.totalIssues }}</strong></article>
            <article><span>Critical</span><strong>{{ summary.critical }}</strong></article>
            <article><span>Warning</span><strong>{{ summary.warning }}</strong></article>
            <article><span>Notice</span><strong>{{ summary.notice }}</strong></article>
          </div>
          <div class="parser-meta">{{ parserMeta }}</div>
          <section class="report-visual"><h3>图纸标注</h3>
            <template v-if="report.visual?.available && report.visual.baseImage"><div class="dxf-overlay-frame" :style="{ width: `${report.visual.width || 960}px`, height: `${report.visual.height || 640}px` }"><img class="pdf-base-image" :src="report.visual.baseImage" alt="PDF 图纸底图" /><div class="dxf-overlay-layer" v-html="report.visual.overlaySvg || ''"></div></div></template>
            <template v-else-if="report.visual?.available && report.visual.baseSvg"><div class="dxf-overlay-frame" :style="{ width: `${report.visual.width || 960}px`, height: `${report.visual.height || 640}px` }"><div class="dxf-base-layer" v-html="report.visual.baseSvg"></div><div class="dxf-overlay-layer" v-html="report.visual.overlaySvg || ''"></div></div></template>
            <div v-else class="visual-warning">{{ visualMessage(report.visual) }}</div>
          </section>
          <section class="issue-section"><div class="issue-section-title"><h3>审查问题</h3><span>{{ report.issues.length }} 项</span></div>
            <div v-if="report.issues.length" class="issue-list"><article v-for="issue in report.issues" :key="issue.id || issue.code" class="issue-card" :class="issue.severity"><div class="issue-heading"><strong>{{ issue.title }}</strong><span class="badge">{{ issue.severity }}</span></div><p>{{ issue.description }}</p><p class="suggestion">{{ issue.suggestion }}</p><p v-if="issue.evidence?.length">证据：{{ issue.evidence.join(" / ") }}</p></article></div>
            <div v-else class="empty-state">未发现明显尺寸审查问题。</div>
          </section>
        </section>
      </template>
    </section>
  </main>
</template>
