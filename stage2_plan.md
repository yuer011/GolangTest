# Stage 2 实装计划与 DLP 通道层级约定

> ⚠️ **已归档（2026-07-28）**：本文是 Stage 2（Agent 最小闭环）阶段的对齐与实装记录，该阶段已完成。其中 §4「DLP 后台分级 + cases 命名约定」仍为活约定，**已提炼进 [tech_design.md](../tech_design.md) §3.6**（活文档权威源）；本文仅作历史留存，不再维护。

> 本文记录 v0.1 骨架完成后，进入 Stage 2 之前与你对齐的关键决策，以及后续 case 目录 / channel 命名所参照的 DLP 管理后台分级。

---

## 1. Stage 2 范围：仅做「Agent 最小闭环」

**目标**：绕过 `CaseRunner`，先把「LLM → 截图 → 解析 → 执行」链路打通。

**交付件**：`dlp-auto agent_demo --instruction "..."` 子命令可跑出真实闭环。

**实装清单（Stage 2 内）**：

| 模块 | 文件 | 状态 |
|---|---|---|
| 截图 / 坐标换算 / resize 1080p | [core/screen.py](../dlp_auto/core/screen.py) | 实装 |
| 豆包 / 火山方舟 OpenAI 兼容 chat | [llm/ark_doubao.py](../dlp_auto/llm/ark_doubao.py) | 实装 |
| Action Space system prompt（JSON 版） | [llm/prompts.py](../dlp_auto/llm/prompts.py) | 实装 |
| JSON 解析 + Schema 校验 + 文本兜底（可开关） | [core/parser.py](../dlp_auto/core/parser.py) | 实装 |
| 动作分发执行 | [core/executor.py](../dlp_auto/core/executor.py) | 实装 |
| Mac 剪贴板 / 键盘 | [actions/_mac/clipboard.py](../dlp_auto/actions/_mac/clipboard.py)、[actions/_mac/keyboard.py](../dlp_auto/actions/_mac/keyboard.py) | 实装 |
| 历史 + 压缩 | [core/history.py](../dlp_auto/core/history.py) | 实装 |
| Agent 主循环 | [core/agent.py](../dlp_auto/core/agent.py) | 实装 |
| `agent_demo` CLI 子命令 | [run.py](../dlp_auto/run.py) | 实装 |

**保持 stub 不动（Stage 2 不实装）**：

- `case/runner.py`、`case/loader.py`
- 所有 `judges/*`
- 所有 `notify/*`、`human/*`、`report/*`
- `actions/_mac/apps.py`、`actions/_mac/usb.py`
- `actions/_windows/*`（v0.1 全 stub）

---

## 2. 模型输出格式：JSON 优先 + 文本兜底（开关）

**最终决定**：
- system prompt 强制要求 JSON Action 输出，与架构文档 D 项一致。
- parser 内置一个文本格式兜底分支（即原 demo 的 `Thought:` / `Action:` 解析逻辑）。
- 是否启用文本兜底由配置开关控制，**默认行为待你实测后再定**。

**配置位置**（[config.yaml](../config.yaml) 内 `agent` 段，Stage 2 实装时新增）：

```yaml
agent:
  parser:
    json_first: true
    fallback_text: true        # 实测后视情况改为 false
```

**parser 行为**：

```
raw  ──▶  尝试 json.loads + JSON Schema 校验
            ├─ 成功 → 返回 ActionDict
            └─ 失败 ─▶ if fallback_text:
                          走 _extract_action_text + parse_action（迁自 demo）
                       else:
                          抛 ParserError
```

---

## 3. Mac apps 实装：Stage 2 不做

`actions/_mac/apps.py` 的 `launch_app` / `quit_app` / `focus_app` 在 Stage 2 全部维持 `NotImplementedError`。

**理由**：
- Stage 2 目标是「最小 Agent 闭环」，启动应用属于业务编排范畴。
- 后续在第一个真实 IM/邮件 case 落地时一并实装（osascript / `open -a` / `lsappinfo` 等方案再选）。

---

## 4. 后续 case 目录与命名：参照 DLP 管理后台分级

### 4.1 DLP 管理后台分级（来源：飞连 DLP「桌面应用」配置截图）

**第一级：场景大类（3 个）**

| 显示名 | 代码命名 | 描述 |
|---|---|---|
| 桌面应用 | `desktop_app` | 检测敏感文件通过聊天软件、网盘等桌面应用的外发行为 |
| Web 网站 | `web` | 检测敏感文件通过 Web 网站的外发行为 |
| 电脑外设 | `peripheral` | 检测敏感文件通过电脑外设的外发行为 |

**第二级：桌面应用下的通道分类（15 个）**

| 显示名 | 代码命名 | 后台条目数 |
|---|---|---|
| 即时通信 | `im` | 42 |
| 网盘 | `cloud_drive` | 18 |
| 邮箱 | `email` | 5 |
| 云文档软件 | `cloud_doc` | 1 |
| 文档笔记 | `doc_notes` | 10 |
| 文件传输 | `file_transfer` | 17 |
| 命令行 | `cli` | 7 |
| 远程控制 | `remote_control` | 13 |
| 代码托管 | `code_hosting` | 1 |
| 办公软件 | `office` | 1 |
| 虚拟机 | `vm` | 6 |
| AI 应用 | `ai_app` | 12 |
| 创意设计 | `design` | 2 |
| 无线传输 | `wireless` | 2 |
| 其它 | `other` | 2 |

> Web 网站 / 电脑外设 的二级分类后续补充。

**第三级：具体通道**（如 `im` 下的 飞书 / 微信 / 钉钉 / Telegram …），由具体 case 的文件名 / `id` 体现。

### 4.2 cases/ 目录结构约定

```
cases/
├── __init__.py
├── desktop_app/
│   ├── __init__.py
│   ├── im/
│   │   ├── __init__.py
│   │   └── case_demo.py
│   ├── cloud_drive/...
│   ├── email/...
│   ├── ...（按需创建，不强制全建）
│   └── other/...
├── web/                   # 暂留空，后续补充二级分类
│   └── __init__.py
└── peripheral/            # 暂留空，后续补充二级分类
    └── __init__.py
```

> 当前阶段只创建用到的目录；新增通道时再建对应 `__init__.py`，避免一堆空文件。

### 4.3 case 字段命名规范

```python
@case(
    id="desktop_app.im.feishu.send_sensitive_file",   # <场景>.<通道>.<具体应用>.<场景描述>
    name="桌面应用 - 即时通信 - 飞书 - 发送敏感文件被拦截",
    channel="desktop_app.im",                          # <场景>.<通道>
    platforms=[Platform.MAC],
    tags=["desktop_app", "im", "feishu", "sensitive"],
)
def define() -> list[Step | None]:
    ...
```

**规则**：
- `id` 唯一定位 case，三段或四段：`<场景>.<通道>[.<具体应用>].<场景描述>`。
- `channel` 用于报告聚合与过滤，统一两段 `<场景>.<通道>`。
- `tags` 至少包含场景、通道；具体应用与子场景标签可选。
- `name` 中文，便于报告人读。

---

## 5. 同步落地的代码改动

本次记录文档时，附带做了：

1. 把 [cases/im/case_demo.py](../cases/desktop_app/im/case_demo.py) 移到 [cases/desktop_app/im/case_demo.py](../cases/desktop_app/im/case_demo.py)。
2. 更新示例 case 的 `id` / `channel` / `tags` 与本文 4.3 节对齐。
3. 创建 `cases/web/__init__.py` 与 `cases/peripheral/__init__.py` 两个占位场景目录。

---

## 6. Stage 2 启动前 Checklist

- [x] Stage 2 范围确认：仅 Agent 最小闭环
- [x] 模型输出格式：JSON 优先 + 可开关的文本兜底
- [x] apps 实装策略：暂不实装
- [x] case 目录与 channel 命名：对齐 DLP 后台分级
- [ ] Stage 2 编码（按本文 §1 实装清单）
