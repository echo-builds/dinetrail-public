import { DEMO_GUIDE, DEMO_PAGES } from "./demo-data.js?v=20261116-3";
import { clearImages, getImage, putImage } from "./image-store.js";

const initialUrlParams = new URLSearchParams(location.search);
const sampleMode = initialUrlParams.get("sample") === "1";
const freshStart = !sampleMode && initialUrlParams.get("fresh") === "1";
const STORAGE_KEY = sampleMode ? "shitu-conversation-sample-v2" : "shitu-conversation-v2";
const SESSION_POINTER_KEY = "shitu-active-session-v1";
const GENERIC_GUIDE_DISH_NAMES = new Set(["牛排", "牛肉", "猪肉", "羊肉", "鸡肉", "烤鸡", "烤鸡肉", "鸭肉", "鱼", "海鲜", "汤", "沙拉", "意面", "面", "汉堡", "甜点", "蛋糕", "咖啡", "茶", "酒"]);
const initialState = {
  guide: null,
  pages: [],
  selections: {},
  messages: [{
    id: "welcome",
    role: "assistant",
    kind: "welcome",
    text: "把攻略或现场菜单发给我。我们可以边看、边问、边选，之前选过的菜会一直保留。",
  }],
  liveModel: false,
  ocrEnabled: false,
  busy: null,
  chatBusy: false,
  draftDishId: null,
};

let state = freshStart
  ? { ...initialState, selections: {}, pages: [], messages: [...initialState.messages] }
  : loadState();
const imageCache = new Map();
let modalReturnFocus = null;
let progressTimer = null;
let sessionId = sampleMode ? null : new URLSearchParams(location.search).get("session");
let sessionReady = false;
let sessionSyncTimer = null;
let sessionInitialization = null;
let homeRequested = false;
let entryDraft = { menuFiles: [], menuPreviews: [], guideSource: "" };
let guideRecoveryAllowed = false;
let operationVersion = 0;
let composerDraft = "";
let eurCnyRate = null;
let eurCnyDate = "";
const activeApiControllers = new Set();

function cancelActiveOperations() {
  operationVersion += 1;
  activeApiControllers.forEach((controller) => controller.abort());
  activeApiControllers.clear();
}

function isOperationCurrent(version) {
  return version === operationVersion;
}

function loadState() {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    const messages = stored.messages?.length ? stored.messages : initialState.messages;
    const cleanedMessages = messages.filter((message, index) => {
      if (!(message.kind === "error" && message.text?.startsWith("这次没有回答成功"))) return true;
      return !messages.slice(index + 1).some((later) => later.role === "assistant" && later.kind === "chat");
    });
    return {
      ...initialState,
      ...stored,
      selections: stored.selections || {},
      pages: stored.pages || [],
      messages: cleanedMessages,
      busy: null,
      chatBusy: false,
    };
  } catch {
    return { ...initialState, selections: {}, pages: [], messages: [...initialState.messages] };
  }
}

function save() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...state, busy: null, chatBusy: false }));
  scheduleSessionSync();
}

function sessionState() {
  return { ...state, busy: null, chatBusy: false };
}

async function sessionRequest(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "content-type": "application/json", ...(options.headers || {}) },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "点餐会话请求失败");
  return data;
}

function setSessionLocation(id) {
  if (!id || sampleMode) return;
  const url = new URL(location.href);
  url.searchParams.set("session", id);
  url.searchParams.delete("fresh");
  history.replaceState(null, "", url);
  localStorage.setItem(SESSION_POINTER_KEY, id);
}

async function createServerSession() {
  if (sampleMode) return null;
  const result = await sessionRequest("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ state: sessionState() }),
  });
  sessionId = result.sessionId;
  sessionReady = true;
  setSessionLocation(sessionId);
  return result;
}

async function initializeDiningSession() {
  if (sampleMode) return;
  if (freshStart) {
    localStorage.removeItem(SESSION_POINTER_KEY);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessionState()));
    await clearImages().catch(() => {});
    await createServerSession();
    return;
  }
  const explicitSession = new URLSearchParams(location.search).get("session");
  const storedSession = localStorage.getItem(SESSION_POINTER_KEY);
  const candidate = explicitSession || storedSession;
  if (candidate) {
    try {
      const result = await sessionRequest(`/api/sessions/${encodeURIComponent(candidate)}`);
      state = {
        ...initialState,
        ...result.state,
        selections: result.state?.selections || {},
        pages: result.state?.pages || [],
        messages: result.state?.messages?.length ? result.state.messages : [...initialState.messages],
        busy: null,
        chatBusy: false,
        liveModel: state.liveModel,
        ocrEnabled: state.ocrEnabled,
      };
      sessionId = result.sessionId;
      sessionReady = true;
      setSessionLocation(sessionId);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(sessionState()));
      return;
    } catch (error) {
      console.warn("点餐会话恢复失败，将创建新会话", error);
      if (explicitSession) {
        state = { ...initialState, selections: {}, pages: [], messages: [...initialState.messages], liveModel: state.liveModel, ocrEnabled: state.ocrEnabled };
      }
      localStorage.removeItem(SESSION_POINTER_KEY);
    }
  }
  await createServerSession();
}

function scheduleSessionSync() {
  if (!sessionReady || !sessionId || sampleMode) return;
  if (sessionSyncTimer) window.clearTimeout(sessionSyncTimer);
  sessionSyncTimer = window.setTimeout(async () => {
    try {
      await sessionRequest(`/api/sessions/${encodeURIComponent(sessionId)}`, {
        method: "PUT",
        body: JSON.stringify({ state: sessionState() }),
      });
    } catch (error) {
      console.warn("点餐会话同步失败", error);
    }
  }, 250);
}

function dataUrlFromBlob(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

async function persistImage(key, dataUrl) {
  await putImage(key, dataUrl).catch(() => {});
  if (sampleMode) return;
  if (sessionInitialization) await sessionInitialization.catch(() => {});
  if (!sessionId || !sessionReady) throw new Error("服务端点餐会话尚未就绪");
  await sessionRequest(`/api/sessions/${encodeURIComponent(sessionId)}/images/${encodeURIComponent(key)}`, {
    method: "POST",
    body: JSON.stringify({ dataUrl }),
  });
}

async function restoredImage(key) {
  const local = await getImage(key).catch(() => null);
  if (local || !sessionId || sampleMode) return local;
  const response = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/images/${encodeURIComponent(key)}`);
  if (!response.ok) return null;
  const dataUrl = await dataUrlFromBlob(await response.blob());
  await putImage(key, dataUrl).catch(() => {});
  return dataUrl;
}

function uid(prefix) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

function esc(value = "") {
  return String(value).replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[character]));
}

function money(value) {
  return new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format(Number(value) || 0);
}

async function loadEurCnyRate() {
  try {
    const response = await fetch("/api/fx/eur-cny");
    if (!response.ok) return;
    const data = await response.json();
    if (!(Number(data.rate) > 0) || !/^\d{4}-\d{2}-\d{2}$/.test(data.date || "")) return;
    eurCnyRate = Number(data.rate);
    eurCnyDate = data.date;
    const estimate = document.querySelector("#order-cny-total");
    if (estimate) estimate.textContent = orderCnyPriceLabel();
  } catch {
    // The waiter-facing euro total remains available when reference rates are offline.
  }
}

function pricingFor(page) {
  if (page?.pricing?.mode) return page.pricing;
  return {
    mode: page?.dishes?.some((dish) => Number(dish.price) > 0) ? "a_la_carte" : "unknown",
    fixedPrice: 0,
    note: "",
  };
}

function dishPriceLabel(dish, pricing = {}) {
  const optionPrices = (dish.priceOptions || []).map((option) => Number(option.price)).filter((price) => price > 0);
  if (optionPrices.length) return `${money(Math.min(...optionPrices))} 起`;
  if (Number(dish.price) > 0) return money(dish.price);
  if (pricing.mode === "fixed_menu") return "套餐内";
  if (pricing.mode === "multiple_fixed_menus") return "套餐选项";
  return "价格待确认";
}

function originalDishName(dish) {
  return String(dish.original || dish.nameZh || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find(Boolean) || dish.nameZh || "";
}

function orderHighlightBox(dish) {
  const box = dish.box || {};
  let x = Number(box.x);
  let y = Number(box.y);
  let width = Number(box.w);
  let height = Number(box.h);
  if (![x, y, width, height].every(Number.isFinite) || width <= 0 || height <= 0) return null;
  if (dish.boxSource === "ocr" && width < 45 && height > width * 1.6) {
    const centerX = x + width / 2;
    const centerY = y + height / 2;
    [width, height] = [height, width];
    x = centerX - width / 2;
    y = centerY - height / 2;
  }
  const centerX = x + width / 2;
  const centerY = y + height / 2;
  width = Math.max(42, Math.min(width, 330)) + 12;
  height = Math.max(11, Math.min(height, 40)) + 8;
  x = Math.max(0, Math.min(1000 - width, centerX - width / 2));
  y = Math.max(0, Math.min(1000 - height, centerY - height / 2));
  return { x, y, width, height };
}

function dishes() {
  return state.pages.flatMap((page) => page.dishes.map((dish) => ({
    ...dish,
    pageId: page.id,
    pageTitle: page.title,
    pagePricing: pricingFor(page),
    pageAsset: page.asset || imageCache.get(page.assetKey) || "",
  })));
}

function draftDish() {
  return state.draftDishId ? dishes().find((dish) => dish.id === state.draftDishId) : null;
}

function selectedDishes() {
  return dishes().filter((dish) => state.selections[dish.id]);
}

function selectedCount() {
  return selectedDishes().reduce((sum, dish) => sum + (state.selections[dish.id] || 0), 0);
}

function total() {
  const selected = selectedDishes();
  const itemTotal = selected.reduce((sum, dish) => sum + (Number(dish.price) || 0) * state.selections[dish.id], 0);
  const fixedPages = new Map();
  selected.forEach((dish) => {
    if (dish.pagePricing?.mode === "fixed_menu" && Number(dish.pagePricing.fixedPrice) > 0) {
      fixedPages.set(dish.pageId, Number(dish.pagePricing.fixedPrice));
    }
  });
  return itemTotal + [...fixedPages.values()].reduce((sum, value) => sum + value, 0);
}

function orderTotalIsKnown() {
  const selected = selectedDishes();
  return selected.length > 0 && selected.every((dish) =>
    Number(dish.price) > 0 ||
    (dish.pagePricing?.mode === "fixed_menu" && Number(dish.pagePricing.fixedPrice) > 0)
  );
}

function orderCnyPriceLabel() {
  if (!eurCnyRate || !orderTotalIsKnown()) return "";
  const amount = new Intl.NumberFormat("zh-CN", {
    style: "currency", currency: "CNY", maximumFractionDigits: 0,
  }).format(total() * eurCnyRate);
  return `约 ${amount} · ECB ${eurCnyDate}`;
}

function orderPriceLabel() {
  const selected = selectedDishes();
  if (!selected.length) return money(0);
  const itemTotal = selected.reduce((sum, dish) => sum + (Number(dish.price) || 0) * state.selections[dish.id], 0);
  const fixedPages = new Map();
  let hasUnknown = false;
  selected.forEach((dish) => {
    if (dish.pagePricing?.mode === "fixed_menu" && Number(dish.pagePricing.fixedPrice) > 0) {
      fixedPages.set(dish.pageId, Number(dish.pagePricing.fixedPrice));
    } else if (!(Number(dish.price) > 0)) {
      hasUnknown = true;
    }
  });
  const fixedTotal = [...fixedPages.values()].reduce((sum, value) => sum + value, 0);
  if (hasUnknown) return "价格待确认";
  if (fixedTotal && itemTotal) return `${money(fixedTotal)} 套餐 + ${money(itemTotal)}`;
  if (fixedTotal) return `${money(fixedTotal)} 套餐`;
  return money(itemTotal);
}

function canImportGuide() {
  return !state.guide && (!state.pages.length || guideRecoveryAllowed);
}

function hasDiningActivity() {
  return state.messages.some((message) => message.kind !== "welcome") || Boolean(state.guide) || Boolean(state.pages.length);
}

function isPristineDiningSession() {
  return !hasDiningActivity() && !state.busy;
}

function isHome() {
  return homeRequested || isPristineDiningSession();
}

function imageFor(key, fallback = "") {
  return imageCache.get(key) || fallback;
}

function toast(message) {
  const element = document.querySelector("#toast");
  element.textContent = message;
  element.classList.add("show");
  window.setTimeout(() => element.classList.remove("show"), 2200);
}

async function api(path, body) {
  const controller = new AbortController();
  activeApiControllers.add(controller);
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(sampleMode ? { "X-Sample-Mode": "1" } : {}),
        ...(sessionReady && sessionId ? { "X-Dining-Session": sessionId } : {}),
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "请求失败");
    return data;
  } finally {
    activeApiControllers.delete(controller);
  }
}

async function* apiStream(path, body) {
  const controller = new AbortController();
  activeApiControllers.add(controller);
  try {
    const response = await fetch(path, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(sessionReady && sessionId ? { "X-Dining-Session": sessionId } : {}),
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.error || "菜单识别请求失败");
    }
    if (!response.body) throw new Error("浏览器无法接收流式菜单");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let newline = buffer.indexOf("\n");
      while (newline !== -1) {
        const line = buffer.slice(0, newline).trim();
        buffer = buffer.slice(newline + 1);
        if (line) yield JSON.parse(line);
        newline = buffer.indexOf("\n");
      }
    }
    buffer += decoder.decode();
    if (buffer.trim()) yield JSON.parse(buffer.trim());
  } finally {
    activeApiControllers.delete(controller);
  }
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function prepareImage(file) {
  const raw = await fileToDataUrl(file);
  const image = new Image();
  image.src = raw;
  await image.decode();
  const maxSide = 3000;
  const scale = Math.min(1, maxSide / Math.max(image.naturalWidth, image.naturalHeight));
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
  canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
  canvas.getContext("2d", { alpha: false }).drawImage(image, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", 0.9);
}

async function menuVisionRegions(dataUrl) {
  const image = new Image();
  image.src = dataUrl;
  await image.decode();
  const width = image.naturalWidth;
  const height = image.naturalHeight;
  if (!width || !height || width / height < 1.08) return [];

  const sampleWidth = Math.min(720, width);
  const sampleHeight = Math.max(1, Math.round(height * sampleWidth / width));
  const sample = document.createElement("canvas");
  sample.width = sampleWidth;
  sample.height = sampleHeight;
  const sampleContext = sample.getContext("2d", { alpha: false, willReadFrequently: true });
  sampleContext.drawImage(image, 0, 0, sampleWidth, sampleHeight);
  const pixels = sampleContext.getImageData(0, 0, sampleWidth, sampleHeight).data;
  const darkness = Array.from({ length: sampleWidth }, (_, x) => {
    let total = 0;
    for (let y = 0; y < sampleHeight; y += 2) {
      const offset = (y * sampleWidth + x) * 4;
      const luminance = pixels[offset] * 0.2126 + pixels[offset + 1] * 0.7152 + pixels[offset + 2] * 0.0722;
      if (luminance < 215) total += (215 - luminance) / 215;
    }
    return total;
  });
  const smoothed = darkness.map((_, x) => {
    let sum = 0;
    let count = 0;
    for (let nearby = Math.max(0, x - 4); nearby <= Math.min(sampleWidth - 1, x + 4); nearby += 1) {
      sum += darkness[nearby];
      count += 1;
    }
    return sum / count;
  });
  const median = [...smoothed].sort((a, b) => a - b)[Math.floor(smoothed.length / 2)] || 1;
  const lowestIn = (start, end) => {
    let best = Math.round(start * sampleWidth);
    for (let x = best + 1; x <= Math.round(end * sampleWidth); x += 1) {
      if (smoothed[x] < smoothed[best]) best = x;
    }
    return { ratio: best / sampleWidth, score: smoothed[best] };
  };
  const firstThird = lowestIn(0.25, 0.42);
  const secondThird = lowestIn(0.58, 0.75);
  const center = lowestIn(0.4, 0.6);
  let cuts = [];
  if (firstThird.score < median * 0.72 && secondThird.score < median * 0.72) cuts = [firstThird.ratio, secondThird.ratio];
  else if (center.score < median * 0.72) cuts = [center.ratio];
  else if (width / height >= 1.15) cuts = [1 / 3, 2 / 3];
  else cuts = [0.5];

  const boundaries = [0, ...cuts, 1];
  return boundaries.slice(0, -1).map((start, index) => {
    const end = boundaries[index + 1];
    const sourceX = Math.round(start * width);
    const sourceWidth = Math.max(1, Math.round((end - start) * width));
    const upscale = Math.min(2, 2400 / Math.max(sourceWidth, height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, Math.round(sourceWidth * upscale));
    canvas.height = Math.max(1, Math.round(height * upscale));
    canvas.getContext("2d", { alpha: false }).drawImage(image, sourceX, 0, sourceWidth, height, 0, 0, canvas.width, canvas.height);
    return { image: canvas.toDataURL("image/jpeg", 0.92), x: start, y: 0, w: end - start, h: 1 };
  });
}

function header() {
  return `<header class="app-header">
    <button type="button" class="header-back" data-action="home" aria-label="返回首页"><i class="ph ph-caret-left" aria-hidden="true"></i></button>
    <div class="session-title">本次点餐</div>
    <span class="header-spacer" aria-hidden="true"></span>
  </header>`;
}

function homeHeader() {
  const hasActivity = hasDiningActivity();
  return `<header class="app-header home-header">
    <div class="wordmark">DineTrail</div>
    ${hasActivity ? `<button type="button" class="home-resume" data-action="resume">继续点餐</button>` : `<div class="home-product">旅行点餐助手</div>`}
  </header>`;
}

function homeView() {
  const draftCount = entryDraft.menuFiles.length;
  const hasDraft = Boolean(draftCount);
  return `<div class="app-shell home-shell">
    ${homeHeader()}
    <main class="home-view">
      <section class="home-hero">
        <h1>看懂菜单，<br>选到想吃的。</h1>
        <p>边看边问边勾选；口味、避雷和小红书推荐，直接对上每道菜。</p>
      </section>
      <div class="home-preview" aria-hidden="true">
        <div class="home-preview-paper"><img src="/assets/menu-mains.svg" alt=""></div>
        <div class="home-preview-result">
          <span class="home-preview-check"><i class="ph ph-check" aria-hidden="true"></i></span>
          <div class="home-preview-result-top"><small>Confit de canard</small><b>26,00 €</b></div>
          <strong>油封鸭腿</strong>
          <p>像咸香的烤鸭腿，外脆内嫩，油脂偏重。</p>
          <span class="home-preview-tag">小红书推荐</span>
        </div>
      </div>
      <section class="home-start" aria-label="开始一次点餐">
        <label class="home-camera-action">
          <i class="ph ph-camera" aria-hidden="true"></i>
          <strong>拍菜单</strong>
          <input class="hidden-input" type="file" id="home-camera-input" accept="image/*" capture="environment" multiple>
        </label>
        <label class="home-album-action"><i class="ph ph-image-square" aria-hidden="true"></i><span>从相册选择</span><input class="hidden-input" type="file" id="home-menu-input" accept="image/*" multiple></label>
      </section>
      ${hasDraft ? `<button type="button" class="home-draft-resume" data-action="entry-draft">已选 ${draftCount} 张菜单 · 继续</button>` : ""}
      ${!state.liveModel ? `<p class="connection-note home-connection-note">真实识别尚未连接，请检查服务端模型配置。</p>` : ""}
    </main>
  </div>`;
}

function welcomeMessage() { return ""; }

function userTextMessage(message) {
  const text = message.text === "帮我读取这篇小红书攻略" ? "已附上小红书攻略" : message.text;
  if (text === "已附上小红书攻略") return "";
  return `<section class="user-turn"><div class="user-bubble">${message.referencedDishName ? `<span class="user-dish-reference">↳ ${esc(message.referencedDishName)}</span>` : ""}${esc(text)}</div></section>`;
}

function userImageMessage(message) {
  const source = imageFor(message.imageKey, message.asset || "");
  const text = message.text === "帮我记住攻略里推荐的菜" ? "已附上攻略截图" : message.text;
  return `<section class="user-turn" data-message-id="${message.id}"><div class="user-bubble image-bubble">
    ${source ? `<img src="${esc(source)}" alt="${esc(message.alt || "用户上传的图片")}">` : ""}
    <p>${esc(text)}</p>
  </div></section>`;
}

function userMenuBatchMessage(messages) {
  const count = messages.length;
  const withGuide = messages.some((message) => message.withGuide);
  const query = withGuide
    ? `帮我结合攻略看看这 ${count} 页菜单`
    : count > 1 ? `帮我看看这 ${count} 页菜单` : "帮我看看这页菜单";
  const images = messages.map((message, index) => {
    const source = imageFor(message.imageKey, message.asset || "");
    if (!source) return "";
    return `<figure class="menu-attachment"><img src="${esc(source)}" alt="${esc(message.alt || `菜单第 ${index + 1} 页`)}"></figure>`;
  }).join("");
  return `<section class="user-turn menu-batch-turn" data-message-id="${messages[0].id}">
    <div class="menu-attachment-grid" data-count="${count}" aria-label="已附上 ${count} 张菜单图片">${images}</div>
    <div class="user-bubble menu-query-bubble">${esc(query)}</div>
  </section>`;
}

function guideResponse() {
  const guide = state.guide;
  if (!guide) return "";
  const matchCount = dishes().filter((dish) => guideItemsForDish(dish).length).length;
  return `<section class="assistant-turn">
    <p class="guide-attached">${matchCount ? `攻略已附上，已在当前菜单标出 ${matchCount} 个相关项目。` : "攻略已附上。拍到对应项目时，会直接标在菜单里。"}</p>
  </section>`;
}

function selectionControl(dish) {
  const selected = Boolean(state.selections[dish.id]);
  return `<button class="dish-select ${selected ? "selected" : ""}" data-action="select" data-id="${dish.id}" aria-label="${selected ? "移出" : "加入"}${esc(dish.nameZh)}" aria-pressed="${selected}">${selected ? `<i class="ph ph-check" aria-hidden="true"></i>` : ""}</button>`;
}

function guideItemsForDish(dish) {
  const matchIds = new Set(dish.guideMatchIds || []);
  return (state.guide?.items || []).filter((item) => matchIds.has(item.id) && !genericGuideItem(item));
}

function normalizedChinese(value) {
  return String(value || "").match(/[\u3400-\u9fff]/g)?.join("") || "";
}

function genericGuideItem(item) {
  return GENERIC_GUIDE_DISH_NAMES.has(normalizedChinese(item?.nameZh));
}

function guideRating(item) {
  const explicit = (String(item?.nameOriginal || "").match(/[⭐🌟★]/gu) || []).length;
  const stored = Number(item?.rating);
  return explicit || (stored > 0 && stored <= 5 ? stored : 0);
}

function guideTone(items) {
  const caution = items.some((item) => item.sentiment === "caution" || guideRating(item) > 0 && guideRating(item) <= 2);
  const recommended = items.some((item) => item.sentiment === "recommended" || guideRating(item) >= 4);
  if (caution && recommended) return "mixed";
  if (caution) return "caution";
  if (recommended) return "recommended";
  return "mentioned";
}

function guideLabel(items) {
  const source = state.guide?.sourceType === "xiaohongshu" ? "小红书" : "攻略";
  if (guideTone(items) === "mixed") return `${source}评价不一`;
  if (guideTone(items) === "recommended") return `${source}推荐`;
  if (guideTone(items) === "caution") return `${source}避雷`;
  return `${source}提及`;
}

const MENU_RECOMMENDATION_LABELS = new Set(["本店特色", "主厨推荐", "厨师推荐", "店长推荐", "招牌菜", "今日推荐", "菜单推荐"]);

function isFrenchClassic(dish) {
  const name = String(dish.original || "").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  return /\b(french onion soup|soupe a l.?oignon|escargots?|snails? with garlic butter|duck confit|confit de canard|boeuf bourguignon|beef bourguignon|creme brulee|ratatouille|cassoulet|coq au vin|bouillabaisse|quiche lorraine|tartiflette|tartine savoyarde)\b/.test(name);
}

function dishTags(dish) {
  const tags = [];
  const guideItems = guideItemsForDish(dish);
  const canShowGuideQuote = state.guide?.sourceType === "xiaohongshu" && guideItems.some((item) => String(item.sourceQuote || "").trim());
  const guideTag = guideItems.length ? { label: guideLabel(guideItems), tone: `guide-${guideTone(guideItems)}`, action: canShowGuideQuote ? "guide-evidence" : null } : null;
  if (guideTag && guideTone(guideItems) !== "mentioned") tags.push(guideTag);
  const menuLabel = String(dish.menuRecommendationLabel || "").trim();
  if (MENU_RECOMMENDATION_LABELS.has(menuLabel)) tags.push({ label: menuLabel, tone: "menu" });
  if (isFrenchClassic(dish)) tags.push({ label: "法式经典", tone: "classic" });
  if (guideTag && guideTone(guideItems) === "mentioned") tags.push(guideTag);
  return tags;
}

function dishTagMarkup(tag, id) {
  const content = esc(tag.label);
  return tag.action
    ? `<button type="button" class="dish-tag ${tag.tone}" data-action="${tag.action}" data-id="${esc(id)}">${content}</button>`
    : `<span class="dish-tag ${tag.tone}">${content}</span>`;
}

function dishRow(dish, page) {
  const tags = dishTags(dish);
  const aiHint = String(dish.aiDecisionHint || "").trim();
  const menuDescription = dish.descriptionOriginal ? String(dish.summary || "").trim() : "";
  const decisionHint = aiHint || menuDescription || "菜品理解暂未生成";
  const priceOptions = (dish.priceOptions || [])
    .filter((option) => option?.label && Number(option.price) > 0)
    .map((option) => `${option.label} ${money(option.price)}`)
    .join(" · ");
  return `<article class="dish-row ${state.selections[dish.id] ? "selected" : ""} ${state.draftDishId === dish.id ? "referenced" : ""}" data-action="quote-dish" data-id="${esc(dish.id)}">
    ${selectionControl(dish)}
    <button type="button" class="dish-copy" data-action="quote-dish" data-id="${esc(dish.id)}" aria-label="引用${esc(dish.nameZh)}提问">
      <div class="dish-original">${esc(dish.original)}</div>
      <div class="dish-name-line"><strong>${esc(dish.nameZh)}</strong></div>
    </button>
    <strong class="dish-price ${Number(dish.price) > 0 ? "" : "non-item-price"}">${dishPriceLabel(dish, pricingFor(page))}</strong>
    ${tags.length ? `<div class="dish-tags">${tags.map((tag) => dishTagMarkup(tag, dish.id)).join("")}</div>` : ""}
    <p class="decision-hint" title="${esc(decisionHint)}">
      <span class="decision-copy">${esc(decisionHint)}</span>
    </p>
    ${priceOptions ? `<p class="dish-price-options">${esc(priceOptions)}</p>` : ""}
  </article>`;
}

function menuResponse(message) {
  const page = state.pages.find((item) => item.id === message.pageId);
  if (!page) return "";
  if (page.streaming && !page.dishes.length) return "";
  const pricing = pricingFor(page);
  const ordered = page.dishes;
  return `<section class="assistant-turn menu-turn" data-page-id="${page.id}">
    ${pricing.mode === "fixed_menu" ? `<p class="menu-pricing-note"><strong>${money(pricing.fixedPrice)} 固定套餐</strong><span>${esc(pricing.note || "以下是套餐可选项，不是每项单独收费")}</span></p>` : ""}
    ${pricing.mode === "multiple_fixed_menus" ? `<p class="menu-pricing-note"><strong>多种固定套餐</strong><span>${esc(pricing.note || "不同套餐价格和可选项不同，请结合原图确认")}</span></p>` : ""}
    <div class="intelligence-surface menu-surface">
      <div class="dish-list">${ordered.map((dish) => dishRow(dish, page)).join("")}
        ${page.streaming ? `<div class="menu-stream-dots" role="img" aria-label="菜单仍在加载"><span></span><span></span><span></span></div>` : ""}
      </div>
    </div>
  </section>`;
}

function chatResponse(message) {
  return `<section class="assistant-turn chat-answer"><p>${esc(message.text)}</p></section>`;
}

function errorResponse(message) {
  return `<section class="assistant-turn error-answer"><p>${esc(message.text)}</p><button data-action="attachments">重新上传</button></section>`;
}

function renderMessage(message) {
  if (message.kind === "welcome") return welcomeMessage(message);
  if (message.kind === "menu-pending") return "";
  if (message.role === "user" && message.kind === "image") return userImageMessage(message);
  if (message.role === "user") return userTextMessage(message);
  if (message.kind === "guide") return guideResponse();
  if (message.kind === "menu") return menuResponse(message);
  if (message.kind === "error") return errorResponse(message);
  return chatResponse(message);
}

function renderMessages(messages) {
  const renderedBatches = new Set();
  return messages.map((message) => {
    if (message.role === "user" && message.kind === "image" && message.batchId) {
      if (renderedBatches.has(message.batchId)) return "";
      renderedBatches.add(message.batchId);
      return userMenuBatchMessage(messages.filter((item) => item.role === "user" && item.kind === "image" && item.batchId === message.batchId));
    }
    return renderMessage(message);
  }).join("");
}

function isMenuBusy() {
  return state.busy?.type === "start" || state.busy?.type === "menu";
}

function hasVisibleDishesInBusyBatch() {
  return isMenuBusy() && state.pages.some((page) => page.batchId === state.busy.batchId && page.dishes.length);
}

function busyLabel() {
  if (!state.busy) return state.chatBusy ? "正在回答问题…" : "";
  if (state.chatBusy && hasVisibleDishesInBusyBatch()) return "正在回答问题…";
  if (state.chatBusy && isMenuBusy()) return "正在读取菜单并回答问题…";
  const elapsed = Math.floor((Date.now() - state.busy.startedAt) / 1000);
  if (state.busy.type === "start") {
    if (state.busy.stage === "preparing-guide") return "正在读取攻略…";
    if (state.busy.stage === "matching") return "正在把攻略推荐匹配到菜单…";
    if (elapsed < 7) return "正在同时读取菜单和攻略…";
    if (elapsed < 18) return "正在整理菜单项目、价格和推荐…";
    return "正在识别菜品并补充味道口感…";
  }
  if (state.busy.type === "guide") {
    if (state.busy.mode === "source") return elapsed < 6 ? "正在读取攻略链接或文案…" : "正在整理推荐菜和提醒…";
    return elapsed < 6 ? "正在读取攻略截图…" : "正在整理推荐菜和提醒…";
  }
  const progress = state.busy.total > 1 ? `第 ${state.busy.current}/${state.busy.total} 页 · ` : "";
  if (elapsed < 6) return `${progress}正在读取菜单图片…`;
  if (elapsed < 16) return `${progress}正在逐项识别菜单内容…`;
  return `${progress}正在核对价格并补充味道口感…`;
}

function busyTurn() {
  if (!state.busy && !state.chatBusy) return "";
  if (hasVisibleDishesInBusyBatch() && !state.chatBusy) return "";
  return `<section class="assistant-turn thinking-turn" aria-live="polite"><span class="thinking-dot"></span><span id="busy-label">${busyLabel()}</span></section>`;
}

function dock() {
  const count = selectedCount();
  const referenced = draftDish();
  const composerBlocked = state.chatBusy || (state.busy && !isMenuBusy());
  return `<footer class="conversation-dock">
    ${count ? `<button class="order-fab" data-action="order" aria-label="查看已选 ${count} 个项目的点菜单"><i class="ph ph-receipt" aria-hidden="true"></i><strong>${count} 项 · ${orderPriceLabel()}</strong></button>` : ""}
    <form class="composer ${referenced ? "composer-expanded" : ""}" id="composer-form">
      ${referenced ? `<div class="composer-reference"><span>↳ 已引用 · <strong>${esc(referenced.nameZh)}</strong></span><button type="button" data-action="clear-dish-reference" aria-label="取消引用${esc(referenced.nameZh)}">×</button></div>` : ""}
      <button type="button" class="composer-tool" data-action="attachments" aria-label="追加现场菜单"><i class="ph ${referenced ? "ph-plus" : "ph-camera-plus"}" aria-hidden="true"></i></button>
      <label class="sr-only" for="composer-input">输入问题</label>
      ${referenced
        ? `<textarea id="composer-input" name="message" rows="2" lang="zh-CN" spellcheck="false" autocapitalize="off" autocorrect="off" placeholder="介绍一下这道菜" ${composerBlocked ? "disabled" : ""}>${esc(composerDraft)}</textarea>`
        : `<input id="composer-input" name="message" lang="zh-CN" spellcheck="false" autocapitalize="off" autocorrect="off" autocomplete="off" value="${esc(composerDraft)}" placeholder="问菜单、拍下一页…" ${composerBlocked ? "disabled" : ""}>`}
      <button class="send-button" aria-label="发送" ${composerBlocked ? "disabled" : ""}><i class="ph ph-arrow-up" aria-hidden="true"></i></button>
    </form>
  </footer>`;
}

function render(follow = false) {
  if (isHome()) {
    document.querySelector("#app").innerHTML = homeView();
    syncProgressTimer();
    return;
  }
  const previousThread = document.querySelector(".conversation");
  const previousScroll = previousThread?.scrollTop || 0;
  const previousInput = document.activeElement?.id === "composer-input" ? document.activeElement : null;
  const composer = previousInput?.closest(".composer");
  const composerBlocked = state.chatBusy || (state.busy && !isMenuBusy());
  if (previousThread && composer && !composerBlocked
      && composer.classList.contains("composer-expanded") === Boolean(draftDish())) {
    // Keep the focused input in the DOM so streaming dishes cannot interrupt Chinese IME composition.
    previousThread.innerHTML = `${renderMessages(state.messages)}${busyTurn()}`;
    previousThread.scrollTop = follow ? previousThread.scrollHeight : previousScroll;
    if (!follow) requestAnimationFrame(() => { previousThread.scrollTop = previousScroll; });
    syncProgressTimer();
    return;
  }
  const cursor = previousInput ? [previousInput.selectionStart, previousInput.selectionEnd] : null;
  document.querySelector("#app").innerHTML = `<div class="app-shell">${header()}<main class="conversation" id="conversation">${renderMessages(state.messages)}${busyTurn()}</main>${dock()}</div>`;
  if (cursor) {
    const input = document.querySelector("#composer-input");
    if (input && !input.disabled) {
      input.focus({ preventScroll: true });
      input.setSelectionRange(cursor[0], cursor[1]);
    }
  }
  const thread = document.querySelector(".conversation");
  if (thread) {
    thread.scrollTop = follow ? thread.scrollHeight : previousScroll;
    if (!follow) requestAnimationFrame(() => { thread.scrollTop = previousScroll; });
  }
  syncProgressTimer();
}

function syncProgressTimer() {
  if (progressTimer) window.clearInterval(progressTimer);
  progressTimer = null;
  if (!state.busy && !state.chatBusy) return;
  if (hasVisibleDishesInBusyBatch() && !state.chatBusy) return;
  progressTimer = window.setInterval(() => {
    const label = document.querySelector("#busy-label");
    if (label) label.textContent = busyLabel();
  }, 1000);
}

function modal(content, className = "") {
  if (!modalReturnFocus || !modalReturnFocus.isConnected) modalReturnFocus = document.activeElement;
  document.querySelector("#modal-root").innerHTML = `<div class="modal-backdrop"><section class="sheet ${className}" role="dialog" aria-modal="true">${content}</section></div>`;
  document.querySelector(".sheet button, .sheet input")?.focus();
}

function closeModal() {
  document.querySelector("#modal-root").innerHTML = "";
  modalReturnFocus?.focus?.();
  modalReturnFocus = null;
}

function clearEntryDraft() {
  entryDraft.menuPreviews.forEach((preview) => URL.revokeObjectURL(preview.url));
  entryDraft = { menuFiles: [], menuPreviews: [], guideSource: "" };
}

function stageEntryMenus(files) {
  const images = [...files].filter((file) => file?.type?.startsWith("image/"));
  if (!images.length) return toast("请选择菜单图片");
  for (const file of images) {
    entryDraft.menuFiles.push(file);
    entryDraft.menuPreviews.push({ name: file.name || "菜单图片", url: URL.createObjectURL(file) });
  }
  entryDraftSheet();
}

function stageEntryGuide(source) {
  const cleaned = String(source || "").trim();
  if (!cleaned) return toast("请粘贴小红书分享链接");
  entryDraft.guideSource = cleaned;
  entryDraftSheet();
}

function entryDraftSheet() {
  const count = entryDraft.menuFiles.length;
  const menuContent = count ? `<div class="draft-menu-grid">${entryDraft.menuPreviews.map((preview, index) => `<figure class="draft-menu-preview"><img src="${esc(preview.url)}" alt="菜单第 ${index + 1} 张"><button type="button" data-action="remove-draft-menu" data-id="${index}" aria-label="移除第 ${index + 1} 张菜单"><i class="ph ph-x" aria-hidden="true"></i></button></figure>`).join("")}<label class="draft-add-menu"><i class="ph ph-plus" aria-hidden="true"></i><span>继续添加</span><input class="hidden-input" id="draft-menu-input" type="file" accept="image/*" multiple></label></div>` : `<label class="draft-menu-empty"><i class="ph ph-camera-plus" aria-hidden="true"></i><strong>添加现场菜单</strong><span>可选择一张或多张</span><input class="hidden-input" id="draft-menu-input" type="file" accept="image/*" multiple></label>`;
  modal(`<header class="sheet-head"><div><small>开始前确认</small><h2>准备本次点餐</h2></div><button class="sheet-close" data-action="close-entry-draft" aria-label="关闭"><i class="ph ph-x"></i></button></header>
    <div class="sheet-body entry-draft-body">
      <section class="draft-section"><div class="draft-section-head"><strong>现场菜单</strong>${count ? `<span>${count} 张</span>` : ""}</div>${menuContent}</section>
      <section class="draft-section draft-guide-section">
        <label class="draft-guide-copy" for="draft-guide-source"><strong>带上你看到的推荐菜</strong><span>如果你提前在小红书看过这家餐厅，粘贴分享链接。识别后会把攻略里提到的菜直接标在菜单上，省得来回对照。</span></label>
        <div class="draft-guide-input"><i class="ph ph-link" aria-hidden="true"></i><input id="draft-guide-source" autocomplete="off" inputmode="url" placeholder="粘贴小红书分享链接（可选）" value="${esc(entryDraft.guideSource)}"><span>可选</span></div>
      </section>
      <button type="button" class="draft-start" data-action="start-entry-draft" ${count ? "" : "disabled"}>${count ? "开始识别" : "请先添加菜单"}</button>
    </div>`, "entry-draft-sheet");
}

function attachmentSheet() {
  modal(`<header class="sheet-head"><div><small>继续本次点餐</small><h2>追加菜单</h2></div><button class="sheet-close" data-action="close-modal" aria-label="关闭"><i class="ph ph-x"></i></button></header><div class="sheet-body attachment-options"><label><strong>拍摄或选择菜单</strong><span>可一次选择多张，全部加入本次点餐</span><input class="hidden-input" id="menu-input" type="file" accept="image/*" multiple></label></div>`);
}

function restartSheet() {
  modal(`<header class="sheet-head"><div><small>清除当前数据</small><h2>重新开始？</h2></div><button class="sheet-close" data-action="close-modal" aria-label="关闭"><i class="ph ph-x"></i></button></header>
    <div class="sheet-body reset-confirm-body">
      <p>本次攻略、菜单、勾选和对话都会删除，且无法恢复。</p>
      <div class="reset-confirm-actions">
        <button type="button" data-action="close-modal">继续当前点餐</button>
        <button type="button" class="confirm-reset" data-action="reset">清空并重新开始</button>
      </div>
    </div>`);
}

function guideImportSheet() {
  if (!canImportGuide() && !isPristineDiningSession()) return toast("攻略只能在开始点餐时导入");
  const returnAction = entryDraft.menuFiles.length || entryDraft.guideSource ? "entry-draft" : "close-modal";
  modal(`<header class="sheet-head"><div><small>可选附件</small><h2>小红书攻略</h2></div><button class="sheet-close" data-action="${returnAction}" aria-label="关闭"><i class="ph ph-x"></i></button></header>
    <div class="sheet-body guide-import-body">
      <form id="guide-import-form" class="guide-import-form">
        <label class="sr-only" for="guide-source">小红书分享链接</label>
        <input id="guide-source" name="source" autocomplete="off" inputmode="url" placeholder="粘贴小红书分享链接" required>
        <button class="guide-import-submit" type="submit">附上攻略</button>
      </form>
    </div>`);
}

function guideFallbackSheet(reason = "") {
  modal(`<header class="sheet-head"><div><small>链接未读取成功</small><h2>上传攻略截图</h2></div><button class="sheet-close" data-action="close-modal" aria-label="关闭"><i class="ph ph-x"></i></button></header>
    <div class="sheet-body guide-fallback-body">
      <p>${esc(reason || "暂时无法读取这篇公开笔记。")}</p>
      <p>截下推荐菜所在页面即可。</p>
      <label class="guide-fallback-upload"><i class="ph ph-image" aria-hidden="true"></i><span>选择攻略截图</span><input class="hidden-input" type="file" id="guide-fallback-input" accept="image/*"></label>
      <button type="button" class="guide-fallback-retry" data-action="guide-import">重新粘贴链接</button>
    </div>`, "guide-fallback-sheet");
}

function guideEvidenceSheet(id) {
  const dish = dishes().find((item) => item.id === id);
  const items = dish ? guideItemsForDish(dish) : [];
  if (!dish || !items.length) return toast("这个项目暂时没有可核对的攻略原文");
  const quotes = [...new Set(items.map((item) => String(item.sourceQuote || "").trim()).filter(Boolean))];
  if (!quotes.length) return toast("这个项目暂时没有可核对的攻略原文");
  const sourceUrl = /^https:\/\//i.test(state.guide?.sourceUrl || "") ? state.guide.sourceUrl : "";
  const quoteTitle = state.guide?.sourceType === "xiaohongshu" ? "帖子原话" : "攻略原话";
  modal(`<header class="guide-evidence-head"><h2>${quoteTitle}</h2><button class="sheet-close" data-action="close-modal" aria-label="关闭"><i class="ph ph-x"></i></button></header>
    <div class="sheet-body guide-evidence-body">
      <div class="guide-quote-list">${quotes.map((quote) => `<p class="guide-source-quote">${esc(quote)}</p>`).join("")}</div>
      ${sourceUrl ? `<a class="guide-source-link" href="${esc(sourceUrl)}" target="_blank" rel="noreferrer">查看小红书原帖 <i class="ph ph-arrow-up-right" aria-hidden="true"></i></a>` : ""}
    </div>`, "guide-evidence-sheet");
}

function orderSourcePage(page, index) {
  const source = page.asset || imageFor(page.assetKey);
  const selected = page.dishes.filter((dish) => state.selections[dish.id]);
  const highlights = selected.map((dish) => orderHighlightBox(dish)).filter(Boolean)
    .map((box) => `<rect class="order-source-highlight" x="${box.x}" y="${box.y}" width="${box.width}" height="${box.height}" rx="5"></rect>`).join("");
  return `<figure class="order-source-page"><div class="order-source-image"><img src="${esc(source)}" alt="菜单原图第 ${index + 1} 页">${highlights ? `<svg class="order-source-overlay" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden="true">${highlights}</svg>` : ""}</div><figcaption>第 ${index + 1} / ${state.pages.length} 页 · 已选 ${selected.length} 项</figcaption></figure>`;
}

function orderSheet() {
  const selected = selectedDishes();
  const needsCalibration = state.ocrEnabled && selected.some((dish) => dish.boxSource !== "ocr");
  modal(`<header class="sheet-head order-sheet-head"><h2>Commande</h2><button class="sheet-close" data-action="close-modal" aria-label="关闭"><i class="ph ph-x"></i></button></header><div class="sheet-body order-sheet-body">
    ${selected.length ? `<div class="order-text-list">${selected.map((dish) => `<div class="order-text-row"><b>${state.selections[dish.id]}×</b><span class="order-dish-copy"><strong>${esc(originalDishName(dish))}</strong></span><strong class="order-row-price">${Number(dish.price) > 0 ? money(dish.price * state.selections[dish.id]) : dish.pagePricing?.mode === "fixed_menu" ? "Inclus" : "—"}</strong></div>`).join("")}</div><div class="order-total"><span>Total</span><div class="order-total-values"><strong>${orderTotalIsKnown() ? money(total()) : "À confirmer"}</strong><small id="order-cny-total">${orderCnyPriceLabel()}</small></div></div>` : `<div class="empty-order"><strong>还没有选择项目</strong><p>回到对话里勾选后，会在这里生成文本点菜单。</p></div>`}
    ${state.pages.length ? `<section class="order-sources"><div class="order-sources-head"><h3>查看原图</h3>${needsCalibration ? `<button class="calibrate-positions" data-action="calibrate">校准勾选位置</button>` : `<span>左右滑动查看 ${state.pages.length} 页</span>`}</div><div class="order-source-carousel" tabindex="0" aria-label="已选项目在 ${state.pages.length} 页菜单原图中的位置">${state.pages.map(orderSourcePage).join("")}</div></section>` : ""}
    </div>`);
}

async function calibratePositions() {
  if (!state.ocrEnabled) return toast("当前部署未配置 OCR 坐标校准");
  const operation = operationVersion;
  const pages = state.pages.filter((page) => page.dishes.some((dish) => state.selections[dish.id] && dish.boxSource !== "ocr"));
  if (!pages.length) return;
  const button = document.querySelector(".calibrate-positions");
  if (button) { button.disabled = true; button.textContent = "正在校准…"; }
  try {
    await Promise.all(pages.map(async (page) => {
      const image = page.asset || imageFor(page.assetKey);
      if (!image) throw new Error("原图已丢失，请重新上传");
      const result = await api("/api/locate-menu", { image, dishes: page.dishes });
      if (!isOperationCurrent(operation)) return;
      page.dishes = result.dishes || page.dishes;
    }));
    if (!isOperationCurrent(operation)) return;
    save();
    orderSheet();
    toast("已根据原文文字行重新定位");
  } catch (error) {
    if (!isOperationCurrent(operation) || error?.name === "AbortError") return;
    if (button) { button.disabled = false; button.textContent = "重试校准"; }
    toast(`校准失败：${error.message}`);
  }
}

async function reset() {
  const previousSession = sessionId;
  let remoteDeletionFailed = false;
  cancelActiveOperations();
  if (sessionSyncTimer) window.clearTimeout(sessionSyncTimer);
  sessionSyncTimer = null;
  clearEntryDraft();
  composerDraft = "";
  guideRecoveryAllowed = false;
  localStorage.removeItem(STORAGE_KEY);
  localStorage.removeItem(SESSION_POINTER_KEY);
  const clearImagesTask = clearImages().catch(() => {});
  imageCache.clear();
  state = { ...initialState, selections: {}, pages: [], messages: [...initialState.messages], liveModel: state.liveModel, ocrEnabled: state.ocrEnabled };
  sessionId = null;
  sessionReady = false;
  homeRequested = false;
  const cleanUrl = new URL(location.href);
  cleanUrl.searchParams.delete("session");
  history.replaceState(null, "", cleanUrl);
  closeModal();
  render(true);
  await clearImagesTask;
  if (previousSession && !sampleMode) {
    try {
      const response = await fetch(`/api/sessions/${encodeURIComponent(previousSession)}`, { method: "DELETE" });
      if (!response.ok) throw new Error("服务端删除失败");
    } catch {
      remoteDeletionFailed = true;
    }
  }
  sessionInitialization = createServerSession();
  await sessionInitialization.catch((error) => console.warn("新建点餐会话失败", error));
  if (remoteDeletionFailed) toast("本机已清空；服务端内容将在 48 小时内自动过期");
}

async function streamMenuUpload(upload, batchId, responseMessage, operation, guideItems = []) {
  const page = {
    id: uid("page"), title: "现场菜单", assetKey: upload.assetKey,
    pricing: { mode: "unknown", fixedPrice: 0, note: "" }, dishes: [],
    batchId, batchIndex: upload.index, streaming: true, streamFailures: 0,
  };
  state.pages.push(page);
  Object.assign(responseMessage, { kind: "menu", pageId: page.id });
  save();
  render(false);
  let finished = false;
  let lastDishPaint = 0;
  try {
    for await (const event of apiStream("/api/analyze-menu-stream", {
      image: upload.image, regions: upload.regions, guideItems,
    })) {
      if (!isOperationCurrent(operation)) return;
      if (event.type === "start") page.streamRegions = event.regions;
      if (event.type === "dish") {
        const wait = Math.max(0, 55 - (performance.now() - lastDishPaint));
        if (wait) await new Promise((resolve) => window.setTimeout(resolve, wait));
        if (!isOperationCurrent(operation)) return;
        page.title = event.title || page.title;
        if (page.pricing.mode === "unknown" && event.pricing?.mode) page.pricing = event.pricing;
        const dish = event.dish;
        if (dish) page.dishes.push({
          ...dish, id: `${page.id}:${dish.id || `${event.index}-${event.ordinal}`}`, decisionHintVersion: 1,
        });
      }
      if (event.type === "region") {
        page.title = event.title || page.title;
        if (page.pricing.mode === "unknown" && event.pricing?.mode) page.pricing = event.pricing;
        page.dishes.push(...(event.dishes || []).map((dish, index) => ({
          ...dish, id: `${page.id}:${dish.id || `${event.index}-${index}`}`, decisionHintVersion: 1,
        })));
      }
      if (event.type === "region-error") {
        page.streamFailures += 1;
        page.streamError = event.message || "部分栏目读取失败";
      }
      if (event.type === "error") throw new Error(event.message || "菜单识别中断");
      if (event.type === "done") {
        page.pricing = event.pricing || page.pricing;
        page.streaming = false;
        finished = true;
      }
      save();
      render(false);
      if (event.type === "dish") lastDishPaint = performance.now();
    }
    if (!finished) throw new Error("菜单识别中断，请重试");
    if (!page.dishes.length) throw new Error("这页菜单没有识别出可点项目，请重试");
  } catch (error) {
    if (!isOperationCurrent(operation) || error?.name === "AbortError") return;
    page.streaming = false;
    if (page.dishes.length) {
      page.streamError = error.message || "识别中断";
    } else {
      state.pages = state.pages.filter((item) => item !== page);
      Object.assign(responseMessage, { kind: "error", text: `第 ${upload.index + 1} 页没有识别成功：${error.message}` });
    }
    save();
    render(false);
  }
}

async function mapWithConcurrency(items, limit, worker) {
  let nextIndex = 0;
  const runners = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (nextIndex < items.length) {
      const index = nextIndex;
      nextIndex += 1;
      await worker(items[index], index);
    }
  });
  await Promise.all(runners);
}

async function analyzeMenus(files) {
  const operation = operationVersion;
  homeRequested = false;
  closeModal();
  const batch = [...files].filter((file) => file?.type?.startsWith("image/"));
  if (!batch.length) return toast("请选择菜单图片");
  const batchId = uid("batch");
  const basePage = state.pages.length;
  const uploads = [];
  state.busy = { type: "menu", batchId, current: 0, total: batch.length, startedAt: Date.now() };
  save();
  render(true);
  for (let index = 0; index < batch.length; index += 1) {
    const image = await prepareImage(batch[index]).catch(() => null);
    if (!isOperationCurrent(operation)) return;
    if (!image) {
      state.messages.push({ id: uid("message"), role: "assistant", kind: "error", text: `第 ${index + 1} 张图片读取失败，请单独重试。` });
      continue;
    }
    const regions = await menuVisionRegions(image).catch(() => []);
    const assetKey = uid("menu-image");
    await persistImage(assetKey, image).catch((error) => console.warn("菜单原图服务端保存失败", error));
    if (!isOperationCurrent(operation)) return;
    imageCache.set(assetKey, image);
    uploads.push({ image, regions, assetKey, index });
    state.messages.push({ id: uid("message"), role: "user", kind: "image", imageKey: assetKey, batchId, text: batch.length > 1 ? `本次上传 ${batch.length} 页 · 第 ${index + 1} 页` : `这是第 ${basePage + 1} 页，帮我看看`, alt: `现场菜单第 ${index + 1} 页` });
  }
  save();
  render(true);
  const responseMessages = new Map();
  uploads.forEach((upload) => {
    const message = { id: uid("message"), role: "assistant", kind: "menu-pending", batchId, batchIndex: upload.index };
    responseMessages.set(upload.index, message);
    state.messages.push(message);
  });
  let completed = 0;
  await mapWithConcurrency(uploads, 2, async (upload) => {
    await streamMenuUpload(upload, batchId, responseMessages.get(upload.index), operation, state.guide?.items || []);
    if (!isOperationCurrent(operation)) return;
    completed += 1;
    state.busy = { type: "menu", batchId, current: completed, total: uploads.length, startedAt: state.busy?.startedAt || Date.now() };
    save();
    render(false);
  });
  if (!isOperationCurrent(operation)) return;
  state.pages = [
    ...state.pages.filter((page) => page.batchId !== batchId),
    ...state.pages.filter((page) => page.batchId === batchId).sort((a, b) => a.batchIndex - b.batchIndex),
  ];
  state.busy = null;
  save();
  render(false);
}

async function startEntryDraft() {
  const files = [...entryDraft.menuFiles];
  const guideSource = entryDraft.guideSource;
  if (!files.length) return toast("请先添加菜单");
  clearEntryDraft();
  if (!guideSource) return analyzeMenus(files);
  return analyzeInitialDining(files, guideSource);
}

async function analyzeInitialDining(files, guideSource) {
  const operation = operationVersion;
  const batch = [...files].filter((file) => file?.type?.startsWith("image/"));
  if (!batch.length) return toast("请选择菜单图片");
  homeRequested = false;
  closeModal();
  const batchId = uid("batch");
  const uploads = [];
  const responseMessages = new Map();
  state.busy = { type: "start", batchId, stage: "reading", current: 0, total: batch.length, startedAt: Date.now() };
  save();
  render(true);

  const guideTask = api("/api/analyze-guide-source", { source: guideSource })
    .then((result) => ({ result }))
    .catch((error) => ({ error }));

  for (let index = 0; index < batch.length; index += 1) {
    const image = await prepareImage(batch[index]).catch(() => null);
    if (!isOperationCurrent(operation)) return;
    if (!image) {
      state.messages.push({ id: uid("message"), role: "assistant", kind: "error", text: `第 ${index + 1} 张图片读取失败，请单独重试。` });
      continue;
    }
    const regions = await menuVisionRegions(image).catch(() => []);
    const assetKey = uid("menu-image");
    await persistImage(assetKey, image).catch((error) => console.warn("菜单原图服务端保存失败", error));
    if (!isOperationCurrent(operation)) return;
    imageCache.set(assetKey, image);
    uploads.push({ image, regions, assetKey, index });
    state.messages.push({ id: uid("message"), role: "user", kind: "image", imageKey: assetKey, batchId, withGuide: true, text: batch.length > 1 ? `本次上传 ${batch.length} 页 · 第 ${index + 1} 页` : "这是第 1 页，帮我看看", alt: `现场菜单第 ${index + 1} 页` });
    state.busy = { type: "start", batchId, stage: "reading", current: index + 1, total: batch.length, startedAt: state.busy.startedAt };
    save();
    render(false);
  }

  uploads.forEach((upload) => {
    const message = { id: uid("message"), role: "assistant", kind: "menu-pending", batchId, batchIndex: upload.index };
    responseMessages.set(upload.index, message);
    state.messages.push(message);
  });
  save();
  render(true);

  state.busy = { ...state.busy, stage: "preparing-guide" };
  save();
  render(false);
  const guideOutcome = await guideTask;
  if (!isOperationCurrent(operation)) return;
  let sourceFailureReason = "";
  if (guideOutcome.result) {
    state.guide = {
      ...guideOutcome.result,
      sourceLabel: guideOutcome.result.sourceType === "xiaohongshu" ? "小红书攻略链接" : "粘贴的攻略文案",
    };
    guideRecoveryAllowed = false;
  } else {
    sourceFailureReason = guideOutcome.error?.message || "暂时无法读取这篇公开笔记。";
    guideRecoveryAllowed = true;
  }
  state.busy = { ...state.busy, stage: "reading" };
  save();
  render(false);

  let completed = 0;
  await mapWithConcurrency(uploads, 2, async (upload) => {
    await streamMenuUpload(upload, batchId, responseMessages.get(upload.index), operation, state.guide?.items || []);
    if (!isOperationCurrent(operation)) return;
    completed += 1;
    state.busy = { type: "start", batchId, stage: "reading", current: completed, total: uploads.length, startedAt: state.busy?.startedAt || Date.now() };
    save();
    render(false);
  });

  if (!isOperationCurrent(operation)) return;

  state.pages = [
    ...state.pages.filter((page) => page.batchId !== batchId),
    ...state.pages.filter((page) => page.batchId === batchId).sort((a, b) => a.batchIndex - b.batchIndex),
  ];

  state.busy = null;
  save();
  render(false);
  if (sourceFailureReason) guideFallbackSheet(sourceFailureReason);
}

async function analyzeGuide(file) {
  const operation = operationVersion;
  if (!canImportGuide() && !guideRecoveryAllowed) return toast("攻略只能在开始点餐时导入");
  homeRequested = false;
  closeModal();
  const image = await prepareImage(file).catch(() => null);
  if (!isOperationCurrent(operation)) return;
  if (!image) return toast("图片读取失败，请换一张重试");
  const imageKey = uid("guide-image");
  await persistImage(imageKey, image).catch((error) => console.warn("攻略原图服务端保存失败", error));
  if (!isOperationCurrent(operation)) return;
  imageCache.set(imageKey, image);
  state.messages.push({ id: uid("message"), role: "user", kind: "image", imageKey, text: "已附上攻略截图", alt: "攻略截图" });
  state.busy = { type: "guide", startedAt: Date.now() };
  save();
  render(true);
  try {
    const result = await api("/api/analyze-guide", { image });
    if (!isOperationCurrent(operation)) return;
    state.guide = { ...result, imageKey, sourceLabel: "上传的攻略截图" };
    guideRecoveryAllowed = false;
    await rematchGuideToPages();
    if (!isOperationCurrent(operation)) return;
    state.messages.push({ id: uid("message"), role: "assistant", kind: "guide" });
  } catch (error) {
    if (!isOperationCurrent(operation) || error?.name === "AbortError") return;
    state.messages.push({ id: uid("message"), role: "assistant", kind: "error", text: `这张攻略暂时没有识别成功：${error.message}` });
  } finally {
    if (!isOperationCurrent(operation)) return;
    state.busy = null;
    save();
    render(true);
  }
}

async function analyzeGuideSource(source) {
  const operation = operationVersion;
  if (!canImportGuide() && !guideRecoveryAllowed) return toast("攻略只能在开始点餐时导入");
  const cleaned = String(source || "").trim();
  if (!cleaned) return toast("请粘贴小红书分享链接或分享文案");
  homeRequested = false;
  closeModal();
  const hasLink = /https?:\/\//.test(cleaned);
  state.messages.push({ id: uid("message"), role: "user", kind: "text", text: hasLink ? "已附上小红书攻略" : "已附上攻略内容" });
  state.busy = { type: "guide", mode: "source", startedAt: Date.now() };
  save();
  render(true);
  let sourceFailed = false;
  let sourceFailureReason = "";
  try {
    const result = await api("/api/analyze-guide-source", { source: cleaned });
    if (!isOperationCurrent(operation)) return;
    state.guide = {
      ...result,
      sourceLabel: result.sourceType === "xiaohongshu" ? "小红书攻略链接" : "粘贴的攻略文案",
    };
    guideRecoveryAllowed = false;
    await rematchGuideToPages();
    if (!isOperationCurrent(operation)) return;
    state.messages.push({ id: uid("message"), role: "assistant", kind: "guide" });
  } catch (error) {
    if (!isOperationCurrent(operation) || error?.name === "AbortError") return;
    sourceFailed = true;
    sourceFailureReason = error.message || "暂时无法读取这篇公开笔记。";
    state.messages.push({ id: uid("message"), role: "assistant", kind: "error", text: "这篇攻略暂时没有读取成功。" });
  } finally {
    if (!isOperationCurrent(operation)) return;
    state.busy = null;
    save();
    render(true);
    if (sourceFailed) guideFallbackSheet(sourceFailureReason);
  }
}

async function rematchGuideToPages() {
  if (!state.guide?.items?.length || !state.pages.length) return;
  const compactDishes = state.pages.flatMap((page) => page.dishes.map((dish) => ({
    id: dish.id,
    original: dish.original,
    nameZh: dish.nameZh,
  })));
  try {
    const result = await api("/api/match-guide", {
      dishes: compactDishes,
      guideItems: state.guide.items,
    });
    const matches = new Map((result.items || []).map((item) => [item.id, item.guideMatchIds || []]));
    state.pages.forEach((page) => page.dishes.forEach((dish) => {
      dish.guideMatchIds = matches.get(dish.id) || [];
    }));
  } catch (error) {
    console.warn("已有菜单与攻略重新匹配失败", error);
  }
}

async function sendChat(message) {
  const operation = operationVersion;
  const referenced = draftDish();
  const text = message.trim() || (referenced ? "介绍一下这道菜" : "");
  if (!text || state.chatBusy || (state.busy && !isMenuBusy())) return;
  state.messages.push({ id: uid("message"), role: "user", kind: "text", text, referencedDishId: referenced?.id || null, referencedDishName: referenced?.nameZh || "" });
  state.draftDishId = null;
  composerDraft = "";
  state.chatBusy = true;
  save();
  render(true);
  try {
    const chatDishes = dishes().map(({ pageAsset, ...dish }) => dish);
    const conversationHistory = state.messages
      .filter((item) => (item.role === "user" && item.kind === "text") || (item.role === "assistant" && item.kind === "chat"))
      .slice(0, -1)
      .slice(-10)
      .map((item) => ({ role: item.role, text: item.text, referencedDishId: item.referencedDishId || null }));
    const result = await api("/api/chat", { message: text, state: { guide: state.guide, dishes: chatDishes, selections: state.selections, history: conversationHistory, referencedDishId: referenced?.id || null } });
    if (!isOperationCurrent(operation)) return;
    for (const action of result.actions || []) {
      if (!dishes().some((dish) => dish.id === action.dishId)) continue;
      if (action.type === "add") state.selections[action.dishId] = state.selections[action.dishId] || 1;
      if (action.type === "remove") delete state.selections[action.dishId];
    }
    state.messages = state.messages.filter((item) => !(item.kind === "error" && item.text?.startsWith("这次没有回答成功")));
    state.messages.push({ id: uid("message"), role: "assistant", kind: "chat", text: result.message, dishIds: result.dishIds || [] });
  } catch (error) {
    if (!isOperationCurrent(operation) || error?.name === "AbortError") return;
    state.messages.push({ id: uid("message"), role: "assistant", kind: "error", text: `这次没有回答成功：${error.message}` });
  } finally {
    if (!isOperationCurrent(operation)) return;
    state.chatBusy = false;
    save();
    render(true);
  }
}

function loadSample() {
  homeRequested = false;
  state.guide = structuredClone(DEMO_GUIDE);
  const page = structuredClone(DEMO_PAGES[1]);
  page.id = "sample-mains";
  state.pages = [page];
  const uploadMessage = { id: uid("message"), role: "user", kind: "image", asset: page.asset, text: "这是第一页，帮我看看", alt: "示例菜单" };
  state.messages = [...initialState.messages, uploadMessage, { id: uid("message"), role: "assistant", kind: "menu", pageId: page.id }];
  save();
  render(false);
  requestAnimationFrame(() => document.querySelector(`[data-message-id="${uploadMessage.id}"]`)?.scrollIntoView({ block: "start" }));
}

document.addEventListener("click", async (event) => {
  if (event.target.id === "modal-root" || event.target.classList?.contains("modal-backdrop")) {
    closeModal();
    return render(false);
  }
  const prompt = event.target.closest("[data-prompt]");
  if (prompt) return sendChat(prompt.dataset.prompt);
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const { action, id } = target.dataset;
  if (action === "quote-dish") {
    if (event.target.closest(".dish-tags") || state.chatBusy || (state.busy && !isMenuBusy()) || !dishes().some((dish) => dish.id === id)) return;
    state.draftDishId = id;
    save();
    render(false);
    document.querySelector("#composer-input")?.focus({ preventScroll: true });
    return;
  }
  if (action === "clear-dish-reference") { state.draftDishId = null; save(); render(false); return; }
  if (action === "attachments") attachmentSheet();
  if (action === "home") return reset();
  if (action === "resume") { homeRequested = false; render(true); }
  if (action === "restart") restartSheet();
  if (action === "guide-import") guideImportSheet();
  if (action === "entry-draft") entryDraftSheet();
  if (action === "close-entry-draft") { closeModal(); render(false); }
  if (action === "remove-draft-menu") {
    const index = Number(id);
    if (Number.isInteger(index) && entryDraft.menuFiles[index]) {
      URL.revokeObjectURL(entryDraft.menuPreviews[index].url);
      entryDraft.menuFiles.splice(index, 1);
      entryDraft.menuPreviews.splice(index, 1);
    }
    entryDraftSheet();
  }
  if (action === "start-entry-draft") {
    const guideInput = document.querySelector("#draft-guide-source");
    if (guideInput) entryDraft.guideSource = guideInput.value.trim();
    startEntryDraft();
  }
  if (action === "close-modal") closeModal();
  if (action === "order") orderSheet();
  if (action === "calibrate") calibratePositions();
  if (action === "select") { if (state.selections[id]) delete state.selections[id]; else state.selections[id] = 1; save(); render(false); }
  if (action === "guide-evidence") {
    guideEvidenceSheet(id);
  }
  if (action === "load-sample") loadSample();
  if (action === "reset") reset();
});

document.addEventListener("input", (event) => {
  if (event.target.id === "draft-guide-source") entryDraft.guideSource = event.target.value;
  if (event.target.id === "composer-input") composerDraft = event.target.value;
});

document.addEventListener("paste", (event) => {
  const images = [...(event.clipboardData?.items || [])]
    .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
    .map((item) => item.getAsFile())
    .filter(Boolean);
  if (!images.length) return;
  event.preventDefault();
  if (isPristineDiningSession()) stageEntryMenus(images);
  else analyzeMenus(images);
});

document.addEventListener("submit", (event) => {
  if (event.target.id === "guide-import-form") {
    event.preventDefault();
    const source = String(new FormData(event.target).get("source") || "");
    if (!guideRecoveryAllowed && isPristineDiningSession()) return stageEntryGuide(source);
    return analyzeGuideSource(source);
  }
  if (event.target.id !== "composer-form") return;
  event.preventDefault();
  sendChat(String(new FormData(event.target).get("message") || ""));
});

document.addEventListener("change", (event) => {
  const files = [...(event.target.files || [])];
  if (!files.length) return;
  event.target.value = "";
  if (event.target.id === "guide-fallback-input") {
    if (!canImportGuide() && !guideRecoveryAllowed) return toast("攻略只能在开始点餐时导入");
    analyzeGuide(files[0]);
  }
  if (["home-menu-input", "home-camera-input", "draft-menu-input"].includes(event.target.id)) {
    if (isPristineDiningSession()) stageEntryMenus(files);
    else analyzeMenus(files);
  }
  if (event.target.id === "menu-input") analyzeMenus(files);
});

document.addEventListener("keydown", (event) => {
  const sheet = document.querySelector(".sheet");
  if (!sheet) return;
  if (event.key === "Escape") { closeModal(); return render(false); }
  if (event.key !== "Tab") return;
  const focusable = [...sheet.querySelectorAll("button:not([disabled]), input:not([disabled]), [href], [tabindex]:not([tabindex='-1'])")];
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable.at(-1);
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
});

render(true);

async function hydrateImages() {
  const keys = [state.guide?.imageKey, ...state.pages.map((page) => page.assetKey), ...state.messages.map((message) => message.imageKey)].filter(Boolean);
  await Promise.all([...new Set(keys)].map(async (key) => { const image = await restoredImage(key); if (image) imageCache.set(key, image); }));
  render(false);
}

async function initializeApp() {
  loadEurCnyRate();
  sessionInitialization = initializeDiningSession();
  await sessionInitialization.catch((error) => console.warn("服务端点餐会话不可用，将保留本地状态", error));
  await hydrateImages();
  try {
    const response = await fetch("/api/status");
    const data = await response.json();
    state.liveModel = Boolean(data.liveModel);
    state.ocrEnabled = Boolean(data.ocrEnabled);
  } catch {
    state.liveModel = false;
    state.ocrEnabled = false;
  }
  render(false);
}

initializeApp();
