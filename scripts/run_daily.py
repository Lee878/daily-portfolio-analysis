#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily-portfolio-analysis v2 统一编排入口（唯一推荐出报告的通道）。

把"取证 → 证据门 → (agent 补证/写卡片) → 证据门复检 → 生成 HTML → 报告门"
串成一条物理管道，用退出码硬性阻断；agent 无法靠"自觉"跳过：

  1) python run_daily.py fetch  --session pre --date 2026-09-21 --holdings <md>
       跑 fetch_data.py 生成证据骨架，再跑证据门；FAIL 会打印待补清单并以码 10 退出。
  2) （agent 补证：行情/财务/资金走 NeoData MCP，公告/新闻走搜索，原地写回 evidence/*.json）
  3) python run_daily.py gate   --session pre --date 2026-09-21 --holdings <md>
       补证后只复检证据门（不重跑 fetch_data，保护已补数据）；PASS(码0) 才能继续。
  4) （agent 基于模板写当天 cards 与 builder）
  5) python run_daily.py report --session pre --date 2026-09-21 \
         --holdings <md> --builder scripts/build_report_<date>.py
       先强制复检证据门 → 运行 builder 生成 HTML → 跑报告门：
         · 证据门不过：不运行 builder，退出 10/11；
         · 报告门 FAIL：删除刚生成的 HTML，退出 12（物理上不留不合格产物）；
         · 双门 PASS：在 HTML 写入不可见门禁签名 <meta name="daily-gate" ...>，退出 0。

只有带 daily-gate 签名的 HTML 才允许 present_files 交付（见 SKILL.md 第 7 步）。

退出码：0=双门 PASS；10=证据门 FAIL（需补证）；11=证据门降级（需显式 --allow-degraded）；
        12=报告门 FAIL（HTML 已删除）；2=参数/环境/builder 错误。
"""
import argparse
import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import gate_check as gate  # noqa: E402
import paths  # noqa: E402

SESSION_CN = {"pre": "盘前报告", "noon": "盘中总结", "post": "盘后总结",
              "quick": "快速诊断"}
FETCH_PY = SCRIPT_DIR / "fetch_data.py"
GATE_PY = SCRIPT_DIR / "gate_check.py"

EXIT_PASS, EXIT_ENV, EXIT_EV_FAIL, EXIT_EV_DEGRADED, EXIT_RP_FAIL = 0, 2, 10, 11, 12

def engine_version_info():
    """返回 (version, MANIFEST 短指纹)；统一走 paths（v2.4.0）。"""
    return paths.version_info()


def resolve_paths(args):
    """解析 holdings 与报告根目录（v2.4.0：统一走 paths，删除豆包云路径回退）。

    优先级：显式参数 > 环境变量 > config/ > 当前目录。
    报告根：显式 > 环境变量 > 便携模式（holdings 同级有 daily-reports/）> data/daily-reports/。
    """
    holdings = paths.resolve_holdings(getattr(args, "holdings", None))
    if holdings is None:
        print("[run_daily][error] 找不到 holdings.md"
              "（试过 config/holdings.md；可用 --holdings 指定）")
        sys.exit(EXIT_ENV)
    report_root = paths.resolve_report_root(getattr(args, "report_root", None), holdings)
    return report_root, holdings


def load_holdings(holdings: Path):
    hs = gate.parse_holdings(holdings.read_text(encoding="utf-8"))
    if not hs:
        print("[run_daily][error] holdings.md 未解析到持仓")
        sys.exit(EXIT_ENV)
    return hs


def load_targets(holdings: Path, session: str):
    """在册持仓 + 关注库（watchlist）合并去重。

    关注库仅纳入"接下来要开盘市场"对应标的（pre→A股/港股，post→美股），
    noon/quick 不纳入；与 gate_check.main、fetch_data.main 的口径保持一致。
    """
    hs = load_holdings(holdings)
    wl_markets = {"pre": {"A股", "港股"}, "post": {"美股"}}.get(session, set())
    wl_path = paths.watchlist_path(holdings)
    watchlist = []
    if wl_markets and wl_path:
        watchlist = [w for w
                     in gate.parse_watchlist(wl_path.read_text(encoding="utf-8"))
                     if w["market"] in wl_markets]
    merged, seen = [], set()
    for h in hs + watchlist:
        key = (h["market"], h["ticker"])
        if key in seen:
            continue
        seen.add(key)
        merged.append(h)
    # 午间只聚焦 A股/港股持仓（与 fetch_data.main、gate_check.main 口径一致）
    if session == "noon":
        merged = [h for h in merged if h["market"] in {"A股", "港股"}]
    return merged


def html_path_for(report_root: Path, date: str, session: str, override: str | None):
    if override:
        return Path(override)
    return report_root / f"{date}-{SESSION_CN[session]}-可视化.html"


# ---------------------------------------------------------------------------
def do_fetch(args):
    report_root, holdings = resolve_paths(args)
    print("=" * 64)
    _v, _b = engine_version_info()
    print(f"[run_daily] Step1/2 取证骨架  session={args.session} date={args.date} 引擎 v{_v} 构建 {_b}")
    print("=" * 64)
    cmd = [sys.executable, str(FETCH_PY), "--holdings", str(holdings),
           "--session", args.session, "--date", args.date,
           "--report-root", str(report_root)]
    if args.no_network:
        cmd.append("--no-network")
    rc = subprocess.run(cmd).returncode
    if rc != 0:
        print("[run_daily][error] fetch_data.py 执行失败")
        sys.exit(EXIT_ENV)
    return do_gate(args)


def do_gate(args):
    report_root, holdings = resolve_paths(args)
    hs = load_targets(holdings, args.session)
    result = gate.check_evidence(report_root, args.date, args.session, hs,
                                 args.allow_degraded)
    gate.render(result)
    code = result["exit_code"]
    if code == gate.PASS:
        print(f"[run_daily] 证据门 PASS，组合机械覆盖率 "
              f"{round(result['combo_coverage']*100,1)}% —— 可进入分析/生成。")
        return EXIT_PASS
    if code == gate.DEGRADED:
        # v2.2.3：显式降级时放行（旧版缺这一支，--allow-degraded 反而恒返回 10，
        # SKILL 写的"数据源全挂可降级放行"实际走不通）
        if args.allow_degraded:
            print("[run_daily] 证据门 DEGRADED：已显式 --allow-degraded，放行。"
                  "报告顶部必须挂'数据不足'横幅，且只给 定性判断。")
            return EXIT_PASS
        print("[run_daily] 证据门：存在覆盖率 <50% 的标的。补证后重跑 gate；"
              "若确无数据，需显式 --allow-degraded 并在报告挂'数据不足'横幅。")
        return EXIT_EV_DEGRADED
    print("[run_daily] 证据门 FAIL：请按上方 problems 与各 evidence/*.json 的 gaps "
          "补证（行情/财务/资金走 NeoData MCP，公告/新闻走搜索；原地写回），然后重跑 gate。")
    return EXIT_EV_FAIL


def _inject_signature(html: Path, date: str, session: str, coverage: float,
                      status: str = "PASS", reason: str = ""):
    """写入门禁签名。status=DEGRADED 表示「有缺口但仍交付」（PRD FR-07）。

    退出码不因签名变化而放宽：门禁没过就仍然非 0，监控照样能抓。
    """
    text = html.read_text(encoding="utf-8")
    if 'name="daily-gate"' in text:
        text = re.sub(r'<meta name="daily-gate"[^>]*>', "", text)
    stamp = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S%z")
    version, build = engine_version_info()
    ver = f'engine={version} build={build} ' if version else ""
    gate = "PASS" if status == "PASS" else "FAIL"
    why = f'reason={reason} ' if reason else ""
    sig = (f'<meta name="daily-gate" content="{status} date={date} session={session} '
           f'evidence={gate} report={gate} coverage={round(coverage*100,1)}% '
           f'{why}{ver}at={stamp}">')
    if "</title>" in text:
        text = text.replace("</title>", "</title>\n" + sig, 1)
    elif re.search(r"<html[^>]*>", text):
        text = re.sub(r"(<html[^>]*>)", r"\1\n" + sig, text, count=1)
    else:
        text = sig + "\n" + text
    html.write_text(text, encoding="utf-8")


def _inject_version_footer(html: Path, coverage: float, status: str = "PASS"):
    """在页脚注入可见版本条：用户打开报告即知用的是哪一版引擎/构建。"""
    text = html.read_text(encoding="utf-8")
    text = re.sub(r'<footer id="daily-version-footer">.*?</footer>', "", text, flags=re.S)
    version, build = engine_version_info()
    gate_txt = "双门禁 PASS" if status == "PASS" else "报告门未过·降级交付"
    footer = (
        '<footer id="daily-version-footer" style="margin:18px 0 6px;padding-top:12px;'
        'border-top:1px solid #21262d;text-align:center;font-size:11px;color:#7d8590;'
        'line-height:1.7;font-family:ui-monospace,Menlo,Consolas,monospace;">'
        f'引擎 v{version} · 构建 {build} · {gate_txt} · 覆盖率 {round(coverage*100,1)}%<br>'
        '本报告由确定性脚本门禁产出，不构成投资建议，决策与后果由用户自行承担。'
        '</footer>')
    if "</body>" in text:
        text = text.replace("</body>", footer + "\n</body>", 1)
    else:
        text += footer
    html.write_text(text, encoding="utf-8")


def _apply_degrade(html: Path, problems, coverage: float) -> int:
    """报告门未过时插入「数据不全」横幅（PRD FR-07 / FR-08）。

    与旧行为的分界：旧版直接 unlink，用户当天什么都拿不到；新版保留真实内容，
    把缺口摆在首屏第一屏，且退出码仍非 0——既有信息又有告警。
    """
    import html as _html
    text = html.read_text(encoding="utf-8")
    # 重跑 report 时先清掉旧横幅（用哨兵界定范围，避免非贪婪误删后续区块）
    text = re.sub(r'<div id="degrade-banner".*?<!--/degrade-->', "", text, flags=re.S)
    shown = list(problems)[:8]
    items = "".join(f"<li>{_html.escape(str(p))}</li>" for p in shown)
    rest = len(problems) - len(shown)
    if rest > 0:
        items += f"<li>…另有 {rest} 项</li>"
    banner = (
        '<div id="degrade-banner" style="margin:14px 0 0;padding:12px 14px;'
        'border:1px solid #f85149;border-left-width:5px;border-radius:6px;'
        'background:#2d1214;color:#ffdcd7;font-size:13.5px;line-height:1.6">'
        '<div style="font-weight:700;font-size:15px;color:#ff7b72">'
        '⚠ 数据不全 · 本报告未通过报告门</div>'
        f'<div style="margin-top:4px;color:#d0a9a4">覆盖率 {round(coverage * 100, 1)}%'
        f' · {len(problems)} 项问题 · 已按降级交付</div>'
        f'<ul style="margin:8px 0 0 18px;padding:0">{items}</ul>'
        '<div style="margin-top:8px;color:#d0a9a4">涉及缺口的数据点已在证据清单中标注；'
        '结论仅作参考，不构成投资建议。</div>'
        '</div><!--/degrade-->')
    if re.search(r"<body[^>]*>", text):
        text = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + banner, text, count=1)
    else:
        text = banner + text
    html.write_text(text, encoding="utf-8")
    return len(shown)


# 徽标统一中性灰，不使用绿/蓝涨跌色（避免与"多方/涨=绿、空方/跌=红"语义混淆）；
# 仅 P4 弱证据/传闻用黄色虚线，便于识别"不可单独成论"。.b 为盘前 builder 自有徽标，
# 在此一并统一配色（本样式注入在 builder CSS 之后，同特异性下生效）。
BADGE_CSS = (
    ".rb,.b{display:inline-block;font-family:ui-monospace,Menlo,Consolas,monospace;"
    "font-size:9.5px;font-weight:400;line-height:1.2;color:#9aa7b4;"
    "background:rgba(139,148,158,.08);border:1px solid rgba(139,148,158,.26);"
    "border-radius:4px;padding:1px 4px;margin:0 1px;vertical-align:baseline;"
    "white-space:nowrap;opacity:.6}"
    ".rb.p1,.rb.p2,.b.p1,.b.p2{color:#c6d0db;border-color:rgba(154,167,180,.42);"
    "background:rgba(154,167,180,.12);opacity:.8}"
    ".rb.p4,.b.p4{color:#d29922;border:1px dashed rgba(210,153,34,.55);"
    "background:rgba(210,153,34,.08);opacity:.92}"
)
_EXISTING_BADGE_RE = re.compile(r'<span class="b [^"]*"[^>]*>.*?</span>', re.S)


def _load_id_meta(report_root: Path, date: str, session: str):
    """从本批次证据 JSON 装载 ID→(最高证据级别, 来源)，供徽标 title/配色。"""
    import glob
    import html as _html  # noqa: F401
    import json
    rank = {"P1": 3, "P2": 2, "P3": 1, "P4": 0}
    meta = {}
    for f in glob.glob(str(report_root / "evidence" / f"{date}_{session}_*.json")):
        try:
            evd = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue

        def put(i, lv, src):
            if not i:
                return
            lv = lv or "P3"
            cur = meta.get(i)
            if cur is None or rank.get(lv, 1) > rank.get(cur[0], 1):
                meta[i] = (lv, src or (cur[1] if cur else ""))

        for p in evd.get("data_points", []):
            put(p.get("id"), p.get("evidence_level"), p.get("source", ""))
        for n in evd.get("news", []):
            put(n.get("id"), n.get("evidence_level"),
                n.get("source") or n.get("headline", ""))
        for c in evd.get("chain_notes", []):
            put(c.get("id"), c.get("evidence_level"),
                c.get("source") or c.get("sector", ""))
    return meta


def _render_badges(html: Path, report_root: Path, date: str, session: str):
    """把正文裸露的 [dp/nw/ch-000] 统一包成弱化小徽标。

    已被 builder 用 <span class="b …"> 渲染过的徽标保持不动；徽标内保留裸文本
    `[xx-000]`，门禁仍按它计数，故不影响报告门。任何 builder 漏渲染都由此兜底，
    保证用户看不到突兀的裸方括号。返回新包裹的徽标数。
    """
    import html as _html
    text = html.read_text(encoding="utf-8")
    meta = _load_id_meta(report_root, date, session)

    protected = []

    def _protect(m):
        protected.append(m.group(0))
        return f"\x00{len(protected)-1}\x00"

    text = _EXISTING_BADGE_RE.sub(_protect, text)
    count = 0

    def _wrap(m):
        nonlocal count
        i = m.group(0).strip("[]")
        lv, src = meta.get(i, ("P3", ""))
        title = _html.escape(f"{lv} · {src}".strip(" ·"), quote=True)
        count += 1
        return f'<span class="rb {lv.lower()}" title="{title}">[{i}]</span>'

    text = gate.ID_RE.sub(_wrap, text)
    text = re.sub("\x00(\\d+)\x00",
                  lambda m: protected[int(m.group(1))], text)

    if count and ".rb{" not in text:
        style = f"<style>{BADGE_CSS}</style>"
        if "</style>" in text:
            text = text.replace("</style>", BADGE_CSS + "</style>", 1)
        elif "</head>" in text:
            text = text.replace("</head>", style + "</head>", 1)
        elif re.search(r"<body[^>]*>", text):
            text = re.sub(r"(<body[^>]*>)", r"\1" + style, text, count=1)
        else:
            text = style + text
    html.write_text(text, encoding="utf-8")
    return count


_BANNER_RE = re.compile(r"(数据覆盖率[^0-9%]{0,12})(\d{1,3})(\s*%)")


def _sync_coverage_banner(html: Path, combo: float):
    """把报告主横幅的覆盖率数字强制校准为门禁机械值（builder 写死会漂移）。

    与 gate_check 的横幅正则同锚点，只替换"数据覆盖率"后第一个百分比，
    不动正文中其他百分比。返回是否改动。
    """
    target = str(int(round(combo * 100)))
    text = html.read_text(encoding="utf-8")
    new, n = _BANNER_RE.subn(
        lambda m: m.group(1) + target + m.group(3), text, count=1)
    if n:
        html.write_text(new, encoding="utf-8")
    return n


def do_report(args):
    report_root, holdings = resolve_paths(args)
    hs = load_targets(holdings, args.session)
    out_html = html_path_for(report_root, args.date, args.session, args.html)

    # ① 生成前强制证据门（不可绕过）
    print("=" * 64)
    print("[run_daily] 生成前强制复检：证据门")
    print("=" * 64)
    ev = gate.check_evidence(report_root, args.date, args.session, hs,
                             args.allow_degraded)
    gate.render(ev)
    # v2.6.0（PRD D-03 / FR-07）：证据门不过**不再阻断出报告**。
    # 缺口本身就是要给用户看的信息；拦住等于让他当天什么都拿不到。
    # 证据门的状态照实传下去，最终签名为 DEGRADED，退出码仍非 0。
    ev_status = "PASS"
    if ev["exit_code"] == gate.FAIL:
        ev_status = "FAIL"
        print(f"[run_daily][降级] 证据门未过（{len(ev['problems'])} 项），"
              "按降级策略继续生成，缺口会写在首屏横幅里。")
    elif ev["exit_code"] == gate.DEGRADED and not args.allow_degraded:
        ev_status = "DEGRADED"
        print("[run_daily][降级] 证据门覆盖率不足，继续生成并标注数据不足。")

    # ② 生成 HTML：--data 走通用渲染器（数据驱动，免写 builder）；否则走旧 builder
    data_path = getattr(args, "data", None)
    if data_path:
        data_path = Path(data_path)
        if not data_path.is_absolute():
            # v2.2.3：按当前工作目录解析（旧版按 scripts/ 解析，相对路径必踩坑）
            data_path = data_path.resolve()
        if not data_path.exists():
            print(f"[run_daily][error] 数据文件不存在：{data_path}"
                  f"（相对路径按当前目录 {Path.cwd()} 解析，建议传绝对路径）")
            return EXIT_ENV
        recon_out = report_root / f"recon-{args.date}-{args.session}.md"
        print("=" * 64)
        print(f"[run_daily] 通用渲染器：{data_path.name}")
        print("=" * 64)
        rc = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "render_report.py"),
             "--data", str(data_path), "--out", str(out_html),
             "--date", args.date, "--session", args.session,
             "--recon-out", str(recon_out),
             "--evidence-dir", str(report_root / "evidence")],
            cwd=str(SCRIPT_DIR)).returncode
        if rc != 0 or not out_html.exists():
            print("[run_daily][error] 渲染器失败，未生成报告。")
            return EXIT_ENV
    else:
        if not args.builder:
            print("[run_daily][error] report 阶段需要 --builder 或 --data")
            return EXIT_ENV
        builder = Path(args.builder)
        if not builder.is_absolute():
            builder = (SCRIPT_DIR / builder).resolve()
        if not builder.exists():
            print(f"[run_daily][error] builder 不存在：{builder}")
            return EXIT_ENV
        print("=" * 64)
        print(f"[run_daily] 运行 builder：{builder.name}")
        print("=" * 64)
        rc = subprocess.run([sys.executable, str(builder)], cwd=str(SCRIPT_DIR)).returncode
        if rc != 0:
            print("[run_daily][error] builder 执行失败，未生成报告。")
            return EXIT_ENV
        if not out_html.exists():
            # 兜底：builder 可能写到了别的路径，尝试在 report-root 找当天 HTML
            cands = sorted(report_root.glob(f"{args.date}*{SESSION_CN[args.session]}*.html"))
            if cands:
                out_html = cands[-1]
            else:
                print(f"[run_daily][error] builder 跑完但找不到产物 {out_html.name}")
                return EXIT_ENV

    # ③ 报告门（不过就删除 HTML）
    print("=" * 64)
    print("[run_daily] 报告门校验")
    print("=" * 64)
    closed = gate.parse_closed_positions(holdings.read_text(encoding="utf-8"))
    rp = gate.check_report(report_root, args.date, args.session, hs, str(out_html),
                           closed=closed)
    gate.render(rp)
    if rp["problems"]:
        # v2.6.0（PRD FR-07）：不再删产物，改为降级交付——保留真实内容，
        # 首屏挂「数据不全」横幅，签名写 DEGRADED，退出码仍为 12 便于监控。
        coverage = rp.get("combo_coverage") or ev["combo_coverage"]
        shown = _apply_degrade(out_html, rp["problems"], coverage)
        _inject_signature(out_html, args.date, args.session, coverage,
                          status="DEGRADED", reason="report_gate")
        _inject_version_footer(out_html, coverage, status="DEGRADED")
        print("=" * 64)
        print(f"[run_daily][降级交付] 报告门 {len(rp['problems'])} 项问题，"
              f"产物已保留并标注缺口：")
        for p in list(rp["problems"])[:shown]:
            print(f"  · {p}")
        print(f"[run_daily] 签名 = DEGRADED，退出码 {EXIT_RP_FAIL}（可被监控抓取）\n  {out_html}")
        print("=" * 64)
        return EXIT_RP_FAIL

    # ④ 双门 PASS：校准覆盖率横幅 → 裸证据 ID 渲染为弱化徽标 → 写入门禁签名
    coverage = rp.get("combo_coverage") or ev["combo_coverage"]
    if _sync_coverage_banner(out_html, coverage):
        print(f"[run_daily] 覆盖率横幅已校准为机械值 {round(coverage*100)}%。")
    n_badges = _render_badges(out_html, report_root, args.date, args.session)
    if n_badges:
        print(f"[run_daily] 已把 {n_badges} 处裸证据 ID 渲染为弱化徽标。")

    # 证据门没过：报告照出，但必须挂横幅 + DEGRADED 签名
    if ev_status != "PASS":
        _apply_degrade(out_html, ev["problems"], coverage)
        _inject_signature(out_html, args.date, args.session, coverage,
                          status="DEGRADED", reason="evidence_gate")
        _inject_version_footer(out_html, coverage, status="DEGRADED")
        print("=" * 64)
        print(f"[run_daily][降级交付] 报告门 PASS，证据门未过 → 签名 DEGRADED，"
              f"退出码 {EXIT_EV_FAIL}\n  {out_html}")
        print("=" * 64)
        return EXIT_EV_FAIL

    _inject_signature(out_html, args.date, args.session, coverage)
    _inject_version_footer(out_html, coverage)
    print("=" * 64)
    print(f"[run_daily] [OK] 双门 PASS（证据门 + 报告门），覆盖率 "
          f"{round(coverage*100,1)}%")
    _ver, _build = engine_version_info()
    print(f"[run_daily] 已写入门禁签名（引擎 v{_ver} 构建 {_build}），唯一允许交付的产物：\n  {out_html}")
    print("[run_daily] 存档 .md 与 evidence/*.json 不交付；present_files 只发该 HTML。")
    print("=" * 64)
    return EXIT_PASS


def ensure_utf8_stdout():
    """Windows 控制台/计划任务默认 GBK，✅ 等字符会 UnicodeEncodeError。

    实现统一到 paths.ensure_utf8_stdout（v2.6.0 收敛）。
    """
    paths.ensure_utf8_stdout()


def main():
    ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description="daily-portfolio-analysis 门禁编排入口")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("fetch", "gate", "report"):
        p = sub.add_parser(name)
        # 默认 None：由 resolve_paths 按 holdings 同级推导，避免写死某台机器的路径
        p.add_argument("--holdings", default=None,
                       help="holdings.md 路径（默认当前目录 holdings.md）")
        p.add_argument("--report-root", default=None,
                       help="报告根目录（默认 holdings 同级的 daily-reports/）")
        p.add_argument("--date", default=dt.date.today().isoformat())
        p.add_argument("--session", choices=["pre", "noon", "post", "quick"], default="pre")
        p.add_argument("--allow-degraded", action="store_true")
        p.add_argument("--brief", default="",
                       help="本次只做简列的关注标的，逗号分隔（临时降级；缺省=全部深度分析）")
        if name == "fetch":
            p.add_argument("--no-network", action="store_true")
        if name == "report":
            p.add_argument("--builder", help="当天报告生成脚本路径（兼容旧模式）")
            p.add_argument("--data", help="紧凑卡片数据JSON，走通用渲染器 render_report.py")
            p.add_argument("--html", help="产物 HTML 路径（默认按命名规则）")
    args = ap.parse_args()
    if getattr(args, "brief", ""):
        os.environ["DAILY_BRIEF_TICKERS"] = args.brief
    if args.cmd == "fetch":
        sys.exit(do_fetch(args))
    if args.cmd == "gate":
        sys.exit(do_gate(args))
    if args.cmd == "report":
        sys.exit(do_report(args))


if __name__ == "__main__":
    main()
