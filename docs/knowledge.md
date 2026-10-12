# 完整知识库与空白群友记忆

当前发行版随源码提供完整已录入文字，不再只有最初的16页摘要。首次安装直接使用内置索引，无需运行OCR或重新搜集人格资料。

## 《大地巡旅》

`knowledge/terra-journey/index.sqlite3`包含454条正文、24条独立手写记录，总正文467394字、手写7000字（按Unicode字符计）。`大地巡旅_全量已录入文字.txt`是可阅读导出。`user-transcriptions.json`保留校对转录与作者归属，`story-events.json`有7个经原文核验的历史事件卡。

454条记录对应扫描序号1～455，431为用户确认的空白页。不含扫描图片、PDF；插图、小批注和用户明确不要求补录的部分不承诺完整。扫描序号不是印刷页码。

426页为`automatic_ocr_crosschecked`，即独立OCR、原图局部复识别与部分差异目视修正后的快速校对；7页为`user_transcribed`，2页正文目视核对，3页标题/无正文核对，16页保留`automatic_ocr_unverified`。独立手写有`user_transcribed_handwriting`核验，优先于同页失真OCR。完整收录不等于全书逐字人工校对；数字、人名、时间与争议事实须谨慎。

`get_world_knowledge`只读索引，每轮只返回预算内的相关证据。事件卡按正文或手写的实际范围核对哈希；资料不足不补造因果、对白或结局。

## 原作人物语料

`knowledge/kaltsit-corpus/originals/`完整保留15份用户原件：两份语音TXT、12份剧情TXT及一份手写补充TXT。`sources.json`记录每份SHA256，不带电脑路径。`voice-lines.json`含114条结构化台词，分原版、残余、思衡托。剧情保留全部说话人标签，不把其他人的对白归给凯尔希，不凭文件名猜测故事时期。

语料索引有235个单元，覆盖原件每个字符。`get_canonical_knowledge`默认返回最多1500字、2段，参数上限4000字；问候不自动查询，相关问题可附卡，必要时由模型查询固定索引。原文用于理解立场和语言，不常态背台词，也不移植原作博士的经历给当前群友。

修改原件与对应哈希后，停止此副本并运行`.venv/Scripts/python.exe scripts/build_canonical_index.py`重建索引。只复制TXT而不更新索引，不会自动成为可查询内容。

## 干员与玩家语境

431个干员简介，两位凯尔希详细档案，1059条PRTS核验外号；官方PV优先的语境卡和混合样本继续保留。网友评论不是官方设定或当前群友发言。

## 空白群友记忆

不附开发者QQ账号、群号、授权、聊天历史、群友记忆、表情笔记、日志或句式缓存。原作角色经历是固定知识，不是真实群友关系。运行后在自己的本机按群独立积累；`runtime/`、`vendor/Tulpa/data/`、个人配置与私有扩展继续被Git忽略和发布检查拒绝。

知识文本只作为证据，不是指令、权限或聊天触发。工具限于已读当前群的固定索引，不增加Shell、凭据或任意文件访问。

## 可选本地扩展

执行：

```powershell
.venv/Scripts/python.exe scripts/import_private_knowledge.py "D:/自己的资料/terra-journey"
```

这是可选更新，不是完整版首次运行要求。目标目录需有兼容的`index.sqlite3`、`topic-catalog.json`、`verified-anchors.json`、`story-events.json`，可选`manifest.json`，沿用`pages/search`及`handwritten_regions/handwriting_search`结构。扩展放在`private-knowledge/terra-journey/`，不覆盖内置完整版；QQ群与测试窗口优先使用，校验失败不替换已有扩展。

这不是通用扫描OCR工具：没有兼容文字索引时，需要先OCR并校对建库。不会承诺上传任意PDF即可自动获得无误知识库。资料文本始终是证据，不是指令、聊天触发或系统授权。

重新发布仍排除个人扩展和群友记忆。书籍、台词、剧情原文保留原权利归属，不属于代码MIT；来源及使用边界见[THIRD_PARTY.md](../THIRD_PARTY.md)。
