// Проверки переходов интерфейса: node --test tests/test_feedback_ui.cjs
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const { join } = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const source = readFileSync(join(__dirname, "../web/script.js"), "utf8");

function element() {
  const classes = new Set();
  return {
    textContent: "", disabled: false, style: {},
    classList: {
      add: (...names) => names.forEach((name) => classes.add(name)),
      remove: (...names) => names.forEach((name) => classes.delete(name)),
      contains: (name) => classes.has(name),
      toggle: (name, enabled) => enabled ? classes.add(name) : classes.delete(name),
    },
  };
}

function waste(changes = {}) {
  return {
    state: "waste", controllerState: "SORTING", eventId: "first",
    type: "paper", lastAnswer: null, ...changes,
  };
}

function setup() {
  const elements = new Map();
  const get = (id) => {
    if (!elements.has(id)) elements.set(id, element());
    return elements.get(id);
  };
  const buttons = [element(), element()];
  const page = element();
  const responses = [];
  const requests = [];
  const alerts = [];
  const timers = new Map();
  let timerId = 0;
  let now = 0;
  const context = vm.createContext({
    document: {
      getElementById: get,
      querySelector: (selector) => selector.startsWith(".page-") ? page : get(selector),
      querySelectorAll: (selector) => selector === ".btn[data-answer]" ? buttons :
        selector === ".waste-page" ? [page] : [],
      addEventListener() {},
    },
    console: { error() {} },
    alert: (message) => alerts.push(message),
    setTimeout: (fn, delay) => {
      timers.set(++timerId, { fn, delay, due: now + delay });
      return timerId;
    },
    clearTimeout: (id) => timers.delete(id),
    fetch: async (url, options) => {
      requests.push({ url, options });
      assert.ok(responses.length, `Unexpected request: ${url}`);
      return responses.shift();
    },
  });
  vm.runInContext(source, context);
  return {
    get, buttons, requests, alerts, responses,
    advance(ms) {
      const target = now + ms;
      while (true) {
        const next = [...timers.entries()]
          .filter(([, timer]) => timer.due <= target)
          .sort((a, b) => a[1].due - b[1].due)[0];
        if (!next) break;
        now = next[1].due;
        timers.delete(next[0]);
        next[1].fn();
      }
      now = target;
    },
    async poll(data) {
      responses.push({ ok: true, json: async () => data });
      await vm.runInContext("fetchState()", context);
    },
    answer(answer = "yes") {
      return vm.runInContext(`handleAnswer(${JSON.stringify(answer)})`, context);
    },
    async finishOverlay(data) {
      const entry = [...timers.entries()].find(([, timer]) => timer.delay === 800);
      assert.ok(entry, "Feedback animation must last 800 ms");
      timers.delete(entry[0]);
      responses.push({ ok: true, json: async () => data });
      entry[1].fn();
      await new Promise(setImmediate);
    },
  };
}

for (const answer of ["yes", "no"]) {
  test(`${answer}: after feedback show finishing until the server is ready`, async () => {
    const ui = setup();
    await ui.poll(waste());
    assert.ok(ui.get("waste-screen").classList.contains("active"));
    ui.responses.push({ ok: true });
    await ui.answer(answer);
    assert.ok(ui.get("feedback-overlay").classList.contains("active"));
    assert.equal(ui.get("feedback-icon").textContent, answer === "yes" ? "✅" : "❌");
    assert.ok(ui.buttons.every((button) => button.disabled));
    await ui.finishOverlay(waste({ lastAnswer: answer }));
    assert.ok(!ui.get("feedback-overlay").classList.contains("active"));
    assert.ok(!ui.get("waste-screen").classList.contains("active"));
    assert.ok(ui.get("idle-screen").classList.contains("active"));
    assert.equal(ui.get("system-status").textContent, "Завершаю сортировку…");
    await ui.poll(waste({ lastAnswer: answer, controllerState: "WAITING_FOR_REMOVAL" }));
    assert.equal(ui.get("system-status").textContent, "Завершаю сортировку…");
    await ui.poll({ state: "idle", controllerState: "IDLE", eventId: null, lastAnswer: null });
    assert.equal(ui.get("system-status").textContent, "Ожидание мусора...");
    await ui.poll(waste({ eventId: "second" }));
    assert.ok(ui.get("waste-screen").classList.contains("active"));
    assert.ok(ui.buttons.every((button) => !button.disabled));
    const posts = ui.requests.filter((request) => request.options?.method === "POST");
    assert.equal(posts.length, 1);
    assert.deepEqual(JSON.parse(posts[0].options.body), { eventId: "first", answer });
  });
}

test("reloading after a recorded answer keeps the question hidden", async () => {
  const ui = setup();
  await ui.poll(waste({ lastAnswer: "yes" }));
  assert.ok(!ui.get("waste-screen").classList.contains("active"));
  assert.equal(ui.get("system-status").textContent, "Завершаю сортировку…");
});

test("a stale poll cannot reopen the answered question", async () => {
  const ui = setup();
  await ui.poll(waste());
  ui.responses.push({ ok: true });
  await ui.answer();
  await ui.poll(waste({ controllerState: "WAITING_FOR_REMOVAL" }));
  assert.ok(!ui.get("waste-screen").classList.contains("active"));
  assert.ok(ui.buttons.every((button) => button.disabled));
});

test("failed feedback keeps the question available for retry", async () => {
  const ui = setup();
  await ui.poll(waste());
  ui.responses.push({ ok: false });
  await ui.answer();
  assert.ok(ui.get("waste-screen").classList.contains("active"));
  assert.ok(!ui.get("feedback-overlay").classList.contains("active"));
  assert.ok(ui.buttons.every((button) => !button.disabled));
  assert.equal(ui.alerts.length, 1);
});

test("repeated taps send only one answer", async () => {
  const ui = setup();
  await ui.poll(waste());
  let resolve;
  ui.responses.push(new Promise((done) => { resolve = done; }));
  const pending = ui.answer();
  await ui.answer();
  assert.ok(ui.buttons.every((button) => button.disabled));
  resolve({ ok: true });
  await pending;
  await ui.answer();
  assert.equal(ui.requests.filter((request) => request.options?.method === "POST").length, 1);
});

test("a late answer for the previous event does not hide the new question", async () => {
  const ui = setup();
  await ui.poll(waste());
  let resolve;
  ui.responses.push(new Promise((done) => { resolve = done; }));
  const pending = ui.answer();
  await ui.poll(waste({ eventId: "second" }));
  resolve({ ok: true });
  await pending;
  assert.ok(ui.get("waste-screen").classList.contains("active"));
  assert.ok(!ui.get("feedback-overlay").classList.contains("active"));
  assert.ok(ui.buttons.every((button) => !button.disabled));
});

for (const [answer, emotion] of [["yes", "happy"], ["no", "sad"]]) {
  test(`${emotion} lasts four seconds without restarting on polls`, async () => {
    const ui = setup();
    await ui.poll(waste({ lastAnswer: answer }));
    const face = ui.get("face-container").classList;
    assert.ok(face.contains(`emotion-${emotion}`));
    ui.advance(2000);
    await ui.poll(waste({ lastAnswer: answer, controllerState: "WAITING_FOR_REMOVAL" }));
    ui.advance(1999);
    assert.ok(face.contains(`emotion-${emotion}`));
    ui.advance(1);
    assert.ok(face.contains("emotion-idle"));
    assert.ok(!face.contains(`emotion-${emotion}`));
    await ui.poll(waste({ lastAnswer: answer, totalCount: 1 }));
    assert.ok(face.contains("emotion-idle"));
    assert.equal(ui.get("system-status").textContent, "Завершаю сортировку…");
  });
}

test("server becoming ready does not cut the feedback emotion short", async () => {
  const ui = setup();
  await ui.poll(waste({ lastAnswer: "yes" }));
  ui.advance(1000);
  await ui.poll({ state: "idle", controllerState: "IDLE", eventId: null, lastAnswer: null });
  assert.ok(ui.get("face-container").classList.contains("emotion-happy"));
  ui.advance(3000);
  assert.ok(ui.get("face-container").classList.contains("emotion-idle"));
});

test("the previous emotion timer cannot interrupt a new event", async () => {
  const ui = setup();
  await ui.poll(waste({ lastAnswer: "yes" }));
  ui.advance(2000);
  await ui.poll(waste({ eventId: "second" }));
  ui.advance(1000);
  assert.ok(ui.get("face-container").classList.contains("emotion-surprised"));
  await ui.poll(waste({ eventId: "second", lastAnswer: "no" }));
  ui.advance(1000);
  assert.ok(ui.get("face-container").classList.contains("emotion-sad"));
  ui.advance(3000);
  assert.ok(ui.get("face-container").classList.contains("emotion-idle"));
});
