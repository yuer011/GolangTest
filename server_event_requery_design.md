# 服务端事件回查重构设计（run 级统一回查 + event_id 精确匹配）

> **已归档（2026-08-07）**：CHG-004 已完成——编码、单测、真机联调（`mock=false` 真连飞连后台、
> 命中裁决加严、会话直传鉴权）全部落地，稳定数据流已上移 [tech_design.md §5](../tech_design.md)
> 与 Changelog（2026-08-06）。本稿作为**设计脉络的历史留存，只读不再维护**。
> ⚠️ 文中「状态：待评审」「本期不实装 / 抓包后再填 / `NotImplementedError`」「§8 待评审确认点」等
> **均为 2026-08-06 设计定稿时的快照，现已全部实现并被真机验证推翻**——真实接口层
> （`feilian_client` 登录 + 查询）已实装，凭据支持会话直传，`pycryptodome` 已引入。
> **当前实际行为一律以代码与 [tech_design.md](../tech_design.md) 为准，切勿把下文当现状。**
>
> ---
>
> **状态**：设计定稿待评审（2026-08-06）。评审通过后编码。
> **关联改动**：`CHG-004`（服务端事件真实回查）——本稿把它从「app 级指纹匹配 + mock」重构为
> 「run 级 event_id 精确回查 + 真实接口预留」。
> **性质**：框架级改动，涉及硬约束 #4（服务端两阶段）数据流。权威现状见
> [tech_design.md](tech_design.md)；本稿定稿后其 §4/§5 与图集需同步。

---

## 1. 背景与问题

现状实现（[server_event.py](../dlp_auto/verify/server_event.py)）有三个结构性问题，用户已确认需重构：

1. **粒度是 app 级，不是 run 级**：现在每跑完一款 app 就查一次
   （[runner.py:78-81](../dlp_auto/case/runner.py) `on_app_finished` → `check_app`）。
   先跑的 app 查得早，没吃满上报延迟窗口；查询次数 = app 数量，重复调用。
2. **查询维度是「多字段指纹全等匹配」，脆弱且无唯一键**：`_fingerprint_hit`
   （[server_event.py:118](../dlp_auto/verify/server_event.py)）按 `file_name/action/device/time`
   逐字段全等比对——时间戳差一秒就不匹配。代码里**没有 event_id 概念**。
3. **登记端从未接线、结果文件无可查线索**：`record_expected_event` 全仓 case 无一处调用，
   链路空转；CSV / CaseReport 里没有任何可事后回查的 id。

用户的新思路：**既然服务端支持按事件 id 查询，就等所有 case 跑完后，根据结果记录统一去查**——
先跑的 case 到那时早已上报完成；对个别没查到的，全局最多等一次上报周期再补查一次。

---

## 2. 目标与非目标

**目标**
- 把服务端回查从 **app 级** 提升为 **run 级**（所有 case 跑完统一查一次）。
- 查询维度从「多字段指纹」改为 **event_id（本地 DLP 日志解析出的事件 UUID）精确匹配**。
- 把 event_id 落进 **CaseReport 与结果 CSV**，使结果文件本身即回查清单、可事后复查。
- 引入 **全局最多一次** 的「等待上报周期后补查」兜底（默认 60s，从 config 读）。
- 真实服务端接口（登录 + 查询）**预留扩展点与配置位**，本期不实装（等抓包后再填）。

**非目标（本期不做）**
- 不实装真实 HTTP（`_login()`/`_query()` 留 `NotImplementedError` + mock）。
- 不改视觉/本地日志两路验收逻辑。
- 不改 Mac 端后端代码（Mac 后端属 [CHG-001](change_tracker.md)，尚未落地）。Mac 的跨平台复用见 §3 前提 F——真机已确认 Mac 也能拿到 UUID，本设计已为其留好位置。

---

## 3. 关键前提（已与用户确认）

> 均已于 2026-08-06 与用户逐条确认。

| # | 前提 | 确认结论 |
|---|------|---------|
| A | event_id 来源 | ✅ **就是本地 DLP 日志里的事件 UUID**。已由 [_base.py:77](../dlp_auto/verify/dlp_log/_base.py) 解析进 `DlpEvent.event_uuid`，并已放入 `rep.extras["checks"]["dlp_log"]["evidence"]["event_uuid"]`（[_windows.py:245](../dlp_auto/verify/dlp_log/_windows.py)）。 |
| B | 启用条件 | ✅ **强依赖 `--policy audit/block`**。只有传 policy 才解析本地日志、才拿得到 UUID → 才做服务端回查。policy=none 时服务端回查自然跳过（无 event_id）。 |
| C | 等待策略 | ✅ 默认 **60s**。语义：查询某事件**首次**没查到 → 全局 `sleep(report_delay_sec)` **一次** → 只补查漏网的；此后再有查不到的**一律不再等**，直接记 inconclusive。全局只等这一次。 |
| D | 真实接口 | ✅ **契约已提供**（不再"等抓包"）：登录参考用户给的 `admin_login.py`（AES 加密密码 → portal_port `/api/v1/login` → 取 cookie+csrf），查询为 admin_port `/api/admin/v2/dynamic_security/edlp/events?event_ids=...`。测试环境 qa9 账号已给。封装进新增 `feilian_client.py`（§5.9）。 |
| E | 旧指纹匹配 | 用户已理解「指纹」= 旧代码在无 event_id 年代靠 `文件名/动作/设备/时间戳` 多字段全等（[`_fingerprint_hit`](../dlp_auto/verify/server_event.py) L118）拼凑的近似唯一标识；改用 event_id 唯一主键后，**整体废弃** `check_app`/`_fingerprint_hit`/`record_expected_event` 那套。 *（待用户最终点头）* |
| F | Mac 跨平台复用 | ✅ **真机已确认 Mac 端也能拿到事件 UUID**，只是**日志路径与解密方式和 Windows 不同**。差异全部封在 Mac 本地日志后端（[CHG-001](change_tracker.md)）内部；服务端回查只认 `rep.event_id`，与平台解耦。故 Mac 后端落地时，只需在其 `_fill_report` 补上与 Windows 同一行 `rep.event_id = ev.event_uuid`，即自动接入本套 run 级服务端回查，**服务端逻辑零改动**。 |

---

## 4. 数据流（新）

```
执行期（每个 case，仅 policy≠none）
  块② 本地日志命中外发事件 → 解析出 event_uuid
    └─ 新增：把 event_uuid 回填到 rep.event_id（_fill_report 里顺手做）
         并随 append_case 落进 CSV「事件ID」列（增量落盘，硬约束 #5）

所有 case 跑完（run 级，一次）           ← 触发点从 app 收尾移到 run 收尾
  收集所有 rep.event_id 非空的 case
    └─ 无 event_id 的 case：记 inconclusive（未取得事件ID，无从回查）
  批量查询服务端（mock 或真实 _query）
    ├─ 查到 → server_event = passed，回填
    └─ 有 case 没查到：
         若尚未等过 → sleep(report_delay_sec) 一次 → 只对未命中的再查一轮
         仍没查到 → server_event = inconclusive（不臆测、绝不 pass，硬约束 #10）
  重新聚合各 case → 覆写 CSV 终版
```

**为什么 run 级只等一次**：延迟主要发生在「最后几个 case 刚跑完、还没上报」。先跑的 case 早报完，
统一查时基本都在；只有末尾少数可能没到，全局等一个上报周期即可覆盖。再没到多半是真没上报
（异常），继续干等无意义，故只等一次、只补一轮。

---

## 5. 涉及改动（具体到文件与函数）

### 5.1 `dlp_auto/report/schema.py`
`CaseReport` 新增字段：
```python
# 本次外发事件在服务端可回查的唯一 id（= 本地 DLP 日志解析出的事件 UUID）。
# 仅 policy≠none 且本地日志命中时有值；供 run 级服务端回查按之精确查询、并落进 CSV。
event_id: str = ""
```

### 5.2 `dlp_auto/verify/dlp_log/_windows.py`
`_fill_report`（[L232](../dlp_auto/verify/dlp_log/_windows.py)）命中时顺手回填 event_id：
```python
if hasattr(rep, "event_id") and ev.event_uuid:
    rep.event_id = ev.event_uuid
```
> 零成本：event_uuid 本就已解析、已进 evidence，这里只多一行搬运。Mac stub 不命中即留空。

### 5.3 `dlp_auto/report/writer.py`
`_CSV_HEADER` 在「服务端判定」附近加一列「事件ID」；`_row` 对应位置输出 `c.event_id or ""`。
> 列位置建议放「DLP事件日志」之后、三路判定之前，语义上属证据列。

### 5.4 `dlp_auto/verify/server_event.py`（核心重写）
- 类属性 `scope` 从 `"app"` 改为 `"run"`（新增一种 scope）。
- **删除** `record_expected_event` / `check_app` / `_fingerprint_hit`（旧指纹套，前提 E）。
- **新增** `check_run(run_report) -> dict[str, CheckOutcome]`：
  - 收集所有 `rep.event_id` 非空的 case → `{event_id: case_id}`；
  - 无 event_id 的 case 直接记 inconclusive；
  - `mock=True`：固定 inconclusive（仅验证链路，不产生生产通过结论，守硬约束 #10）；
  - `mock=False`：调 `_query(event_ids)` → 命中/未命中；
  - **全局一次等待**：首轮有未命中 → `sleep(report_delay_sec)` 一次 → 只对未命中的 event_id
    再 `_query` 一轮；仍未命中记 inconclusive。用实例标志 `self._waited` 保证只等一次。
- **新增扩展点（本期留空）**：
  ```python
  def _login(self) -> None:
      """登录服务端换取会话/token（抓包后实装）。当前 NotImplementedError。"""
  def _query(self, event_ids: list[str]) -> dict[str, dict]:
      """按 event_id 批量查，返回 {event_id: 事件详情}（抓包后实装）。当前 mock/未实装。"""
  ```
- `build_server_event_checker` 增读 `verify.server.report_delay_sec`（默认 60）、以及登录相关
  配置位（`login_url`/`username`/`password` 等占位，敏感项走 secret，硬约束 #1/#11）。

### 5.5 `dlp_auto/verify/manager.py`
- `app_checkers` 语义调整：服务端 checker 归到新的 `run_checkers`（scope="run"），
  或复用现有列表但触发时机改到 run 级（见下）。建议**新增 `run_checkers` 列表 + `on_run_finished`**，
  与 app 级钩子并存、互不影响（app 级钩子本期无使用者，但保留扩展位）。
- 新增 `on_run_finished(run_report)`：遍历 run_checkers 调 `check_run`，异常降级 inconclusive
  （硬约束 #6），回填后对每个 rep 重新 `_aggregate`。
- `_aggregate` 的 `expected_names` 把 run_checkers 也纳入 AND 门。

### 5.6 `dlp_auto/case/runner.py`
- **删除** app 收尾处的 `on_app_finished` 服务端回查调用（[L78-81](../dlp_auto/case/runner.py)）。
- 在 `run()` 组装完 `report`（[L89-101](../dlp_auto/case/runner.py)）**之后**、覆写 CSV **之前**，
  调 `self.verifier.on_run_finished(report)`。
- 覆写终版 CSV 的条件从 `app_checks` 改为 `run_checks`（有 run 级 checker 时覆写）。

### 5.7 `dlp_auto/verify/__init__.py`
`build_manager` 里 `check_server` 分支改为把 checker 放进 `run_checkers`：
```python
if check_server:
    from .server_event import build_server_event_checker
    run_checkers.append(build_server_event_checker(settings))
return VerificationManager(case_checkers=..., run_checkers=run_checkers, policy=policy)
```
> 另需守前提 B：`check_server=True` 但 `policy=none` 时，run.py 给出忽略提示
> （无 event_id，查不了），与 `--check-log` 在 none 下被忽略的处理一致。

### 5.8 config + example（非敏感入库，凭据入 secret）
`config/config.yaml` 补 `verify.server` 段（**非敏感**：域名/端口/时间窗，可入库）：
```yaml
verify:
  server:
    mock: true                    # 阶段一 true（恒 inconclusive）；真实接口就绪后置 false
    report_delay_sec: 60          # 某事件首次没查到时，全局等待一次的上报周期（秒）
    # ── 真实接口（值来自用户提供的测试环境；非敏感，可入库）──
    host: feilian-qa9.local.ifeilian.cn   # 目标环境域名（默认 qa9，可改）
    admin_port: 8443              # 查询接口端口：/api/admin/v2/dynamic_security/edlp/events
    portal_port: 10443            # 登录接口端口：/api/v1/login
    timeout_sec: 10
    query_window_days: 1          # 按 event_id 查询时 start/end 时间窗兜底（天）
```
`config/config.secret.example.yaml` 补**凭据**模板（真实值写入 gitignore 的 config.secret.yaml）：
```yaml
verify:
  server:
    admin_user: ${FEILIAN_ADMIN_USER}   # 管理员账号
    admin_pwd: ${FEILIAN_ADMIN_PWD}     # 管理员密码（绝不入库/不落日志，硬约束 #4/#11）
```
> **安全红线**：用户提供的 autotest_config.py 内含**明文管理员密码**，**不得原样入库**。
> 取值迁移：host/端口 → config.yaml；账号/密码 → config.secret.yaml（gitignored）。
> 原 .py 的 `from .base_config import BaseConfig` 相对导入在本仓库不成立，故不引入该文件。

### 5.9 `dlp_auto/verify/feilian_client.py`（新增，阶段二真实接口）
把登录与查询封装为自包含 HTTP 客户端，`server_event._login()/_query()` 委托它，与判定逻辑解耦：
- `login(cfg) -> {"cookie","csrf-token"}`：改写自用户提供的 admin_login.py——
  AES-256-CBC（固定 salt=md5(2^53-1) 派生 key，iv=sha1(key)[:16]）加密密码 →
  POST `https://{host}:{portal_port}/api/v1/login?...` → 从响应 Cookie 提取 `csrf-token`+`session`。
  凭据从 Settings（secret）读，绝不写入日志/报告。
- `query_events(event_ids, auth, window) -> {event_id: detail}`：GET
  `https://{host}:{admin_port}/api/admin/v2/dynamic_security/edlp/events`
  `?event_ids=<逗号连接>&start=&end=&os=web&tab=edlp/event/alarm&limit=&offset=0`，
  用 login 的 cookie+csrf 鉴权，解析响应判定各 event_id 命中与否。start/end 由 run 起止
  时间 ±`query_window_days` 推导。
- 依赖：`requests`（已在 pyproject）、`pycryptodome`（**需新增**，用于 AES）。

---

## 6. 硬约束合规自检

| 约束 | 本设计如何满足 |
|------|---------------|
| #1 零猜测 | event_id、接口地址、上报周期只从 config/日志读；接口未就绪不臆测参数，留 `NotImplementedError`。 |
| #4 两阶段 | 仍是「登记(event_id)→批量查→回填」，粒度从 app 提升到 run。 |
| #6 验收零副作用 | `check_run` 全程 try/except，异常只降级 inconclusive，不打断 run。 |
| #10 执行≠有效 | 查不到、mock、无 event_id 一律 inconclusive，绝不 pass。 |
| #11 凭据安全 | 登录凭据只放 secret yaml/环境变量，绝不进日志/报告；base_url 可入库。 |
| #2 解耦可删 | `--check-server` 默认关；关掉后行为与现在完全一致（run_checkers 为空，on_run_finished no-op）。 |

---

## 7. 分阶段实施

- **阶段一（框架改造）**：5.1–5.7 全部落地，`_query`/`_login` 留扩展点走 mock。
  验收：`--policy audit --check-server` 跑通，CSV 出现「事件ID」列且有值，服务端列记 inconclusive（mock）。
- **阶段二（真实接口，已解锁）**：接口契约已由用户提供（登录参考 admin_login.py、查询 curl 见 §5.9），
  新增 `feilian_client.py` 实装 `login()`/`query_events()`，补 `pycryptodome` 依赖与 secret 配置，
  `mock` 置 false 真机验证。**阶段一、二可在同一次任务连续落地**（契约已全，不再受"等抓包"阻塞）。

> 说明：原计划阶段二"等与用户一起抓包"，用户已直接提供测试环境账号、登录实现与查询 curl，
> 该外部依赖已解除；仅剩真机联调（token 有效性、响应字段命中判据）。

---

## 8. 待评审确认点

**框架层（阶段一）**
1. CSV「事件ID」列的**位置**：放「DLP事件日志」之后、三路判定之前，可否？
2. `manager` **新增 `run_checkers` + `on_run_finished`**（已细化说明，见 §5.5）——确认按此实现。
3. `report_delay_sec` 默认 **60s**（已确认 ✅）。

**真实接口层（阶段二，用户已给契约）**
4. 阶段一、二**一并落地**还是先合阶段一？（契约已全，建议一并落地，一次到位。）
5. **依赖 `pycryptodome`**：登录密码 AES 加密需要它，将加入 pyproject `dependencies`——确认可引入。
6. **凭据迁移方案**：账号密码放 `config.secret.yaml`（gitignored）、host/端口放 `config.yaml`，
   不引入含明文密码的 `autotest_config.py`——确认。
7. **默认环境 host**：config.yaml 里默认写 `feilian-qa9.local.ifeilian.cn`（你现在用的），
   还是留空强制显式配？（建议写默认 qa9，方便开箱即用。）
8. **查询判据**：按 event_id 查到即算命中（`server_event=passed`）——响应里是否还需校验某状态字段
   （如事件状态=已处理/告警）？此点需真机联调时你确认返回结构后定。

---

## 变更记录

- 2026-08-06：初稿。基于现状代码全量核对（server_event/runner/manager/writer/schema/dlp_log），
  确认 event_uuid 已解析可复用；定「run 级 + event_id + 全局等一次 + 接口预留」方案，待评审。
- 2026-08-06：补前提 F（Mac 真机已确认能拿 UUID、跨平台复用零改服务端）。
- 2026-08-06：用户提供飞连测试环境真实接口契约（登录 admin_login.py 参考 + 查询 curl + qa9 账号），
  阶段二解锁。补 §5.9 `feilian_client.py` 设计、§5.8 凭据安全迁移（明文密码不入库）、
  阶段实施改为一、二可连续落地；§8 增补真实接口层确认点（pycryptodome 依赖/凭据迁移/默认 host/查询判据）。
