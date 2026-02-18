/**
 * AgentTeams Desktop 客户端入口
 *
 * 职责：
 * 1. 启动后端服务（Python sidecar）
 * 2. 启动 Client Runtime（Python sidecar）
 * 3. 加载 Web 前端（iframe 或直连）
 * 4. 维护 Runtime 健康检查
 */

const BACKEND_URL = "http://127.0.0.1:8000";
const RUNTIME_URL = "http://127.0.0.1:19800";
const HEALTH_CHECK_INTERVAL = 15_000;

let runtimeOnline = false;

async function checkService(url: string, timeout = 3000): Promise<boolean> {
  try {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeout);
    const resp = await fetch(`${url}/health`, { signal: controller.signal });
    clearTimeout(id);
    return resp.ok;
  } catch {
    return false;
  }
}

async function waitForBackend(): Promise<void> {
  const loadingText = document.getElementById("loading-text");
  let attempts = 0;
  const maxAttempts = 60;

  while (attempts < maxAttempts) {
    if (loadingText) {
      loadingText.textContent = `正在连接后端服务... (${attempts + 1}/${maxAttempts})`;
    }
    if (await checkService(BACKEND_URL)) {
      return;
    }
    await new Promise((r) => setTimeout(r, 1000));
    attempts++;
  }
  throw new Error("后端服务启动超时");
}

function loadWebUI(): void {
  const app = document.getElementById("app");
  if (!app) return;

  const iframe = document.createElement("iframe");
  iframe.src = BACKEND_URL;
  iframe.id = "webui-frame";

  app.innerHTML = "";
  app.appendChild(iframe);
}

async function checkRuntime(): Promise<void> {
  const dot = document.getElementById("runtime-dot");
  const status = document.getElementById("runtime-status");
  const versionInfo = document.getElementById("version-info");

  try {
    const resp = await fetch(`${RUNTIME_URL}/health`);
    if (resp.ok) {
      const data = await resp.json();
      runtimeOnline = true;
      if (dot) {
        dot.classList.remove("offline", "checking");
        dot.classList.add("online");
      }
      if (status) status.textContent = `Runtime: 在线 v${data.version}`;
      if (versionInfo) versionInfo.textContent = `能力: ${(data.capabilities || []).join(", ")}`;
    } else {
      throw new Error("非 200 响应");
    }
  } catch {
    runtimeOnline = false;
    if (dot) {
      dot.classList.remove("online", "checking");
      dot.classList.add("offline");
    }
    if (status) status.textContent = "Runtime: 离线（本地能力不可用）";
    if (versionInfo) versionInfo.textContent = "";
  }
}

async function main(): Promise<void> {
  try {
    await waitForBackend();
    loadWebUI();
  } catch (err) {
    const loadingText = document.getElementById("loading-text");
    if (loadingText) {
      loadingText.textContent = `启动失败: ${err}。请确认后端服务已运行。`;
    }
  }

  await checkRuntime();
  setInterval(checkRuntime, HEALTH_CHECK_INTERVAL);
}

document.addEventListener("DOMContentLoaded", main);
