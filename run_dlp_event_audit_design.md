# Run 级 DLP 事件审计（疑似误报旁路）设计

> 已归档（2026-08-17）：CHG-020 已实现，编码/测试/文档均已同步，稳定约束（默认关 /
> 不改结论 / `collect_events` 接口）已上移 [tech_design.md](../tech_design.md) §5 与 Changelog；
> 本稿转为只读历史留存，保留完整设计推导供追溯，后续如重启须另立改动 ID 与新设计稿。
>
> **状态**：**已实现（2026-08-13，CHG-020）**。用户确认三条核心口径（旁路只观测 / 截图重试计
> `expected_retry` / 进程名只记录不硬匹配）后完成编码、测试与文档同步。稳定约束已上移
> [tech_design.md](../tech_design.md)（§5 扩展点 + Changelog）；本稿保留完整设计推导供追溯。
> **定位**：在一次 run 的时间窗内，全量扫描 DLP 客户端本地日志产生的事件，用「预期事件台账」
> 反向筛出**没有任何 case 能解释**的 DLP 事件，单独输出「疑似误报列表」。
> **底线**：这是**旁路诊断能力**——只新增独立产物，**不修改**任何现有 case 的
> `execution_status` / `delivery_outcome` / `verification_status` / 最终 `status`，也不改退出码。
> **默认关、可整体删除**：不传开关时行为与不引入本能力完全一致（对齐硬约束 #11、AGENTS §1.2）。
> **前置阅读**：[tech_design.md](../tech_design.md)（硬约束 #1 零猜测 / #3 字节偏移 / #6 验收零副作用 /
> #10 执行成功≠DLP 有效）、[dlp_client_log_verify_design.md](../dlp_client_log_verify_design.md)（两端日志后端）。

---

## 1. 背景与目标

现有验收只回答「**本 case 期望的那条外发事件在不在**」（本地日志按唯一文件名/图片类型命中，服务端按
`event_id` 精确回查）。它是**逐 case、正向**的：只关心「我要的事件有没有出现」。

但它**看不到**另一类问题：一次 run 期间，DLP 客户端可能产生**我们没有预期到**的外发事件——
可能是被测软件的后台行为、测试机上人工/系统操作、或某条 case 触发了计划外的第二次外发。
这些事件如果本应被拦截却放行、或本应无事却告警，就是**潜在误报/漏报**，当前框架完全不记录。

**设计目标**：

1. **记录真实 run 边界**：测试开始时间、所有 case 执行结束时间、事件窗口封口时间。
2. **登记预期事件**：每条 case 在会产生外发的 step 上，登记它「预期制造哪些 DLP 事件」
   （文件类按唯一文件名，截图/图片类按 step 时间窗），形成**预期事件台账**。
3. **run 结束后全量扫描**：在 run 时间窗内收集两端后端解析出的**全部**真实 DLP 事件，
   用预期台账逐条解释；解释不了的进入**疑似误报列表**。
4. **单独输出、旁路呈现**：疑似误报只写独立 JSON/CSV 产物 + 控制台一行汇总，**不污染**主报告结论。

**非目标（本期不做）**：

- 不判定疑似事件「究竟是误报还是漏报」——只负责**筛出无法解释的事件**供人工复核。
- 不解析事件的命中规则/命中内容/人员设备等字段级细节（那是 `CHG-003` / 回归 B 级的范畴）。
- 不用进程名做硬匹配（当前截图验收不依赖进程名，真机映射未核实前不臆测，硬约束 #1）。

---

## 2. 首要原则：旁路、默认关、零猜测

- **旁路零副作用**：本能力**不注册为 checker**，不进入 `expected_names`，因此不参与
  [OutcomeAggregator](../../dlp_auto/verify/aggregator.py) 的任何 AND 门判定；不改 case 结论（硬约束 #6）。
- **默认关、可整体删除**：由独立开关 `--scan-unexpected-events` 控制，默认关闭；
  删除新增模块后 `run` 行为与现在完全一致。
- **零猜测**：日志路径、marker、图片扩展名、轮转文件、落盘缓冲等**只从 config 读**；
  缺配置时扫描记 `inconclusive` 并提示补哪些字段，不臆测（硬约束 #1）。
- **字节偏移 / 时间窗**：复用两端后端既有的「解密 → 时间窗过滤」，不做全量裸扫（硬约束 #3）。

### 2.1 真正的硬约束 vs 可选防御

本能力**天然不影响主流程**：case 结论由 aggregator 算完并落盘之后，扫描才在末尾执行；
扫描是纯读日志 + 写两个独立文件的旁路动作，即使整个崩掉也改不动已算出的 case 结论。
基于这个前提，明确区分「必须做」和「做了更稳妥」：

**硬约束（不做会出真问题）：**

1. **顺序**：run 级事件扫描必须排在**主报告持久化之后**——绝不能插在 writer 前面，否则才可能真弄丢主报告。
2. **失败标 `inconclusive`、不冒充干净**：若扫描只跑了一半（如某一端后端抛错），列表可能「看起来干净」
   但其实没扫全；此时必须标 `inconclusive` 并说明原因，**不得**把「没扫完」冒充成「没发现问题」（硬约束 #10）。

**可选防御（做了更稳妥，不做也不影响 case 结论与主报告）：**

- 用 try/except 包住 auditor 调用：**唯一收益**是避免一个纯诊断功能崩溃时，让整条命令带着 traceback
  **非零退出**（case 全过、也写盘了，命令却对 CI/脚本显示「失败」）。这只关乎退出码体面，**不涉及**保护结论，
  故列为可选防御而非硬要求。
- 预期登记内联在 case step 里（热路径），本质只是「往 list 里 append 一个对象」，几乎不会抛；
  对它做防御是「别让一个记账小 bug 拖垮真 case」，同样属可选防御，与保护主流程无关。

---

## 3. Run 时间边界

现有 [RunReport](../../dlp_auto/report/schema.py) 已有 `started_at/finished_at`，但 `finished_at`
当前在服务端回查前后写入，语义不够精确。本能力显式记录四个时间点：

| 时间点 | 含义 |
|---|---|
| `run_started_at` | 第一条 case 执行前 |
| `actions_finished_at` | 最后一条 case 及 app teardown 执行完毕 |
| `event_window_finished_at` | 在 `actions_finished_at` 基础上再等一次落盘缓冲（settle） |
| `run_finished_at` | 本地扫描、服务端回查、最终报告全部完成 |

**事件扫描窗口**取：

```
run_started_at  <=  event_time  <=  event_window_finished_at
```

刻意**不**把可能长达数十秒的服务端回查等待算进事件窗口，避免把回查期间无关的后台事件卷进来。
`event_window_finished_at = actions_finished_at + verify.run_event_audit.final_settle_sec`。

---

## 4. 预期事件登记

给「可能产生 DLP 事件」的 `Step` 增加一个默认空的元数据（未标记的 step 行为完全不变）：

```python
DlpExpectation(kind="file")    # 文件外发：可用唯一文件名精确归属
DlpExpectation(kind="image")   # 截图/图片外发：只能按 step 时间窗归属
```

Runner 仅对被标记的 step 记录：

- `case_id`
- step 开始时间、结束时间（构成该 step 的「事件发射窗口」）
- 预期类型 `file` / `image`
- `sensitive_file`：文件类复用现有唯一文件名（run_id 级唯一）
- 实际匹配到的事件 UUID、进程名、文件名（扫描阶段回填）

登记在**共享工厂层**统一标注（IM / 浏览器 / AI 对话共享脚手架各自的发送 step），
不要求每条 case 重复实现；这样新增 case 自动获得登记能力。

---

## 5. 截图重试的处理

截图外发日志通常只有固定名 `screenshot.png`，**无法**像文件那样生成并匹配唯一文件名。
若一条截图 case 中途重试（AI 纠错重拍/重发），会产生**多条**图片事件，不能简单当误报。处理如下：

1. 以截图发送 step 的**整个执行区间**作为「事件发射窗口」。
2. 窗口内所有**图片类型**事件都归属到该 case。
3. 第一条标记 `expected`。
4. 其余标记 `expected_retry`，逐条记录第 2/3… 次尝试及各自 UUID、实际文件名。
5. 落在 step 结束之后的落盘缓冲区、且无法唯一归属的图片事件标记 `ambiguous`
   （原因注明「可能是截图重试或延迟落盘」）。
6. `ambiguous` 进入疑似误报列表——**不**把明确重试直接判成误报，也**不**静默吞掉边界不清的事件。

---

## 6. 事件归类优先级

run 结束后，两端后端**一次性**收集窗口内全部真实 DLP 事件，按 UUID 去重，逐条按优先级归类：

1. 事件 UUID 已被某 case 的 checker 命中 → `expected`
2. 事件唯一文件名与某 case 的 `sensitive_file` 精确匹配 → `expected`
3. 同一唯一文件名出现多次 → 首条 `expected`、其余 `expected_retry`
4. 图片事件落在某个已标记截图 step 的发射窗口内 → `expected` / `expected_retry`（见 §5）
5. 可能同时匹配多个窗口，或仅落在延迟缓冲区无法唯一归属 → `ambiguous`
6. 没有任何预期登记能解释 → `unexpected`

进程名**只记录不硬匹配**（真机映射未核实，硬约束 #1）。

### 6.1 事件行 vs 批量管理汇总行（真机边界，2026-08-14 修）

归类的前提是「进来的每条都是一次真·外发事件」。但真机复核发现：`event_marker`
（`dlp_event_upload_handler.cpp`）这个「行首锚」只锁定**源文件位置**，能挡住宿主 shell
回显（那是 `ndlp_svc_mgr.cpp`），却**挡不住同一个 cpp 自己打的管理型汇总行**。真实日志
实测：同一 marker 命中 **3554 行，其中仅 1 行是真事件**，其余 3553 行是三类批量汇总——
`start upload dlp event, size:N` / `upload dlp batch, db loaded:... batched:...` /
`upload associate tag size:N`，它们**既无事件UUID、也无 origin file path**。

- **为何 case 级 `check()` 不受影响**：它靠 `_match(origin_file_path)` 命中唯一文件名/图片
  扩展名，空 path 的汇总行天然被滤掉，故此坑一直未暴露。
- **为何审计会中招**：§6 规则 6 兜底把「无任何预期能解释」的事件判 `unexpected`；这些汇总行
  无 UUID（规则 1 跳过）、无匹配文件名（规则 2/3 跳过）、非图片（规则 4/5 跳过），全部落进
  规则 6 → 3553 条噪声涌入疑似误报 CSV，产物直接失去可用性。
- **修复（旁路内、零回归）**：只在**审计专用**的 `collect_events`（Windows 后端）里追加一道
  过滤——**丢弃「既无事件UUID 又无 origin file path」的行**。两者皆空的行对 §6 任何一条
  归类规则都无信息量，安全丢弃；case 级共用的 `_collect_events` 不动，`check()` 逐字节不变。
  真机复验：修复前 2 分钟窗即扫出 8 条全判 `unexpected`（皆噪声），修复后 30 分钟窗
  `total=0 / unexpected=0`。回归测试见 `tests/test_dlp_log_windows.py::CollectEventsNoiseFilterTests`。

### 6.2 Mac 端为何无需同款过滤（真机实测，2026-08-14）

有了 Windows 这个坑，自然要问：**Mac 端 `collect_events` 会不会有同类噪声？** 结论是
**不会**，且已用本机现有全量日志（无需新跑 case）实测坐实——根因在于**两端 marker 的语义层级不同**：

- **Windows 的 marker 是源文件名** `dlp_event_upload_handler.cpp`：同一个 cpp 既打「单条外发
  事件」又打「批量上传汇总」，marker 区分不了二者，故汇总行混入、需在 `collect_events` 末尾兜底过滤。
- **Mac 的 marker 是语义标签** `dlp audit event:`（[_mac.py](../../dlp_auto/verify/dlp_log/_mac.py)
  `_collect_events` 第一步 `if self.event_marker not in line: continue`）：它**只在真正产生一条
  audit 事件时才打**，管理/扫描/批处理行用的是别的前缀，marker 本身就是干净的语义边界。
- 叠加解析器 `parse_mac_event_line` 的**三道前置硬门槛**（category 精确等于 `EDLP:DLP` +
  marker 之后必须是**合法 JSON** + `eventId` 必须是**合法 UUID**，任一不过直接 `return None`）：
  Windows 那种 `start upload dlp event, size:N` 纯文本汇总行，在 Mac 这套链路里连第一步 marker
  都过不了，更谈不上进事件列表。**等价的严格性 Windows 靠末尾兜底过滤实现，Mac 前置在解析里就完成了。**

**实测数据（本机 31 个 `edlp.*.log`，覆盖 2026-08-11 ~ 08-13 约两天）：**

| 维度 | Mac 实测 | Windows（§6.1 实测） |
|---|---|---|
| 含 `category=EDLP:DLP` 的行 | 累计 **数十万行**（每文件数千~八千）| — |
| 含 `marker=dlp audit event:` 的行 | **仅 14 行**（散落 6 个文件）| 3554 行（单窗口）|
| 其中能解析成真事件（带合法 UUID）| **14 行（100%）** | 1 行 |
| **含 marker 但非真事件（= 需过滤的噪声）** | **0 行** | 3553 行 |

关键对比是「几十万行 `EDLP:DLP` 管理噪声 vs 仅 14 行 `dlp audit event:`」：Mac 日志里**同样存在**
海量 EDLP 扫描/管理行，但它们**不带审计 marker**，在解析第一步即被滤除，根本到不了归类逻辑。

**结论**：Mac 端 `collect_events` 不需要照搬 Windows 的「无 UUID/无 path」兜底过滤——**补了也是
死代码**（没有无 UUID 的行能进来）。**限定**：本次样本里 14 条真事件均为正常 L1 audit 事件，
未覆盖真实「疑似误报」形态；「Mac 在误报场景下的表现」仍需一次真机 `--scan-unexpected-events`
跑出 `unexpected` 产物才能盖棺。此处证明的是「**Mac 的 marker + 解析链能把海量管理噪声挡在门外**」。

---

## 7. 输出产物

**不改**现有主 CSV 和飞书多维表格，新增两个本地产物（写入 run 的报告目录）：

```
reports/<run_id>_dlp_event_audit.json      # 完整台账
reports/<run_id>_unexpected_dlp_events.csv # 仅 ambiguous + unexpected
```

`*_dlp_event_audit.json` 保存完整台账：

- run 四个时间点
- 扫描状态：`completed` / `inconclusive`（+ 原因）
- 全部事件及其分类 `expected` / `expected_retry` / `ambiguous` / `unexpected`
- 汇总计数：总事件数、预期数、重试数、模糊数、疑似数

`*_unexpected_dlp_events.csv` 只输出 `ambiguous + unexpected`，列：

```
事件时间、事件UUID、进程、文件名、原始路径、分类原因、
当时执行的 case_id、最近 case_id、原始日志摘要
```

控制台追加一行汇总（示例）：

```
DLP 事件审计：总计 12，预期 9，重试 1，模糊 1，预期外 1（详见 <run_id>_unexpected_dlp_events.csv）
```

---

## 8. 组件边界与后端接口

- 新增独立组件 `RunEventAuditor`：编排「读预期台账 → 调后端收集事件 → 归类 → 写产物」。
  **不**注册为 checker，**不**进入 `expected_names`，因此对 [aggregator.py](../../dlp_auto/verify/aggregator.py) 零影响。
- 两端后端各增加一个统一只读方法：

```python
collect_events(window_start, window_end) -> list[DlpEvent]
```

  - Windows：沿用「全量解密 → 按明文时间窗过滤」；
  - Mac：沿用 `sudo -n cat <log> | bread -` 解密后按时间窗过滤；
  - 路径、marker、扩展名、轮转文件**只从 config 读**。

---

## 9. 开关与配置

新增 CLI 开关，默认关闭：

```
--scan-unexpected-events
```

即使未传 `--policy` 也可生成诊断列表（纯观测），但**不得**据此产生任何 DLP 通过结论
（`inconclusive/mock/skipped` 绝不生成生产通过结论，硬约束 #10）。

落盘缓冲配置（与现有服务端「5 秒 × 3 次」量级对齐，不另猜等待时间）：

```yaml
verify:
  run_event_audit:
    final_settle_sec: 15
```

---

## 10. 待用户确认的核心口径

1. **旁路**：疑似误报列表只旁路输出，**不影响** case 最终结论与退出码。
2. **截图**：截图 step 内多条图片事件视为**预期重试**，边界不清者进 `ambiguous`（不直接判误报）。
3. **进程名**：初期只记录、不作硬匹配依据。

---

## 11. 实施与验证（确认口径后再执行）

实施时新增 `CHG-020`，同步 `tech_design.md`（新增可选能力/数据流）、图集、README、config 模板。
核心测试：

- 唯一文件正常匹配为 `expected`；
- 同名文件重复发送归 `expected_retry`；
- 截图一次 / 截图多次重试；
- 延迟截图事件归 `ambiguous`；
- 真正无归属文件归 `unexpected`；
- 日志轮转、UUID 去重、窗口上下边界；
- 扫描排在主报告持久化之后（硬约束 1）；扫描只跑一半时标 `inconclusive` 不冒充干净（硬约束 2）；
- **开关关闭时，现有行为与主报告完全不变（零回归）**。
