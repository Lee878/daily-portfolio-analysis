# 贡献指南

这个项目的核心价值是**门禁不可绕过**。任何改动都不能削弱它。

## 三条硬规则

1. **不放宽门禁**
   证据门阈值（覆盖率 50% / 70%）、新闻条数与来源族、多空不同源、P4 不得单独成论、
   报告门引用校验——一律不得为了让某次报告通过而调低。要改必须先有讨论与版本记录。

2. **每个 bug 配一条回归用例**
   修完 bug 在 `tests/test_regressions.py` 加一项，能复现原始缺陷。
   `python -m unittest discover -s tests` 必须全绿（当前 197 项）。

3. **改受管文件后重算指纹**
   受管文件 = `SKILL.md`、`README.md`、`LICENSE`、`pyproject.toml`、`CHANGELOG.md`、
   `scripts/*.py`、`references/*.md`、`assets/**`、`tests/*.py`。

   ```bash
   python scripts/release.py manifest     # 只是改内容
   python scripts/release.py bump minor   # 发版（同步 VERSION / pyproject / SKILL）
   ```

   否则 `doctor` 会报漂移，定时任务第一步就会停。

## 提交信息

```
feat(scope): 一句话说清做了什么
fix(scope): 修了什么
docs: 文档
test: 测试
chore: 工程/杂项
```

## 本地开发流程

```bash
python -m pip install -e ".[dev]"
ruff check .
python -m unittest discover -s tests -p "test_*.py"
python scripts/release.py doctor
```

## 不要提交的东西

- `config/`（真实持仓、关注库、送达配置：含金额与券商）
- `data/`（报告与证据 JSON：含成本与账户）
- `.archive/`（历史迁移包）
- 任何密钥、邮箱密码、Cookie

`.gitignore` 已经覆盖，提交前请用 `git status` 确认。

## 改渲染器时特别注意

报告门按**行**统计多空独立证据，按 `<div class="card">` 切卡片，按 `<h3>` 认标的。
改模板请读 `references/report-html-template.md` 的"报告门兼容约束"，并跑一次
`python scripts/run_daily.py report` 端到端验证。

## 免责

本项目输出的是研究分析参考，不构成投资建议。任何改动都不应改变这一点。
