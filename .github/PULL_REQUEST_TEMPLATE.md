## 这个 PR 做了什么


## 影响面

- [ ] 只改文档/工程化
- [ ] 改脚本逻辑（已补回归用例）
- [ ] 改门禁（**需在描述里说明理由与前后阈值**）
- [ ] 改报告样式（已跑端到端 `run_daily report` 验证）

## 自检

- [ ] `python -m unittest discover -s tests` 全绿
- [ ] `python scripts/release.py doctor` 全绿
- [ ] 改过受管文件后已跑 `release.py manifest` / `bump`
- [ ] 没有提交 `config/`、`data/`、`.archive/`、任何密钥
