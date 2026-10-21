#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""daily-portfolio-analysis 定时任务蓝绿重建"操作单"生成器。

重要约束：cron 的 list/create/delete 是 agent 工具，纯 Python 脚本无法直接调用。
本脚本只负责把"该建什么、怎么识别旧的、哪些绝不能动、按什么顺序"固化成一份
确定性操作单；实际增删由 agent 按 BOOTSTRAP.md 与本操作单执行，不允许自由发挥。

子命令：
  plan      打印《重建操作单》（标题/schedule/模板路径/识别与保护规则/步骤）
  dry-run   只读自检：模板齐全、首句标题对应、ENG 指纹一致（不删改任何 cron）
"""
import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ENG = SCRIPT_DIR.parent
TPL = ENG / "assets/cron-templates"

TARGETS = [
    {"key": "pre", "title": "盘前持仓报告", "schedule_type": "cron",
     "schedule": "30 8 * * 1-5", "template": "pre.md"},
    {"key": "noon", "title": "盘中半日总结", "schedule_type": "cron",
     "schedule": "0 12 * * 1-5", "template": "noon.md"},
    {"key": "post", "title": "盘后总结与美股前瞻", "schedule_type": "cron",
     "schedule": "0 20 * * 1-5", "template": "post.md"},
]
# 绝不能被重建误伤的任务（标题精确匹配）
PROTECT_TITLES = ["周度复盘导师", "每日健身训练报告"]


def engine_version():
    vf = ENG / "VERSION.json"
    if vf.exists():
        return json.loads(vf.read_text(encoding="utf-8")).get("version")
    return None


def template_path(t):
    return TPL / t["template"]


def validate_templates():
    errs = []
    for t in TARGETS:
        p = template_path(t)
        if not p.exists():
            errs.append(f"缺模板 {p}")
            continue
        text = p.read_text(encoding="utf-8")
        if not text.strip():
            errs.append(f"模板为空 {p.name}")
            continue
        first = text.strip().splitlines()[0]
        if f"「{t['title']}」" not in first:
            errs.append(f"{p.name} 首句标题不是「{t['title']}」：{first[:40]}")
    return errs


def build_plan():
    return {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "engine_version": engine_version(),
        "principle": "标准只在 ENG；cron 极薄只触发；蓝绿先建后删；幂等。",
        "protect_titles": PROTECT_TITLES,
        "match_old_rule": (
            "list_cron_jobs 后，仅把【标题严格等于 targets.title 且 schedule_type=cron "
            "且运行环境=云电脑】的任务识别为待替换旧任务；protect_titles 与任何其他任务"
            "一律不动。同标题可能有多个时，用 cron_job_id 区分新旧，不凭标题删除。"),
        "targets": [
            {**t, "template_path": str(template_path(t)),
             "query_instruction": "create_cron_job 的 query 必须逐字等于该模板文件全文"}
            for t in TARGETS
        ],
        "steps": [
            "1) list_cron_jobs(enable=true)，按 match_old_rule 记录旧任务的 cron_job_id 集合 OLD。",
            "2) 对每个 target 调 create_cron_job(title, schedule_type=cron, schedule, enable=true, "
            "query=模板全文)，记录新 cron_job_id 集合 NEW。",
            "3) 再次 list 自检：NEW 中每个任务 schedule 正确、next_trigger_time 合理；"
            "确认 OLD 与 NEW 不相交。",
            "4) 跑 release.py doctor（ENG/RT 指纹 + 测试全绿）与 redeploy.py dry-run。",
            "5) 自检全部通过后，对 OLD 中每个 id 调 delete_cron_job；NEW 保留。",
            "6) 终检 list：恰好存在 3 个目标任务（标题+schedule 正确），输出《重建回执》。",
        ],
        "rollback": (
            "若 create 后自检/doctor 不通过：不要 delete OLD；删除本次 NEW，保留旧任务，"
            "并 present《重建需人工确认说明》。若环境不允许 create/delete，同样不制造半吊子状态。"),
        "idempotent": "若 list 发现 3 个任务已是目标版本（query 与模板一致），不重复创建，仅出回执。",
    }


def cmd_plan():
    plan = build_plan()
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


def cmd_dry_run():
    print("[redeploy] dry-run 只读自检（不删改任何 cron）")
    errs = validate_templates()
    if errs:
        for e in errs:
            print("  [X]", e)
        return 1
    print("  [OK] 三份模板齐全、非空、首句标题对应")
    rc = subprocess.run([sys.executable, str(SCRIPT_DIR / "release.py"), "verify",
                         "--target", "ENG"]).returncode
    if rc != 0:
        print("  [X] ENG 指纹与 MANIFEST 不一致：先 release.py bump/manifest。")
        return 1
    print("  [OK] ENG 指纹一致（版本 %s）" % engine_version())
    print("  [OK] 可按 plan 的 steps 执行蓝绿重建。")
    return 0


def main():
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="cron 蓝绿重建操作单")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("plan")
    sub.add_parser("dry-run")
    args = ap.parse_args()
    sys.exit(cmd_plan() if args.cmd == "plan" else cmd_dry_run())


if __name__ == "__main__":
    main()
