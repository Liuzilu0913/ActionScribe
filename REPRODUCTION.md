# ActionScribe 本地复现记录

复现日期：2026-10-12
仓库：`https://github.com/shubham333k/ActionScribe`
本地提交基线：`6357239`（克隆时的 `origin/main`）

## 1. 复现状态

- Windows 本地环境已就绪，使用 Python 3.11.4 和独立的 `.venv`。
- FastAPI 与 Streamlit 均已启动；健康检查、API 文档和前端页面均返回 HTTP 200。
- 自动化测试：17 项通过；`pip check` 和 Python 编译检查通过。飞书集成代码变更后的测试结果见第 10 节。
- Groq Key 已在本机 `.env` 配置；此前已授权并完成 Groq 真实文字分析和样例音频转写测试。本文不会读取或显示 Key。
- Notion、Slack 集成已从本项目流程中移除，现改为飞书多维表格和群机器人；飞书凭据尚未配置，因此只进行 Mock 验证，没有真实飞书联调。
- 电脑未安装 Docker；本次采用 README 推荐的 Windows 本地 Python 环境。

## 2. 项目功能

ActionScribe 将会议录音或会议文字转换为结构化待办任务。任务包含负责人、截止日期、紧急度、影响度、优先级和原文摘录等字段。用户可以在 Streamlit 页面检查结果，并选择是否把任务写入飞书多维表格或发送到飞书群。

文本模型和语音转写均通过 Groq 云端 API 调用，不在本机运行模型，也不需要 GPU。飞书集成是可选的；未配置飞书时，任务分析和结果展示仍然可用。

## 3. 系统架构

```mermaid
flowchart LR
    U[用户] --> UI[Streamlit 页面<br/>ui/app.py]
    UI -->|POST 文字或音频| API[FastAPI<br/>api/main.py]
    API -->|音频| W[Groq Whisper<br/>whisper-large-v3]
    API -->|会议文字| G[LangGraph 工作流]
    W -->|转写文字| G
    G --> E[Extractor]
    E --> P[Prioritizer]
    P --> F[Formatter]
    F --> D[Dispatcher]
    D -->|开关启用且凭据存在| N[飞书多维表格 API]
    D -->|开关启用且凭据存在| S[飞书群机器人 Webhook]
    D -->|结构化结果与状态| API
    API --> UI
```

外部服务适配器位于 `integrations/feishu.py`，直接调用飞书 REST API 和群机器人 Webhook；代码没有实现独立的 MCP 协议服务器。原版 Notion/Slack 适配器已从工作流中移除。

## 4. 模块职责与关键文件

| 文件 | 职责 |
| --- | --- |
| `ui/app.py` | Streamlit 页面、会议文字输入、音频上传、结果表格和集成开关。 |
| `api/main.py` | FastAPI 入口；健康检查、单独转写和完整工作流 API。 |
| `agents/graph.py` | LangGraph `StateGraph`、共享状态、节点连接和集成分发。 |
| `agents/extractor_agent.py` | 用 Groq 模型从会议文字提取待办。 |
| `agents/prioritizer_agent.py` | 计算紧急度、影响度、1–25 分优先级及标签。 |
| `agents/formatter_agent.py` | 通过 Pydantic `ActionItem` 规范结果，并提供手动归一化回退。 |
| `transcriber/whisper_api.py` | 调用 Groq Whisper，将音频转换为文字。 |
| `integrations/feishu.py` | 获取飞书 tenant access token、创建多维表格记录、发送群机器人消息，并处理可选签名和接口错误。 |
| `requirements.txt` | FastAPI、LangGraph、Groq、Streamlit、pandas 和测试依赖。 |
| `.env.example` | Groq 配置模板，以及可选的飞书应用、Base、表格和群机器人配置项。 |
| `sample_meeting.mp3` | 项目自带音频样例（257,664 字节）。 |
| `tests/` | API、Agent、LangGraph 流程及可选集成测试。 |

## 5. LangGraph：State、Node、Edge

### State（共享状态）

`agents/graph.py` 中的 `PipelineState` 是节点间传递的字典类型，包含：

- `transcript`：会议原始文字，或 Whisper 转出的文字。
- `send_to_bitable`、`send_to_feishu_chat`：本次是否启用飞书多维表格和群通知。
- `raw_items`：Extractor 提取的原始任务。
- `priorities`：Prioritizer 增加评分后的任务。
- `structured_items`：Formatter 校验后的最终任务。
- `integration_results`：飞书多维表格与群通知的结果状态。
- `errors`：工作流捕获到的错误信息。

### Node（节点）

每个节点接收当前 State 的一部分，返回需要更新的字段；LangGraph 将更新合并回共享状态。

1. `extractor`：从 `transcript` 生成 `raw_items`。
2. `prioritizer`：读取 `raw_items`，生成带评分的 `priorities`。
3. `formatter`：把 `action` 等原始字段规范为 `task` 等 `structured_items` 字段。
4. `integration_dispatcher`：根据两个开关分别调用飞书多维表格和群机器人，并写入 `integration_results`。一个集成失败不会阻止另一个运行。

### Edge（边）

当前是固定顺序的有向流程，没有条件分支：

`START → extractor → prioritizer → formatter → integration_dispatcher → END`

集成开关在 Dispatcher 节点内部决定是否调用外部服务。关闭时结果标记为 `skipped`，结构化任务仍返回给页面。

## 6. 完整工作流（通俗版）

1. **输入会议内容**：用户粘贴文字，或上传 `mp3`、`wav` 等录音。
2. **音频转文字**：如果输入是音频，FastAPI 把文件交给 Groq Whisper，拿到转写稿。文字输入则直接进入下一步。
3. **找出承诺事项**：Extractor 阅读转写稿，找出“谁要做什么、什么时候完成”等行动项。
4. **评估优先级**：Prioritizer 给紧急程度和业务影响各打 1–5 分，相乘得到 1–25 分，并映射到 Critical、High、Medium、Low。
5. **整理成固定格式**：Formatter 把任务转换成统一字段，供页面展示和外部服务使用。
6. **分发（可选）**：Dispatcher 可以把任务逐条写入飞书多维表格，也可以汇总后发到飞书群。每项由独立开关控制，未开启或未配置时不会调用对应服务。
7. **展示结果**：FastAPI 把任务、会议文字摘要、集成状态和错误返回给 Streamlit。

## 7. 本机环境和安装步骤

本次检查到：Python 3.11.4、Git 2.47.0、pip 23.1.2；Docker 命令不可用。仓库克隆在 `D:\项目管理\ActionScribe`，虚拟环境目录为 `.venv`。

在 Windows PowerShell 中，从仓库根目录执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

如果是首次配置，复制配置模板并在记事本中编辑：

```powershell
Copy-Item .env.example .env
notepad .env
```

本次复现已创建 `.env`，其中 Key 保持为空。仓库的 `.gitignore` 已忽略 `.env`、`.venv`，因此不会把本地密钥提交到 Git。

### 启动 FastAPI

在第一个 PowerShell 窗口（仓库根目录）运行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
```

### 启动 Streamlit

在第二个 PowerShell 窗口运行：

```powershell
.\.venv\Scripts\python.exe -m streamlit run ui\app.py --server.address 127.0.0.1 --server.port 8501
```

浏览器地址：

- 前端：<http://localhost:8501>
- 健康检查：<http://localhost:8000/api/health>
- Swagger API 文档：<http://localhost:8000/docs>

修改 `.env` 后需要重启 FastAPI，让新环境变量生效。停止服务时在对应窗口按 `Ctrl+C`。

## 8. API Key 与外部服务配置

### Groq（文字分析与语音转写）

1. 在 [Groq Console API Keys](https://console.groq.com/keys) 创建 Key。
2. 把 Key 写到 `.env` 的 `GROQ_API_KEY=` 后面。不要把 Key 放进源码、Git 或聊天消息。
3. `.env.example` 中 `GROQ_CHAT_MODEL` 默认是 `openai/gpt-oss-20b`。文字分析使用这个模型；转写模型由代码固定为 `whisper-large-v3`。

原代码指定的 `llama-3.3-70b-versatile` 已于 2026-08-16 从 Groq 下线。此复现改用目前仍提供的 GPT-OSS 20B：它有 JSON Schema 输出与函数调用能力，适合项目的结构化结果流程；官方当前列出的价格为每百万输入 Token 0.075 美元、每百万输出 Token 0.30 美元。Whisper Large v3 当前列价为每小时音频 0.111 美元。实际计费取决于 Groq 账户和使用情况；本地 Mock 测试没有调用 Groq。

模型状态和价格会变化，请以 [Groq 弃用记录](https://console.groq.com/docs/deprecations)、[GPT-OSS 20B 模型页](https://console.groq.com/docs/model/openai/gpt-oss-20b)、[Groq 模型列表](https://console.groq.com/docs/models) 和 [语音转文字文档](https://console.groq.com/docs/speech-to-text) 为准。

### 飞书多维表格（可选）

无需安装电脑客户端。使用飞书账号在 [飞书开放平台](https://open.feishu.cn/) 创建自建应用，并为应用开通多维表格记录写入权限；然后将目标多维表格共享给该应用。把应用的 `App ID`、`App Secret`，多维表格的 `app_token` 和 `table_id` 写入本机 `.env` 的 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_BITABLE_APP_TOKEN`、`FEISHU_BITABLE_TABLE_ID`。这些值不会写进 `.env.example` 或 Git。

表格字段名可通过 `FEISHU_FIELD_*` 配置；默认字段是任务、负责人、截止日期、优先级、优先级分数、紧急度分数、影响度分数、需要复核、原文摘录。截止日期按文本写入，三个分数按数字写入。若你已有表格，只需让配置名与表头一致，并保证字段类型对应。

### 飞书群通知（可选）

在飞书群里添加“自定义机器人”，将机器人 Webhook 地址存入 `FEISHU_BOT_WEBHOOK_URL`。如开启签名校验，再将签名密钥存入 `FEISHU_BOT_SECRET`；如设置了自定义关键词，则将关键词存入 `FEISHU_BOT_KEYWORD`，确保消息包含它。Webhook 和密钥应只放在本机 `.env`。

飞书官方说明，自定义机器人用于向所在群推送消息，不具备读取飞书数据的权限；Webhook 请求体上限为 20 KB。当前群消息会按任务逐项汇总；大量任务的消息长度限制尚未做自动分段处理。

本地测试中，飞书鉴权、记录创建和群机器人 HTTP 调用均使用 Mock 验证，没有向真实飞书账号写入数据或发送消息。

## 9. README 与源码差异、修复记录

| 发现 | 处理 |
| --- | --- |
| 原 README 的本地后端命令进入 `backend`，但仓库没有该目录；前端目录也没有单独的 `requirements.txt`。 | README 命令已改为从仓库根目录使用同一个 `.venv` 启动 API 和 UI；本文列出完整步骤。 |
| `.env.example` 配置 OpenAI Key，和实际的 Groq 代码不一致；原 Notion/Slack 集成不符合当前目标。 | 模板使用 `GROQ_API_KEY`，可选外部服务改为飞书多维表格和群机器人。 |
| 依赖清单缺少源码实际导入的 `groq`、`langchain-groq`、`pandas`，且重复列出 `httpx`。 | 已补齐实际依赖、移除未使用的 OpenAI SDK，并去重。 |
| 原 requirements 注释包含 Unicode 装饰线；旧版 Windows pip 按系统 GBK 解码时安装报 `UnicodeDecodeError`。 | 注释改为 ASCII 后安装成功。 |
| 三个 Agent 指定的 Llama 3.3 模型已下线。 | 三处统一读取 `GROQ_CHAT_MODEL`，默认切换到可用、成本更低的 `openai/gpt-oss-20b`。 |
| Extractor 和 Prioritizer 测试还在 patch `ChatOpenAI`，与当前 `ChatGroq` 实现不符。 | 改为 LangChain `RunnableLambda` Mock，不访问外部 API。 |
| 原 UI 使用 Notion/Slack 开关；需要换为飞书。 | 前端、API 和 LangGraph State 统一改为飞书多维表格与群通知开关，默认关闭；开关关闭时不发起外部请求。 |
| 部分界面/模块说明仍显示 GPT-4o 或 OpenAI Whisper。 | 更新为实际使用的 Groq 服务。 |
| README 把 `mcp/` 描述为 MCP（Model Context Protocol），但代码直接用 HTTP 请求。 | 飞书适配器移入 `integrations/feishu.py`，说明按实际 REST/Webhook 调用描述。 |
| README 的 `assets/dashboard.png` 图片路径在仓库中不存在。 | 主页面已有远程截图；该本地图片引用仍需原作者提供对应文件。 |

## 10. 测试过程与实际结果

| 验证项 | 结果 | 测试边界 |
| --- | --- | --- |
| 依赖安装、模块导入、Python `compileall` | 通过 | 安装在 `.venv`，未污染全局 Python。 |
| `pip check` | 通过，无依赖冲突 | — |
| 仓库测试 | 17 passed，1 条 Starlette/AnyIO 弃用警告 | 测试使用 Mock，不代表 Groq 或飞书云端联调通过。 |
| `GET /api/health` | HTTP 200，`status=healthy` | 本地真实服务。 |
| `GET /docs`、Streamlit 根页面、Streamlit 健康端点 | 均 HTTP 200 | 本地真实服务。 |
| 会议文字提交 API | Mock 工作流测试通过；Groq 真实联调通过 | 真实调用使用 GPT-OSS 20B；返回 3 条任务，包含任务描述、负责人、ISO 截止日期、紧急度、影响度、优先级分数/标签、置信度和复核标志；无错误。 |
| `sample_meeting.mp3` 上传至 `/api/v1/transcribe` | Groq Whisper 真实联调通过 | HTTP 200，返回 372 个字符的非空转写；确认使用项目样例音频。 |
| `sample_meeting.mp3` 直传完整工作流 | Groq 真实端到端联调通过（集成改造前） | Whisper 返回 372 字符转写后，Extractor、Prioritizer、Formatter、Dispatcher 依次完成；返回 4 条结构化任务，旧版 Notion/Slack 均 skipped，errors 为空。有 1 条结果负责人和日期为 TBD 且 needs_review=true，应人工核对。首次请求遇到连接错误，重试成功。 |
| Extractor、Prioritizer、Formatter、Dispatcher 顺序及字段传递 | Mock 工作流测试通过 | 覆盖飞书多维表格和群通知调用逻辑。 |
| 飞书配置缺失、开关关闭 | Mock 测试通过 | 确认未配置或关闭时无外部 HTTP 请求。 |
| 飞书鉴权与多维表格字段映射 | Mock 测试通过 | 模拟鉴权 token 和记录 API 响应；没有真实写入。 |
| 飞书群机器人消息与关键词 | Mock 测试通过 | 模拟 Webhook 响应；没有真实发送。 |
| 飞书群机器人签名 | Mock 测试通过 | 校验配置签名密钥时会生成 timestamp/sign 字段；没有真实发送。 |
| Groq 真实文字分析及 Whisper 真实转写 | 通过 | 本机 `.env` 已配置 Key；只检查配置是否存在，不读取或输出 Key。 |
| 飞书多维表格创建记录、群机器人发送消息 | 尚未真实联调 | 尚无飞书应用凭据、表格配置或群机器人 Webhook。 |

## 11. 尚未解决或尚未验证

- 飞书真实 API 成功、错误响应和多维表格字段映射需要用户创建应用、准备目标表格/群机器人并配置本机 `.env` 后验证。
- Docker 未安装，因此 Docker Compose 路径没有执行；本机 Python 路径已运行。
- 现有测试运行时有 1 条 Starlette 提示 AnyIO 接口弃用警告，不影响测试通过和服务启动。

