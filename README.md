# quant-web

量化市场看板 —— 纯静态网站，供 Cloudflare Pages 部署。

**公开仓库：绝不包含任何个人持仓、成本价等敏感信息。** 数据只有全市场公开行情（代码/名称/现价/涨跌幅/主力资金流向）。

## 文件结构

- `index.html` —— 深色、手机友好的看板页面
- `app.js` —— 拉取 `data/latest.json` 渲染页面
- `gen_webdata.py` —— 从 `quant.db` 生成 `data/latest.json`（本地运行）
- `data/latest.json` —— 最新一日全市场快照（由 gen_webdata.py 生成）

## 数据更新方式

每天收盘后，在本地运行：

```bash
python3 gen_webdata.py
```

该脚本默认取 quant.db 中最新的交易日数据，生成 `data/latest.json`，
再 commit & push 到 main 分支，Cloudflare Pages 自动重新部署。

手动指定日期：`python3 gen_webdata.py --date 2026-10-22`
