// 用 CDP 精确模拟手机视口并截图（--window-size 在 headless=new 下不可靠）
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const os = require("os");

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const PORT = 9333;
const TMP = os.tmpdir();

const files = process.argv.slice(2);
if (!files.length) {
  console.error("usage: node shoot.js <html> [html2 ...]");
  process.exit(1);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function main() {
  const userDir = fs.mkdtempSync(path.join(TMP, "cdp-"));
  const chrome = spawn(CHROME, [
    "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
    `--remote-debugging-port=${PORT}`, `--user-data-dir=${userDir}`,
    "--no-first-run", "--no-default-browser-check", "about:blank",
  ], { stdio: "ignore" });

  // 等调试端口就绪
  let version = null;
  for (let i = 0; i < 60; i++) {
    await sleep(250);
    try {
      const r = await fetch(`http://127.0.0.1:${PORT}/json/version`);
      version = await r.json();
      break;
    } catch (e) { /* 继续等 */ }
  }
  if (!version) { console.error("chrome 未就绪"); chrome.kill(); process.exit(1); }

  for (const file of files) {
    const abs = path.resolve(file);
    const created = await (await fetch(`http://127.0.0.1:${PORT}/json/new?${encodeURI(abs)}`, { method: "PUT" })).json();
    const ws = new WebSocket(created.webSocketDebuggerUrl);

    let id = 0;
    const pending = new Map();
    const send = (method, params = {}) => new Promise((res, rej) => {
      const mid = ++id;
      pending.set(mid, { res, rej });
      ws.send(JSON.stringify({ id: mid, method, params }));
    });

    await new Promise((res) => { ws.onopen = res; });
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.id && pending.has(msg.id)) {
        const p = pending.get(msg.id);
        pending.delete(msg.id);
        msg.error ? p.rej(new Error(JSON.stringify(msg.error))) : p.res(msg.result);
      }
    };

    await send("Page.enable");
    await send("Runtime.enable");
    // 默认 iPhone 14 Pro：390 x 844，DPR 2；VW=1280 VH=900 MOBILE=0 走桌面
    const VW = parseInt(process.env.VW || "390", 10);
    const VH = parseInt(process.env.VH || "844", 10);
    const MOBILE = process.env.MOBILE !== "0";
    await send("Emulation.setDeviceMetricsOverride", {
      width: VW, height: VH, deviceScaleFactor: MOBILE ? 2 : 1, mobile: MOBILE,
    });
    await send("Page.navigate", { url: "file:///" + abs.replace(/\\/g, "/") });
    await sleep(1600);

    // 量一下真实布局宽度，确认没溢出
    const m = await send("Runtime.evaluate", {
      expression: `JSON.stringify({
        vw: document.documentElement.clientWidth,
        sw: document.documentElement.scrollWidth,
        bh: document.body.scrollHeight
      })`,
      returnByValue: true,
    });
    const metrics = JSON.parse(m.result.value);
    console.log(path.basename(file), JSON.stringify(metrics));

    // 首屏
    const shot1 = await send("Page.captureScreenshot", {
      format: "png", captureBeyondViewport: false,
    });
    const base = path.basename(file, ".html");
    fs.writeFileSync(path.join(TMP, `m-${base}-hero.png`), Buffer.from(shot1.data, "base64"));

    // 分段切片：便于逐屏审阅，不用看超长整页
    const slices = (process.env.SLICES || "900,2400,4200")
      .split(",").map((s) => parseInt(s, 10)).filter((n) => !isNaN(n));
    let k = 0;
    for (const y of slices) {
      if (y + 900 > metrics.bh) break;
      const sh = await send("Page.captureScreenshot", {
        format: "png", captureBeyondViewport: true,
        clip: { x: 0, y, width: VW, height: Math.min(900, VH), scale: 1 },
      });
      fs.writeFileSync(path.join(TMP, `m-${base}-s${k++}.png`), Buffer.from(sh.data, "base64"));
    }

    // 长图（整页，限高 9000 CSS px 防止过大）
    const clipH = Math.min(metrics.bh, 9000);
    const shot2 = await send("Page.captureScreenshot", {
      format: "png", captureBeyondViewport: true,
      clip: { x: 0, y: 0, width: VW, height: clipH, scale: 1 },
    });
    fs.writeFileSync(path.join(TMP, `m-${base}-full.png`), Buffer.from(shot2.data, "base64"));
    console.log("  ->", `m-${base}-hero.png`, `m-${base}-s0..s${k - 1}.png`, `m-${base}-full.png`);

    await fetch(`http://127.0.0.1:${PORT}/json/close/${created.id}`);
    ws.close();
  }

  chrome.kill();
  process.exit(0);
}

main().catch((e) => { console.error(e); process.exit(1); });
