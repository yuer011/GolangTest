# DLP 客户端日志验证设计（平台后端可插拔）

> **状态**：Windows/Mac 后端均已实现；Mac 文件/截图 audit 真机链路已通过。
> **定位**：三路验收中的「块②：DLP 客户端本地日志检索」的落地方案——从「明文按特征匹配」升级为
> 「解密加密日志 → 时间窗增量 → 解析真实外发事件 → 提取字段并上报」，且**按平台拆开、互不假设一致**。
> **前置阅读**：[tech_design.md](./tech_design.md)（硬约束 #1/#3/#6/#10、验收/报告机制）、
> [dlp_policy_assertion_design.md](./dlp_policy_assertion_design.md)（policy 断言、聚合语义）。

---

## 1. 背景与目标

现有 `verify/dlp_log.py` 假设 DLP 客户端日志是**明文**，用「字节偏移增量 + contains/regex 特征匹配」判定。
但真实的 corplink 客户端日志（Windows）是**加密**的，需专用解密器解密后才能读；且日志里混有
其他噪声（见 §3.3），不能裸子串匹配。故需要一套**面向真实日志**的验证方案。

**设计目标**：

1. **只有传策略（audit/block）才走日志验证**（对齐用户需求 1）。
2. **解密 + 增量**：加密日志需解密才能读；避免每次全量重复处理带来的浪费，做「时间窗增量」。
3. **解析真实外发事件**：提取事件 UUID、process name、外发文件路径、整条日志行；判定「是否我们本次外发」；
   把整条日志记进结果报告并上传多维表格（对齐用户需求 3）。
4. **平台拆开**：Windows 与 Mac 的日志路径、解密方式、事件格式不同，按平台隔离；
   Mac 能力收敛在 `_mac.py` + 配置子块，**零回归、不碰 Windows**。

**非目标**（本期不做）：

- **区分「审计 vs 阻断」类型**：当前日志行看不出 `action=BLOCK/AUDIT`，`rule_name` 是 UUID 无法直接判类型
  （零猜测硬约束下不臆测）。本期只判定「时间窗内有无我方外发事件」。后续若客户端日志暴露类型字段再扩展。
- **用 `leakFileActions` 区分 audit/block**：真实样本里有该字段，但数值语义尚未标定；
  零猜测约束下不据此下策略类型结论。

---

## 2. 首要原则：平台后端可插拔 + 零猜测 + 验收零副作用

> 与项目硬约束一脉相承，这里明确本能力的三条底线。

- **平台后端可插拔**：`DlpLogChecker` 是平台无关的**门面**，只保证 checker 接口与 `CheckOutcome` 形状；
  所有平台特有逻辑（解密器、日志路径、事件格式、锚点、扩展名判定、写盘/轮转兜底）下沉到
  `_windows.py` / `_mac.py`。**门面不含任何 Windows/Mac 假设**。
- **零猜测（硬约束 #1）**：日志路径、解密器路径、事件锚点、图片扩展名等**全部从 config 读**，
  缺配置记 `inconclusive` 并提示补哪些字段，绝不臆测。
- **验收零副作用（硬约束 #6）**：解密器缺失/路径缺失/解密失败/文件读不到/sudo 未授权 → 一律降级
  `inconclusive`，**绝不打断 run、绝不 fake pass**（守住硬约束 #3/#10：`inconclusive` 不生成通过结论）。

---

## 3. Windows 后端设计（本期完整实现）

### 3.1 实测结论（决定设计的事实）

以下均在真机（本项目开发机）实测确认：

| 项 | 实测结果 | 对设计的影响 |
|---|---|---|
| 解密器用法 | `win-corplink-log-decode.exe SRC DST`，**能直接读被 corplink 独占锁定的原文件**（exit 0） | 无需先「共享读拷贝」，直接解密原始日志到 `.tmp/` |
| 全量解密耗时 | ~130ms（4.8MB 日志） | 性能非瓶颈，**全量解密完全可接受** |
| 尾部字节切片解密 | ❌ 得乱码（整文件流式加密，已实测证伪） | **「只解密后 N 字节 / N 行」不可行**；增量改到明文层做（§3.4） |
| 文件轮转 | `ow_system.log` → `ow_system.1.log`…`.8.log`，单文件约 10MB 才轮转 | 单条 case 几十秒~几分钟，轮转概率极低，做防御兜底即可 |
| 真事件行格式 | 见 §3.2 | 可稳定正则解析 uuid / process name / origin file path |

### 3.2 真实事件行格式

解密后的明文里，一条真实 DLP 外发事件形如（单行）：

```
[2026-08-03 19:55:02.251] [21956:7028] [default] [info] dlp_event_upload_handler.cpp:2262 事件UUID : 509034d2-79e7-4763-a542-eb218e0fcce6 rule_name: c53d7651-b689-4030-b636-d31d314d42ab tag name is file:builtin:any_file | process name is QQ.exe | origin file path is C:\path\to\dlp_sample_xxx.txt
```

可解析字段：

- **行首时间戳** `[YYYY-MM-DD HH:MM:SS.mmm]`：用于时间窗过滤（§3.4）。
- **事件 UUID**：`事件UUID : <uuid>`。
- **process name**：`process name is <exe>`（如 `QQ.exe` / `Feishu.exe`）。
- **origin file path**：`origin file path is <路径>`——文件外发是完整路径含唯一文件名；
  软件自带截图外发时为 `screenshot.png`（无目录、无唯一名）。
- `tag name` 实测**恒为 `file:builtin:any_file`**，**区分不了图片/普通文件**——故截图类判定只能靠
  origin file path 的扩展名（§3.5），不能靠 tag name。

### 3.3 ⚠️ 关键坑：日志混有「我方 shell 回显」的假事件

corplink 客户端会把宿主（Trae 等）的工具 I/O 也记进同一个日志文件，形如
`... ndlp_svc_mgr.cpp:643 on websocket msg, req: {...}`，其 JSON 里**照抄了命令文本**——
若命令里带 `事件UUID`/`dlp_event` 字样（例如排查日志时），就会出现「看起来像事件、实则是命令回显」的行。

**对策**：匹配必须**锚定真正的事件发射源**——行内需同时含 `event_marker`（配置值
`dlp_event_upload_handler.cpp`）**且** `事件UUID :`。绝不用 `dlp_event` / `事件UUID` 裸子串匹配。
`event_marker` 走 config（零猜测、可改）。

### 3.4 解密 + 时间窗增量

用户设想的「只解密尾部/增量字节」在字节层**不可行**（流式加密，§3.1）。但因全量解密仅 ~130ms，
把「增量」上移到**明文层时间窗**，效果等价、性能无损：

1. **`on_case_start`**：记录 `window_start = datetime.now()`（本地时钟，带小幅 guard 回拨防边界丢事件）。
   替代旧的「字节偏移」——解密后字节偏移已失效。
2. **`check`**：
   1. `decoder <原始加密日志> <.tmp/dlp_decoded/<run_case>.log>` 全量解密（直读独占锁定的原文件）。
   2. 按行读明文，**只保留**「行首时间戳 ≥ `window_start`」**且**「含 `event_marker` + `事件UUID :`」的真事件行
      （这就是"增量"：只处理本次外发时间窗内的真实事件）。
   3. 解析字段 → 按 §3.5 判定 → 命中提取、未命中兜底。
   4. 用完删除临时明文文件。
3. **写盘延迟兜底**：事件可能比动作晚几秒落盘。首轮未命中时，按 `settle_wait_sec`（默认 3s，可配、设 0 关）
   等待一次、重解一次再判。
4. **轮转兜底**：若当前 `ow_system.log` 的最早一行时间戳已晚于 `window_start`，说明期间发生过轮转 →
   追加解密 `rotated_globs`（默认 `ow_system.1.log`）一起纳入时间窗过滤。

> 临时明文一律落 `.tmp/dlp_decoded/`（项目内，符合硬约束「测试产物在项目内」），用完即删。

### 3.5 判定语义与「是不是我们本次外发」

本期**只做「有无外发事件」**（不区分审计/阻断）：

- **passed**：时间窗内找到**我们本次外发**的真事件。
- **failed**：解密成功、时间窗覆盖，但窗内**无**我们的事件。
- **inconclusive**：解密器/路径缺失、解密失败、文件读不到（降级，不打断 run）。

「是不是我们本次外发」按 case 类型区分，**用 `rep.sensitive_file` 是否有值自动区分，无需改 case**：

| case 类型 | 判据 | 说明 |
|---|---|---|
| **文件类**（拖拽/上传/复制粘贴，`sensitive_file` 有值） | 某真事件 `origin file path` **包含本次唯一文件名**（`dlp_sample_xxx.txt`） | 唯一名，零歧义 |
| **截图类**（软件自带截图，`sensitive_file` 为空） | 某真事件 `origin file path` **扩展名 ∈ `image_exts`**（`.png/.jpg/.jpeg/.bmp/.gif`） | 用户拍板：tag name 区分不了，按扩展名判「文件类型对应上」；**不校验进程名** |

> **进程名不参与匹配**（用户拍板），仅作为提取字段用于上报。

### 3.6 提取与上报

命中后从该真事件行提取并回填：

- `CheckOutcome.evidence`：`{path, hit_line, event_uuid, process_name, origin_file_path, window_start}`。
- `CaseReport.dlp_process_name`：process name（如 `QQ.exe`）。
- `CaseReport.dlp_event_log`：**整条原始日志行**（含事件 UUID，供人工复核/追溯）。
- → CSV 新增列「进程名称」「DLP事件日志」。
- → 多维表格新增列「进程名称」「DLP事件日志」。

---

## 4. Mac 后端

### 4.1 已确认事实

| 项 | 已确认结果 | 对设计的影响 |
|---|---|---|
| 加密日志 | `/Library/CorpLink/logs/edlp.log`，root:admin、0600 | 读取需要 sudo |
| 解密器 | 仓库根目录 `bread`，Mach-O universal binary（x86_64 + arm64） | 双架构 Mac 可运行 |
| bread 用法 | `bread filename`；帮助同时明确支持 `bread -` 从 stdin 读取 | 可做最小权限管道 |
| 明文时间戳 | `2026-08-08 17:34:23.729526000`（无方括号、纳秒） | Mac 独立解析器，截到微秒比较 |
| 真事件锚 | 类别 `EDLP:DLP` + 消息开头 `dlp audit event:` | 不复用 Windows marker |
| 事件格式 | marker 后为 JSON，行尾跟 `(Responder.mm:716)` | 用 `JSONDecoder.raw_decode`，不做字符串切片猜括号 |

### 4.2 最小权限解密

用户提供的直接命令是 `sudo bread /Library/CorpLink/logs/edlp.log`。但仓库内 `bread`
对当前用户可写，直接 sudo 会让仓库二进制以 root 运行。实现使用 bread 官方帮助支持的
stdin 模式，收窄为：

```text
sudo -n cat /Library/CorpLink/logs/edlp.log | /absolute/repo/bread -
```

- 只有系统 `cat` 以 root 身份运行；`bread` 保持当前用户权限。
- 两段都由 `subprocess.run` 直接传 argv，不经过 shell。
- 加密字节和解密明文只驻留内存，不创建明文临时文件。
- 使用 `sudo -n` 禁止热路径弹密码提示；运行前需在同一终端手工执行 `sudo -v`。
  没有授权、环境禁止 sudo、超时或进程失败均返回 `inconclusive`。
- 长期运行推荐用 `scripts/setup_mac_dlp_log_sudo.sh --apply` 安装精确规则：
  `<login_user> ALL=(root) NOPASSWD: /bin/cat <config中的Mac日志路径>`。脚本默认只预览，
  写入前用 `visudo` 校验，安装后清除临时 sudo ticket，并端到端验证
  `sudo -n cat | bread -` 能解析出配置 marker；`--check` 可单独复检且只报告事件数，
  `--remove` 可撤销。规则不授权 bread 或其它 root 命令。脚本使用 POSIX shell/awk
  读取固定配置层级，不依赖 Python、PyYAML 或虚拟环境。

### 4.3 真实事件解析

原始 bread 默认输出的真实事件行形如：

```text
2026-08-08 17:34:23.729526000 DEBG [...] [EDLP:DLP] dlp audit event: {"eventId":"...","appLeak":{"appName":"feishu"},"targetFile":{"leakFilePath":"/Users/.../测试计划.jmx","leakFileName":"测试计划.jmx","leakFileExtension":".jmx"}} (Responder.mm:716)
```

结构化提取：

- `eventId` → `DlpEvent.event_uuid` → 命中后回填 `rep.event_id`；
- `appLeak.appName` → `dlp_process_name`；
- `targetFile.leakFilePath` / `leakFileName` / `leakFileExtension` → 外发文件匹配；
- `leakTargetTag` → evidence；
- 完整原始事件行 → `dlp_event_log`。

`eventId` 必须能解析为 UUID；marker 命中但 JSON 损坏或 ID 非法的行不计为真实事件。
后端不依赖默认格式，而是调用 `bread -f "%d<TAB>%C<TAB>%m"` 固定为
“时间戳 / 类别 / 消息”三列；类别精确命中 `event_category` 且消息以
`event_marker` 开头才解析 JSON，避免其它模块把完整事件文本回显到消息体时产生假命中。
`configDesc` 是 JSON 字符串内嵌 JSON，当前判定不需要其内容，不做二次解析。

### 4.4 时间窗、匹配与重试

- `on_case_start` 记录 `window_start` 并回拨 2 秒防边界抖动。
- 每轮读取/解密完整文件，但只保留时间戳 ≥ `window_start` 的真实事件。
- 文件 case：`leakFilePath` 包含本次唯一文件名，或 `leakFileName` 与之相等。
- 截图 case：`leakFileExtension`（缺失时回退路径扩展名）属于配置的 `image_exts`。
- 首轮未命中按 `settle_wait_sec` / `settle_retries` 短等待多轮重查，命中即停。
- `leakFileActions` 暂不用于 audit/block 分型：audit 下命中当前 `dlp audit event`
  可判 passed；block 下仍回填 eventId 供服务端回查，但本地日志保持 `inconclusive`。
- block 下完全未命中时也在重试耗尽后记 `inconclusive`，因为缺日志不是“阻断失败”的
  反证；audit 下未命中仍记 `failed`。

### 4.5 真机验收结果

2026-08-08 使用 Mac 企业微信四条正式 case 执行
`--policy audit --check-server --lark-base`：

- 拖拽、上传、复制粘贴均按本次唯一文件名命中，截图按图片类型命中
  `screenshot.png`；四条事件的 `appLeak.appName` 均为 `wxwork`。
- 四条均从 Mac 日志回填唯一 `eventId`，CSV、按 run_id 隔离的末步截图和运行结果
  Base 均成功生成。
- 首次 run 因本机 `config.secret.yaml` 缺 `verify.server` 凭据，服务端路按设计降级
  `inconclusive`，未影响 UI、日志或 Base 链路。补齐 secret 后复用原四个 eventId
  独立回查，均恰好命中一条服务端放行事件，符合 audit 预期。
- 补齐凭据后再以相同参数完整重跑，最终 `total=4 passed=4`，CSV、四张末步截图和
  新建运行结果 Base 均记录 4/4 通过。
- 该结果关闭 `CHG-001` 的 sudo + bread + case 真跑门禁；block 下
  `leakFileActions` 的含义仍无样本依据，继续由 `CHG-003` 跟踪。

---

## 5. 触发方式（对齐用户需求 1）

**`policy ∈ {audit, block}` → 自动挂载 dlp_log checker**；`policy=none` → 不挂载。

- `--check-log` **降级为从属开关**：`policy=none` 时即使传 `--check-log` 也不验证日志，仅在
  [run.py](../dlp_auto/run.py) 打提示「`--check-log` 需配合 `--policy` 使用，本次已忽略」。
- 这是相对现状的**行为变化**（原 `--check-log` 可独立生效），已与用户确认知悉。

---

## 6. 代码结构（平台后端可插拔）

把原单文件 `verify/dlp_log.py` 重构为包，对齐 `actions/_windows`、`actions/_mac` 的既有平台分层约定：

```
dlp_auto/verify/dlp_log/
├── __init__.py     # 工厂 build_dlp_log_checker() + DlpLogChecker 门面（平台无关）
├── _base.py        # 后端协议 LogVerifyBackend + DlpEvent 数据结构 + 平台无关 helper（时间戳解析等）
├── _windows.py     # WindowsCorplinkBackend：解密→时间窗→真事件解析→文件/截图匹配（本期完整实现）
└── _mac.py         # MacCorplinkBackend：sudo cat → bread stdin → JSON 事件解析
```

- **`__init__.py`**：`DlpLogChecker`（`name="dlp_log"`, `scope="case"`）按 `core.platform.CURRENT` 选后端，
  `on_case_start`/`check` 全委托后端。工厂 `build_dlp_log_checker(settings)` 读当前平台配置子块、建对应后端。
- **`_base.py`**：定义 `LogVerifyBackend` 协议（`on_case_start(ctx)` / `check(ctx) -> CheckOutcome`
  / `collect_events(window_start, window_end) -> list[DlpEvent]`）、`DlpEvent` dataclass
  （uuid/process_name/origin_file_path/raw_line/ts）、`EventCollectError` 异常、平台无关的行首时间戳解析等纯函数。
  其中 `collect_events` 供旁路 run 级事件审计（CHG-020，默认关）全量取窗内事件用，复用各后端既有
  「解密 → 时间窗过滤」逻辑；无法完成时抛 `EventCollectError`（配置缺失/解密失败/读不到）。逐 case 验收
  （`on_case_start`/`check`）完全不依赖它，两条链路解耦，详见 [run_dlp_event_audit_design.md](./archive/run_dlp_event_audit_design.md)。
- **`_windows.py` / `_mac.py`**：各自独享平台逻辑，互不引用。

---

## 7. 配置（每平台一个自包含子块，形状可不同）

```yaml
verify:
  dlp_log:
    windows:
      path: C:\Users\<user>\AppData\Local\corplink-ow\logs\ow_system.log
      decoder: <仓库内 win-corplink-log-decode.exe 的路径>
      event_marker: "dlp_event_upload_handler.cpp"   # 锚定真事件发射源，规避 shell 回显假事件
      image_exts: [".png", ".jpg", ".jpeg", ".bmp", ".gif"]
      settle_wait_sec: 3          # 事件落盘延迟兜底：首轮未命中先等一次再重判（0=关）
      rotated_globs: ["ow_system.1.log"]   # 轮转兜底
    mac:
      path: /Library/CorpLink/logs/edlp.log
      decoder: bread
      use_sudo: true
      timeout_sec: 60
      event_category: "EDLP:DLP"
      event_marker: "dlp audit event:"
      image_exts: [".png", ".jpg", ".jpeg", ".bmp", ".gif"]
      settle_wait_sec: 5
      settle_retries: 3
```

- 工厂只读**当前平台**子块、只建对应后端；Mac 子块可以是完全不同的形状。
- 敏感/机器相关路径（decoder 绝对路径等）建议放 `config.secret.yaml`，`config.yaml` 只留模板占位。

---

## 8. 改动文件清单

| 文件 | 改动 | 平台性 |
|---|---|---|
| `dlp_auto/verify/dlp_log/`（新包，取代原 `dlp_log.py`） | 门面 + `_base` + `_windows` + `_mac` + `_legacy` | Win / Mac 实现 |
| [config/config.yaml](../config/config.yaml) | `verify.dlp_log.windows` / `mac` 自包含子块 | 分平台 |
| [dlp_auto/verify/__init__.py](../dlp_auto/verify/__init__.py) | `build_manager` 改为 policy 门控自动挂载 | 平台无关 |
| [dlp_auto/run.py](../dlp_auto/run.py) | `--check-log` + `policy=none` 提示；触发逻辑对齐 | 平台无关 |
| [dlp_auto/report/schema.py](../dlp_auto/report/schema.py) | `CaseReport` 加 `dlp_process_name`、`dlp_event_log` | 平台无关 |
| [dlp_auto/report/writer.py](../dlp_auto/report/writer.py) | CSV 加「进程名称」「DLP事件日志」列 | 平台无关 |
| [dlp_auto/report/lark_base_hook.py](../dlp_auto/report/lark_base_hook.py) | 多维表格 `_FIELDS`/`_RECORD_FIELDS`/`_case_row` 加两列 | 平台无关 |
| [docs/tech_design.md](./tech_design.md) | §4/§5 + Changelog 记「dlp_log 平台后端拆分，Mac 待实现」 | 文档 |

---

## Changelog

- 2026-08-08：实现 Mac 后端。确认 root 日志路径、bread 单参数/stdin 用法、纳秒时间戳和
  `dlp audit event` JSON；使用 `sudo -n cat | bread -` 最小权限内存解密，解析
  `eventId`/`appLeak`/`targetFile`，接入文件/截图匹配、报告字段与服务端 event_id 回查；
  block 下因动作映射未标定只回填 eventId、日志保持 `inconclusive`；
  新增 13 项 Mac 专项测试。企业微信三条文件 case 和一条截图 case 的真实
  sudo + bread + eventId + 服务端 audit 放行回查均已验证通过。
- 2026-08-03：初稿。定义平台后端可插拔结构、Windows 后端完整方案（解密+时间窗增量+真事件解析+
  文件/截图判定+字段上报）、Mac stub 与后续落地清单、policy 门控触发、配置分平台子块。
  本期实现范围：**Windows 完整 + Mac stub**。
