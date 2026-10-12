# 凯尔希 QQ 群聊机器人

Windows 源码发行版。使用当前凯尔希·思衡托角色卡，在 QQ 群里接话、看图、检索明日方舟资料，支持自然气泡、按语境 @、引用对象绑定和克制的主动参与。

推理链：**QQ → 独立安装的 OneBot v11 桥接 → 内置 Tulpa MCP 源码 → 本机 Codex CLI → GPT-6 Luna**。

不需要 OpenAI API Key。使用者须登录自己的 Codex 账号并能使用 GPT-6 Luna；仍会消耗该账号的 Codex 额度。模型不可用或额度不足时暂停，不自动切换模型。源码包不是 Windows 成品安装包，不带 QQ 登录态、模型账号或 Python 环境。

## 首次使用

1. 准备 Windows 10/11 x64、Python 3.12或3.13 x64（含`py`启动器）、Node.js LTS；双击 `01-安装依赖.cmd`。缺少前两项时，可在 PowerShell 执行 `./setup.ps1 -InstallPrerequisites` 安装，再重开终端。安装脚本不会启动群回复。
2. 执行 `codex login`，登录自己的账号。CLI 不在 PATH 时，将原生 `codex.exe` 路径填入本机配置的 `codex_path`。项目使用独立 MCP 名称 `kaltsit_bot`，仅在当前模型调用中注入，其他全局连接在该调用中禁用；不写入或替换全局 Codex 配置。若全局已有同名配置则报错停止，避免传输配置合并冲突。[官方 MCP 配置说明](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
3. 独立安装 [NapCat/兼容 OneBot](https://github.com/NapNeko/NapCatQQ)，登录自己的 QQ。按其[配置文档](https://napneko.github.io/config/basic)开启 HTTP 服务与**正向 WebSocket 服务**，仅绑定 `127.0.0.1`；默认示例使用端口 3000/3001，两个服务填写同一个随机 Token，并启用心跳。不要填反向 WebSocket 地址。
4. 双击 `02-配置机器人.cmd`，填写 QQ号、一个或多个群号、OneBot 地址及 Token。程序核验实际登录账号和所在群；输入 `YES` 才为这些群授权接收、看图、发消息，不授予群管理权限。
5. 双击 `07-检查接入.cmd` 检查依赖、QQ 和知识库。实际模型检查需另外执行 `.venv/Scripts/python.exe doctor.py --model-test`，消耗一次模型调用，不向 QQ 发送测试消息。
6. 双击 `03-启动机器人.cmd`。关闭启动窗口不影响后台；保持 QQ 和桥接在线。双击 `05-查看状态.cmd` 看各群状态，`04-停止机器人.cmd` 停止，`08-暂停群回复.cmd` 暂停。暂停完成后再次启动即可恢复，记忆和聊天数据不删除。

首次配置不是只填 QQ 密码就能完成：桥接登录、Codex 登录和本机安装由使用者完成。准备好这些前置条件后，只需配置自己的账号和目标群，不需要编写人格或重建基础知识库。

## 人格与测试

- `prompts/persona_full.txt`：完整角色卡；`prompts/persona_runtime.txt`：每次推理实际使用的卡。
- `skills/kaltsit-dialogue-output/`：发送前整体表达重组。
- `skills/kaltsit-bubble-coherence/`：整组气泡承接及跨轮模板检查。
- 两份 Skill 都在同一次 Luna 生成中指导表达，没有第二轮润色模型，也不代表微调权重或保证每次都完全符合角色。
- 默认 Luna high、Fast 关闭；普通回复 1 条，按独立意思自然分成 2～3 条。@ 按对象交错和切换使用，最多首条，博士称呼位置自由。
- 成功发送的最近 8 次回应用于避免句式重复，不把 UNKNOWN/失败草稿当已说过的话，不跨群混用。
- 双击 `06-人格测试窗口.cmd` 打开文字测试；源码包默认端口 **18883**，用于避免与已有本机测试窗口冲突，可在配置中调整。窗口与群聊使用同一人格、Skill及知识库；测试不发送QQ群消息，历史保存在浏览器本地。

修改运行人格后应停止并重新配置/启动，使 Tulpa 的旧会话快照更新。只改两份表达 Skill 时，停止并重启即可。

## 基础信息库

随包提供干员简要资料、PRTS核验外号映射、舟圈评论语境提炼、泰拉世界观摘要与已校对事件卡。官方事实、评论玩笑和角色改编分别保留来源及边界。

**公开版不是整本《大地巡旅》**：不含扫描图、PDF、全书OCR、完整档案或剧情台词合集。可按 [本地完整资料导入](docs/knowledge.md)添加使用者自己的资料，不需要重新OCR，也不要把导入结果提交GitHub。资料库大小和完整程度不会被伪报为开发者个人版本。

## 多群与数据

- 每个安装目录绑定一个 QQ 账号，可选择 1～8 个群；换账号先停止并重新配置。多个账号使用独立副本和不同端口。
- 每群独立 Worker、话题便签、发送回执、句式缓存和运行日志；默认全部群共享最多 1 个并发模型任务，可配置为 2。
- 每轮只提供近期必要上下文；空闲等待由本机处理，不启动模型。主动发言默认普通候选 0.5%、兴趣候选 1.5%，5分钟冷却、30分钟最多2次；直接叫名、@、引用及真正续聊按既有规则处理。
- 仅配置群的授权连接开放持续群聊；未配置的群不启用。程序核对实际QQ账号，发现换号或HTTP/WS账号不同会停止接收。
- 所有运行文件在 `runtime/` 与 `vendor/Tulpa/data/` 等忽略目录，不随源码发布。必要聊天片段、图片和检索资料仍会发送给模型服务。

## 测试与开发

```powershell
.venv/Scripts/python.exe scripts/run_tests.py
node tests/test_hook.cjs
.venv/Scripts/python.exe scripts/smoke_fake_bridge.py
.venv/Scripts/python.exe scripts/check_cli_transport.py
.venv/Scripts/python.exe scripts/check_release.py
```

回归测试使用合成账号、合成群及模拟OneBot，不调用真实QQ发送，不调用模型。真实跨账号的扫码登录与长时间群聊，需要用户在自己的环境验收；不要把离线测试称为真实 QQ 全链路验收。已验证环境和限制见 [验证报告](docs/validation.md)。

## 上传 GitHub

将此目录的源码内容提交到新仓库即可。未提供自动推送脚本。先运行发布检查；不上传 `.venv/`、`config/config.json`、`runtime/`、私有知识扩展、登录文件或完整使用过的目录。`.gitignore` 只能防止新的误提交，不能清除已提交过的秘密。

本项目新增程序与 Skill 使用 [MIT](LICENSE)；Tulpa源码保留其 [MIT](vendor/Tulpa/LICENSE)。第三方知识素材不因代码许可证而被重新许可，见 [来源与许可](THIRD_PARTY.md)。

当前源码发行版只自动部署所选QQ群的持续回复。Tulpa包含私聊发送等底层接口，但没有在本包配置中启用私聊自动代聊；不要将这一点误称为已实现。也不包含微信自动投放或定时故事任务。
