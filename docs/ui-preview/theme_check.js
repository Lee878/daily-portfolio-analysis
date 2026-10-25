// 双主题的浏览器实测：AC-02 / AC-03 / AC-04 / AC-05 / AC-06。
//
// 为什么必须真跑浏览器：主题机制全是"改属性 + 读存储 + 绑事件"，
// 静态看代码看不出首帧闪不闪、点了会不会刷新、存储坏了会不会抛异常。
// 这四条 AC 的判定式本身就写着"用无头浏览器打开样例 HTML"。
//
// 用法：node docs/ui-preview/theme_check.js <样例.html>
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const os = require("os");

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const PORT = 9351;
const TMP = os.tmpdir();
const file = path.resolve(process.argv[2]);
if (!fs.existsSync(file)) {
  console.error("样例不存在：" + file);
  process.exit(2);
}
const URL_ = "file:///" + file.replace(/\\/g, "/");

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
function check(name, ok, detail) {
  results.push({ name, ok: !!ok, detail: detail === undefined ? "" : String(detail) });
  console.log((ok ? "  [OK] " : "  [FAIL] ") + name + (detail !== undefined ? "  " + detail : ""));
}

async function main() {
  const userDir = fs.mkdtempSync(path.join(TMP, "theme-cdp-"));
  const chrome = spawn(CHROME, [
    "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
    `--remote-debugging-port=${PORT}`, `--user-data-dir=${userDir}`,
    "--no-first-run", "--no-default-browser-check", "about:blank",
  ], { stdio: "ignore" });

  let version = null;
  for (let i = 0; i < 60; i++) {
    await sleep(250);
    try {
      version = await (await fetch(`http://127.0.0.1:${PORT}/json/version`)).json();
      break;
    } catch (e) {}
  }
  if (!version) { console.error("chrome 未就绪"); chrome.kill(); process.exit(1); }

  const created = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: "PUT" })).json();
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
  await send("Log.enable");

  const evalJs = async (expression) => {
    const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + " " + (r.exceptionDetails.exception && r.exceptionDetails.exception.description || ""));
    return r.result.value;
  };

  const goto = async () => {
    await send("Page.navigate", { url: URL_ });
    await sleep(1200);
  };

  // ---------- AC-06 · 首帧无闪烁 ----------
  console.log("\n== AC-06 首帧无主题闪烁 ==");
  await send("Page.addScriptToEvaluateOnNewDocument", {
    source: `
      window.__frames = [];
      function snap(tag){
        try{
          var de = document.documentElement;
          window.__frames.push({
            tag: tag,
            attr: de.getAttribute('data-theme'),
            bg: getComputedStyle(document.body || de).backgroundColor,
            t: Math.round(performance.now())
          });
        }catch(e){ window.__frames.push({tag:tag, err:String(e)}); }
      }
      requestAnimationFrame(function(){ snap('raf1');
        requestAnimationFrame(function(){ snap('raf2'); }); });
    `,
  });

  // 预置 localStorage = light
  await goto();
  const seed = await evalJs(`(function(){try{localStorage.setItem('dpa-theme','light');return localStorage.getItem('dpa-theme');}catch(e){return 'ERR:'+e.name;}})()`);
  check("localStorage 可写（file:// 同源）", seed === "light", "seed=" + seed);

  await goto();
  const first = await evalJs(`JSON.stringify(window.__frames)`);
  const frames = JSON.parse(first);
  const attrAtFirst = frames.length ? frames[0].attr : null;
  const bgAtFirst = frames.length ? frames[0].bg : null;
  check("首帧 data-theme 已是 light（无浅色闪帧）", attrAtFirst === "light",
        "首帧 attr=" + attrAtFirst + " bg=" + bgAtFirst + " frames=" + first);

  // ---------- AC-01 · 默认深色（清空存储后重载）----------
  console.log("\n== AC-01 无存储时回落深色 ==");
  await evalJs(`(function(){try{localStorage.removeItem('dpa-theme');return 1;}catch(e){return 0;}})()`);
  await goto();
  const dflt = await evalJs(`JSON.stringify({attr:document.documentElement.getAttribute('data-theme'),bg:getComputedStyle(document.body).backgroundColor,ls:(function(){try{return localStorage.getItem('dpa-theme');}catch(e){return 'ERR';}})()})`);
  const d = JSON.parse(dflt);
  check("无存储 → 深色", d.attr === "dark", dflt);
  check("深色底色实算正确", d.bg === "rgb(15, 20, 25)", "body bg=" + d.bg);

  // ---------- AC-03 · 控件可点，点击即切换 ----------
  console.log("\n== AC-03 切换控件可点 ==");
  const btnCount = await evalJs(`document.querySelectorAll('#theme-toggle').length`);
  check("恰有 1 个 #theme-toggle", btnCount === 1, "count=" + btnCount);
  const btnInfo = await evalJs(`(function(){var b=document.getElementById('theme-toggle');return JSON.stringify({tag:b.tagName,type:b.getAttribute('type'),label:b.getAttribute('aria-label'),text:b.textContent.trim()});})()`);
  const bi = JSON.parse(btnInfo);
  check("是 <button> 且 type=button", bi.tag === "BUTTON" && bi.type === "button", btnInfo);
  check("有 aria-label", !!bi.label, bi.label);
  check("无可见文本（纯图标）", bi.text === "", "text=" + JSON.stringify(bi.text));

  const navBefore = await evalJs(`performance.navigation ? performance.navigation.type : -1`);
  await evalJs(`document.getElementById('theme-toggle').click()`);
  await sleep(400);
  const after = await evalJs(`JSON.stringify({attr:document.documentElement.getAttribute('data-theme'),bg:getComputedStyle(document.body).backgroundColor,ls:localStorage.getItem('dpa-theme'),meta:document.querySelector('meta[name="theme-color"]').getAttribute('content'),nav:performance.navigation?performance.navigation.type:-1})`);
  const a = JSON.parse(after);
  check("点击后切到浅色", a.attr === "light", after);
  check("浅色底色实算正确", a.bg === "rgb(250, 249, 246)", "body bg=" + a.bg);
  check("选择已持久化到 dpa-theme", a.ls === "light", "ls=" + a.ls);
  check("theme-color 跟随切换", a.meta === "#faf9f6", "meta=" + a.meta);
  check("未发生导航（performance.navigation 未增加）", a.nav === navBefore,
        "before=" + navBefore + " after=" + a.nav);

  // ---------- AC-04 · 重新加载仍是浅色 ----------
  console.log("\n== AC-04 重新加载后主题保持 ==");
  await goto();
  const reload = await evalJs(`JSON.stringify({attr:document.documentElement.getAttribute('data-theme'),bg:getComputedStyle(document.body).backgroundColor})`);
  const rl = JSON.parse(reload);
  check("重载后仍是浅色", rl.attr === "light", reload);

  // ---------- AC-05 · 存储抛异常时回落深色且无未捕获错误 ----------
  console.log("\n== AC-05 localStorage 抛异常时回落深色 ==");
  const errs = [];
  ws.addEventListener("message", (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.method === "Runtime.exceptionThrown") {
      errs.push(JSON.stringify(msg.params.exceptionDetails));
    }
  });
  // 用新文档把 localStorage 全部方法替换成抛异常的桩
  await send("Page.addScriptToEvaluateOnNewDocument", {
    source: `
      Object.defineProperty(window, 'localStorage', {
        configurable: true,
        get: function(){ throw new DOMException('denied', 'SecurityError'); }
      });
    `,
  });
  await goto();
  const broke = await evalJs(`JSON.stringify({attr:document.documentElement.getAttribute('data-theme'),bg:getComputedStyle(document.body).backgroundColor})`);
  const bk = JSON.parse(broke);
  check("localStorage 抛异常 → 回落深色", bk.attr === "dark", broke);
  check("无未捕获 JS 错误", errs.length === 0, "exceptions=" + JSON.stringify(errs));

  chrome.kill();
  const failed = results.filter((r) => !r.ok);
  console.log("\n" + "=".repeat(56));
  console.log(`共 ${results.length} 项，通过 ${results.length - failed.length}，失败 ${failed.length}`);
  if (failed.length) {
    failed.forEach((f) => console.log("  [FAIL] " + f.name + "  " + f.detail));
    process.exit(1);
  }
  console.log("双主题浏览器实测全部通过");
  process.exit(0);
}
main().catch((e) => { console.error(e); process.exit(1); });
