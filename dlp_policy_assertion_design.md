# DLP 策略断言（审计 / 阻断）适配设计

> 状态：**分阶段落地中**。**P0 已实现**（`--policy` 开关 + `delivery_outcome` 维度 + aggregator none/audit 分支 + 报告两列，2026-07-29）；**P1 重试联动已实现**（block 下视觉重试改自检话术，方案①′，2026-07-29）；**P1 ②日志分型已实现**（dlp_log 按 policy 选特征 + 产出 `hit_policy_type`，2026-07-29）；**P1 ①aggregator block 判定分支已实现**（`delivery_outcome × 阻断日志` 交叉验证，含情况一/二，2026-07-29）；**P1 全部完成**，P2–P3 仍为设计稿。
>
> **前置阅读**：[tech_design.md](./tech_design.md)（硬约束、验收/报告机制）、[架构图集](./tech_design_diagrams.md)（图 4 聚合策略）。
> 本文属于**框架级改动**设计，落地时需在 tech_design 追加变更记录与硬约束。

---

## 1. 背景与目标

### 1.1 现状

当前框架的验收隐含一个假设：**外发动作成功 = 通过**。
- case 的视觉 `verify` 文案写死"外发成功"语义（如"相比操作前新增了一条刚发出的文件消息…否则判不通过"）。
- 聚合器 [aggregator.py:27](../dlp_auto/verify/aggregator.py) 在 `execution_status ∈ {error, skipped, failed}` 时**直接短路判失败，看都不看日志**。

### 1.2 真实的 DLP 策略有两种后续动作

策略由人**手动在 DLP 管理后台配置**，运行时框架并不知道后台配了什么，需要由**运行方显式告知**本次运行对应的策略：

| 策略 | 外发动作预期 | 客户端日志 | 管理后台审计日志 | 桌面弹窗 |
|------|-------------|-----------|----------------|---------|
| **审计（audit）** | **成功**发出 | 有**审计类**日志 | 有**审计类**记录 | 可能有（频率控制，不保证） |
| **阻断（block）** | **失败**（软件自身提示：卡住 / 外发失败提示） | 有**阻断类**日志 | 有**阻断类**记录 | 可能有（频率控制，不保证） |

**关键洞察（含用户修正）**：审计和阻断都会产生日志，但**日志类型不同**——管理后台里审计记录与阻断记录略有区别，客户端日志同理。所以三处校验的差异是：
- **外发动作**：审计要成功，阻断要失败（成败预期翻转）。
- **客户端日志 / 后台回查**：不能只判"有没有日志"，要判"**是不是对应策略类型的日志**"（审计场景要命中审计类特征，阻断场景要命中阻断类特征）。

这让日志校验从"命中即可"升级为"**命中正确类型**"，是本设计相比初稿的关键强化。

### 1.3 目标

让 case 结果能**根据本次运行配置的策略类型来断言**：
- 审计：外发成功 + 命中**审计类**日志 → 通过。
- 阻断：外发失败（被拦截）+ 命中**阻断类**日志 → 通过。
- 防假阳性（双重）：
  1. 阻断场景下"外发失败"必须是**被 DLP 拦截**，而不是操作自身出错——靠日志命中区分（真拦截有日志，纯操作出错没有）。
  2. 命中的日志必须是**对应策略类型**——审计场景命中了阻断类日志、或反之，说明后台策略与预期不符，不能判通过。

---

## 2. 首要设计原则

1. **策略是「运行级」参数，不是 case 级**（依据需求确认）。
   - 一次运行整体按**一个策略**断言。策略需人工提前在 DLP 后台配好，运行方知道本次要测哪些 case、预期是什么。
   - 不同软件配了不同策略（如微信审计、飞书阻断）→ **分两次运行**，各带各的策略参数。
   - 好处：**不给 CaseSpec 加字段、不下沉 per-case strategy**，case 定义零改动，同一份 case 两种策略都能复用。
2. **case 的视觉 verify 文案不改**。视觉判定只客观回答"外发成没成功"；"这个客观结果是好是坏"交给**策略感知的聚合器**裁定。
3. **执行 ≠ 验收**（延续现有硬约束）。报告继续分列展示"执行结果 / DLP 验收 / 最终结论"，本设计只改变**聚合规则**，不改变分列语义。
4. **零猜测**。策略类型只从运行参数 / config 读，缺失时使用 `none`（见 §6），不启用策略断言；
   拦截日志特征只从 config 读。
5. **增量、可回退**。默认策略 = 现状行为；不传策略参数时结果与今天完全一致。

---

## 3. 运行入口：策略参数

新增 CLI 开关（互斥，默认不指定 = 沿用现状「所有已启用 checker 全过」语义）：

```
--policy audit    # 本次运行断言：外发应成功 + 日志命中
--policy block    # 本次运行断言：外发应被拦截（失败）+ 日志命中
# 不传 --policy → 现状行为（不启用策略感知，等价今天）
```

装配链（对齐现有 [run.py:120-126](../dlp_auto/run.py) / [verify/__init__.py:30-50](../dlp_auto/verify/__init__.py)）：
- `main()` 解析 `--policy`，传给 `build_manager(settings, ..., policy=args.policy)`。
- `build_manager` 把 policy 传入 `VerificationManager(policy=...)`。
- 也支持 config 兜底：`verify.policy`（CLI > config > 默认）。

> 为什么放运行参数而非 case：策略在 DLP 后台是"当前生效配置"，同一批 case 今天测审计、明天测阻断都可能。绑到 case 上会导致改后台配置就要改 case，违背解耦。

---

## 4. 聚合逻辑改造（核心）

改造点集中在 [aggregator.py](../dlp_auto/verify/aggregator.py) 与 [manager.py](../dlp_auto/verify/manager.py)，是本设计**唯一的结构性硬骨头**。

### 4.1 收窄 `execution_status` + 新增 `delivery_outcome` 维度

**动机（P0 修正）**：现状把「AI 有没有把动作做完」和「文件到底发没发出去」混成了同一个 `execution_status`。阻断场景下，「文件没发出去」是**预期结果**，但它会顺着视觉判定冒泡成 `execution_status=failed`，再被 [aggregator.py:29](../dlp_auto/verify/aggregator.py) 的「执行失败即短路判 failed」直接判死——于是**阻断真生效反被判成不通过**。所以不能只加维度，还要把 `execution_status` 的定义改窄。

- **`execution_status`（收窄）**：只回答「**AI 有没有把机械动作做完**」（找到文件、拖入、点了「发送」按钮）。只要动作执行到位就是 `passed`，**哪怕文件根本没发出去**。它只描述自动化健康度，不再承载「外发成功与否」。
- **`delivery_outcome`（新增独立维度）**：`sent / blocked / unknown`，只回答「**文件实际发出去了没有**」。这一维度与 execution 解耦——阻断场景 AI 点完发送（execution=passed）+ 文件被拦（delivery=blocked）是**正常且期望**的组合。
- **绝不把 `execution_status=failed` 当成阻断成功。** 阻断正确的判定来自 `delivery_outcome=blocked` + 阻断类日志佐证，而非执行失败。

> `delivery_outcome` 的来源（P1 待定，落地时确认）：优先由**阻断类日志/软件自身外发失败提示**推断，而非仅靠视觉。视觉在 block 下不可靠（见 §4.5）。

### 4.2 给聚合器传入 policy

`OutcomeAggregator.aggregate(...)` 增参 `policy: str = "none"`（`none` = 现状分支，保证零回归）。
`VerificationManager._aggregate()` 从 `self.policy` 透传。
`delivery_outcome` 与「日志命中类型」各建模为**一路独立校验**，一起喂进上一轮保留的「全过才通过」AND 门（§4.3）。

### 4.3 判定表（policy 感知，`delivery_outcome × 日志` 交叉验证）

判定轴从「exec × 日志」改为「**`delivery_outcome`（文件实际发没发出去）× 阻断/审计类日志**」。日志列区分四态：**命中正确类型**（审计场景命中审计类 / 阻断场景命中阻断类）、**命中错误类型**（命中了另一种策略的日志）、**未命中**、**未启用/缺失**。

| policy | delivery_outcome | 控制面日志 | 最终 status | 说明 |
|--------|------------------|-----------|------------|------|
| **none**（现状） | — | 见 [aggregator.py](../dlp_auto/verify/aggregator.py) 现有分支 | 不变 | 完全回退 |
| **audit** | sent | 命中审计类 | **passed** ✅ | 正常外发且有正确类型日志 |
| audit | sent | 命中阻断类 | failed | 后台配的是阻断？与预期策略不符 |
| audit | sent | 未命中 | failed | 发出去了却没日志 → DLP 失效 |
| audit | sent | 未启用/缺失 | inconclusive | 没开日志验收，不下通过结论 |
| audit | blocked | 任意 | failed | 审计策略下不该被拦，外发失败 → 异常 |
| **block** | blocked | 命中阻断类 | **passed** ✅ | 双证据齐全：没发出去 + 阻断类日志 → 阻断真生效 |
| block | blocked | 未命中 | **inconclusive** | **情况一**：没发出去但缺铁证，无法归因给 DLP（可能网络/软件/AI 出错）→ 不判通过、也不冤枉判失败 |
| block | blocked | 命中审计类 | failed | 有日志但是审计类 → 后台其实没配阻断 |
| block | blocked | 未启用/缺失 | inconclusive | 无日志证据，无法确认是拦截还是操作出错 |
| block | **sent** | **命中阻断类** | **failed** ⚠️ | **情况二（曾遇到的 bug）**：文件已发出（泄露）却命中阻断日志 → **日志无翻案权**，阻断实际失效 |
| block | sent | 命中/未命中 | failed | 该拦没拦住，外发成功 → 阻断失效 ❌ |
| block | unknown | 任意 | inconclusive | 连发没发出去都不确定，无法归因 |

**要点（交叉验证的两条铁律）**：
- **passed 只出现在「`delivery_outcome` 与日志两个维度都指向同一策略」那一格**。任一维度不达标、或两者**互相矛盾**（情况二：一个说 sent、一个说 blocked），都不给 pass。这正是上一轮保留「全过 AND 门」、删掉 `any_pass` OR 门的直接收益——否则「日志命中」单独一路就能把泄露 case 拉成通过，复现老 bug。
- **日志绝不能单独给 case 翻案**：日志只证明「DLP 记了一笔」，不证明「文件真被拦住」。情况二里文件已 `sent`，无论日志命中什么都判 failed。
- **情况一（阻断但无日志）判 inconclusive 而非 failed**：缺铁证时「阻断生效」这个结论立不住，但也不能冤枉判失败——按「无证据不判通过」记 inconclusive，提示补日志路径/重跑。
- **命中错误类型**：命中了但类型不对，说明后台实际策略与本次运行声明不符，判 failed 并在 issue 点明「实际命中 X 类日志，与预期 Y 不符」。
- block 的核心仍是**推翻 [aggregator.py:29](../dlp_auto/verify/aggregator.py) 的「exec 失败即判 failed」短路**——但推翻的方式是「不再用 exec 表达外发结果」，改由 `delivery_outcome` 承载（§4.1）。

> **✅ 已落地（2026-07-29，P1 ①aggregator block 判定分支）**：[aggregator.py](../dlp_auto/verify/aggregator.py) `_aggregate_block` 与 audit 分支对称，按 `delivery_outcome` 分派：
> - `error/skipped` → 短路保留其自身状态（验收零副作用）。
> - `delivery=sent` → **failed**（情况二：文件已发出=泄露，日志无翻案权，**不看 checks 直接判失败**）。
> - `delivery=blocked` → 复用「全过才通过」AND 门 [`_aggregate_checks`](../dlp_auto/verify/aggregator.py)，只看 dlp_log 的统一 `status`。
> - 其余（unknown/空） → **inconclusive**（连拦没拦住都不确定）。
>
> **关键：聚合器不读 `hit_policy_type`**（对齐 [architecture_review_notes.md](./architecture_review_notes.md)「聚合器不应读取 checker 内部字段」）。「命中的是审计类还是阻断类」这个类型对错判断**定死在 checker**——`_check_typed` 已把「命中阻断类=passed / 命中审计类=failed（错配）/ 未命中=inconclusive（情况一）」编码进统一 `status`，聚合器沿用 AND 门即自然收敛出判定表 6 行。故 §4.4 里「未命中」的语义按策略分流：**block 未命中→inconclusive**（情况一，缺阻断铁证不冤枉判失败）；**audit 未命中→failed**（应留审计痕却没有=失效）。
> 判定表全部 6 行 + 情况一/二 + 短路已落 [test_p0_guards.py](../tests/test_p0_guards.py) `PolicyAggregatorTests`（block 6 项）+ `LogPolicyTypingTests`（未命中分流 2 项），全套 56 测试绿。

### 4.4 日志 checker 如何区分策略类型

日志类型的区分**下沉到 checker**，聚合器只消费 checker 产出的结论（保持聚合器纯粹）。改造 [dlp_log.py](../dlp_auto/verify/dlp_log.py) 与 [server_event.py](../dlp_auto/verify/server_event.py)：

- checker 从 manager 获得当前 `policy`，据此选用**对应策略类型的匹配特征**。
- checker 的 `CheckOutcome` 除 `passed/failed`，在 `evidence` 里额外记录**实际命中的日志类型**（`hit_policy_type: "audit" | "block" | None`），供聚合器判断"命中正确类型 / 错误类型"。
- 语义细化（对齐现有 [dlp_log.py:110-118](../dlp_auto/verify/dlp_log.py) 的 passed/failed）：
  - 命中当前 policy 对应特征 → `passed` + `hit_policy_type=当前policy`。
  - 命中了另一种 policy 特征 → `failed` + `hit_policy_type=另一种`（证据仍记录，便于诊断后台配置错位）。
  - 都没命中 → **按策略分流**：`audit`→`failed`（应留审计痕却没有=失效）；`block`→`inconclusive`（情况一，缺阻断铁证不冤枉判失败）。无特征配置 → `inconclusive`（同现状）。

> 若后续真机确认审计/阻断日志特征其实**无法区分**（比如同一条记录、只是后台展示不同），则退化为"命中即可"，`hit_policy_type` 记 `unknown`，判定表中"命中错误类型"行不触发。这条留给 P3 真机验证。

> **✅ 已落地（2026-07-29，②日志分型）**：`policy` 经 [manager.py](../dlp_auto/verify/manager.py) `on_case_start` 注入 [outcome.py](../dlp_auto/verify/outcome.py) `CheckContext.policy`（manager 注入，runner 不感知），[dlp_log.py](../dlp_auto/verify/dlp_log.py) `check()` 据此分派：
> - **分型模式**（policy=audit/block 且配了任一 `*_audit_*`/`*_block_*` 特征）：命中当前类型→`passed`+`hit_policy_type=当前`；命中另一类型→`failed`+`hit_policy_type=另一种`；**未命中按策略分流**（`audit`→`failed`、`block`→`inconclusive`，均 `hit_policy_type=None`）；**当前策略特征缺失→`inconclusive`（绝不回退通用特征假通过）**。
> - **兼容模式**（policy!=none 但只配通用 `contains/regex`）：命中→`passed`+`hit_policy_type=unknown`。
> - **零回归**（policy=none）：走通用特征，evidence **不写** `hit_policy_type`，与历史逐字节一致。
> - 配置合法性：[build_manager](../dlp_auto/verify/__init__.py) 对非法 `verify.policy` 值（如拼错）**抛错**，不静默回退 none。
> - **本步不碰 aggregator / server_event**：`hit_policy_type` 仅由 checker 产出落 `evidence`，消费它属下一步「block 判定分支」；服务端接口未接入，不写预留代码（真机就绪时按 §4.6 在指纹加 `disposition` 键即可）。

### 4.5 视觉判定与 block 模式下的重试联动

- 现状：视觉只"记录一列"，不进聚合（[manager.py:87-89](../dlp_auto/verify/manager.py) 的 expected_names 不含 visual）。
- 本设计**沿用现状**：视觉仍只记录、不进聚合。原因：
  - audit：视觉"外发成功"= `delivery_outcome=sent` 层已表达。
  - block：软件的"外发失败提示"形态各异，视觉文案不稳定；用 `delivery_outcome` + 阻断日志更可靠。
- **重试联动（P1 关键缺口，必须一并改）**：视觉「不进聚合」还不够——agent 内部的**重试**也吃视觉结论。见 [agent.py:104-113](../dlp_auto/core/agent.py)，当 `retry_on_verify_fail=True` 且视觉验收未通过时，会回灌「任务尚未完成，请继续操作」逼 AI **重发**。而 block 场景下：
  - case 的视觉 verify 文案写的是「外发成功」语义 → 文件被拦（正确！）→ 视觉判 failed → **触发重试逼 AI 反复外发** → 耗光 `max_verify_retries` → 最终 `verify_status=failed`。
  - 后果：**阻断真生效反被重试拖成 failed**，且白烧步数。这是纯加 `delivery_outcome`、只改聚合器**救不回来**的——重试发生在 agent 内、远早于聚合。
  - 落地要求：`policy` 必须**透传到 agent/verify 层**，在 block 模式下**关闭或翻转**「成功语义的视觉重试」。三选一（P1 落地时定）：
    1. block 下直接令 `retry_on_verify_fail=False`（阻断结果不可能靠重发改变，重试无意义）；
    2. block 下视觉判据**翻转**为「确认出现外发失败/被拦提示」；
    3. block 下 agent 完全不做视觉 verify，外发结果全交给 `delivery_outcome` + 日志。
  - **✅ 已落地（2026-07-29，方案 ①′「自检话术」）**：`policy` 透传进 [agent.py](../dlp_auto/core/agent.py) `do()`；视觉重试**保留**（不硬关），但把回灌话术从「继续操作达成目标」（诱导重发）改为 `_retry_hint(reason, "block")` 的**自检话术**——只让模型确认「外发动作本身是否到位」：真没做完（拖拽没到位/点歪）则补做，已做完就 finished、**绝不重复发送**。
    - 相比①（硬关）的取舍：①′ **保留了对「机械动作没做到位却误报 finished」的恢复能力**（用户关注点：拖歪/点偏），同时不再逼 AI 反复外发文件。
    - 未选②/③：②的「被拦提示」文案各异不稳定（§4.5 已论证不可靠）；③会丢视觉证据列且把 `delivery_outcome` 退化成 unknown。
    - 零回归：`none`/`audit` 保持历史话术逐字节不变；[runner.py](../dlp_auto/case/runner.py) `_run_step` 透传 `self.verifier.policy`，block 抑制时打印一行可观测日志。
- 弹窗：**只记录不断言**（见 §5）。
  > 溯源：即 [architecture_review_notes.md](./architecture_review_notes.md) 「推荐的精简方案」第 6 条「暂缓弹窗记录」。本设计把该临时决定正式定级为 §7 的 **P2（未开始）**——语义一致：弹窗因频控不参与断言，末步截图已能留证据，视觉识别收益低。

### 4.6 配置 schema（按策略区分日志特征）

沿用现有 `verify.dlp_log` 结构（[dlp_log.py:131-139](../dlp_auto/verify/dlp_log.py) 的 `build_dlp_log_checker`），在 `default_*` / `cases.<id>` 两级都支持**按策略类型分特征**。向后兼容：只写 `contains/regex`（不分类型）时退化为"命中即可"。

```yaml
verify:
  policy: audit          # 可选；CLI --policy 优先。none(默认)/audit/block
  dlp_log:
    path:
      mac: /Users/.../dlp_client.log
      windows: C:\...\dlp_client.log
    # ① 不区分类型（现状写法，向后兼容）：命中即 passed，hit_policy_type=unknown
    default_contains: "outbound file"
    # ② 按策略类型分特征（本设计新增）：审计/阻断各自的日志指纹
    default_audit_contains: "action=AUDIT"       # 审计类特征
    default_block_contains: "action=BLOCK"       # 阻断类特征
    default_audit_regex: null
    default_block_regex: null
    cases:
      case_feishu_drag_send:
        audit_contains: "file_id=... level=L3 action=AUDIT"
        block_contains: "file_id=... level=L3 action=BLOCK"
```

- checker 按当前 policy 选用 `*_audit_*` 或 `*_block_*` 特征；同时用**另一种**特征做"命中错误类型"检测（§4.3）。
- 服务端回查（[server_event.py](../dlp_auto/verify/server_event.py)）同理：预期事件指纹里带 `disposition: audit|block` 字段，`_fingerprint_hit` 已按非下划线键匹配，加一个键即可，无需改匹配逻辑。


---

## 5. 报告改造

### 5.1 新增列（对齐 [writer.py:19-24](../dlp_auto/report/writer.py) 的 `_CSV_HEADER`）

在现有列基础上追加：

| 新列 | 来源 | 含义 |
|------|------|------|
| **预期策略** | run 参数 policy | 审计 / 阻断 / 未指定 |
| **外发结果** | `delivery_outcome` | 已发出 / 被拦截 / 未知——判定的核心维度（§4.1），与「执行结果」分列 |
| **拦截弹窗** | 视觉观察（可选） | 是否观察到桌面弹窗（是/否/未观察）——**仅记录，不参与断言**（频率控制，未弹不代表失效） |

- `CaseReport` 加字段：`expected_policy: str = ""`、`delivery_outcome: str = ""`；`extras["popup_observed"]` 记录弹窗观察结果。
- `expected_policy` 由 runner 从 manager/context 注入到每个 rep；`delivery_outcome` 由 agent/verify 层推断后写入。

### 5.2 语义不变

`execution_status / verification_status / status` 三列语义不变（`execution_status` 按 §4.1 收窄为「动作是否做完」）；`status` 的计算规则被 policy + `delivery_outcome` 影响。人读报告时可从"预期策略 + 执行结果 + 外发结果 + 日志判定"四列还原出为什么最终是通过/不通过。

---

## 6. 默认值与回退

- **不传 `--policy`** → `policy="none"` → 聚合器走现有分支，**行为与今天逐字节一致**（关键回归保证）。
- **传 `--policy audit/block`** → 自动挂载客户端本地日志 checker，无需再加 `--check-log`。
- `--check-log` 仅为兼容旧脚本保留：`policy=none` 时即使传入也会被忽略；它不能独立开启
  日志校验，也不能关闭策略自动启用的日志校验。
- 日志 checker 命中失败或证据不足时仍按判定表得到 `failed/inconclusive`，禁止因为自动启用
  就生成假通过。

---

## 7. 分阶段计划

| 阶段 | 范围 | 改动点 | 复杂度 | 进展 |
|------|------|--------|--------|------|
| **P0** | 骨架 + 审计 + 维度拆分 | `--policy` 开关；**`execution_status` 收窄 + 新增 `delivery_outcome` 维度**（§4.1）；aggregator 加 `policy` 参数 + `audit`/`none` 分支；manager 透传；报告加"预期策略/外发结果"列 | 中 | **✅ 已落地（2026-07-29）** |
| **P1** | 阻断断言 + 日志分型 + 重试联动 | ~~aggregator `block` 分支（按 `delivery_outcome × 日志` 交叉验证，含情况一/二，见 §4.3）~~ **✅ 已落地（2026-07-29，①，见 §4.3 落地小结）**；~~dlp_log 支持 `*_audit_*`/`*_block_*` 特征选择 + `hit_policy_type`；命中错误类型判定~~ **✅ 已落地（2026-07-29，②，见 §4.4）**；~~**policy 透传 agent、block 下关闭/翻转视觉重试**（§4.5）~~ **✅ 重试联动已落地（2026-07-29，方案①′）**；启动告警（build_manager 非法 policy 抛错）✅；判定表落测试 ✅ | 中～大（硬骨头） | **✅ P1 全部完成（2026-07-29）**：重试联动 + ②日志分型 + ①block 判定分支，判定表 6 行 + 情况一/二落测试，全套 56 测试绿。server_event 分型待接口接入（P3）；delivery 来源在 block 下由视觉推断（阻断日志/软件失败提示的进一步精化留 §4.1 待定项） |
| **P2** | 弹窗记录（= review「精简方案」第 6 条「暂缓弹窗」） | 视觉观察弹窗写入 `extras["popup_observed"]` + 报告"拦截弹窗"列（仅记录） | 小 | 未开始 |
| **P3** | 真机特征标定 | 真机采集审计/阻断两种客户端日志与后台记录样本，确认特征差异，填入 config 的 `*_audit_*`/`*_block_*`；若确认无法区分则退化 `unknown` | 中 | 依赖真机日志样本 |

> P0 的关键是先把 `delivery_outcome` 从 `execution_status` 里拆出来——这是所有阻断判定的地基，晚拆会返工。P1 已把"按类型选特征 + hit_policy_type + 重试联动"纳入实现（schema 先就位、可用占位特征跑通逻辑）；P3 是把占位换成真机标定的真实特征。若真机确认审计/阻断日志**无法区分**，P1 逻辑自动退化为"命中即可"（`hit_policy_type=unknown`），不返工。

---

## 8. 需同步更新的文档与测试

落地时（非本次）：
- [tech_design.md](./tech_design.md)：§3 验收层补 policy 说明；§4 硬约束新增一条（策略断言从运行参数读、不臆测、block 无日志证据不判通过）；Changelog 记录。
- [tech_design_diagrams.md](./tech_design_diagrams.md)：图 4（结果聚合策略）补 policy 分支。
- [tests/test_p0_guards.py](../tests/test_p0_guards.py)：现有「全过守卫」测试（`test_requires_every_expected_check_passed`）保持；新增 audit/block 判定表测试。
- [AGENTS.md](../AGENTS.md)：硬约束速查表补一行。

---

## 9. 开放问题（待确认后落地）

1. 阻断时"软件自身外发失败提示"是否需要视觉确认，还是纯靠 `delivery_outcome` + 日志即可？（本设计倾向后者，见 §4.5）
2. ~~审计与阻断的客户端日志特征是否不同？~~ **已确认后台审计/阻断记录略有区别**（用户反馈）→ 客户端日志与服务端回查都按类型校验（§4.4/§4.6）。剩余待办：真机标定两类特征的**具体字段**（P3）。
3. `delivery_outcome` 的判定来源在 block 下如何最稳？（候选：阻断类日志 / 软件外发失败提示 / 两者结合）——见 §4.1 待定项，P1 落地时确认。
4. `--policy` 是否需要支持第三种 `none-required`（软件本身无需 DLP 管控）？暂不纳入，需要时再加。
