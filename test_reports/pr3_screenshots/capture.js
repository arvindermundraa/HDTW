// PR 3 screenshots.
//
// Two changed surfaces to capture:
// 1. Future Me chat after asking a scope-redirect question — exercises
//    the new redirects (e.g. "Should I try keto?" → specialized_diets).
// 2. Week 2 cafeteria scenario label — shows the new "Calories: N" line
//    added per the nutrition team's 2026-11-06 item 3.
//
// Each at 390 px (phone) and 1280 px (desktop). Run from the repo root:
//     node test_reports/pr3_screenshots/capture.js

const WebSocket = require("../../frontend/node_modules/ws");
const chromeLauncher = require("../../frontend/node_modules/chrome-launcher");
const fs = require("node:fs");
const path = require("node:path");

const APP = "http://localhost:3001";
const EMAIL = "maya.demo@example.com";
const PASSWORD = "demo-pass-123";
const OUT = path.join(__dirname);

async function cdp(ws, method, params) {
  const id = cdp._id = (cdp._id || 0) + 1;
  return new Promise((resolve, reject) => {
    const onMessage = (data) => {
      const msg = JSON.parse(data.toString());
      if (msg.id === id) {
        ws.off("message", onMessage);
        msg.error ? reject(new Error(`${method}: ${msg.error.message}`)) : resolve(msg.result);
      }
    };
    ws.on("message", onMessage);
    ws.send(JSON.stringify({ id, method, params }));
  });
}

async function wait(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function waitFor(ws, expr, timeoutMs = 10000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    const r = await cdp(ws, "Runtime.evaluate", { expression: expr, returnByValue: true });
    if (r.result && r.result.value) return true;
    await wait(200);
  }
  throw new Error(`timed out waiting for ${expr}`);
}

async function connect(wsUrl) {
  const ws = new WebSocket(wsUrl, { perMessageDeflate: false });
  await new Promise((resolve, reject) => {
    ws.once("open", resolve);
    ws.once("error", reject);
  });
  return ws;
}

async function login(ws) {
  // Fetch a token server-side, then plant it into window.localStorage
  // (what @react-native-async-storage/async-storage uses on web).
  const resp = await fetch("http://localhost:8001/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: EMAIL, password: PASSWORD }),
  });
  if (!resp.ok) throw new Error(`login API failed: ${resp.status}`);
  const token = (await resp.json()).token;
  // Visit the app on a cold page so localStorage is same-origin.
  await cdp(ws, "Page.navigate", { url: `${APP}/auth` });
  await waitFor(ws, "!!document.querySelector('[data-testid=auth-email]')", 45000);
  // Set the token the way Storage.secureSet does: JSON-encoded string.
  await cdp(ws, "Runtime.evaluate", {
    expression: `localStorage.setItem('llhs.token', ${JSON.stringify(JSON.stringify(token))}); true;`,
  });
  await cdp(ws, "Page.navigate", { url: `${APP}/(tabs)` });
  await waitFor(ws, "!location.pathname.startsWith('/auth')", 15000);
  await wait(1500);
}

async function viewport(ws, w, h) {
  await cdp(ws, "Emulation.setDeviceMetricsOverride", {
    width: w, height: h, deviceScaleFactor: 2, mobile: w < 600,
  });
}

async function shot(ws, filename) {
  const { data } = await cdp(ws, "Page.captureScreenshot", { format: "png" });
  const outPath = path.join(OUT, filename);
  fs.writeFileSync(outPath, Buffer.from(data, "base64"));
  console.log(`  wrote ${filename}`);
}

async function futureMeFlow(ws, filenamePrefix, width, height) {
  await viewport(ws, width, height);
  await cdp(ws, "Page.navigate", { url: `${APP}/(tabs)/future-me` });
  await wait(2500);
  await cdp(ws, "Runtime.evaluate", {
    expression: `
      (function() {
        const input = document.querySelector('input[placeholder*="Ask" i], input[placeholder*="type" i], textarea');
        if (!input) return false;
        const setter = Object.getOwnPropertyDescriptor(input.__proto__, 'value').set;
        setter.call(input, 'Should I try keto?');
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        const buttons = Array.from(document.querySelectorAll('button, [role=button], [data-testid]'));
        const send = buttons.find(b => /^\\s*send\\s*$/i.test(b.textContent || '') || b.getAttribute?.('data-testid') === 'coach-send');
        if (send) send.click();
        return !!send;
      })();`,
  });
  await wait(4500);
  await shot(ws, `${filenamePrefix}-${width}.png`);
}

async function scenarioFlow(ws, filenamePrefix, width, height) {
  await viewport(ws, width, height);
  await cdp(ws, "Page.navigate", { url: `${APP}/week/scenarios?week=2` });
  await wait(4000);
  // Pick cafeteria + 2 others, then Start.
  await cdp(ws, "Runtime.evaluate", {
    expression: `
      (function() {
        const pick = (id) => {
          const el = document.querySelector('[data-testid="settings-chip-' + id + '"]');
          if (el) el.click();
          return !!el;
        };
        pick('cafeteria');
        pick('restaurant');
        pick('home');
        const start = document.querySelector('[data-testid="settings-start"]');
        if (start) start.click();
        return true;
      })();`,
  });
  await wait(4500);
  await shot(ws, `${filenamePrefix}-${width}.png`);
}

(async () => {
  console.log("launching chrome");
  const chrome = await chromeLauncher.launch({
    chromeFlags: ["--headless=new", "--disable-gpu", "--hide-scrollbars"],
    logLevel: "silent",
  });
  try {
    const tabs = await fetch(`http://127.0.0.1:${chrome.port}/json`).then((r) => r.json());
    const target = tabs.find((t) => t.type === "page");
    const ws = await connect(target.webSocketDebuggerUrl);
    await cdp(ws, "Page.enable");
    await cdp(ws, "Runtime.enable");

    await viewport(ws, 390, 1100);
    console.log("logging in");
    await login(ws);

    for (const w of [390, 1280]) {
      const h = w < 600 ? 1100 : 900;
      console.log(`capturing future-me redirect at ${w}×${h}`);
      await futureMeFlow(ws, "future-me-redirect", w, h);
      console.log(`capturing week2 cafeteria label at ${w}×${h}`);
      await scenarioFlow(ws, "week2-cafeteria-label", w, h);
    }
    ws.close();
  } finally {
    await chrome.kill();
  }
  console.log("done");
})().catch((e) => { console.error(e); process.exit(1); });
