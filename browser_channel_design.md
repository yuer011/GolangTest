# 浏览器通道设计（Windows）

> 已归档（2026-08-17）：CHG-014 本期 10 款浏览器已接入并真机通过，稳定约束已上移
> tech_design.md、README 与 add-case skill；本稿转为只读历史留存，后续若重接世界之窗等
> 须另立改动 ID 与新设计稿，不直接复活本文。
>
> 状态：本期完成（CHG-014，2026-08-08）
>
> 本期范围：`https://dlptest.com/https-post/`，已接入 Edge、谷歌、360 极速、Firefox、
> 2345、360 安全、猎豹、傲游、QQ、搜狗共 10 款浏览器，各覆盖**拖拽上传**与
> **点击上传**。世界之窗因页面/UI 异常，本期明确跳过。

## 1. 目标与边界

Windows DLP 管理范围包含 11 款浏览器：

1. 360 极速浏览器
2. 谷歌浏览器
3. 火狐浏览器
4. Edge 浏览器
5. 2345 浏览器
6. 360 安全浏览器
7. 猎豹浏览器
8. 傲游浏览器
9. QQ 浏览器
10. 搜狗浏览器
11. 世界之窗浏览器

除世界之窗外，其余 10 款均已在本机逐款核对安装路径、exe、启动协议、窗口复用和清理行为。
世界之窗不生成不可运行 case；后续若重新接入，仍须另行真机核对，不复用其他浏览器参数。

DLPTest 页面只验证文件 HTTPS POST：

- 拖拽上传：从文件资源管理器拖文件到 `File upload` 区域，再点击该表单的 Submit。
- 点击上传：点击 `Drop files here or click to add`，在系统文件对话框选文件，再点击 Submit。
- 页面接收成功的明确结果为：
  `Received. Nothing was stored. Check your DLP console for an incident.`

页面“文件已进入队列”不等于发生外发；只有点击 Submit 后才会向 `/api/http-post/`
发起 multipart POST。站点说明请求体会被读取后丢弃，不保存、不转发。

本期不包含：

- 邮箱网站、Web IM 网站及其登录/会话协议；
- Mac 浏览器实现；
- 世界之窗浏览器；
- 通过 DOM/WebDriver 直接操作页面。正式 case 仍走项目既有的截图 + AI GUI 操作，
  确保经过真实桌面浏览器与 DLP 链路。

## 2. 目录与分类

Web 通道按**网站业务类型**分二级目录：

```text
cases/web/
  im/                 # 后续：Web IM
  email/              # 后续：Web 邮箱
  other/              # 通用网站 / 协议测试站
    windows/
      case_2345.py
      case_360_safe.py
      case_360_speed.py
      case_chrome.py
      case_edge.py
      case_firefox.py
      case_liebao.py
      case_maxthon.py
      case_qq_browser.py
      case_sogou.py
```

本期 DLPTest 属于 `other`，`channel="web.other"`。浏览器是执行载体，同时也是报告的
`app` 聚合维度；每个浏览器文件只保留两条薄 case。case id 采用：

```text
web.other.<browser>.dlptest_https_post.drag_drop
web.other.<browser>.dlptest_https_post.click_upload
```

不采用 `other/<browser>/<site>.py` 的更深目录：网站数量尚少时会制造空层级；以后同类网站增加，
可在同一浏览器文件里继续登记不同 site 的 case，站点流程仍由下述适配层复用。

## 3. 分层

### 3.1 浏览器会话层：`dlp_auto/case/web_windows_common.py`

只负责与具体网站无关的 Windows 浏览器能力：

- 从 `config.web.browsers.windows.<key>` 读取 exe、启动协议和等待时间；
- 使用项目内唯一临时 profile 新开隔离实例，绝不激活或复用用户已有浏览器窗口；
- 记录启动前窗口集合、本次新增 HWND、根 PID 与子进程集合；
- 同一浏览器的多条 case 复用这一个受管窗口，每条 case 开头重置到目标 URL；
- 提供最大化、前台激活、左侧资源管理器布局、系统文件对话框填路径等确定性原语；
- Chrome 使用 `managed_session`，只关闭本次 HWND/PID 树，保护用户原窗口；
- 用户不日常使用的浏览器使用 `all_under_roots`，冷启动前和 app 组结束后都按配置的安装
  根目录清零进程；进程真实映像不在安全根目录内时绝不结束；
- 删除临时 profile；Firefox 等延迟退出进程在限定时间内重试清理，超时显式报错；
- cleanup 精确关闭本 case 打开的上传目录资源管理器，并删除本次唯一文件。

会话层不识别 DLPTest、邮箱或 IM 页面元素。

### 3.2 站点协议层：`dlp_auto/case/web_dlptest_windows.py`

只描述 DLPTest HTTPS POST 页面协议：

- 目标 URL 从 `config.web.sites.dlptest.https_post_url` 读取，缺失即明确报错，不臆造；
- 拖拽上传和点击上传各自的 AI 导航话术；
- 上传前把 `File upload` 卡片居中；Submit 不可见时只允许向下滚动一次；
- Submit 前 hard step 重新激活受管浏览器，避免其它窗口抢前台；
- 明确右侧 `File upload` 表单、唯一文件名，并用 `action_limits={"click": 1,
  "scroll": 1}` 在执行层限制 Submit 只点一次、兜底只滚一次；
- Firefox、QQ、360 极速可声明独立 AI 弹窗步骤，按当前视觉关闭浏览器非业务弹窗，
  禁止固定坐标；
- 以页面返回的接收成功文案做视觉验收；
- 复用浏览器会话层的打开、布局、填对话框和 cleanup。

未来 `web/email`、`web/im` 可复用浏览器会话层，但各自新增站点协议层，避免把登录、收件人、
会话等差异塞进 DLPTest 流程。

### 3.3 case 矩阵层：`cases/web/other/windows/case_<browser>.py`

每款浏览器只声明：

- 报告名、配置 key；
- 两个 `@case` 的报告字段；
- 调用 DLPTest 的 `drag_drop_steps()` / `click_upload_steps()`；
- 注册精确的 browser session teardown。

不复制文件生成、窗口管理或页面操作长话术。

## 4. 会话隔离与清理

### 4.1 为什么不能复用 `apps.open_app`

`apps.open_app` 的语义是“已有可见窗口则激活”，适合 IM，但违反浏览器要求：

- 会抢占用户已打开的浏览器窗口；
- 导航会覆盖用户当前标签；
- 按浏览器进程名统一 teardown 可能误关用户窗口。

浏览器通道必须创建**受管独立实例**。

### 4.2 独立实例

Edge、Chrome、2345、猎豹、傲游、QQ、搜狗使用经真机验证的 Chromium 隔离启动协议：

```text
<exe> --user-data-dir=<项目内唯一临时目录>
      --new-window <url>
      --no-first-run
      --no-default-browser-check
      --disable-background-mode
```

Firefox 使用 `-no-remote -profile <目录> -new-window`。360 极速、360 安全使用经实证的
`windows_shell_cold_start`，启动后再在受管窗口内确定性导航 URL，不把 Chromium 参数硬套。

profile 路径位于 `.tmp/browser_sessions/`，包含浏览器 key、UTC 微秒、PID/随机后缀，
不同运行不复用。是否使用该 profile 由启动协议决定。

### 4.3 精确识别本次窗口

启动前记录目标 exe 的全部可见顶层 HWND；启动后轮询同 exe 新增的可见 HWND，取面积最大的
新窗口作为本次受管窗口。窗口识别不依赖网页标题，避免标题变化或相同标签误伤。

### 4.4 精确关闭

浏览器 app 的两条 case 跑完后：

1. 向记录的受管 HWND 发 `WM_CLOSE` 并等待实例退出；
2. `managed_session` 只兜底结束本次根 PID / 已记录子进程；
3. `all_under_roots` 再按配置安全根目录清零残留，确保下次冷启动；
4. 删除本次临时 profile；
5. Chrome 不触碰启动前已存在的任何 HWND/PID。

即使 case 中途失败，app 级 teardown 仍执行。拖拽 case 自己打开的资源管理器还会通过
`cleanup()` 在 case finally 中精确关闭，形成双层清理。

## 5. 文件与窗口布局

测试文件全部在项目内：

```text
.tmp/dlp_web_sample_template.txt
.tmp/web_upload/dlptest_<browser>_<时分秒>_<随机>/
  dlp_web_sample_<时分秒>_<随机>.txt
```

模板放在上传目录外；每条 case 创建独占目录并只生成一个唯一副本，既不删除其它 run/case
的文件，也保证 AI 面前只有一个候选文件；basename 写入 `ctx.extras["sensitive_file"]`。

拖拽上传布局：

1. 受管浏览器窗口最大化；
2. 文件资源管理器打开本次唯一文件目录；
3. 资源管理器确定性移动到工作区左侧约 40%，并置前；
4. 浏览器仍铺满背景，DLPTest 右侧 `File upload` 区域保持可见；
5. AI 只做“从左侧唯一文件拖到右侧上传框 → 确认队列出现唯一文件 → 点一次 Submit”。

点击上传不打开资源管理器。AI 只点击上传框触发系统文件对话框，完整路径由 hard step 调
`apps.fill_open_dialog()` 写入，避免视觉模型输入长路径。

文件进入队列后，Submit 会被队列向下推。当前在**上传前**执行：

1. `Ctrl+Home` 回到顶部；
2. `ArrowDown` 5 次，总计约 200 CSS px，使 `File upload` 卡片居中；
3. 上传后通常无需滚动；只有当前画面确实看不到右侧 Submit 时，AI 才允许向下滚动一次；
4. 滚动一次仍找不到就 `call_user`，禁止第二次滚动；
5. Submit 前重新激活受管浏览器，动作上限保证只执行一次点击。

该方案避免 `PageDown` 把 Submit 顶到视口顶部，也不依赖跨 DPI/浏览器不稳定的滚轮像素估算。

## 6. 配置

所有站点 URL、浏览器路径和启动协议只从 `config/config.yaml` 读取：

```yaml
web:
  sites:
    dlptest:
      https_post_url: https://dlptest.com/https-post/
  browsers:
    windows:
      chrome:
        executable: C:\Program Files\Google\Chrome\Application\chrome.exe
        launch_protocol: chromium_isolated
        window_wait_sec: 15
      firefox:
        executable: C:\Program Files\Mozilla Firefox\firefox.exe
        launch_protocol: firefox_isolated
        process_cleanup:
          mode: all_under_roots
          roots: [C:\Program Files\Mozilla Firefox]
```

10 款路径均已在当前真机核对存在。换机路径不同只改配置，不改 case。缺配置、路径不存在、
协议未支持或 `all_under_roots` 缺安全根目录时明确报错并指出缺哪个字段。

## 7. 验收

### 7.1 静态与隔离验证

- `py_compile` / 全量模块加载；
- 配置缺失、路径不存在、未知协议有明确错误；
- 启动探针确认新 HWND 不在启动前集合；
- 关闭探针确认本次 HWND/PID 消失、启动前窗口仍在；
- 临时 profile 与上传副本清理完成。

### 7.2 真机 GUI

真机 GUI 只允许：

```powershell
.\scripts\run_case.ps1 -Filter <case_id 子串> -DebugShots -Policy audit
.\scripts\wait_run.ps1 -TimeoutSec 600
```

适配阶段默认 `-Policy audit`，它会自动启用客户端日志验收；本期不传 `-CheckServer`。
每款浏览器各跑：

1. `drag_drop`
2. `click_upload`

验收点：

- 每款浏览器只新增一个隔离窗口；
- 两条 case 复用该窗口并重置页面；
- 文件只加入/提交一次，无循环上传；
- accepted 路径显示明确成功文案；
- app 分组结束后受管浏览器窗口和资源管理器均无残留；
- Chrome 用户原有窗口不被导航、不被关闭；
- 报告分别保留执行/视觉结果和客户端日志结果；日志无事件时必须失败，不用 GUI 成功翻案。

### 7.3 本期真机结果（2026-08-07 至 2026-08-08）

- Edge 点击上传：文件对话框 2-3 个 AI step，Submit 2 个 AI step，完整成功文案通过；
- Edge 拖拽上传：一次拖拽进入唯一文件队列，Submit 一次点击成功；
- Chrome 整组：两条 case 复用同一受管窗口，第二条开头重置 URL，不新开第二窗口；
- Chrome 拖拽 / 点击上传：两条均在受管窗口内完成，Submit 单次点击，完整成功文案通过；
- Chrome 用户原有窗口基线 `HWND=66610 / PID=20872` 在整组结束后仍存在且未被导航；
- 每组结束后，受管浏览器 HWND/进程、项目内临时 profile、上传目录和本 case Explorer
  均无残留；
- 2345、Firefox、猎豹、傲游、QQ、搜狗在 `audit` 下各 `2/2 passed`，客户端日志分别命中
  `2345Explorer.exe`、`firefox.exe`、`liebao.exe`、`Maxthon.exe`、`QQBrowser.exe`、
  `SogouExplorer.exe` 及本次唯一文件名；服务端回查未启用；
- 360 极速、360 安全的 4 条 GUI/视觉均成功，但客户端日志验收均失败，报告正确显示
  “执行成功、已发出、DLP 验收不通过”：
  - 360 极速只有软件使用记录，没有本次上传的外发 hook / 事件；
  - 360 安全能捕获 `360se.exe` 和文件路径，但日志显示 `browser_url/browser_text` 为空，
    `skip audit match`，随后 `returns true without event`；
- 世界之窗因页面/UI 异常，本期不生成 case；
- 合并最新远端覆盖率同步能力并补齐浏览器 App Key 映射后，全量标准库回归
  `123 tests OK`。

## 8. 后续接入清单

世界之窗若后续重新接入，必须重新收集：

- 实际安装路径；
- 顶层窗口所属 exe basename；
- 是否支持独立 profile / 新窗口参数；
- 首次启动页、默认浏览器提示是否能稳定关闭；
- 关闭受管窗口后是否残留后台进程；
- 拖拽与点击上传在该浏览器是否有专有确认弹窗。

信息不全时状态记“等待外部输入”，不复制现有浏览器参数冒充已支持。
