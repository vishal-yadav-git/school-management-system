import { spawn } from "child_process";
import fs from "fs";
import path from "path";

const CHROME_PATH = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const TEMP_PROFILE = path.join(process.env.TEMP || "C:\\Temp", "chrome_test_lb_" + Date.now());

class CDPClient {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.id = 1;
    this.callbacks = new Map();
  }

  async connect() {
    if (this.ws.readyState === WebSocket.OPEN) return;
    await new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = reject;
    });

    this.ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && this.callbacks.has(msg.id)) {
        const { resolve, reject } = this.callbacks.get(msg.id);
        this.callbacks.delete(msg.id);
        if (msg.error) reject(msg.error);
        else resolve(msg.result);
      }
    };

    await this.send("Page.enable");
    await this.send("Runtime.enable");
  }

  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = this.id++;
      this.callbacks.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async eval(expr) {
    const res = await this.send("Runtime.evaluate", {
      expression: expr,
      returnByValue: true,
      awaitPromise: true,
    });
    return res.result?.value;
  }
}

async function run() {
  const chromeProc = spawn(CHROME_PATH, [
    "--remote-debugging-port=9222",
    "--headless=new",
    "--no-first-run",
    "--no-default-browser-check",
    `--user-data-dir=${TEMP_PROFILE}`,
    "http://localhost:3000/"
  ]);

  await new Promise(r => setTimeout(r, 3000));

  const listRes = await fetch("http://127.0.0.1:9222/json");
  const targets = await listRes.json();
  const pageTarget = targets.find(t => t.type === "page");
  if (!pageTarget) throw new Error("No page target");

  const client = new CDPClient(pageTarget.webSocketDebuggerUrl);
  await client.connect();

  await client.send("Page.setDeviceMetricsOverride", {
    width: 1440,
    height: 900,
    deviceScaleFactor: 1,
    mobile: false,
  });

  // Scroll down to the Leaderboard section
  const lbCoords = await client.eval(`(() => {
    const sec = document.querySelector('section[aria-label="Top 10 Institute Leaderboard"]');
    if (!sec) return null;
    const r = sec.getBoundingClientRect();
    window.scrollTo({ top: window.scrollY + r.top - 120, behavior: "instant" });
    return { top: r.top, found: true };
  })()`);

  console.log("Leaderboard section found:", lbCoords);
  await new Promise(r => setTimeout(r, 900));

  // Capture screenshot of desktop leaderboard
  const screenshotRes = await client.send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync("docs/screenshots/leaderboard_desktop.png", Buffer.from(screenshotRes.data, "base64"));
  console.log("Screenshot saved to docs/screenshots/leaderboard_desktop.png");

  // Mobile viewport verification
  await client.send("Page.setDeviceMetricsOverride", {
    width: 390,
    height: 844,
    deviceScaleFactor: 2,
    mobile: true,
  });

  await client.eval(`(() => {
    const sec = document.querySelector('section[aria-label="Top 10 Institute Leaderboard"]');
    if (sec) {
      const r = sec.getBoundingClientRect();
      window.scrollTo({ top: window.scrollY + r.top - 80, behavior: "instant" });
    }
  })()`);

  await new Promise(r => setTimeout(r, 800));

  const mobShot = await client.send("Page.captureScreenshot", { format: "png" });
  fs.writeFileSync("docs/screenshots/leaderboard_mobile.png", Buffer.from(mobShot.data, "base64"));
  console.log("Screenshot saved to docs/screenshots/leaderboard_mobile.png");

  chromeProc.kill();
  process.exit(0);
}

run().catch(e => {
  console.error(e);
  process.exit(1);
});
