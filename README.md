# ActionScribe｜会议行动项助手

> 本仓库是在 [原始 ActionScribe 项目](https://github.com/shubham333k/ActionScribe) 基础上完成的 Windows 本地复现与飞书适配版本。README 按本仓库现有代码和运行方式编写。

ActionScribe 将会议录音或文字整理成结构化行动项。它使用 Groq 提供的 Whisper API 转写音频，并用 Groq 上的聊天模型提取任务、评估优先级。用户可以查看结果，并选择将任务写入飞书多维表格或发送到飞书群机器人。

## 功能

- 支持粘贴会议文字，或上传 MP3、WAV、M4A、OGG、WEBM 音频；上传上限为 25 MB。
- 使用 Groq Whisper Large v3 进行云端转写；无需本地 GPU。
- 由 LangGraph 串联任务提取、优先级评估、格式化和集成分发。
- 按紧急度与影响度评分，生成 1–25 分的优先级及标签。
- 启用飞书多维表格时，每次提交都会在配置的 Base 中创建新数据表并写入本次任务。
- 启用飞书群通知时，发送包含会议名称、日期和行动项的摘要。
- 多维表格和群通知共用前端的会议名称与日期；关闭两项集成时可只做分析。

## 系统架构

~~~mermaid
flowchart LR
    U[用户] --> UI[Streamlit 中文界面]
    UI --> API[FastAPI]
    API -->|音频输入| W[Groq Whisper]
    API -->|转写文本或会议文字| E[Extractor]
    W --> E
    E --> P[Prioritizer]
    P --> F[Formatter]
    F --> D[Dispatcher]
    D -->|启用时| B[飞书多维表格 API]
    D -->|启用时| C[飞书群机器人 Webhook]
    D --> API
    API --> UI
~~~

LangGraph 使用共享的 PipelineState 保存会议文字、会议名称和日期、集成开关、各阶段任务及错误。流程按 Extractor → Prioritizer → Formatter → Dispatcher 顺序运行。Dispatcher 先处理多维表格，再处理群通知；一项集成失败不会阻止另一项继续执行。

## 主要目录

~~~text
agents/                 LangGraph 状态、节点和任务处理 Agent
api/main.py             FastAPI 接口与请求前置校验
integrations/feishu.py  飞书多维表格及群机器人适配器
transcriber/            Groq Whisper 音频转写
ui/app.py               Streamlit 前端
tests/                  API、Agent、工作流和集成测试
sample_meeting.mp3      项目自带音频样例
.env.example            本地环境变量模板
REPRODUCTION.md         中文复现记录、联调权限及测试边界
~~~

## 环境要求

- Windows 10/11；推荐 Python 3.11。
- Groq API Key 用于会议文字分析和音频转写。
- 飞书集成为可选项；不配置时仍可运行会议分析和查看结果。
- Groq 请求由 Groq 账户计费规则管理。开始真实分析或转写前，请确认账户设置。

## 安装

在 PowerShell 中执行：

~~~powershell
git clone https://github.com/Liuzilu0913/ActionScribe.git
Set-Location ActionScribe

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

Copy-Item .env.example .env
notepad .env
~~~

在本机的 .env 文件中填写需要使用的凭据。至少需要配置 Groq：

~~~dotenv
GROQ_API_KEY=在此填写你自己的Groq密钥
GROQ_CHAT_MODEL=openai/gpt-oss-20b
~~~

不要把真实密钥写进 README、源码或提交记录。仓库的 .gitignore 已忽略 .env；提交前仍应检查 Git 状态和提交差异。.env.example 仅包含空配置项和非敏感默认值。

## 启动

在两个独立的 PowerShell 窗口中，分别从项目根目录运行。

窗口一：启动 FastAPI：

~~~powershell
.\.venv\Scripts\Activate.ps1
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
~~~

窗口二：启动 Streamlit：

~~~powershell
.\.venv\Scripts\Activate.ps1
streamlit run ui/app.py --server.address 127.0.0.1 --server.port 8501
~~~

打开以下地址：

- Streamlit 页面：http://localhost:8501
- 后端健康检查：http://localhost:8000/api/health
- FastAPI 接口文档：http://localhost:8000/docs

如果更改后页面没有更新，请确认当前使用的是本项目目录中的进程，并重启旧的 Uvicorn 服务。开发启动命令包含 --reload。

## 飞书多维表格

在飞书开放平台创建自建应用，并为应用开通多维表格管理权限。将应用添加为目标多维表格 Base 的可访问应用或协作者。需要的本机配置项为：

~~~dotenv
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_BITABLE_APP_TOKEN=
~~~

其中 FEISHU_BITABLE_APP_TOKEN 是 Base 的标识。程序不再依赖固定 table_id：每次启用写入时，都会在这个 Base 中创建新表，并用创建接口返回的 table_id 写入记录。表名基于 YYYY-MM-DD_会议名称；若重名则递增添加 _1、_2 等后缀。旧表和旧记录不会被更新或删除。

每张表会按 FEISHU_FIELD_* 配置创建任务、负责人、截止日期、优先级、分数、复核状态和原文摘录等字段。没有自定义映射时，使用 .env.example 中的默认列名。评分列为数字类型，其余字段为文本类型。

需要为自建应用开通 bitable:app 权限，并确保应用身份能够访问目标 Base。具体审批和发布流程以飞书开放平台及应用后台的权限提示为准。

结果页面会显示多维表格写入状态和实际写入数量。根据本项目界面设置，页面不显示本次新建数据表名称和链接；需要查看新表时，请在飞书 Base 左侧的数据表列表中查找。

## 飞书群机器人

在飞书群中添加自定义机器人，把 Webhook 地址写在本机 .env：

~~~dotenv
FEISHU_BOT_WEBHOOK_URL=
FEISHU_BOT_SECRET=
FEISHU_BOT_KEYWORD=
~~~

Webhook 是必需项；如果机器人启用了签名校验，则填写 FEISHU_BOT_SECRET；如果要求自定义关键词，则填写 FEISHU_BOT_KEYWORD。密钥和 Webhook 地址不得提交到 Git。

群消息包含会议行动项数量、会议名称、日期，以及每项任务的优先级、负责人和截止日期。若同时启用了多维表格且本次写入全部成功，消息中会附上本次新表链接；若写入失败，消息会说明实际写入数，不会附成功链接。只启用群通知时不会创建表或附加旧链接。

## 会议元数据与错误处理

启用多维表格或群通知中的任一项时，会议名称和日期必填。名称会去除首尾空格；日期必须为有效的 YYYY-MM-DD。后端会在调用 Groq 或飞书之前重复校验。两项集成都关闭时，会议名称和日期可以留空。

多维表格名称遵循飞书的名称限制。对于不能用于表名的字符，接口会在调用模型前拒绝请求；过长名称会按限制截短。记录写入失败时，接口和页面会返回实际成功/失败数量。建表请求超时且无法确认是否创建时，应先检查 Base 中的数据表列表再重试。

## API 接口

- GET /api/health：后端健康状态。
- GET /docs：交互式 FastAPI 文档。
- POST /api/v1/transcribe：接收音频并返回转写文本。
- POST /api/v1/pipeline/process：接收会议文字或音频、集成开关和会议元数据，返回行动项与集成结果。

## 测试与复现记录

在虚拟环境中运行现有测试：

~~~powershell
pytest -q
~~~

此前记录的完整测试套件为 36 项通过。真实 Groq 与飞书联调的范围、Mock 覆盖项、权限问题处理和尚未覆盖的完整页面端到端流程，见 [REPRODUCTION.md](REPRODUCTION.md)。

本地复现使用 Python 虚拟环境。仓库包含 Docker 相关文件，但当前复现未验证 Docker Compose 启动路径。

## 许可证

本项目包含的许可证见 [LICENSE](LICENSE)。
