# 架构 Review 临时笔记（冗余 / 臃肿风险排查）

> 状态：**临时存放**，非正式方案。用于记录一次针对「当前最新架构 + 后续策略断言方案」的
> 冗余排查结论，供后续决定是否落地整改。整改动手前请再确认；结论稳定后可并入
> [tech_design.md](./tech_design.md) 或删除本文件。
>
> 审查时点：现有 23 项单测全部通过；本次仅 Review，未改任何代码。

---

## 总体判断

主链路 `RunContext → Runner → Agent → Checker → Aggregator → Writer` 边界清晰、**不臃肿**。
真正的臃肿风险来自两类：**未接线的半成品模块**，以及**后续方案把「观察结果」硬塞进「执行状态」**。
按下面清单收敛即可，无需扩大架构。

---

## 按严重度排序的问题

### P0 · 阻断方案不应复用 `execution_status=failed` —— ✅ 已落地（2026-07-29）

- 现象：策略断言设计稿准备把「执行失败 + 命中阻断日志」直接翻译成 `passed`
  （[dlp_policy_assertion_design.md](./dlp_policy_assertion_design.md) §4.2）。
- 风险：当前 `execution_status=failed` 是**多义**的——可能是 DLP 正确阻断，也可能是
  AI 没点中 / UI 定位失败 / Judge 没看到发送成功 / 达到 max_steps。
  来源见 [runner.py:181-197](../dlp_auto/case/runner.py) 与 [agent.py:114-130](../dlp_auto/core/agent.py)。
  把「执行失败」翻译成「测试通过」会破坏「执行状态只描述自动化健康度」这条最清晰的边界。
- 建议：新增一个**独立的外发结果观察维度**，不要动 execution 语义：

  ```text
  execution_status: passed / failed / error        # 自动化本身是否正常
  delivery_outcome:  sent / blocked / unknown       # 外发实际结果（新增）
  ```

  阻断正确的判定应为：`execution_status=passed` + `delivery_outcome=blocked` +
  `dlp_log=passed`（阻断类）→ 最终 passed。**绝不把执行失败当成通过。**
- **已细化进设计稿（2026-07-27）**：设计稿 §4.1 已改为「收窄 `execution_status` + 新增 `delivery_outcome`」；
  §4.3 判定表改按 `delivery_outcome × 日志` 交叉验证，覆盖两个边缘 case——
  **情况一**（阻断但无日志 → inconclusive，不冤枉判失败）、**情况二**（没阻断但有日志 / 文件已发出却命中阻断日志 →
  failed，**日志无翻案权**）；§4.5 补了「block 下必须联动关闭/翻转 agent 的视觉重试」（见 [agent.py:104-113](../dlp_auto/core/agent.py)，
  否则阻断生效会被重试拖成 failed）。
- **已落代码（2026-07-29，P0 范围）**：`CaseReport` 加 `expected_policy`/`delivery_outcome`
  维度；`OutcomeAggregator.aggregate()` 加 `policy` 参数——`none` 分支逐字节回退现状（零回归），
  新增 `audit` 分支消费 `delivery_outcome` 走 §4.3 判定表；`block` 分支 P0 暂占位为 inconclusive（属 P1）；
  `VerificationManager` 持 `policy` 并从视觉推断 `delivery_outcome` 透传；`run.py` 加
  `--policy audit|block` CLI（不传=none）+ block 缺日志告警；CSV / Lark Base 加「预期策略 / 外发结果」两列。
  新增 10 项策略聚合守卫测试（含 none 零回归、audit 判定表、block 占位），全套 36 测试绿。
  见 tech_design Changelog 2026-07-29。
- **重试联动已落地（2026-07-29，方案①′「自检话术」）**：`Agent.do()` 加 `policy` 参数，
  block 下把视觉重试的回灌话术从「继续操作达成目标」改为「自检外发动作是否到位、别重发」
  （`Agent._retry_hint`）；`runner` 透传 `verifier.policy`。既保留「拖歪/点偏后误报 finished」
  的恢复能力，又不逼 AI 反复重发。新增 `RetryHintPolicyTests` 4 项，全套 40 测试绿。
- **②日志分型已落地（2026-07-29）**：`CheckContext` 加 `policy`（`VerificationManager.on_case_start`
  注入，runner 不感知）；`dlp_log` 按 policy 选 `*_audit_*`/`*_block_*` 特征，产出 `hit_policy_type`
  （命中当前/另一类型/缺失分别 passed/failed/inconclusive，绝不回退通用特征假通过）；`build_manager`
  对非法 policy 抛错。新增 `LogPolicyTypingTests` 7 项 + `PolicyConfigValidationTests` 2 项，全套 50 测试绿。
  **①block 判定分支已落地（2026-07-29，P1 收官）**：`_aggregate_block` 与 audit 对称——
  `sent`→failed（日志无翻案权）/`blocked`→复用「全过 AND 门」/其余→inconclusive；**聚合器只看
  checker 统一 `status`，不读 `hit_policy_type`**（见下方「聚合器不应读取 checker 的 hit_policy_type」条，
  已采纳）；为此 `_check_typed` 未命中按策略分流（block→inconclusive=情况一、audit→failed）。判定表
  6 行 + 情况一/二落 `PolicyAggregatorTests`，全套 56 测试绿。**P1 全部完成。**

### P1 · `strategy` 与 `policy` 会叠成重复判定体系 —— ✅ 已落地（2026-07-27）

- 现象：已有 `all_pass / any_pass`，设计又要加 `none / audit / block`（设计稿 §3）。两者组合出 6 套语义。
- 冲突点：`any_pass`（一路通过即通过）与需求直接矛盾——审计/阻断都要求
  **客户端日志与后台日志都正确**，不能一路命中就放行。
- **已处置**：直接删除 `any_pass` 分支与整个 `strategy` 参数（aggregator/manager/`__init__`），
  聚合只保留唯一语义「所有已启用 checker 全过才通过」。「可有可无 / 未实装」的验收路
  用「不启用（不进 expected_names）」表达，而非返回假 pass。后续 `policy` 直接在这套
  单一语义上叠加，不再有 strategy 交叉。见 tech_design Changelog 2026-07-27。

### P1 · 聚合器不应读取 checker 的 `hit_policy_type` —— ✅ 已采纳（2026-07-29）

- 现象：设计让 checker 往 `evidence` 写 `hit_policy_type`，再由通用聚合器判断类型对不对
  （设计稿 §4.3）。这让通用聚合器依赖某个具体 checker 的内部字段，耦合度上升。
- 建议：**判类型的责任下沉给 checker**：
  - checker 接收期望策略；命中正确类型 → `passed`；命中错误类型 → `failed`；
    实际命中类型只写进 `evidence` 供人诊断。
  - aggregator 仍只看统一的 `status`。新增 checker 时无需改聚合器。
- **落地（2026-07-29，block 判定分支）**：`_aggregate_block` 全程只读 checker 的 `status`（复用「全过
  AND 门」），一行没读 `hit_policy_type`。类型对错定死在 `dlp_log._check_typed`：命中阻断类=passed /
  命中审计类=failed / 未命中按策略分流。`grep hit_policy_type dlp_auto/verify/aggregator.py` 仍为空，
  佐证聚合器未耦合 checker 内部字段。

### P1 · `dlp_auto/judges/` 是整套重复且未接线的骨架 —— ✅ 已删除（2026-07-28）

- **原始意图（溯源）**：`judges/` 是早期规划的 **step 级声明式断言 DSL**。case
  原计划通过 `assert_visual(...)`、`assert_file_log(...)`、`assert_http(...)` 创建
  Judge 对象，再由 `step()` 识别为 `kind="assert"`，统一调用
  `evaluate(ctx) -> JudgeResult{passed,detail,evidence}`：
  - `VisualJudge`：截屏后交给 LLM 判断界面是否符合预期，默认选择 `llm.judge`；
  - `FileLogJudge`：检查本地文件/日志是否存在并匹配文本或正则；
  - `HttpJudge`：请求 DLP 后台接口并验证响应。
- **为何被取代**：上述三个证据源后来按实际生命周期拆进当前主链路：
  - 视觉：`ai(..., verify=...)` → `Agent` → `core/judge.py`，由
    `run.py` 注入 `registry.judge`；未单配 judge 时仍由 `LLMRegistry`
    回退到 default；
  - 本地日志：`verify/dlp_log.py` 在 case 生命周期内按字节偏移检索；
  - 服务端事件：`verify/server_event.py` 按 app 执行「登记指纹 → 批量查询 → 回填」；
  - 结论统一交给 `VerificationManager` / `OutcomeAggregator` 聚合并写报告。
  因此删除旧 `judges/` **不删除也不削弱双模型接入点**，只移除一套从未接线、
  已被 `core/judge.py + verify/` 取代的旧接口。
- **删除前审计（2026-07-28）**：全仓无任何主流程、case 或测试 import
  `dlp_auto.judges`；三个 `evaluate()` 全部是 `NotImplementedError`。唯一残留入口是
  `spec.step()` 对 `evaluate` 的鸭子类型识别，但 Runner 对 `assert` 仅打印
  「暂未接入，记为通过」，形成**断言未执行却假通过**的风险。
- **已处置（2026-07-28）**：删除 `judges/` 包、`StepKind` 中的 `assert`、
  `step()` 的 Judge 鸭子类型入口及 Runner 的静默通过分支。旧断言对象现在会在
  case 定义阶段明确抛 `TypeError`，而非制造假阳性。历史设计保留在
  `docs/archive/architecture.md`，不再作为可用接口。

### P2 · 预留模块 `human/` `notify/` 占用主认知路径

- 现象：两者均未接线，但 Runner 仍收 `notify/human` 参数（[runner.py:28-50](../dlp_auto/case/runner.py)），
  `config.yaml` 暴露完整配置段，README 把它们作为正式架构介绍。
- 建议：未接线能力不要进默认配置与「快速上手」；可移到 `experimental/` 或等真正启用再恢复。

### P2 · provision 名字大于实际能力

- 现象：`--ensure-ready` 目前：安装未探测到 → `skipped`；manual 未探测到 → 放行；
  未登记 app → 放行（[provisioner.py:45-100](../dlp_auto/provision/provisioner.py)）。
  实质是「探测并提示」，不是「确保就绪」。
- 建议：P3 落地前，措辞改为诊断性质，或不在 README 主流程展示，避免「环境已被保障」的误解。

### P2 · 文档入口已漂移

- 审查时现象：README 把 883 行的 `architecture.md（v0.1 草案）`当「详细架构」，其中大量未接线规划；
  真正可信的是 `tech_design.md`。`run.py` / `runner.py` 顶部注释还写着「尚未实装」「留待后续」，已过时。
- **已处置（2026-07-28）**：主阅读路径收敛为三层——
  1. `README.md`：安装与运行
  2. `AGENTS.md`：开发约束
  3. `tech_design.md`：当前架构事实

  旧阶段计划、v0.1 草案已移入 `docs/archive/`；README 架构链接已改指向
  `tech_design.md`，`run.py` / `runner.py` 顶部说明已按现状校正。

---

## 推荐的精简落地方式（策略断言）

不需要新包，也不需要复杂策略引擎：

1. CLI 增加 `--policy audit|block`。
2. 新增 `delivery_outcome: sent|blocked|unknown` 维度（见 P0）。
3. 客户端 / 服务端 checker 按 policy 选对应特征，自行判断日志类型是否正确。
4. Aggregator 只聚合三件事：自动化是否正常、外发结果是否符合 policy、必需 checker 是否全过。
5. policy 由 `VerificationManager` 持有并写入报告，**不给 Runner 增加策略分支**。
6. 暂缓「弹窗记录」：频控导致它不参与断言，末步截图已能留证据，额外做视觉识别收益低。
   > 已正式定级：见 [dlp_policy_assertion_design.md](./dlp_policy_assertion_design.md) §7 **P2（未开始）** 与 §4.5/§5「弹窗只记录不断言」。

---

## 待办清单（勾选后可并入正式文档）

> 状态核对时点：2026-07-28（据代码实况核对，非凭记忆）。
> 图例：`[x]` 已完成 · `[~]` 部分完成 · `[ ]` 未开始。

| # | 严重度 | 事项 | 状态 | 代码实况 / 缺口 |
|---|--------|------|------|------------------|
| 1 | **P0** | 引入 `delivery_outcome`，阻断不复用 execution 失败 | `[x]` | P0 已落代码（2026-07-29）：aggregator `policy` 参数 + none/audit 分支 + delivery_outcome 维度 + `--policy` CLI + 报告两列。**P1 全部完成（2026-07-29）**：重试联动（方案①′，block 自检话术）+ ②日志分型（`dlp_log` 产出 `hit_policy_type`）+ ①block 判定分支（`delivery × 阻断日志` 交叉验证，判定表 6 行 + 情况一/二），全套 56 测试绿。 |
| 2 | P1 | 删 `any_pass` / `strategy`，聚合收敛单一语义 | `[x]` | 已删（aggregator/manager/`__init__`），22 测试绿。2026-07-27 |
| 3 | P1 | 日志类型判定下沉 checker，聚合器只看 `status` | `[x]` | **已落地（2026-07-29）**：`dlp_log._check_typed` 按 policy 分型并把类型对错定死进 `status`（命中阻断类 passed / 命中审计类 failed / 未命中按策略分流）；`_aggregate_block` 只读统一 `status` 复用「全过 AND 门」，`grep hit_policy_type aggregator.py` 为空，聚合器零耦合 checker 内部字段。 |
| 4 | P1 | 删 `judges/` 包与 `assert` 半成品入口 | `[x]` | 已删；保留活跃的 `LLMRegistry.judge` + `core/judge.py` 双模型验收链路。2026-07-28 |
| 5 | P2 | `human/` `notify/` 移出默认配置与主文档 | `[ ]` | `config/config.yaml:39,48` 仍有 notify/human 配置段；`README.md:17-18,178-179` 仍作正式架构介绍 |
| 6 | P2 | provision 措辞校正为诊断性质 | `[ ]` | 未改；`--ensure-ready` 实为"探测并提示" |
| 7 | P2 | 收敛文档入口 + 旧文档归档 | `[x]` | 已归档旧文档；README 改指向 `tech_design.md`；`run.py` / `runner.py` 过时说明已校正。2026-07-28 |

**下一步建议优先级**：P0（delivery_outcome，价值最高、设计稿已就绪）＞ P1 日志类型判定下沉 checker（随 P0 一起落地）＞ P2 其余。
