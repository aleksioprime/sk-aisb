// DOM-элементы
const idleScreen = document.getElementById("idle-screen");
const wasteScreen = document.getElementById("waste-screen");
const wastePages = document.querySelectorAll(".waste-page");
const feedbackOverlay = document.getElementById("feedback-overlay");
const feedbackIcon = document.getElementById("feedback-icon");
const statCount = document.getElementById("stat-count");
const statWeight = document.getElementById("stat-weight");
const faceContainer = document.getElementById("face-container");
const systemStatus = document.getElementById("system-status");
const diagnostics = document.getElementById("diagnostics");
const exitOverlay = document.getElementById("exit-overlay");
const exitMessage = document.getElementById("exit-message");
const exitCancel = document.getElementById("exit-cancel");
const exitConfirm = document.getElementById("exit-confirm");
const devPanel = document.getElementById("dev-panel");
const devDebugPanel = document.getElementById("dev-debug-panel");
const devDebugData = document.getElementById("dev-debug-data");
// Режим разработчика переживает переход в настройки и обратно, но сам
// выключается после 15 минут без касаний, чтобы не остаться перед посетителями.
const DEV_MODE_KEY = "umka-dev-mode";
const DEV_DEBUG_KEY = "umka-dev-debug";
const DEV_MODE_IDLE_MS = 15 * 60 * 1000;
let devModeTimer = null;
const originalUrl = "https://умка.москва/#top";
const encodedUrl = encodeURI(originalUrl);
// затем передать encodedUrl в text

// Маппинг ключей API на CSS-классы страниц
const typeToClass = {
  paper: "paper",
  plastic_aluminum: "plastic",
  organic: "organic",
  non_recyclable: "non-recyclable",
};

let currentState = null;
let acceptedFeedback = null;
let answerPending = false;
let feedbackTimer = null;
const FEEDBACK_EMOTION_MS = 4000;
let feedbackEmotionTimer = null;
let feedbackEmotionEventId = null;
let pollTimer = null;
let idleAnimationTimer = null;
let activeAnimationTimeout = null;
let isRandomAnimationActive = false;
let isTouching = false;
let avoidTimeout = null;
let exitTapTimes = [];
// Без подтверждения результат показывается resultSeconds, затем экран гаснет.
let resultEventId = null;
let resultTimer = null;
let dismissedEventId = null;

// Пул случайных idle-анимаций
const idleAnimations = [
  { class: "animation-wink-left", duration: 400 },
  { class: "animation-wink-right", duration: 400 },
  { class: "animation-double-blink", duration: 800 },
  { class: "animation-look-left", duration: 1100 },
  { class: "animation-look-right", duration: 1100 },
  { class: "animation-look-up", duration: 1100 },
  { class: "animation-look-down", duration: 1100 },
  { class: "animation-squint", duration: 1000 },
  { class: "animation-smile", duration: 1100 },
  { class: "animation-thoughtful", duration: 1200 },
  { class: "animation-sleepy", duration: 2500 },
  { class: "animation-roll", duration: 800 },
  { class: "animation-flash", duration: 800 },
  { class: "animation-swing", duration: 1300 },
  { class: "animation-bounce", duration: 800 },
  { class: "animation-tilt", duration: 700 },
  { class: "animation-shake", duration: 800 },
  { class: "animation-pulse", duration: 1000 },
  { class: "animation-confused", duration: 1000 },
  { class: "animation-curious", duration: 1600 },
  { class: "animation-excited", duration: 1000 },
  { class: "animation-scan", duration: 1900 },
  { class: "animation-blush", duration: 1300 },
  { class: "animation-focus", duration: 900 },
];

document.addEventListener("DOMContentLoaded", () => {
  initQRCode();
  fetchState();
  pollTimer = setInterval(fetchState, 1000);

  document.querySelectorAll(".btn[data-answer]").forEach((btn) => {
    btn.addEventListener("click", () => {
      handleAnswer(btn.dataset.answer);
    });
  });

  setEmotion("idle");
  scheduleIdleAnimation();

  faceContainer.addEventListener("click", handleFaceTouch);
  faceContainer.addEventListener("click", registerDevModeTap);
  faceContainer.addEventListener(
    "touchstart",
    (e) => {
      e.preventDefault();
      registerDevModeTap();
      handleFaceTouch(e);
    },
    { passive: false },
  );

  // kiosk_token нужен кнопке «Закрыть экран», поэтому служебные ссылки его сохраняют.
  for (const link of document.querySelectorAll("[data-keep-query]")) {
    link.href = link.getAttribute("href") + window.location.search;
  }

  exitCancel.addEventListener("click", hideExitDialog);
  exitConfirm.addEventListener("click", requestKioskExit);

  document.getElementById("dev-exit").addEventListener("click", () => setDevMode(false));
  document.getElementById("dev-close-screen").addEventListener("click", showExitDialog);
  document.getElementById("dev-debug").addEventListener("click", () => {
    setDevDebug(devDebugPanel.hidden);
  });
  document.addEventListener("pointerdown", () => {
    if (devPanel && !devPanel.hidden) setDevMode(true);
  });
  setDevMode(readDevModeExpiry() > Date.now());
  setDevDebug(storageGet(DEV_DEBUG_KEY) === "1");
});

// sessionStorage может быть недоступен (приватный режим, тесты): режим тогда
// просто не сохраняется между страницами.
function storageGet(key) {
  try { return sessionStorage.getItem(key); } catch (error) { return null; }
}

function storageSet(key, value) {
  try {
    if (value === null) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, value);
  } catch (error) { /* не обязательно */ }
}

function readDevModeExpiry() {
  return Number(storageGet(DEV_MODE_KEY) || 0);
}

// Включить режим разработчика (или продлить его) либо выключить.
function setDevMode(enabled) {
  clearTimeout(devModeTimer);
  devPanel.hidden = !enabled;
  document.body?.classList.toggle("dev-mode", enabled);
  if (enabled) {
    storageSet(DEV_MODE_KEY, String(Date.now() + DEV_MODE_IDLE_MS));
    devModeTimer = setTimeout(() => setDevMode(false), DEV_MODE_IDLE_MS);
  } else {
    storageSet(DEV_MODE_KEY, null);
    setDevDebug(false);
    hideExitDialog();
  }
}

function setDevDebug(visible) {
  const show = visible && !devPanel.hidden;
  devDebugPanel.hidden = !show;
  storageSet(DEV_DEBUG_KEY, show ? "1" : null);
  if (show && currentState) renderDevDebug(currentState);
}

// Отладочные данные поверх экрана: то, что обычно видно только по SSH.
function renderDevDebug(data) {
  if (!devDebugData || devDebugPanel.hidden) return;
  const detection = data.detection
    ? `${data.detection.className} ${Math.round(data.detection.confidence * 100)}% · ${data.detection.area} пикс.`
    : "ничего";
  const platform = data.platform || {};
  devDebugData.textContent = [
    `автомат: ${data.controllerState}`,
    `видит: ${detection}`,
    `пустая площадка: снимков ${platform.references ?? 0}, разница ${platform.difference ?? "—"}` +
      (platform.rejected ? " → отсеяно" : ""),
    `моторы: ${data.hardware?.driver || "—"} · ${data.hardware?.message || ""}`,
    `экран: ${data.display?.confirm === false ? "без подтверждения" : "с подтверждением"}`,
    `последнее: ${data.lastAction || "—"}`,
    `всего: ${data.totalCount ?? 0} шт · ${data.totalWeight ?? 0} кг`,
    data.error ? `ошибка: ${data.error}` : "",
  ].filter(Boolean).join("\n");
}

// Пять касаний логотипа за четыре секунды включают режим разработчика.
function registerDevModeTap() {
  const now = Date.now();
  exitTapTimes = exitTapTimes.filter((timestamp) => now - timestamp <= 4000);
  exitTapTimes.push(now);
  if (exitTapTimes.length >= 5) {
    exitTapTimes = [];
    setDevMode(true);
  }
}

function showExitDialog() {
  exitMessage.textContent = "Программа сортировки продолжит работать в фоне.";
  exitConfirm.disabled = false;
  exitOverlay.classList.add("active");
}

function hideExitDialog() {
  exitOverlay.classList.remove("active");
}

async function requestKioskExit() {
  const token = new URLSearchParams(window.location.search).get("kiosk_token");
  if (!token) {
    exitMessage.textContent =
      "Экран открыт не через ярлык UMKA. Закройте Chromium через Alt+F4 или по SSH.";
    return;
  }
  exitConfirm.disabled = true;
  exitMessage.textContent = "Закрываю экран...";
  try {
    const response = await fetch(
      `http://127.0.0.1:3001/exit?token=${encodeURIComponent(token)}`,
      {
        method: "POST",
      },
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
  } catch (error) {
    console.error("Не удалось закрыть kiosk:", error);
    exitMessage.textContent =
      "Не удалось закрыть экран. Используйте Alt+F4 или SSH.";
    exitConfirm.disabled = false;
  }
}

function initQRCode() {
  if (typeof QRCode === "undefined") {
    console.warn("Библиотека QRCode не загружена. Скачайте qrcode.min.js.");
    return;
  }
  new QRCode(document.getElementById("qrcode"), {
    text: encodedUrl,
    width: 150,
    height: 150,
    colorDark: "#0a1f1a",
    colorLight: "#ffffff",
    correctLevel: QRCode.CorrectLevel.H,
  });
}

// Обработка касания мордочки
function handleFaceTouch(e) {
  if (isTouching) return;
  if (feedbackEmotionTimer !== null) return;
  if (currentState && currentState.state === "waste") return;

  isTouching = true;

  // Сначала устанавливаем эмоцию (сбросит инлайн-стили лапок, но это произойдёт до позиционирования)
  setEmotion("surprised");

  const rect = faceContainer.getBoundingClientRect();
  let clientX, clientY;
  if (e.touches) {
    clientX = e.touches[0].clientX;
    clientY = e.touches[0].clientY;
  } else {
    clientX = e.clientX;
    clientY = e.clientY;
  }

  const x = clientX - rect.left;
  const y = clientY - rect.top;
  const thirdX = rect.width / 3;
  const thirdY = rect.height / 3;

  let escapeClass = "";
  if (x < thirdX) {
    escapeClass = "eyes-escape-left";
  } else if (x > 2 * thirdX) {
    escapeClass = "eyes-escape-right";
  } else if (y < thirdY) {
    escapeClass = "eyes-escape-up";
  } else if (y > 2 * thirdY) {
    escapeClass = "eyes-escape-down";
  } else {
    const dirs = [
      "eyes-escape-left",
      "eyes-escape-right",
      "eyes-escape-up",
      "eyes-escape-down",
    ];
    escapeClass = dirs[Math.floor(Math.random() * dirs.length)];
  }

  faceContainer.classList.add(escapeClass);

  // Перемещаем лапки к точке касания
  const pawLeft = document.querySelector(".paw-left");
  const pawRight = document.querySelector(".paw-right");
  if (pawLeft && pawRight) {
    const pawOffsetX = 20;
    const pawOffsetY = -20;

    pawLeft.style.left = x - pawOffsetX + "px";
    pawLeft.style.right = "auto";
    pawLeft.style.bottom = rect.height - y + pawOffsetY + "px";
    pawLeft.style.top = "auto";

    pawRight.style.left = x + pawOffsetX + "px";
    pawRight.style.right = "auto";
    pawRight.style.bottom = rect.height - y + pawOffsetY + "px";
    pawRight.style.top = "auto";

    faceContainer.classList.add("paw-grab");

    pawLeft.style.opacity = "1";
    pawRight.style.opacity = "1";
    pawLeft.style.transform = "scale(1)";
    pawRight.style.transform = "scale(1)";
  }

  clearTimeout(avoidTimeout);
  avoidTimeout = setTimeout(() => {
    faceContainer.classList.remove(escapeClass, "paw-grab");
    if (currentState && currentState.state === "idle") {
      setEmotion("idle");
    }
    isTouching = false;
  }, 500);
}

// Удаление всех классов анимаций
function clearAnimationClasses() {
  const classes = [
    "animation-wink-left",
    "animation-wink-right",
    "animation-double-blink",
    "animation-look-left",
    "animation-look-right",
    "animation-look-up",
    "animation-look-down",
    "animation-squint",
    "animation-smile",
    "animation-thoughtful",
    "animation-sleepy",
    "animation-roll",
    "animation-flash",
    "animation-swing",
    "animation-bounce",
    "animation-tilt",
    "animation-shake",
    "animation-pulse",
    "animation-confused",
    "animation-curious",
    "animation-excited",
    "animation-scan",
    "animation-blush",
    "animation-focus",
  ];
  faceContainer.classList.remove(...classes);
}

// Установка базовой эмоции
function setEmotion(emotion) {
  if (!faceContainer) return;
  faceContainer.classList.remove(
    "emotion-idle",
    "emotion-surprised",
    "emotion-happy",
    "emotion-sad",
  );
  clearAnimationClasses();
  if (emotion) {
    faceContainer.classList.add(`emotion-${emotion}`);
  }

  // Сброс инлайн-стилей лапок (но при касании сброс происходит до установки новых позиций)
  const pawLeft = document.querySelector(".paw-left");
  const pawRight = document.querySelector(".paw-right");
  if (pawLeft && pawRight) {
    pawLeft.style.opacity = "";
    pawRight.style.opacity = "";
    pawLeft.style.transform = "";
    pawRight.style.transform = "";
    pawLeft.style.left = "";
    pawLeft.style.right = "";
    pawLeft.style.bottom = "";
    pawLeft.style.top = "";
    pawRight.style.left = "";
    pawRight.style.right = "";
    pawRight.style.bottom = "";
    pawRight.style.top = "";
  }

  isRandomAnimationActive = false;
  if (activeAnimationTimeout) {
    clearTimeout(activeAnimationTimeout);
    activeAnimationTimeout = null;
  }
}

// Эмоция на ответ пользователя с возвратом к обычным глазам через четыре секунды.
function showFeedbackEmotion(answer, eventId) {
  // Каждый ответ проигрывается один раз; опрос API не продлевает анимацию.
  if (feedbackEmotionEventId === eventId) return;
  feedbackEmotionEventId = eventId;
  clearTimeout(feedbackEmotionTimer);
  setEmotion(answer === "yes" ? "happy" : "sad");
  feedbackEmotionTimer = setTimeout(() => {
    feedbackEmotionTimer = null;
    setEmotion("idle");
  }, FEEDBACK_EMOTION_MS);
}

// Планирование случайной idle-анимации
function scheduleIdleAnimation() {
  if (idleAnimationTimer) clearTimeout(idleAnimationTimer);
  const delay = Math.random() * 4000 + 4000;
  idleAnimationTimer = setTimeout(() => {
    if (
      currentState &&
      currentState.state === "idle" &&
      feedbackEmotionTimer === null &&
      !isRandomAnimationActive &&
      !isTouching
    ) {
      playRandomIdleAnimation();
    }
    scheduleIdleAnimation();
  }, delay);
}

// Воспроизведение случайной анимации
function playRandomIdleAnimation() {
  if (!faceContainer || isRandomAnimationActive) return;
  const anim =
    idleAnimations[Math.floor(Math.random() * idleAnimations.length)];
  isRandomAnimationActive = true;
  faceContainer.classList.add(anim.class);
  activeAnimationTimeout = setTimeout(() => {
    faceContainer.classList.remove(anim.class);
    isRandomAnimationActive = false;
    activeAnimationTimeout = null;
  }, anim.duration);
}

// Получение состояния с сервера
async function fetchState() {
  try {
    const res = await fetch("/api/state");
    if (!res.ok) throw new Error("Ошибка API");
    const data = await res.json();
    if (JSON.stringify(data) !== JSON.stringify(currentState)) {
      currentState = data;
      updateUI(data);
    }
  } catch (err) {
    console.error("Ошибка получения состояния:", err);
  }
}

// Обновление интерфейса
function updateUI(data) {
  // Локальное подтверждение защищает от запоздавшего опроса с lastAnswer=null.
  const answer = data.lastAnswer ||
    (acceptedFeedback && acceptedFeedback.eventId === data.eventId
      ? acceptedFeedback.answer : null);
  // Подтверждение выключено в настройках: кнопок нет, результат гаснет сам.
  const autoMode = data.display?.confirm === false;
  wasteScreen.classList.toggle("no-confirm", autoMode);
  const autoDone = autoMode && data.state === "waste" && dismissedEventId === data.eventId;
  const finishing = data.state === "waste" && (Boolean(answer) || autoDone);
  statCount.textContent = data.totalCount ?? 0;
  statWeight.textContent = data.totalWeight ?? 0;
  const cameraText = data.camera?.ok
    ? "камера готова"
    : `камера: ${data.camera?.message || "ошибка"}`;
  const modelText = data.model?.ok
    ? "модель готова"
    : `модель: ${data.model?.message || "ошибка"}`;
  diagnostics.textContent = `${cameraText} · ${modelText} · режим: ${data.hardware?.driver || "—"}`;
  renderDevDebug(data);
  diagnostics.classList.toggle(
    "has-error",
    !data.camera?.ok || !data.model?.ok || Boolean(data.error),
  );
  const statuses = {
    IDLE: "Ожидание мусора...",
    CANDIDATE: "Проверяю предмет...",
    SORTING: "Сортирую предмет...",
    WAITING_FOR_REMOVAL: "Уберите предмет с площадки",
  };
  systemStatus.textContent =
    finishing ? "Завершаю сортировку…" :
      statuses[data.controllerState] || "Система запущена";
  document.querySelectorAll(".btn[data-answer]").forEach((btn) => {
    btn.disabled = answerPending || Boolean(answer);
  });

  if (finishing) {
    // Меняем только экран: сервер продолжает ждать завершения механики
    // и подтверждённого освобождения площадки перед следующим сбросом.
    showIdle(data);
    showFeedbackEmotion(answer || "yes", data.eventId);
    if (idleAnimationTimer) clearTimeout(idleAnimationTimer);
  } else if (data.state === "idle") {
    showIdle(data);
    if (feedbackEmotionTimer === null) {
      setEmotion("idle");
    }
    scheduleIdleAnimation();
  } else if (data.state === "waste") {
    // Новый предмет прерывает старую эмоцию; её таймер не должен менять новый экран.
    clearTimeout(feedbackEmotionTimer);
    feedbackEmotionTimer = null;
    showWaste(data);
    setEmotion("surprised");
    if (autoMode) startResultTimer(data);
    if (idleAnimationTimer) clearTimeout(idleAnimationTimer);
  }
}

// Запустить полосу и таймер показа результата один раз для каждого события.
function startResultTimer(data) {
  if (resultEventId === data.eventId) return;
  resultEventId = data.eventId;
  const seconds = data.display?.resultSeconds || 5;
  const bar = document.querySelector(".waste-page.active .result-timer-bar");
  if (bar) {
    bar.classList.remove("running");
    bar.style.setProperty("--result-seconds", `${seconds}s`);
    void bar.offsetWidth; // Перезапуск CSS-анимации для нового события.
    bar.classList.add("running");
  }
  clearTimeout(resultTimer);
  resultTimer = setTimeout(() => {
    dismissedEventId = data.eventId;
    if (currentState) updateUI(currentState);
  }, seconds * 1000);
}

function showIdle(data) {
  wasteScreen.classList.remove("active");
  idleScreen.classList.add("active");
}

function showWaste(data) {
  idleScreen.classList.remove("active");
  wasteScreen.classList.add("active");
  wastePages.forEach((page) => page.classList.remove("active"));
  const pageClass = typeToClass[data.type] || "paper";
  const targetPage = document.querySelector(`.page-${pageClass}`);
  if (targetPage) targetPage.classList.add("active");
  else document.querySelector(".page-paper").classList.add("active");
}

async function handleAnswer(answer) {
  const eventId = currentState?.eventId;
  if (!eventId || answerPending || currentState.lastAnswer ||
      acceptedFeedback?.eventId === eventId) return;
  answerPending = true;
  document.querySelectorAll(".btn[data-answer]").forEach((btn) => {
    btn.disabled = true;
  });
  try {
    const res = await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer, eventId }),
    });
    if (!res.ok) throw new Error("Ошибка отправки ответа");
    acceptedFeedback = { eventId, answer };
    // Пока шёл POST, сервер мог уже перейти к следующему предмету.
    if (currentState?.eventId !== eventId) return;
    feedbackIcon.textContent = answer === "yes" ? "✅" : "❌";
    feedbackOverlay.classList.add("active");
    updateUI(currentState);
    clearTimeout(feedbackTimer);
    feedbackTimer = setTimeout(() => {
      feedbackOverlay.classList.remove("active");
      fetchState();
    }, 800);
  } catch (err) {
    console.error("Ошибка:", err);
    alert("Не удалось отправить ответ");
  } finally {
    answerPending = false;
    if (currentState) updateUI(currentState);
  }
}
