# corplink-dlp-auto 架构设计文档（v0.1 草案）

> ⚠️ **已归档（2026-07-28）**：本文是 v0.1 开工前的架构草案，使命（对齐模块边界后开始编码）已完成，与现状多处不符（报告已改 CSV、配置改 `config/` 目录、judges/notify/human 未接线、新增 verify/provision 等）。**权威现状请看 [tech_design.md](../tech_design.md)**；本文仅作历史留存，不再维护。

> 本文是「DLP 自动化测试 Agent」的第一版架构稿，目的是让你 review 模块边界、关键接口、目录结构后再开始编码。  
> 所有不确定的点都会标 `TODO(确认)`，编码前我会再来找你确认。

---

## 1. 目标与范围

### 1.1 我们要做什么

一个**基于 AI + GUI 自动化**的 DLP 测试执行器：

- 输入：一份 case 列表（飞连各类 DLP 通道的测试用例）
- 过程：Agent 串行执行每个 case，case 内部支持 `AI 自然语言指令` 和 `Python 硬动作` 混合驱动
- 输出：每个 case 的 `pass/fail/error` + 步骤日志 + 截图 + 断言证据，落到 JSON 报告

### 1.2 为什么不走传统自动化

DLP 的拦截动作横跨 IM、邮件、浏览器上传、本地外发 …… 多通道控件指纹差异大；
传统 selector 适配成本高，**让视觉模型识别画面 + 决策动作**更划算。

### 1.3 第一版不做什么

- 不做并行执行（先串行）
- 不做分布式（单机跑；Mac 和 Windows 各自跑各自的，不做远程编排）
- 不做 case 编辑器/可视化平台（只跑 case）
- 不做模型自训练（只调豆包 1.8 vision）

### 1.4 跨平台目标

- 被测端覆盖 **macOS** 与 **Windows**，运行方式：**同仓库双机器独立运行**（同一份代码 clone 到 Mac 和 Win，各自启动 runner）
- v0.1 只交付 mac 实现，但平台抽象层、目录骨架、case 平台标注、快捷键映射等接口在 v0.1 全部就位，windows 后续补即可
- 平台识别：**默认自动探测，config 可强制覆盖**

---

## 2. 技术背景对照

| 借鉴对象 | 借鉴点 | 我们怎么用 |
|---|---|---|
| OSWorld 的 `mm_agents/doubao_agent.py` | "截图 → 多模态 prompt → 解析 action → 执行 → 进入下一轮"的主循环骨架 | 复刻这套 loop，但执行端在本机 Mac 上而非 VM 内 |
| UI-TARS | 1000×1000 归一化坐标 / Action Space 设计 / 历史压缩策略 | 借鉴坐标系与 action 类型集合，但格式改为结构化 JSON |
| 你本地的 `ai-ui/uitars_run.py` | 截图、坐标换算、pyautogui 执行、中文剪贴板粘贴、history 截断 | **直接迁移并重构**为本仓库的 `core/executor.py` + `core/screen.py` |

---

## 3. 总体分层

```
┌─────────────────────────────────────────────────────────────┐
│  CLI / Runner                  python -m dlp_auto.run cases/ │
└──────────────┬──────────────────────────────────────────────┘
               │
        ┌──────▼──────┐
        │ CaseRunner  │  串行调度、setup/teardown、报告聚合
        └──────┬──────┘
               │ 一个 case
        ┌──────▼─────────────────────────────────────────┐
        │           Case (Python module)                 │
        │  steps = [                                     │
        │     ai("打开飞书的与张三的对话"),               │
        │     hard.drag_file("a.txt", target="chat_box"),│
        │     ai("点击发送"),                             │
        │     assert_visual("出现 DLP 拦截弹窗"),         │
        │     assert_http(api="...", expect={...}),      │
        │  ]                                             │
        └──────┬─────────────────────────────────────────┘
               │
   ┌───────────┴────────────┐
   │                        │
┌──▼──────────┐      ┌──────▼─────────┐
│  AI Agent   │      │  Hard Actions  │  Python 直调 pyautogui /
│ (loop)      │      │ (lib/actions)  │  subprocess / pyperclip / ...
└──┬──────────┘      └────────────────┘
   │
┌──▼─────────────┐  ┌─────────────┐  ┌──────────────┐
│ LLMProvider    │  │  Executor   │  │  Screen      │
│ (Ark Doubao)   │  │  (do_action)│  │ (capture)    │
└────────────────┘  └──────┬──────┘  └──────┬───────┘
                           │                │
                       ┌───▼────────────────▼──┐
                       │   Platform Adapter    │
                       │  (mac / windows ...)  │
                       └───────────────────────┘
```

五个核心可替换抽象：
- `LLMProvider`：哪家模型、哪种协议
- `ActionExecutor`：动作怎么落到操作系统（pyautogui / 远程 VM / Android adb...）
- `Platform`：屏蔽 mac / windows 在快捷键、剪贴板、路径、app 启动方式上的差异
- `Judge`：怎么判断步骤/case 通过
- `CaseLoader`：case 用什么格式承载

---

## 4. 目录结构

```
corplink-dlp-auto/
├── docs/
│   └── architecture.md                # 本文档
├── dlp_auto/                          # 主包名
│   ├── __init__.py
│   ├── run.py                         # CLI 入口：python -m dlp_auto.run
│   ├── config.py                      # 配置加载（环境变量 + config.yaml）
│   │
│   ├── core/                          # 核心运行时（与 DLP 业务无关）
│   │   ├── agent.py                   # Agent 主循环：感知-决策-执行
│   │   ├── executor.py                # 动作执行器：JSON action -> pyautogui（含 mod 键映射）
│   │   ├── screen.py                  # 截图 / 坐标换算（处理 Retina 缩放等）
│   │   ├── parser.py                  # 模型输出 JSON 解析 & 校验
│   │   ├── history.py                 # 多轮 history 管理
│   │   └── platform.py                # 平台探测 + Platform 枚举 + 配置覆盖
│   │
│   ├── llm/                           # 模型 Provider 抽象层
│   │   ├── base.py                    # LLMProvider 抽象类
│   │   ├── ark_doubao.py              # 火山方舟 OpenAI 兼容（豆包 1.8）
│   │   └── prompts.py                 # System prompt + Action JSON Schema
│   │
│   ├── judges/                        # 断言抽象（可在 case 中混用）
│   │   ├── base.py                    # Judge 抽象类
│   │   ├── visual.py                  # AI Visual Judge（再走一次模型）
│   │   ├── file_log.py                # 本地日志 / 文件存在性检查（路径走 platform 配置）
│   │   └── http.py                    # HTTP 接口回查
│   │
│   ├── actions/                       # 硬动作库（按平台分包 + 统一门面）
│   │   ├── __init__.py                # 门面：按 CURRENT_PLATFORM 自动路由到 _mac / _windows
│   │   ├── _common/                   # 跨平台通用部分（纯 Python、无系统依赖）
│   │   │   └── files.py               # 创建/清理测试文件、生成敏感内容
│   │   ├── _mac/                      # mac 专属实现
│   │   │   ├── apps.py                # open -a "Lark" / osascript ...
│   │   │   ├── clipboard.py           # pbcopy / pbpaste
│   │   │   ├── keyboard.py            # cmd 键、中文输入
│   │   │   └── usb.py                 # diskutil 挂载等
│   │   └── _windows/                  # windows 专属实现（v0.1 只放占位 stub）
│   │       ├── apps.py                # subprocess.start / powershell ...
│   │       ├── clipboard.py           # pyperclip / win32clipboard
│   │       ├── keyboard.py            # ctrl 键、中文输入
│   │       └── usb.py                 # WMI / pnputil 等
│   │
│   ├── case/                          # Case 框架
│   │   ├── spec.py                    # CaseSpec / Step / 上下文 / setup/cleanup 钩子
│   │   ├── loader.py                  # CaseLoader 抽象 + 默认 PythonModuleLoader
│   │   └── runner.py                  # CaseRunner：调度 / setup / cleanup / skip
│   │
│   ├── notify/                        # 通知（仅推送，不接收回复）
│   │   ├── base.py                    # Notifier 抽象 + 事件枚举
│   │   ├── webhook.py                 # 通用 POST JSON webhook
│   │   ├── feishu_bot.py              # 飞书自定义机器人（含签名）
│   │   └── dispatcher.py              # 多通道分发 + 事件过滤
│   │
│   ├── human/                         # 人工介入 resume（仅接收回复）
│   │   ├── base.py                    # HumanResolver 抽象 + ResumeResult
│   │   ├── composite.py               # CompositeResolver：多渠道并行 first-win
│   │   ├── terminal.py                # v0.1 默认：终端按回车 / r / q
│   │   ├── webhook_server.py          # 本地 HTTP server 监听 POST /resume/<token>
│   │   ├── feishu_card.py             # 飞书卡片按钮回调（占位 stub，v0.2）
│   │   └── file_watch.py              # 监听文件写入（占位 stub，CI 场景）
│   │
│   └── report/                        # 报告
│       ├── schema.py                  # JSON 报告数据结构
│       ├── writer.py                  # 写入 reports/run_{ts}/result.json
│       └── hook.py                    # 预留扩展点（HTML / 上报平台）
│
├── cases/                             # 业务 case 目录
│   ├── _common/                       # 共享 setup/teardown / 通道相关 helper
│   │   ├── im_feishu.py
│   │   ├── browser_upload.py
│   │   └── mail_outlook.py
│   └── im/
│       └── case_im_send_sensitive_file.py    # 示例 case（platforms=["mac","windows"]）
│
├── reports/                           # 运行产物（gitignore）
├── config.yaml                        # 模型 endpoint、超时、debug 开关
├── pyproject.toml / requirements.txt
└── README.md
```

> 说明：包名用 `dlp_auto`（不用 `corplink_dlp_auto` 是因为下划线名太长不利于 import）。如果你希望用别的名字告诉我即可。

---

## 5. 关键接口（伪代码）

### 5.1 LLMProvider 与双接入点

```python
# dlp_auto/llm/base.py
class LLMProvider(Protocol):
    def chat(self, messages: list[dict], **kwargs) -> str: ...
    @property
    def name(self) -> str: ...
```

```python
# dlp_auto/llm/ark_doubao.py
class ArkDoubaoProvider(LLMProvider):
    def __init__(self, base_url, api_key, model):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
    def chat(self, messages, *, temperature=0, max_tokens=1024) -> str:
        ...
```

**双接入点策略（来自第 11 节确认结果）**：

```python
# dlp_auto/llm/__init__.py
@dataclass
class LLMRegistry:
    default: LLMProvider          # 必有：Agent 决策用
    judge: LLMProvider            # 若 config.llm.judge 未配，则 = default

def build_registry(settings) -> LLMRegistry:
    default = build_provider(settings.llm.default)
    judge = build_provider(settings.llm.judge) if settings.llm.judge else default
    return LLMRegistry(default=default, judge=judge)
```

- 用法：`agent` 注入 `registry.default`；`VisualJudge` 注入 `registry.judge`
- 单 case 也支持覆盖：`assert_visual("...", llm="judge")` / `assert_visual("...", llm="default")`，给后续做"裁判员消融实验"留活口。

> **预留切换点**：未来加 `UITarsProvider`、`DoubaoVisionV2Provider`，只要实现 `chat()` 即可。`config.yaml` 里通过 `llm.default.provider: ark_doubao` 选择。

### 5.2 Action JSON Schema（豆包 1.8 输出契约）

由于豆包 1.8 是通用 vision 模型，我们让它输出**严格的 JSON**（不出现 Markdown 代码块），由 `parser.py` 校验后下发到 executor。

```jsonc
// 单步示例
{
  "thought": "聊天框在右下，先把文件拖进去",
  "action": "drag",
  "args": {
    "start": [120, 800],   // 1000×1000 归一化坐标
    "end":   [620, 720]
  },
  "done": false             // true 表示当前 AI step 完成
}
```

完整 action 集合（与 UI-TARS 对齐，但去掉 `call_user`）：

| action | args | 说明 |
|---|---|---|
| `click` | `{point:[x,y]}` | 单击 |
| `double_click` | `{point:[x,y]}` | 双击 |
| `right_click` | `{point:[x,y]}` | 右键 |
| `drag` | `{start:[x,y], end:[x,y]}` | 拖拽 |
| `type` | `{content:"..."}` | 输入文本（中文走剪贴板） |
| `hotkey` | `{keys:"mod+v"}` | 快捷键，**`mod` 在 mac=cmd / win=ctrl，由 Executor 翻译** |
| `scroll` | `{point:[x,y], direction:"up\|down\|left\|right"}` | 滚动 |
| `wait` | `{seconds: 2}` | 等待 |
| `finished` | `{}` | 当前 AI step 完成（≠ case 通过） |

`Executor.do(action_dict)` 返回 `(is_finished: bool, observation: str)`，循环回到 Agent。

### 5.3 Judge（断言抽象）

```python
# dlp_auto/judges/base.py
class Judge(Protocol):
    name: str
    def evaluate(self, ctx: StepCtx) -> JudgeResult: ...

@dataclass
class JudgeResult:
    passed: bool
    detail: str
    evidence: dict     # screenshot_path / http_resp / log_excerpt 等
```

三种内置实现：

| Judge | 用法 | 实现要点 |
|---|---|---|
| `VisualJudge` | `assert_visual("出现 DLP 拦截弹窗，文案包含'禁止外发'", llm="judge")` | 截当前屏（强制落盘）→ 走 `LLMRegistry.judge` → 让模型只输出 `{"passed":bool,"reason":"..."}`。`llm` 参数可选 `"default"` / `"judge"`，缺省 `"judge"` |
| `FileLogJudge` | `assert_file_log(path="~/Library/.../dlp.log", contains="BLOCK")` | 本地文件读取 + 文本/正则匹配 |
| `HttpJudge` | `assert_http(url=..., method="POST", body=..., expect=lambda r: r["events"][0]["action"]=="block")` | 通过 `requests` 调 DLP 后台接口 |

> 设计要点：每个 Judge 的失败信息都要带 evidence，Visual Judge 自动归档截图，HTTP Judge 自动归档请求/响应 JSON。

### 5.4 Case 形态（已确认：Python module）

由于硬动作选了 Python 脚本，case 用 Python module 最自然：

```python
# cases/im/case_im_send_sensitive_file.py
from dlp_auto.case.spec import case, step, ai, hard, on_platform, setup, cleanup, need_human
from dlp_auto.core.platform import Platform
from dlp_auto.actions import files, apps        # 门面，自动按当前平台分发
from dlp_auto.judges import assert_visual, assert_http

@case(
    id="IM-001",
    name="飞书向外部用户发送敏感文件应被 DLP 拦截",
    channel="im.feishu",
    tags=["block", "sensitive_file"],
    platforms=[Platform.MAC, Platform.WINDOWS],
)
def define():
    return [
        # 前置：可省略；写在这里就是 case 级 setup
        setup(lambda ctx: files.create_sensitive(ctx.paths.sensitive_dir / "a.txt")),

        step("启动飞书并打开外部用户对话", hard(lambda: apps.open_app("Lark"))),
        step("拖拽文件到聊天框", ai("将桌面上的 a.txt 拖到聊天框")),
        step("点击发送", ai("点击聊天框的发送按钮")),

        on_platform(Platform.MAC,
            step("断言出现 mac 横幅样式拦截",
                 assert_visual("画面顶部出现 DLP 拦截横幅，包含'禁止外发'", llm="judge"))),
        on_platform(Platform.WINDOWS,
            step("断言出现 win 模态弹窗",
                 assert_visual("出现 DLP 拦截模态弹窗，包含'禁止外发'", llm="judge"))),

        step("断言后台事件", assert_http(
            url="http://dlp.test/api/events",
            params={"user": "qa01"},
            expect=lambda r: r["events"][0]["action"] == "block",
        )),

        # 后置清理：仅清理本 case 产生的临时文件，不动飞连/飞书状态
        cleanup(lambda ctx: files.cleanup(ctx.paths.sensitive_dir / "a.txt")),
    ]
```

**关键约定**：
- `setup()` 与 `cleanup()` 都是**可选**的；不写时 runner 不做任何环境改动（飞连不重启、飞书不 kill）
- `cleanup()` 即使在 case fail / error 时也会执行（`try/finally`），但不影响 case 最终状态
- case 内任何步骤可以调用 `need_human("请手动确认拦截弹窗已弹出")` 触发"暂停 + 通知"，详见第 13 节

`CaseLoader` 抽象保留：

```python
class CaseLoader(Protocol):
    def load(self, src: str | Path) -> list[CaseSpec]: ...

class PythonModuleLoader(CaseLoader): ...    # 默认实现，v0.1 唯一实现
# class YamlLoader(CaseLoader): ...          # 后续按需扩展
```

### 5.5 Agent 主循环

```python
# dlp_auto/core/agent.py
class Agent:
    def __init__(self, llm: LLMProvider, executor: ActionExecutor,
                 screen: Screen, max_steps=30):
        ...

    def do(self, instruction: str, ctx: StepCtx) -> StepResult:
        history = []
        for step in range(self.max_steps):
            # screen.capture() 内部会按 settings.screen.resize_to 缩放
            # 是否落盘 PNG 由 settings.screen.capture_each_step 控制
            screenshot = self.screen.capture(persist=ctx.settings.screen.capture_each_step)
            messages = build_messages(SYSTEM_PROMPT, instruction, history, screenshot.b64)
            raw = self.llm.chat(messages)
            action = parse_action_json(raw)        # 结构化 JSON 校验
            if action.action == "finished":
                return StepResult.ok()
            obs = self.executor.do(action)
            history.append(TurnRecord(step, action, obs))
            history = compress_history(history, keep=10)
        return StepResult.timeout()
```

> 断言点的截图由 Judge 自己控制：`VisualJudge` 永远落盘（`capture_final_assert=true`），`File/HttpJudge` 也会顺手存一张以便排查。

---

## 6. 主循环时序

```
CaseRunner
  ├─ for case in cases:
  │     ├─ if CURRENT_PLATFORM not in case.platforms:
  │     │     mark "skipped" → next case
  │     ├─ try:
  │     │     ├─ case.setup(ctx)         # 可选；只做本 case 的准备（创建测试文件等）
  │     │     ├─ for step in case.steps:
  │     │     │     ├─ if step.kind == "ai":   Agent.do(step.instruction, ctx)
  │     │     │     ├─ if step.kind == "hard": run python callable
  │     │     │     ├─ if step.kind == "assert": Judge.evaluate(ctx)
  │     │     │     ├─ if step.kind == "need_human": pause + notify(NEED_HUMAN)
  │     │     │     └─ record StepReport (status, screenshot, log...)
  │     │     └─ status = passed / failed
  │     ├─ except Exception as e:
  │     │     status = error; notify(CASE_ERROR, evidence=...)
  │     ├─ finally:
  │     │     ├─ case.cleanup(ctx)       # 可选；try/finally 保证一定执行
  │     │     └─ if status == failed: notify(CASE_FAILED, evidence=...)
  │     └─ flush CaseReport -> reports/run_{ts}/{case_id}.json
  └─ aggregate -> reports/run_{ts}/summary.json (含 platform 字段)
```

任意一个 step 失败：默认终止当前 case（标 fail）但继续下一个 case。
> TODO(确认)：是否需要支持 step 级别的 `continue_on_fail` / `retry`？

---

## 7. 配置与环境

```yaml
# config.yaml
# 加载优先级：环境变量 > 本文件 > 代码内默认值
llm:
  # 默认接入点：用于 Agent 决策动作 + 未指定 judge 模型时的 VisualJudge 兜底
  default:
    provider: ark_doubao
    base_url: ${ARK_BASE_URL:-https://ark.cn-beijing.volces.com/api/v3}
    api_key: ${ARK_API_KEY}
    model: ${ARK_MODEL:-ep-20xxxxx-doubao-1-8-vision}
  # 可选：断言专用接入点。不配则 fallback 到 default
  judge:
    # provider: ark_doubao
    # api_key: ${ARK_JUDGE_API_KEY}
    # model: ${ARK_JUDGE_MODEL}

agent:
  max_steps: 30
  step_wait_sec: 0.9

# 截图策略：每步截图（debug 用）+ 最后断言必截图（始终强制）
screen:
  capture_each_step: true       # 每个 AI step 是否落盘 PNG，可在 config / env 切换
  capture_final_assert: true    # 断言点（无论 pass/fail）一定截图，建议保持 true
  resize_to: [1920, 1080]       # 喂给 LLM 的截图统一缩放分辨率（统一坐标基准）

executor:
  failsafe: true
  type_interval: 0.02

# 平台相关：默认自动探测，下面字段都是「可覆盖项」
platform:
  force: null                            # 设为 "mac" / "windows" 可强制覆盖自动探测
  overrides:
    mac:
      paths:
        sensitive_dir: ~/dlp_test
        feishu_log: ~/Library/Logs/Lark/
      app_names:
        feishu: "Lark"
    windows:
      paths:
        sensitive_dir: C:\dlp_test
        feishu_log: C:\Users\%USERNAME%\AppData\Roaming\Lark\
      app_names:
        feishu: "Feishu.exe"

# 通知：仅推送，不接收回复
notify:
  enabled: false
  channels:
    # 通用 webhook（POST JSON）
    - type: webhook
      url: ${NOTIFY_WEBHOOK_URL}
    # 飞书机器人（自定义机器人，POST 文本/卡片）
    - type: feishu_bot
      webhook: ${FEISHU_BOT_WEBHOOK}
      secret: ${FEISHU_BOT_SECRET}        # 可选签名
  # 哪些事件触发推送
  events: [case_failed, case_error, need_human]

# 人工介入：仅接收 resume，与 notify 解耦
human:
  default_timeout_sec: 300
  default_channels: [terminal]            # 缺省 resolver 列表；case 可覆盖
  webhook_server:
    enabled: false                        # v0.1 默认关，开启后 runner 拉起本地 HTTP server
    host: 0.0.0.0
    port: 7421
    base_url: http://localhost:7421       # 通知里附给用户的访问地址

report:
  dir: reports
  keep_screenshots: true
```

> 配置加载实现（`dlp_auto/config.py`）：
> 1. 读 `config.yaml`（不存在用空字典）
> 2. 对每个字段走 `env_var | yaml_value | code_default` 三级回退
> 3. 输出全局 immutable Settings 单例

`config.py` 负责合并环境变量与 yaml，给各模块下发。

---

## 8. 报告格式（v0.1）

```jsonc
// reports/run_20260601_120000/summary.json
{
  "run_id": "20260601_120000",
  "platform": "mac",                        // 本次 run 所在平台
  "started_at": "...",
  "ended_at": "...",
  "stats": { "total": 10, "passed": 7, "failed": 2, "error": 1, "skipped": 0 },
  "cases": [
    { "id": "IM-001", "name": "...", "status": "passed", "platforms": ["mac","windows"], "report_path": "IM-001.json" }
  ]
}

// reports/run_20260601_120000/IM-001.json
{
  "id": "IM-001",
  "channel": "im.feishu",
  "status": "failed",
  "duration_ms": 24300,
  "steps": [
    {
      "name": "拖拽文件到聊天框",
      "kind": "ai",
      "status": "passed",
      "agent_steps": [
        { "thought": "...", "action": {...}, "screenshot": "screenshots/01.png" }
      ]
    },
    {
      "name": "断言出现 DLP 拦截",
      "kind": "assert",
      "judge": "VisualJudge",
      "status": "failed",
      "evidence": { "screenshot": "...", "model_reason": "未发现拦截弹窗" }
    }
  ]
}
```

`report/hook.py` 预留 `on_run_finished(run_dir)`，未来要发飞书机器人 / 出 HTML / 上报平台都在这里加。

---

## 9. 跨平台支持设计

### 9.1 设计原则

1. **AI 层共用，硬层分发**：豆包接收的 prompt、截图、JSON 输出与平台无关；硬动作和路径 100% 按平台分发。
2. **case 默认是跨平台的**：通过 `platforms=[...]` 字段声明支持范围，框架做匹配；只有少数步骤不同时用 `on_platform()` 局部分支。
3. **不在 case 里出现 `if sys.platform == ...`**：所有平台差异下沉到 `actions/` 与 `core/platform.py`，case 保持业务可读。
4. **v0.1 只实现 mac，但 windows 接口先占位**：`actions/_windows/*.py` 里函数签名齐全，函数体抛 `NotImplementedError("v0.1 未实现 windows")`；这样 windows 上跑 case 会立刻得到清晰的错误，而不是模糊的 import 失败。

### 9.2 平台差异盘点

| 层 | 是否有差异 | 处理方式 |
|---|---|---|
| LLM 层（决策） | ❌ 无差异 | 共享 prompt / schema / parser |
| 截图 `core/screen.py` | ⚠️ Retina 缩放系数不同 | 在 `screen.py` 内部统一为「逻辑像素」，对外暴露统一接口 |
| Executor click/drag/scroll | ❌ pyautogui 已抹平 | 直接用 |
| Executor `hotkey` | ✅ mac=cmd / win=ctrl | Action 协议用 `mod` 关键字，Executor 翻译 |
| Executor `type` 中文 | ✅ pbcopy vs pyperclip | 由 `actions/_mac/clipboard.py` / `_windows/clipboard.py` 实现，Executor 通过 platform 抽象调用 |
| `actions/` 应用启动、USB、文件路径 | ✅ 差异最大 | 按平台分包 |
| `judges/file_log.py` 路径 | ✅ | 路径走 `config.platform.overrides.<plat>.paths` |
| Case 业务步骤 | ⚠️ 大部分一致 | `platforms` 字段声明支持，`on_platform()` 局部分支 |

### 9.3 Platform 抽象

```python
# dlp_auto/core/platform.py
import platform as _plat
from enum import Enum

class Platform(str, Enum):
    MAC = "mac"
    WINDOWS = "windows"

def detect() -> Platform:
    sys = _plat.system().lower()
    if sys == "darwin":
        return Platform.MAC
    if sys == "windows":
        return Platform.WINDOWS
    raise RuntimeError(f"Unsupported platform: {sys}")

# 全局只读单例（启动时由 config.py 决定，支持 force 覆盖）
CURRENT: Platform = detect()
```

```python
# dlp_auto/core/executor.py 关键片段
class Executor:
    def __init__(self, platform: Platform):
        self.platform = platform
        self._mod_key = "command" if platform == Platform.MAC else "ctrl"

    def hotkey(self, keys: str):
        keys = keys.replace("mod", self._mod_key)
        pyautogui.hotkey(*keys.split("+"))

    def paste_text(self, text: str):
        # 走 actions/_<plat>/clipboard.py
        from dlp_auto.actions import clipboard
        clipboard.set_text(text)
        self.hotkey("mod+v")
```

### 9.4 actions 门面分发

```python
# dlp_auto/actions/__init__.py
from dlp_auto.core.platform import CURRENT, Platform

if CURRENT == Platform.MAC:
    from ._mac import apps, clipboard, keyboard, usb
elif CURRENT == Platform.WINDOWS:
    from ._windows import apps, clipboard, keyboard, usb

from ._common import files       # 跨平台共用

__all__ = ["apps", "clipboard", "keyboard", "usb", "files"]
```

case 里 `from dlp_auto.actions import apps` 拿到的就是当前平台的实现，无感切换。

### 9.5 case 平台标注

```python
@case(
    id="USB-001",
    platforms=[Platform.MAC, Platform.WINDOWS],  # 必填，用于 runner 跳过
)
```

辅助函数 `on_platform(plat, step_obj)`：当 `CURRENT != plat` 时返回 `None`，被 `define()` 过滤掉。

支持三种典型 case：
- 跨平台 case：`platforms=[MAC, WINDOWS]`，所有 step 共用
- 跨平台但局部分支：基础 step 共用 + 局部 `on_platform()`
- 平台独享 case：`platforms=[WINDOWS]`，mac runner 跳过

### 9.6 路径 / app 名走配置

case 和 judge 不要硬编码路径，统一从 `ctx.paths` 读：

```python
# 在 case 中
log = ctx.paths.feishu_log         # 自动读 config.platform.overrides.<当前平台>.paths.feishu_log
apps.open(ctx.app_names.feishu)
```

### 9.7 v0.1 windows 占位策略

```python
# dlp_auto/actions/_windows/apps.py
def open_app(name: str):
    raise NotImplementedError("v0.1 windows actions 未实现，请等待后续版本或自行扩展")
```

好处：
- 框架完整性可在 mac 上验证
- 未来补 windows 时只需替换函数体，无需改框架结构
- 误在 win 跑会得到清晰错误而非 import 失败

---

## 10. 通知与人工介入（Notifier）

### 10.1 触发事件

| 事件 | 来源 | 默认推送 |
|---|---|---|
| `CASE_FAILED` | 任何断言失败 | ✅ |
| `CASE_ERROR` | case 内抛未捕获异常（含三方 app 启动失败、模型调用失败） | ✅ |
| `NEED_HUMAN` | case 主动调用 `need_human("...")`，runner 暂停等用户处理 | ✅ |
| `RUN_FINISHED` | 整个 run 结束，发送 summary | ❌（默认关，可在 config 打开） |

### 10.2 通道抽象

```python
# dlp_auto/notify/base.py
class Notifier(Protocol):
    def send(self, event: NotifyEvent, payload: NotifyPayload) -> None: ...

@dataclass
class NotifyPayload:
    title: str                         # 简短标题
    summary: str                       # 详情文本
    case_id: Optional[str] = None
    screenshot_path: Optional[Path] = None
    extra: dict = field(default_factory=dict)  # 给具体通道自由扩展
```

### 10.3 内置通道

- `WebhookNotifier`：POST JSON，字段 = NotifyPayload 的 dataclass.asdict
- `FeishuBotNotifier`：飞书自定义机器人，支持文本/卡片，可加 `secret` 签名

### 10.4 NEED_HUMAN：推送与等待解耦

> ⚠️ **`need_human()` 是完全可选的 step。** case 不调用它就根本不会触发任何人工介入逻辑（`human/` 模块和 webhook server 都不会启动）。
> 大多数 DLP case 应当走纯 AI + 断言闭环；只有必须人工二次确认（例如外设/打印这种 AI 难以自动判定的场景）才用它。

`need_human()` 同时做两件事：

1. **推送**：经 `NotifyDispatcher` 把"需要人工介入"消息发到所有配置的通知通道（webhook / 飞书机器人 / ...）
2. **等待**：经 `HumanResolver` 阻塞等待人工反馈，决定后续是 `approved / rejected / timeout`

这两件事**完全解耦**，仅靠 `correlation_id` 关联：

```
need_human()
  ├─ NotifyDispatcher.emit(NEED_HUMAN, payload)   # 仅推送，不收回复
  │     └─ 用户在手机/IM/邮件 看到提示 + 截图 + 关联 ID
  │
  └─ CompositeResolver.wait(payload, timeout)     # 仅等待，不发推送
        ├─ TerminalResolver  线程：等回车
        ├─ WebhookResolver   线程：等 HTTP POST /resume/<token>
        └─ ... 任意 resolver 先返回即胜出，其余被取消
```

#### 10.4.1 HumanResolver 抽象

```python
# dlp_auto/human/base.py
class HumanResolver(Protocol):
    name: str
    def wait(self, payload: NotifyPayload, timeout_sec: int) -> ResumeResult: ...
    def cancel(self) -> None: ...   # 被 first-win 时用来释放资源

@dataclass
class ResumeResult:
    decision: Literal["approved", "rejected", "timeout", "error"]
    by: str                               # 哪个 resolver 给的回复
    note: str = ""                        # 用户备注（可选）
    raw: dict = field(default_factory=dict)
```

#### 10.4.2 v0.1 内置 Resolver

| Resolver | 行为 | v0.1 |
|---|---|---|
| `TerminalResolver` | 终端 prompt：`[Enter]=approve / r=reject / q=quit`；超时按 timeout | ✅ 实现 |
| `WebhookResolver` | 启动本地 `http://0.0.0.0:<port>/resume/<token>` server，接收 `POST {decision, note}` | 🟡 接口齐全；本地能跑，远程访问需自己暴露端口 |
| `FeishuCardResolver` | 飞书机器人卡片按钮回调（依赖 lark 服务端配置） | ⏸️ 占位 stub，v0.2 |
| `FileResolver` | 监听某文件写入（CI 场景：`echo approve > .resume`） | ⏸️ 占位 stub |

#### 10.4.3 CompositeResolver（多渠道并行 first-win）

```python
# dlp_auto/human/composite.py
class CompositeResolver(HumanResolver):
    def __init__(self, resolvers: list[HumanResolver]): ...
    def wait(self, payload, timeout_sec):
        # 起多个线程并行 wait，任一返回即 set Event 并 cancel 其它
        # 返回最先到达的 ResumeResult
```

case 作者无需感知组合逻辑，写法：

```python
step("人工确认弹窗内容", need_human(
    title="请人工确认 DLP 拦截弹窗文案",
    timeout_sec=300,                              # 默认 5 分钟，超时按 fail 处理
    channels=["terminal", "webhook"],            # 可选；缺省读 config 默认值
    on_reject="fail",                             # reject 时把 case 判 fail（默认）
))
```

#### 10.4.4 配置

```yaml
human:
  default_timeout_sec: 300
  default_channels: [terminal]                    # 默认仅终端等待
  webhook_server:
    enabled: false
    host: 0.0.0.0
    port: 7421
    base_url: http://localhost:7421               # 通知里附给用户的访问地址
```

> v0.1 默认就能跑（仅 terminal）；想用 webhook 时把 `webhook_server.enabled` 打开，runner 启动时拉起本地 HTTP server，run 结束时优雅关闭。

#### 10.4.5 在 case 报告里的体现

```jsonc
{
  "name": "人工确认弹窗内容",
  "kind": "need_human",
  "status": "passed",
  "resume": {
    "decision": "approved",
    "by": "WebhookResolver",
    "note": "弹窗文案与预期一致",
    "duration_ms": 38210
  }
}
```

### 10.5 Dispatcher

```python
# dlp_auto/notify/dispatcher.py
class NotifyDispatcher:
    def __init__(self, channels: list[Notifier], events: set[NotifyEvent]):
        ...
    def emit(self, event, payload):
        if event not in self.events: return
        for ch in self.channels:
            try: ch.send(event, payload)
            except Exception as e: log.warning(f"notify channel {ch} failed: {e}")
```

- 通知失败**不能影响主流程**（捕获后只记日志）
- 由 `CaseRunner` 与 `need_human()` step 注入；不直接暴露给 case 作者

---

## 11. 与你 demo 的差异说明

| `ai-ui/uitars_run.py` | 本仓库 |
|---|---|
| 单文件、单 instruction、main 直跑 | 拆分成 agent / executor / screen，被 case runner 调用 |
| 输出格式：`Thought:\nAction: click(...)`（UI-TARS 风格） | 结构化 JSON（豆包 1.8 通用模型更稳定） |
| history 直接拼 assistant 消息 | 同思路，独立成 `core/history.py`，可压缩、可裁剪 |
| 没有断言概念 | 引入 Judge 抽象 + 三类内置实现 |
| 中文输入用 pbcopy + cmd+v | 保留，搬到 `actions/keyboard.py`，并兼容 Linux 的 xclip |

---

## 12. 已确认决策（汇总）

> 第 11 节遗留待决项已经全部得到回答，固化在这里。后续讨论以本节为准。

| 编号 | 决策 | 落点 |
|---|---|---|
| D1 | 包名 = `dlp_auto` | 第 4 节目录结构 |
| D2 | case 形态 = Python module（`@case` + `define()` 列表）| 5.4 |
| D3 | 模型配置加载顺序 = **env > config.yaml > 代码默认** | 7 节、`config.py` |
| D4 | LLM 双接入点：`llm.default`（Agent + 兜底 judge）+ `llm.judge`（可选） | 5.1、7 节 |
| D5 | 截图策略：`capture_each_step` 可配，`capture_final_assert` 强制 true | 5.5、7 节 |
| D6 | v0.1 不做 step retry / continue_on_fail | 主循环时序 |
| D7 | 三方 app 启动失败：直接 case error + 触发 `CASE_ERROR` 通知（不重试） | 第 10 节 |
| D8 | case 间隔离：runner 不做任何隔离；清理由 case 自己 `cleanup()` | 5.4、6 节时序 |
| D9 | `platforms` 字段无默认值，case 必须显式声明 | 9.5 |
| D10 | 截图统一 1080p 后再喂模型，1000×1000 归一化坐标基于此 | 9.2、5.5 |
| D11（新增） | `need_human()` step 触发暂停 + 通知，超时按 fail 处理 | 10.4 |
| D12（新增） | Notifier 失败不阻塞主流程 | 10.5 |
| D13（新增） | `need_human()` 推送（notify）与等待（human resolver）解耦；resolver 可插拔、多渠道并行 first-win，v0.1 内置 terminal + webhook server，预留 feishu card / file watch | 10.4 |
| D14（新增） | `need_human()` 完全可选；case 不调用则 `human/` 与 webhook server 都不会被实例化 | 10.4 |

---

## 13. 下一步

我会按以下顺序提交（每步可单独 review）：

1. **建仓骨架**
   - `dlp_auto/` 全部空模块 + `__init__.py` + 占位 docstring
   - `actions/_windows/*.py` 函数签名齐全 + `NotImplementedError`
   - `config.yaml` + `config.py`（env > yaml > default 三级回退）
   - `cases/` 空目录 + `cases/im/case_demo.py` 占位
   - `pyproject.toml`、`.gitignore`

2. **Core 主循环（迁移你的 demo）**
   - `core/platform.py`：探测 + 强制覆盖
   - `core/screen.py`：截图 + retina 缩放 → 1080p + 落盘策略
   - `core/executor.py`：JSON action 执行 + `mod` 键映射 + 中文剪贴板
   - `core/parser.py`：JSON Schema 校验
   - `core/agent.py`：感知-决策-执行循环

3. **LLM Provider**
   - `llm/base.py`、`llm/ark_doubao.py`、`llm/__init__.py:LLMRegistry`

4. **Judge 三件套**
   - `judges/visual.py`（接 `llm.judge`）、`judges/file_log.py`、`judges/http.py`

5. **Notifier + Human Resolver**
   - `notify/webhook.py`、`notify/feishu_bot.py`、`notify/dispatcher.py`
   - `human/terminal.py`（v0.1 默认）
   - `human/webhook_server.py`（可选启用）
   - `human/composite.py`（多渠道 first-win）
   - `human/feishu_card.py` / `human/file_watch.py`（占位 stub）

6. **Case 框架 + 端到端 Demo**
   - `case/spec.py`（含 `setup/cleanup/need_human/on_platform`）
   - `case/runner.py`（含 try/finally + skip + notify hook）
   - `report/writer.py`
   - 第一个 mac 平台示例 case 跑通

请你最终 review 第 12 节（决策汇总）有没有偏差，没有的话我就开始第 1 步搭骨架。
