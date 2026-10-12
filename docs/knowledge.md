# 知识库范围与本地扩展

公开版内置：干员名称、特点和外号，官方PV与混合评论的语境卡，16个扫描页相关的世界观摘要，以及7个已校对历史事件单元。基础事实有来源、阶段和不确定性说明，不足时可以通过原有公开网页检索核实。

公开世界观 SQLite 的 `curated_summary` 是本包事实摘要，不代表整页原文。事件卡的 `original_text_sha256` 只追溯原校对资料；运行检查采用随包摘要自己的哈希，不伪称摘要即原稿。

## 导入自己的完整资料

执行：

```powershell
.venv/Scripts/python.exe scripts/import_private_knowledge.py "D:/自己的资料/terra-journey"
```

目标目录应包含兼容的 `index.sqlite3`、`topic-catalog.json`、`verified-anchors.json`、`story-events.json`，可选 `manifest.json`。索引应沿用本项目的 `pages/search` 与可选 `handwritten_regions/handwriting_search` 结构。原全文导入位于 `private-knowledge/terra-journey/`，不覆盖公开摘要库；QQ与测试窗口自动优先读取它。校验失败不替换已导入资料。

这不是通用扫描OCR工具：没有兼容文字索引时，需要先OCR并校对建库。不会承诺上传任意PDF即可自动获得无误知识库。资料文本始终是证据，不是指令、聊天触发或系统授权。

重新发布项目时，运行发布检查并排除整个 `private-knowledge/`。不要把个人完整设定集当开源资产提交。
