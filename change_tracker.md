# 改动与技术文档维护台账

> **状态**：长期维护，不归档。
> **最近核对**：2026-08-11，按当前代码、配置和 `docs/` 实况盘点。
> **用途**：统一记录后续改动、完成状态、对应技术文档及归档条件，避免待办散落在多份设计稿中。

---

## 1. 权威来源与边界

| 内容 | 权威来源 | 本文职责 |
|---|---|---|
| 系统实际如何运行 | 代码、配置、测试 | 只记录状态和证据，不替代代码 |
| 框架约束、架构、稳定数据流 | [tech_design.md](./tech_design.md) | 记录哪些改动必须同步到该文档 |
| 架构图 | [tech_design_diagrams.md](./tech_design_diagrams.md) | 记录哪些改动会影响图 |
| 某项改动的详细方案 | 对应设计稿 / 提案 | 建立“改动项 → 设计稿”映射 |
| 待开发、进行中、已完成状态 | **本文** | 作为统一状态入口 |
| 已完成使命的历史材料 | [archive/](./archive/README.md) | 记录归档条件和归档结果 |

基本原则：

1. 新功能或框架改动开始设计时，先在本文登记一个稳定 ID，再创建或关联详细技术文档。
2. 详细设计仍写在各自文档中；本文只保留范围、状态、下一步、完成证据和归档门槛。
3. 同一改动的代码、测试、设计稿、`tech_design.md` 必须在同一次任务中同步，提交前核对本文状态。
4. 代码行为与文档冲突时以代码为准，同时把文档漂移登记为待办，禁止靠猜测修正文档。

---

## 2. 状态定义

| 状态 | 含义 |
|---|---|
| `待评估` | 只有问题和候选方向，尚未决定是否实施 |
| `待开始` | 范围和方案已明确，可以实施 |
| `进行中` | 已开始实施，但验收条件尚未全部满足 |
| `部分完成` | 已交付独立阶段，仍有明确剩余阶段 |
| `暂缓` | 已决定当前不推进，保留触发条件 |
| `等待外部输入` | 缺真机样本、接口契约等外部条件，不能零猜测推进 |
| `已完成` | 代码、测试、用户文档、技术文档均已同步 |
| `已取消` | 明确决定不做；原因及替代方案已写入对应文档 |
| `已归档` | 关联改动均为终态，且文档已移入 `docs/archive/` |

只有 `已完成`、`已取消`、`已归档` 属于终态。`暂缓` 和 `等待外部输入` 仍是活跃待办。

---

## 3. 活跃改动台账

| ID | 改动 / 功能 | 状态 | 下一步或触发条件 | 详细技术文档 | 完成时必须同步 |
|---|---|---|---|---|---|
| `CHG-026` | 回归管理后台 run 级浏览器与登录态复用 | 已完成 | 同一回归 run 内共享受管 Chrome，case 结束不关闭；run 结束默认统一释放，`--keep-browser-open` 可保留。公共后台环境和 UI 管理员凭据上移到 `regression.admin`，与 `verify.server` 隔离。97 项 Mac/回归相关测试通过；本轮未再次创建水印策略，真机会话复用待新增第二条管理后台 case 后联跑复核 | [回归框架方案](./regression_case_analysis/framework_adaptation.md) | 已同步代码/config/secret 模板/专项测试/README/`add-case`/`tech_design.md`/图 8；通道 `CaseRunner` 和 Web 生命周期未修改 |
| `CHG-025` | 独立数据安全回归最小执行层 + 屏幕水印 R40/R41 | 已完成 | 已实现并验证独立 registry/loader/runner、本地报告、`ui_state`、回归 reflect 隔离和 R40/R41 水印 case；`add-case` 已增加通道/回归类型分流，回归分支不进入固定覆盖率同步。2026-08-31 BOE Mac 真机验证：手机号唯一员工选择成功，R40/R41 均 passed；后续 R42～R45 另立改动项 | [回归框架方案](./regression_case_analysis/framework_adaptation.md)、[自动化 Case 清单](./regression_case_analysis/AUTOMATION_CASES.md) | 已同步代码/config/secret 模板/专项测试/README/`add-case`/`tech_design.md`/图 8/真机结果；回归 case 不进固定覆盖率清单 |
| `CHG-024` | Mac 五款浏览器通道：独立新窗口 + DLPTest HTTPS POST 上传 | 已完成 | Safari、谷歌、Edge、Firefox、360 极速各覆盖拖拽/点击上传；五款点击批次和五款拖拽批次均 `failed=0,error=0`，每条完成唯一文件入队、Submit、成功文案与资源清理。每 case 独立窗口，地址栏整段粘贴 URL，动态完整路径 + 双 Return 打开文件；无 policy 时按设计为 `inconclusive`。用户于 2026-08-21 确认结果 | 无独立设计稿；权威现状见 [tech_design.md §3.7](./tech_design.md)、[用例说明/Mac-浏览器外发.md](./用例说明/Mac-浏览器外发.md) 与 [LESSONS.md #27](../LESSONS.md) | 已同步代码/config/专项测试/README/用例说明/`tech_design.md`/图 6/`add-case` skill/覆盖清单；Base 新增 10 条，仓库遗漏 0 |
| `CHG-001` | Mac DLP 客户端日志验证后端 | 已完成 | 2026-08-08 用 Mac 企业微信四类正式 case 真跑通过：`sudo -n cat \| bread -` 对拖拽/上传/复制粘贴分别按唯一文件名命中，对自带截图按图片类型命中 `screenshot.png`；四条均回填唯一 `eventId` 和 `app=wxwork`，CSV/末步截图/运行结果 Base 均落盘。首次完整 run 因本机 secret 缺服务端凭据按设计降级 `inconclusive`；补齐 secret 后复用原四个 eventId 独立回查，均恰好命中一条服务端放行事件；随后同参数完整重跑，最终 4/4 passed，CSV/四张末步截图/新建运行结果 Base 均成功。`leakFileActions` 的 block 语义未标定，不属于后端可用性门禁，继续由 `CHG-003` 跟踪 | [dlp_client_log_verify_design.md §4](./dlp_client_log_verify_design.md) | `_mac.py`、平台配置、13 项专项测试、sudoers 脚本、README、`tech_design.md`/图集均已同步；block 样本与分型留在 `CHG-003` |
| `CHG-002` | 策略断言 P2：拦截弹窗仅记录、不参与断言 | 暂缓 | 用户重新确认弹窗证据有实际收益时启动；也可明确取消 | [dlp_policy_assertion_design.md §4.5/§7](./dlp_policy_assertion_design.md) | 报告 Schema/CSV/Lark、测试、README、`tech_design.md` |
| `CHG-003` | 策略断言 P3：真机标定审计/阻断特征并关闭开放问题 | 部分完成 | Windows“是否有本次外发事件”已落地；仍需真实样本确认审计/阻断能否区分，并确定 block 下 `delivery_outcome` 的稳定来源 | [dlp_policy_assertion_design.md §7/§9](./dlp_policy_assertion_design.md)、[dlp_client_log_verify_design.md](./dlp_client_log_verify_design.md) | config、checker 测试、聚合回归、`tech_design.md`、图集 |
| `CHG-004` | 服务端事件回查：run 级 event_id 精确回查 → 全局等一次 → 回填 | 已归档 | 真机联调通过（2026-08-06）：QQ `drag_drop` 真跑 `mock=false`、真连飞连后台，服务端按 event_id 首查即命中判 `passed`（另有首查 miss→全局等一次补查命中，验证「补查一次」真机生效）；`_extract_events` 经真实命中响应验证解析正确；`config.yaml` 置 `mock: false` 常开（总开关仍是 `--check-server`+`--policy`，默认关、零回归）。联调另暴露并修复 run 级翻转后 issue 残留 bug（`aggregator.py` + 回归测试）。**加严（2026-08-06）**：命中裁决从「查到即过」升级为「恰好一条 + `event_result.intercept` 处置动作 vs policy 交叉校验」（>1 条判 failed 原因落表；audit 应放行/block 应拦截，判据经真实 event_id 探针实证由用户敲定），真机双向自洽（audit→passed、同事件 block→failed）。**鉴权增强（2026-08-06）**：`feilian_client` 加「会话直传」——`session_cookie`+`csrf_token` 优先跳过登录、账号密码 AES 登录回退（纯增强、默认不变，会话直传不必存长期明文密码更安全）。**已归档（2026-08-07）**：设计稿达门槛，`git mv` 入 `docs/archive/`，3 处代码/配置引用已改指归档路径 | [archive/server_event_requery_design.md](./archive/server_event_requery_design.md)（已归档）；权威现状见 [tech_design.md §5](./tech_design.md) 与 Changelog 2026-08-06 | 已同步 `tech_design.md`/图集；设计稿已归档（见 §4） |
| `CHG-005` | provision P3：自动登录 | 暂缓 | 第一阶段不再依赖人工预登录，且凭据/验证码方案明确后启动 | [app_provisioning_design.md §7 P3](./app_provisioning_design.md) | `provision/`、secret 模板、安全测试、README、`tech_design.md`、图集 |
| `CHG-006` | provision P4：自动安装 | 暂缓 | 各软件分端下载地址、探测路径和静默参数经真机核实后启动 | [app_provisioning_design.md §7 P4](./app_provisioning_design.md) | `apps.yaml`、安装实现、平台测试、README、`tech_design.md`、图集 |
| `CHG-007` | 架构 Review P2 收尾：`human/notify` 暴露面与 provision 措辞 | 待开始 | 决定移除未接线模块的默认配置/主文档入口，或正式接线；把“保障”措辞校正为当前真实的探测能力 | [architecture_review_notes.md P2](./architecture_review_notes.md) | config、README、`tech_design.md`、图集、AGENTS 索引（如有） |
| `CHG-008` | `max_steps` 按通道或单 AI step 细分 | 待评估 | 接入高步数通道或再次出现全局阈值冲突时，重新评估方向 A/B | [max_steps_per_case_proposal.md](./max_steps_per_case_proposal.md) | config、Agent/Runner、测试、README、`tech_design.md` |
| `CHG-009` | 规模化覆盖路线图复核与剩余里程碑 | 部分完成 | 先按当前代码重审 M1-M6：共享 IM 脚手架、联系人配置和多软件覆盖已有等价实现；M3 配置生成、M6 批量治理等仍需确认是否需要 | [scale_up_plan.md](./scale_up_plan.md) | 计划状态、add-case skill、README；框架变化同步 `tech_design.md` |
| `CHG-010` | 截图独立清理脚本与文档实况对齐 | 待开始 | 当前 `tech_design.md` 写明 `cleanup_screenshots.py`，但仓库尚无该脚本；应实现独立脚本，或把文档改成“规划中” | [tech_design.md §4 硬约束 #8](./tech_design.md) | `scripts/`、脚本测试/使用说明、README、`tech_design.md` Changelog |
| `CHG-011` | Windows IM 托盘挂机自动唤窗（点击托盘图标） | 已完成 | 修复「托盘态 open_app 弹登录窗 / 外部 ShowWindow 制造 Electron 僵尸窗」：新增独立模块 [`_windows/tray.py`](../dlp_auto/actions/_windows/tray.py)，`wake_from_tray` 用 `uiautomation` 展开 Win11 XAML 溢出区（`TopLevelWindowForOverflowXamlIsland`）→ 按 Name 子串定位 `SystemTray.NormalButton` → **单击**唤主窗。**默认关、可整体删除**（`uiautomation` 延迟导入；开关 `open_app(wake_tray=)` 参数 / 环境变量 `DLP_AUTO_TRAY_WAKE`，默认关；删掉 `tray.py` 后 `open_app` 恒退回「提示人工点」，已验证零回归）。真机验证：QQ 托盘态 `open_app('qq', wake_tray=True)` → 主窗弹出且**真人确认打字/点击正常**。根因与排查纪实见 [LESSONS.md #18](../LESSONS.md) | 无独立设计稿；权威现状见 [tech_design.md](./tech_design.md) 与 [LESSONS.md #18](../LESSONS.md) | 已同步 `tech_design.md`（可选能力表 + Changelog）；`pyproject` 依赖标注 |
| `CHG-012` | 配置驱动的 app 级收尾（跑完统一收起窗口） | 已完成 | 把 [runner._run_app_teardown](../dlp_auto/case/runner.py) 从「硬编码 close + 仅靠 case 端 `register_app_teardown`」升级为**配置驱动**：`config.yaml` 新增顶层 `teardown` 段（`enabled`/`default_action`/`apps` 按名覆盖），支持 `close`（WM_CLOSE 关窗缩托盘、保留登录，默认）/`minimize`（SW_MINIMIZE）/`quit`（关窗后残留则 TerminateProcess，**丢登录态**）/`none`。新增 [`apps.app_teardown(name, action)`](../dlp_auto/actions/_windows/apps.py) 执行原语 + `_normalize_app_key`（报告名/中文别名→app_key 集中映射）+ `_kill_app_processes`。**默认关、可整体删除**（`_DEFAULTS.teardown.enabled=False`）；QQ/飞书等未注册 close 的 app 也能统一收尾。2026-08-12 扩展：主配置显式设置 `千问: close`（缩托盘保留登录态）与 `WeLink: quit`；WeLink 每次 run 由调用 `run_case.ps1` 的父 PowerShell 以 `Start-Process -PassThru` 冷启动并保持 4 秒，不走托盘恢复；quit 枚举全部 PID，只清理真机核实安装根目录下的进程。复制粘贴 case 真机完成冷启动、唯一 TXT 外发和视觉验收，组尾关闭 1 个窗口并终止 14 个进程，复查进程/HWND 均归零 | 无独立设计稿；权威现状见 [tech_design.md](./tech_design.md)、Changelog 与 [LESSONS.md #25](../LESSONS.md) | 已同步 config/代码/脚本/测试/README/add-case skill/`tech_design.md`/LESSONS；全量 `172 tests OK` |
| `CHG-013` | 固定多维表格维护仓库 Case 覆盖与覆盖率仪表盘 | 已完成 | 已创建 [DLP 自动化覆盖清单](https://bytedance.larkoffice.com/base/AEOmbtgJiaUDPdsgbACcrTAynie)：Case/软件表以 `PythonModuleLoader` 注册结果为分子；“飞连支持目录”通过显式 `--refresh-catalog` 从 `cloud-config/main` 的 `app_v5.yaml` + zh-CN i18n 稀疏拉取 Windows/Mac 完整分母，日常 Case 同步不访问远端；指标卡继续使用“覆盖率指标”，综合/Windows/Mac 三张堆积图改为直接使用“飞连支持目录”，按 `通道名称 × 映射状态` 汇总固定为 1 的 `统计单位`，点击色块可下钻对应软件×端明细。当前基线版本 `26072801`：168 款软件、270 个软件×端；2026-08-21 日常同步后仓库/Base 均为 86 条平台注册记录，覆盖 23 款软件/29 个软件×端，软件覆盖率 13.69%、端覆盖率 10.74%、Windows 16.67%、Mac 5.07%，仓库遗漏为 0。新增 [`sync-case-coverage`](../.trae/skills/sync-case-coverage/SKILL.md) skill，以 `case_id@platform` 为 Case 唯一键，只补缺失、不覆盖/删除历史；`add-case` 已接入收尾 | 无独立设计稿；skill 为同步规则权威来源 | 已同步 README、`add-case` skill；已核实并显式登记浏览器、企业微信和阿里旺旺共 7 个 case slug→飞连 App Key 别名；同步脚本兼容 Windows npm `lark-cli.cmd`，日常/目录同步均维护 `统计单位=1`；不改变运行框架，无需更新 `tech_design.md`/图集 |
| `CHG-014` | Windows 浏览器通道：隔离新窗口 + DLPTest HTTPS POST 上传 | 已归档 | 已接入 Edge、Chrome、360 极速、Firefox、2345、360 安全、猎豹、傲游、QQ、搜狗共 10 款，每款覆盖拖拽/点击上传；世界之窗因页面/UI 异常本期明确跳过。Chrome 用 `managed_session` 保护用户已有窗口，其余按配置安全根目录执行 `all_under_roots` 冷启动与组尾清零；启动弹窗由独立 AI step 视觉处理。上传前居中卡片，Submit 前 hard 激活，并以 `action_limits(click=1, scroll=1)` 防重复提交。新增 8 款共 16 条 GUI/视觉全部成功；`audit` 下 2345/Firefox/猎豹/傲游/QQ/搜狗共 12 条通过，360 极速无外发事件、360 安全因 browser URL/text 为空跳过匹配，共 4 条正确判 failed；服务端未启用。合并最新远端后全量 `123 tests OK`，进程/profile/上传目录无残留。**已归档（2026-08-17）**：设计稿达门槛，`git mv` 入 `docs/archive/`，README/tech_design/add-case skill 3 处引用已改指归档路径 | [archive/browser_channel_design.md](./archive/browser_channel_design.md)（已归档） | 已同步代码/config/测试/README/add-case skill/`tech_design.md`/LESSONS；三层拓扑不变，图集无需修改。360 两款是客户端 DLP 覆盖缺口，不在自动化侧放宽 checker |
| `CHG-015` | 全新 Mac 环境依赖安装验收 | 暂缓 | 依赖静态审计已完成：直接 import 对应的基础依赖已声明 `requests`/`urllib3`/`pycryptodome`，Mac extra 已声明 `pyobjc-framework-Cocoa`/`Quartz`/`ApplicationServices`。后续恢复时使用 Python ≥3.10 新建干净 venv，升级 pip/setuptools 后执行 `pip install -e ".[dev,mac]"`，再验证 `AppKit`/`Foundation`/`Quartz`/`ApplicationServices`/`Crypto` 导入与 `pip check`；本轮按用户要求不继续干净环境安装验证 | 无独立设计稿 | 验证完成后更新本台账；如发现声明缺口，同步 `pyproject.toml` 与 README 安装说明 |
| `CHG-016` | 飞连支持目录适配例外人工标注 | 已完成 | 2026-08-10 在固定 Base“飞连支持目录”新增人工字段：`适配状态`仅含“暂缓”“不适配”，留空表示默认可适配、等待排期；`适配说明`记录原因、解除条件或复查时间。两个字段不改变官方覆盖率分母，日常同步和 `--refresh-catalog` 均不得写入或覆盖 | 无独立设计稿；权威规则见 [`sync-case-coverage`](../.trae/skills/sync-case-coverage/SKILL.md) | 已同步 skill 字段说明，并新增测试锁定目录全量刷新/日常同步的字段映射不包含人工字段 |
| `CHG-017` | 阿里旺旺 Windows 图片外发适配 | 已完成 | 新增拖拽/上传/复制粘贴/自带截图 4 条 case；`AliIM.exe`、标题「淘宝旺旺」、目标群、托盘账号 Name 均经真机核实。共享 `ImApp` 增加默认空图片模板/池，`open_app/tray` 增加可选 config 托盘 hint；阿里旺旺在业务 case 内自组装专属提示词，统一“先唯一文件名文字、后图片、hard 回车一次、只读气泡验收”。拖拽半屏预览被遮时先关闭 Explorer、恢复原窗口矩形再确认。4 条分别 `audit` 真机通过，DLP 均命中 `AliIM.exe`；覆盖 Base 已新增 4 条且仓库遗漏为 0 | 无独立设计稿；权威现状见 [tech_design.md](./tech_design.md) Changelog 2026-08-10 与 [LESSONS.md #23](../LESSONS.md) | 已同步代码/config/secret 模板/测试/add-case skill/覆盖 skill/`tech_design.md`/LESSONS；架构拓扑不变，图集无需修改 |
| `CHG-018` | 数据安全回归 case 承接与独立执行层 | 部分完成 | 已完成 Bits/XMind 61 条逐项分析，目标候选 38 条。CHG-025 已落第一条纵向切片：Phase 0/1 的最小独立 registry/loader/runner/local writer 与 R40/R41 水印 case；其余 assertion adapter、R42～R61 候选仍按阶段推进。回归链路不复用或修改主 `CaseSpec`、`CaseRunner`、`VerificationManager`、Aggregator、CSV Writer，不提供 `--lark-base`，不进入覆盖率同步 | [XMind 原文快照](./regression_case_analysis/SOURCE_CASES.md)、[自动化 Case 清单](./regression_case_analysis/AUTOMATION_CASES.md)、[框架方案](./regression_case_analysis/framework_adaptation.md) | 后续每个 Phase 拆独立 CHG 并同步代码/测试/README/`tech_design.md`/图集；默认主 run 和覆盖率同步必须继续排除回归目录 |
| `CHG-023` | Lark Windows IM 四类外发与飞书进程隔离 | 已完成 | 新增海外版 Lark 拖拽/上传/复制粘贴/自带截图 4 条 case，统一外发到配置群聊“DLP测试”。真机确认 Lark=`C:\Program Files\Lark\app\Lark.exe`、可见主窗标题含 `lark`、托盘 Name 为“Lark - 1 个运行窗口”；国内飞书为独立 `Feishu.exe`/“飞书 已固定”。修复既有 apps/tray 交叉登记，避免两款同时运行时认错客户端。4 条 GUI/视觉均通过，文件三类均需确认发送、非 auto-send；未启用 DLP checker，按硬约束 #10 记 `inconclusive`。复制粘贴首跑暴露 Judge 引用历史文件误判，手动发送验收已改为 before→after 必须新增当前最新文件气泡；全量 247 项单测通过。覆盖 Base 新增 4 条 Case、1 条软件汇总，仓库遗漏为 0 | 无独立设计稿；权威现状见 [tech_design.md](./tech_design.md) Changelog 2026-08-17 | 已同步代码/config 模板/测试/README/`tech_design.md`/add-case skill/覆盖 Base；反哺生成上传/复制粘贴/截图 3 份 Windows hints；架构拓扑不变、无需改图集 |
| `CHG-022` | AI应用通道扩展：Poe Windows 对话外发 | 已完成 | 新增 Poe 3 条文档外发 case（拖拽、上传、复制粘贴），不含截图。真机核对 `Poe.exe` 安装于 `%LOCALAPPDATA%\Poe`、主窗标题恒空、点“+”直接弹系统文件对话框、回车即发送。`apps.py` 新增默认不放行的空标题 app 名单，只对 `poe.exe` 强匹配放行；`AiChatApp` 新增默认 False 的 `attach_opens_dialog_directly`，Poe 上传只点一次“+”。3 条 GUI/视觉均通过；同时将 AI 对话验收统一收紧为“我方本次唯一消息与附件 + 输入框清空 + 该消息后新 AI 回复”，上传复验时 Judge 明确认出全部证据。未启用 DLP checker，按硬约束 #10 均记 `inconclusive`。收尾后主窗销毁但 4 个后台进程仍在，再次启动 `Poe.exe` 后进程数不变并恢复唯一主窗，故启用 `relaunch_if_hidden`。全量 239 项单测通过；覆盖 Base 新增 3 条 Case、1 条软件汇总，仓库遗漏为 0 | 无独立设计稿；权威现状见 [tech_design.md](./tech_design.md) §3.8 与 Changelog 2026-08-17 | 已同步代码/测试/README/`tech_design.md`/add-case skill/覆盖 Base；反哺生成 Poe 上传与拖拽两份 Windows hints；架构拓扑不变、无需改图集 |
| `CHG-021` | AI应用通道扩展：元宝 + Kimi Windows 对话外发 | 已完成 | 在 `desktop_app.ai_chat` 共享脚手架上新增元宝（沿用千问 5 类外发）与 Kimi（文件/图片共用上传入口，故 4 条：拖拽文档、上传文件、复制粘贴文档、截图）。`apps.py` 登记 `yuanbao.exe` / `Kimi.exe`（标题短词，配合进程名强匹配）。`AiChatApp` 新增两个差异开关吸收 app 行为、不改共享逻辑：`screenshot_auto_capture`（Kimi 点“+”菜单截图行即自动截当前窗口、无需框选/确认）、`document_send_via_button`（Kimi 回车只换行不发送，文档改走“点发送按钮 + change 验收”，硬性要求聊天区新增我方消息且输入框清空，既治回车不发送、又避免 presence 误判同一对话旧消息）；两开关默认千问/元宝语义（`False`），零回归。真机：Kimi 上传文件、复制粘贴文档 GUI/视觉通过；上传文件 `--policy audit` 真跑，DLP 客户端 `PreFileAudit` 命中 `Kimi.exe`+唯一文件名但未升级为带 UUID 的已提交事件，经用户核对确认为 DLP 侧未覆盖 Kimi 的有效缺口（非框架问题），按硬约束 #10 记 `failed` 不翻案。**补记既存漂移**：元宝（commit 44f9d1b）当时改脚手架未登记，本项一并纳入 | 无独立设计稿；权威现状见 [tech_design.md](./tech_design.md) Changelog 2026-08-17、图 7 | 已同步代码/测试（`tests/test_ai_chat_kimi.py`）/`tech_design.md`（§3.8 + Changelog）/README（AI应用外发章节扩到千问/元宝/Kimi）/add-case skill（windows.md §6.3 补两个新开关）；图 7 拓扑不变、无需改图集 |
| `CHG-020` | Run 级 DLP 事件审计（疑似误报旁路） | 已归档 | 2026-08-13 用户确认三条核心口径（旁路只观测 / 截图重试计 `expected_retry` / 进程名只记录不硬匹配）后完成编码：记录 run 真实时间边界，在时间窗内全量扫描两端 DLP 客户端日志事件，用「预期事件台账」（文件类按唯一文件名、截图/图片类按发送 step 时间窗归属，重试计 `expected_retry`、边界不清计 `ambiguous`）反向筛出无法解释的 `unexpected` 事件，单独输出 `<run_id>_dlp_event_audit.json` + `<run_id>_unexpected_dlp_events.csv` + 控制台一行汇总。**旁路诊断**：不注册 checker、不进 `expected_names`、不改任何 case 结论/退出码；由 `--scan-unexpected-events` 控制、默认关、可整体删除（`CaseRunner.auditor` 为 None 时逐字节零回归）；扫描失败只记 `inconclusive`、不冒充干净。实现落点：新增 `verify/event_audit.py`（`RunEventAuditor`），两端后端新增只读 `collect_events`，`Step` 新增默认空 `dlp_expectation` + `expect_dlp` 标注，IM/AI 对话/Web 共享工厂已标注外发 step。**对未来 case 的兼容要求已写入 add-case skill**。**已归档（2026-08-17）**：设计稿达门槛，`git mv` 入 `docs/archive/`，代码/配置/其它文档引用已改指归档路径，顶部加归档说明，本稿保留完整设计推导供追溯 | [archive/run_dlp_event_audit_design.md](./archive/run_dlp_event_audit_design.md)（已归档） | 已同步代码/测试（`tests/test_event_audit.py` 23 项全绿）/config/README/`tech_design.md`（§5 扩展点 + Changelog）/add-case skill；两端后端仅新增只读 `collect_events(window_start, window_end)`，开关关闭与现状逐字节一致（零回归）；架构三层拓扑不变，图集无需修改。**2026-08-14 修复（Windows）**：真机复核发现 `event_marker` 行首锚挡不住同一 cpp 的批量管理汇总行（`start upload dlp event`/`upload dlp batch`/`associate tag`，实测同 marker 3554 行仅 1 行真事件，其余无 UUID+无 path），会被审计规则 6 全判 `unexpected` 淹没产物；在审计专用 `collect_events` 末尾过滤「无 UUID 且无 path」行修复（case 级 `check()` 不动、零回归），设计稿新增 §6.1、`tech_design.md` Changelog 追加、新增 `tests/test_dlp_log_windows.py::CollectEventsNoiseFilterTests` 5 项，真机复验修复后 30 分钟窗 `total=0/unexpected=0` |
| `CHG-019` | 新增 AI应用通道并适配千问 Windows 对话外发 | 已完成 | 新建 `desktop_app.ai_chat` 独立目录与 Windows 共享脚手架；千问覆盖拖拽文档、上传文档、上传图片、复制粘贴文档、截屏提问 5 条。每条先确认日常模式，再按“左侧第一条历史对话；无历史则当前页”进入；附件前写测试声明与唯一标识。文档 hard 回车一次，图片/截图 AI 只点一次发送按钮；AI 的“收到”回复无验收权。5 条 GUI/视觉均成功，上传文档 audit 曾命中 `qianwen.exe`，其余无 policy 运行按设计为 `inconclusive`。补充千问隐藏主窗单实例恢复，主配置显式 `千问: close` 以在整组结束后关闭主窗到托盘并保留登录态；同时修复 audit/block 将后续执行失败被中间视觉或日志翻案的问题。全量 `172 tests OK`；覆盖 Base 新增 5 条 Case 和 1 条软件汇总，仓库遗漏为 0 | 无独立设计稿；权威现状见 [tech_design.md](./tech_design.md) Changelog 2026-08-12、图 7 与 [LESSONS.md #24](../LESSONS.md) | 已同步代码/config/测试/README/add-case skill/`tech_design.md`/图集/LESSONS/覆盖清单 |

### 3.1 当前完成基线

这些阶段已完成，但其所属设计文档仍有后续项，因此暂不归档：

| 已完成阶段 | 完成证据 | 所属文档为何仍保留 |
|---|---|---|
| 策略断言 P0/P1：policy、`delivery_outcome`、日志分型、block 聚合、重试联动 | `verify/aggregator.py`、`verify/dlp_log/_legacy.py`、`tests/test_p0_guards.py` | `CHG-002/003` 未终态 |
| Windows/Mac DLP 加密日志验证：平台独立解密、时间窗、真实事件解析、报告/event_id 回填 | `verify/dlp_log/_windows.py`、`verify/dlp_log/_mac.py`、`tests/test_dlp_log_{windows,mac}.py`；Mac 企业微信文件/截图 audit 真跑通过 | `CHG-001` 已完成；设计文档仍关联 `CHG-003` 的 block 分型开放项 |
| 服务端事件回查（CHG-004）：run 级 event_id 回查、全局补查一次、真实登录+查询客户端、策略门控、事件ID 列、**命中裁决加严（恰好一条 + 处置 vs policy）**、**会话直传鉴权（cookie 优先、登录回退）** | `verify/server_event.py`、`verify/feilian_client.py`、`report/schema.py`、`report/writer.py`、`verify/dlp_log/_windows.py`、`verify/manager.py`、`case/runner.py`、`verify/__init__.py`、`config/*`、`README.md`、`pyproject.toml`、`tests/test_server_event_requery.py`（全量 99 项通过） | `CHG-004` 已完成并**已归档（2026-08-07）**，设计稿移入 `docs/archive/`（Mac 端 `CHG-001` 是独立改动项，不阻塞本项归档） |
| provision P0-P2：配置迁移、清单 Schema、默认关闭的探测骨架 | `provision/`、`config/apps.yaml`、`tests/test_provision.py` | `CHG-005/006` 暂缓但未取消 |
| 架构 Review P0/P1：聚合语义收敛、冗余 judges 删除、文档入口整理 | `architecture_review_notes.md` 清单 #1-4/#7 | `CHG-007` 的清单 #5/#6 未完成 |
| RunContext / OutcomeAggregator 解耦 | [architecture_decoupling.md](./architecture_decoupling.md)、`tech_design.md` 变更记录 | 当前仍被 AGENTS/tech_design 引用，作为架构决策说明保留 |

---

## 4. 技术文档生命周期

| 文档 | 类型 | 关联改动 | 当前状态 | 归档门槛 |
|---|---|---|---|---|
| [tech_design.md](./tech_design.md) | 长期权威文档 | 全部框架改动 | 长期维护 | 不归档 |
| [tech_design_diagrams.md](./tech_design_diagrams.md) | 长期权威图集 | 架构/数据流改动 | 长期维护 | 不归档 |
| [change_tracker.md](./change_tracker.md) | 状态台账 | 全部待办与文档 | 长期维护 | 不归档 |
| [dlp_client_log_verify_design.md](./dlp_client_log_verify_design.md) | 阶段性设计 | `CHG-001/003` | Windows/Mac 后端及 Mac audit 真跑完成；策略分型仍待 block 样本 | `CHG-003` 完成或取消，且 block 分型结论已上移 `tech_design.md` |
| [dlp_policy_assertion_design.md](./dlp_policy_assertion_design.md) | 阶段性设计 | `CHG-002/003/004` | P0/P1 完成，P2/P3 未终态 | P2/P3 完成或明确取消，§9 开放问题全部关闭，稳定语义已上移权威文档 |
| [archive/server_event_requery_design.md](./archive/server_event_requery_design.md) | 阶段性设计 | `CHG-004` | **已归档（2026-08-07）** | 已达门槛并归档：真机联调完成、run 级回查数据流已上移 `tech_design.md`（§4 #4、§5、Changelog）与图集；`git mv` 入 `docs/archive/`，3 处代码/配置引用已改指归档路径，顶部加归档说明标注设计期快照已被实现推翻 |
| [app_provisioning_design.md](./app_provisioning_design.md) | 阶段性设计 | `CHG-005/006` | P0-P2 完成，P3/P4 暂缓 | P3/P4 完成或明确取消，仍需保留的安全/配置约束已上移权威文档 |
| [architecture_review_notes.md](./architecture_review_notes.md) | 临时 Review | `CHG-007` | 5/7 项完成 | 清单 #5/#6 完成或取消，结论合并进 `tech_design.md` 后归档 |
| [max_steps_per_case_proposal.md](./max_steps_per_case_proposal.md) | 提案 | `CHG-008` | 待评估、暂不实施 | 实施完成，或明确否决并把最终决策写入 `tech_design.md`/`LESSONS.md` |
| [scale_up_plan.md](./scale_up_plan.md) | 路线图 | `CHG-009` | 与当前代码部分重叠，待复核 | M1-M6 均标为完成/取消，活约定提炼进 add-case skill 与权威文档 |
| [architecture_decoupling.md](./architecture_decoupling.md) | 架构决策说明 | 已完成基线 | 保留 | 只有当内容已完整吸收进 `tech_design.md` 且所有引用已更新时才可归档 |
| [archive/browser_channel_design.md](./archive/browser_channel_design.md) | 阶段性设计 | `CHG-014` | **已归档（2026-08-17）** | 已达门槛并归档：10 款浏览器已接入并真机通过，稳定约束已上移 `tech_design.md`、README 与 add-case skill；`git mv` 入 `docs/archive/`，README/tech_design/add-case 3 处引用已改指归档路径，顶部加归档说明 |
| [archive/run_dlp_event_audit_design.md](./archive/run_dlp_event_audit_design.md) | 阶段性设计 | `CHG-020` | **已归档（2026-08-17）** | 已达门槛并归档：编码/测试/文档已同步，稳定约束（默认关/不改结论/`collect_events` 接口）已上移 `tech_design.md` §5 与 Changelog；`git mv` 入 `docs/archive/`，代码/配置/其它文档引用已改指归档路径，顶部加归档说明，本稿保留完整设计推导供追溯 |
| [regression_case_analysis/](./regression_case_analysis/README.md) | 回归分析 / 分阶段实施说明 | `CHG-018/025/026` | 61 条已分析；目标候选 38 条；Phase 0/1 的独立 registry/runner/local writer、R40/R41 与管理后台 run 级会话复用已实现，其余 adapter/case 分阶段推进 | 38 条均完成/取消，稳定约束已上移 `tech_design.md`/对应 skill，回归 case 清单仍有维护价值时保留 |

---

## 5. 每次改动的文档维护流程

### 5.1 新增需求或提案

1. 在 §3 新增 `CHG-NNN`，写清范围、状态、触发条件和对应文档。
2. 没有详细设计稿时，先在“详细技术文档”列标记“待新建”；复杂框架改动不得只写在本文。
3. 需要新增 CLI、模块、接口、数据流、报告或硬约束时，提前列出必须同步的权威文档。

### 5.2 开始实施

1. 状态改为 `进行中`。
2. 在详细设计稿中标出本次实施范围，避免把未来阶段误写成已实现。
3. 对框架改动先核对默认关闭、可删除、零回归、安全和平台隔离约束。

### 5.3 完成实施

同一次任务、提交前完成以下核对：

- [ ] 代码和配置已落地，行为以代码实况为准。
- [ ] 风险对应的单测/集成验证已完成并记录结果。
- [ ] 详细设计稿中的阶段/清单已更新为完成。
- [ ] 框架改动已更新 `tech_design.md` 对应章节和 Changelog。
- [ ] 架构或数据流变化已更新 `tech_design_diagrams.md`。
- [ ] 用户可见参数、配置和产物变化已更新 README/example。
- [ ] 本文状态、完成证据和剩余项已更新。

只有全部满足后，状态才能改为 `已完成`。

### 5.4 取消或暂缓

- `暂缓`：保留未完成状态，必须写明重新启动的触发条件。
- `已取消`：写清取消原因、替代方案和影响；若原方案已被取代，旧文档进入归档审查。
- 不得用“暂缓”伪装“已完成”，也不得因为代码暂时不用就删除设计背景。

---

## 6. 归档门禁

阶段性技术文档只有同时满足以下条件才可以归档：

1. 关联的全部 `CHG-NNN` 均为 `已完成` 或 `已取消`，不存在 `暂缓/等待外部输入`。
2. 文档内的阶段表、TODO、开放问题已全部关闭；历史示例不会再被当作现状。
3. 仍然有效的架构、约束、配置和运维知识已提炼到 `tech_design.md`、README、AGENTS 或对应 skill。
4. 使用 `rg "<文件名>"` 检查源码、配置和其它文档引用；先更新引用，再移动文件。
5. 在文件顶部添加：`> 已归档（YYYY-MM-DD）：<完成或取消原因>`。
6. 使用 `git mv docs/<file> docs/archive/<file>`，不复制，不丢历史。
7. 更新本文 §3/§4 为 `已归档`，写明归档日期与新路径。

归档后原则上只读。若需求重新启动，应创建新的改动 ID 和新设计稿，引用旧归档作为历史背景，不直接复活旧文档。

---

## 7. 本次盘点发现的文档健康问题

以下问题已映射到 §3，不在本次直接改写其它文档：

1. `app_provisioning_design.md` 顶部仍写“暂不含实现”，但其 P0-P2 已落地；推进 `CHG-005/006` 前应先校正状态头。
2. `scale_up_plan.md` 仍按早期 M1-M6 设想描述，但当前已有 `im_windows_common.py`、`contacts.py` 和多款 Windows IM case；需通过 `CHG-009` 按代码重新核对，不能直接照旧计划实施。
3. `tech_design.md` 硬约束 #8 提到 `cleanup_screenshots.py`，仓库实际不存在；已登记为 `CHG-010`。
4. `architecture_review_notes.md` 的审查时点和测试数量是历史快照；在 `CHG-007` 收尾时统一更新并归档，不把旧数字当当前基线。
