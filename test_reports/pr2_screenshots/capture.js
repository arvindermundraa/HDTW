// Chrome DevTools Protocol screenshotter. Logs in via the actual UI
// (AsyncStorage on web uses IndexedDB, not localStorage, so injecting a
// token programmatically from outside doesn't work), then captures the
// two screens changed in PR 2: the Week 1 feedback step (new combined
// Grains/Fats bars + the rank-based "Areas with room to grow" list) and
// the Eat dashboard (new rank-based Room-to-grow section). Captures
// each at 390 px wide ("phone") and 1280 px wide ("desktop").
//
// Run from the repo root (both servers already running):
//   node test_reports/pr2_screenshots/capture.js

const WebSocket = require("../../frontend/node_modules/ws");
const chromeLauncher = require("../../frontend/node_modules/chrome-launcher");
const fs = require("node:fs");
const path = require("node:path");

const APP = "http://localhost:3001";
const EMAIL = "maya.demo@example.com";
const PASSWORD = "demo-pass-123";
const OUT = path.join(__dirname);

const SHOTS = [
  { id: "eat-390", path: "/eat", width: 390, height: 1100 },
  { id: "eat-1280", path: "/eat", width: 1280, height: 900 },
  { id: "week1-feedback-390", path: "/week/feedback?week=1", width: 390, height: 1400 },
  { id: "week1-feedback-1280", path: "/week/feedback?week=1", width: 1280, height: 900 },
];

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
    const r = await cdp(ws, "Runtime.evaluate", {
      expression: expr, returnByValue: true,
    });
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
  // The login screen lives at /auth.
  await cdp(ws, "Page.navigate", { url: `${APP}/auth` });
  await waitFor(ws, "!!document.querySelector('[data-testid=auth-email]')");
  await cdp(ws, "Runtime.evaluate", {
    expression: `
      (function() {
        const setValue = (el, v) => {
          const setter = Object.getOwnPropertyDescriptor(el.__proto__, 'value').set;
          setter.call(el, v);
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new Event('change', { bubbles: true }));
        };
        setValue(document.querySelector('[data-testid=auth-email]'), ${JSON.stringify(EMAIL)});
        setValue(document.querySelector('[data-testid=auth-password]'), ${JSON.stringify(PASSWORD)});
        const btn = document.querySelector('[data-testid=auth-submit]');
        if (btn) btn.click();
        return true;
      })();
    `,
  });
  // Wait until we land on an authed route (anything but /auth).
  await waitFor(ws, "!location.pathname.startsWith('/auth')", 15000);
  await wait(1200);
}

async function screenshotAt(ws, shot) {
  await cdp(ws, "Emulation.setDeviceMetricsOverride", {
    width: shot.width, height: shot.height, deviceScaleFactor: 2, mobile: shot.width < 600,
  });
  await cdp(ws, "Page.navigate", { url: `${APP}${shot.path}` });
  // Let the page render and any API calls settle.
  await wait(3500);
  // Extra wait if the dashboard shows the "couldn't load" fallback — one retry.
  const needRetry = await cdp(ws, "Runtime.evaluate", {
    expression: `!!document.body.innerText.match(/couldn't load this right now/i)`, returnByValue: true,
  });
  if (needRetry.result.value) {
    await cdp(ws, "Runtime.evaluate", {
      expression: `
        (function() {
          const b = Array.from(document.querySelectorAll('button, [role=button], div[aria-role=button]'))
            .find(x => /try again/i.test(x.textContent || ''));
          if (b) b.click();
          return true;
        })();`,
    });
    await wait(2500);
  }
  const { data } = await cdp(ws, "Page.captureScreenshot", { format: "png" });
  const outPath = path.join(OUT, `${shot.id}.png`);
  fs.writeFileSync(outPath, Buffer.from(data, "base64"));
  console.log(`  wrote ${path.basename(outPath)}`);
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

    // Log in once at an interim viewport.
    await cdp(ws, "Emulation.setDeviceMetricsOverride", {
      width: 390, height: 1000, deviceScaleFactor: 2, mobile: true,
    });
    console.log("logging in via the UI");
    await login(ws);

    for (const shot of SHOTS) {
      console.log(`capturing ${shot.id} (${shot.width}×${shot.height})`);
      await screenshotAt(ws, shot);
    }
    ws.close();
  } finally {
    await chrome.kill();
  }
  console.log("done");
})().catch((e) => { console.error(e); process.exit(1); });
