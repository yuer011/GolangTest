"""桌面应用 - 即时通信 - QQ - DLP 外发 case 集合（Windows 端）。

平台：Windows（本文件位于 cases/desktop_app/im/windows/，仅含 windows 端 case）。
迁移标注：每个 @case 均显式声明 platforms=[Platform.WINDOWS]，目录与声明双重标注。

本文件参照同目录 case_feishu.py 的四类外发 case 改写，QQ 专有差异（真机实测/用户确认）：
- 应用名：Windows 上 QQ（NTQQ 新版）可执行文件为 QQ.exe，主窗口标题就是「QQ」
  （极短，标题子串几乎必误伤，故窗口匹配靠 qq.exe 进程名强匹配，见 apps._EXE_NAMES）。
- 外发目标：**群「DLP测试」**（飞书 case 发给个人联系人；QQ 这里统一发到该测试群）。
- 全局搜索快捷键：**Ctrl+F**（用户确认；飞书为 Ctrl+K）。
- 自带截图：聊天窗工具栏截图按钮（用户确认，交互与飞书同款：点按钮→框选→确认→
  进输入框→发送）。
- 文件管理器 / 敏感文件目录：与飞书 case 复用同一套（explorer 打开项目内 .tmp/dlp_test）。

IM 最低场景覆盖（见 add-case SKILL 二·补充）——QQ Windows 端四类外发全覆盖：
1. 拖拽外发       → case_drag_drop  「拖拽文件到对话框」
2. 自带上传外发   → case_upload     「对话框文件上传」（加号/文件夹入口→文件）
3. 复制粘贴外发   → case_copy_paste 「复制粘贴文件外发」（复制文件本体 Ctrl+C/V）
4. 自带截图外发   → case_screenshot 「自带截图外发」（聊天框工具栏截图按钮）

每个 @case 对应报告里的一行「软件 × 测试场景 × 具体外发动作」。
"""
from __future__ import annotations

import os
import subprocess
import time
import uuid
from datetime import datetime

from dlp_auto.actions import apps, clipboard, keyboard
from dlp_auto.case.contacts import outbound_target
from dlp_auto.case.spec import Step, ai, case, cleanup, hard, step
from dlp_auto.core.platform import Platform

_APP = "QQ"
_APP_NAME = "QQ"                 # 系统识别名 / 窗口标题关键字（可执行文件 QQ.exe）
# 外发目标会话（用户创建的测试群）。默认 "DLP测试"，可在不入库的
# config/contacts.yaml 里按平台覆盖（换人/换机时改配置即可，无需动 case）。
_GROUP = outbound_target("desktop_app.im", "qq", default="DLP测试")
# 敏感测试文件来源目录（Windows）。放在项目工作目录下的 .tmp 内，
# 既保证可读写（不触发外部路径的权限/沙箱限制），又与运行产物一起被 .gitignore 忽略。
_SENSITIVE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "..", ".tmp", "dlp_test",
)
_SENSITIVE_DIR = os.path.abspath(_SENSITIVE_DIR)
# 固定样例文件路径（各 case 共用；文件名全 ASCII，便于在系统文件对话框里直接输入路径）
_SAMPLE_FILE = os.path.join(_SENSITIVE_DIR, "dlp_sample.txt")


def _app_name(ctx) -> str:
    if ctx is None or ctx.settings is None:
        return _APP_NAME
    return ctx.settings.get("platform", "overrides", "windows", "app_names", "qq",
                            default=_APP_NAME)


def _open_qq(ctx) -> None:
    # QQ 冷启动 + 登录态恢复较慢，wait 长一些确保窗口稳定在前台。
    # wake_tray=True：QQ 常缩系统托盘后台挂机（进程在、主窗隐藏），此时既不能重开
    # （非单例会弹登录窗）也不能外部硬拉（Electron 僵尸窗，见 LESSONS #18），唯一可靠
    # 唤窗方式是模拟点击托盘图标 —— 开启该能力（需装 uiautomation，见 pyproject [tray]）。
    # 未装依赖 / 点不到时自动回退「提示人工点托盘」，不影响主流程。
    apps.open_app(_app_name(ctx), wait_sec=6.0, wake_tray=True)


def _focus_search(ctx) -> None:
    """激活 QQ 并按 Ctrl+F 打开全局搜索（确定性、无害）。

    仅负责「把 QQ 弄到前台 + 打开搜索框」这类确定动作；到底搜谁、点哪条结果，
    交给后面的 AI 步视觉判断（DLP 通道众多，进会话这类视觉导航若全写死 hard step
    不可维护）。

    关键：Windows 前台锁可能让单次激活只闪任务栏而未真正置前，若此时按 Ctrl+F，
    快捷键会打到错误窗口（如 IDE），搜索框根本没开、后续输入全丢（见 LESSONS.md #6）。
    故先用 ensure_foreground 复核+重试确保 QQ 确实在前台，再发 Ctrl+F；仍失败则
    显式打印告警（不静默），便于日志定位。
    """
    ok = apps.ensure_foreground(_app_name(ctx))
    if not ok:
        print("  ⚠️ QQ 未能确认置于前台（前台锁/窗口未找到）；Ctrl+F 可能打到其它"
              "窗口。请确保 QQ 已登录且未最小化。后续 AI 步将尝试视觉兜底。")
    time.sleep(0.5)
    keyboard.hotkey("ctrl", "f")          # QQ Windows 全局搜索
    time.sleep(1.0)


def _enter_conversation_steps() -> list[Step]:
    """四类 case 共用的前置步骤：打开 QQ → 聚焦搜索 → AI 进入「DLP测试」群会话。

    抽成函数避免四个 case 重复维护同一段指令（尤其搜索进会话的 ai 话术）。
    进会话交给 AI 视觉导航；话术基于飞书 case 实测稳定路径（见 LESSONS.md #3）：
    必须先在搜索框输入名字过滤结果，再在结果里识别**群会话条目**点击，禁止在
    「常用/历史」浮层里直接点头像（会认错会话/点进别的群或个人）。
    与飞书差异：目标是**群**（多人/群图标、名字为「DLP测试」），不是个人条目。

    **本步不加变化型 verify**（见 LESSONS.md #7）：进会话是幂等的导航手段——QQ 常
    恢复到上次打开的会话，若一打开就已在「DLP测试」群，正确行为是「无需操作、直接
    finished」，此时 before→after 无变化，变化型 Judge 必判不过（真实踩坑）。真正的
    DLP 验收落在后面「发文件/截图到群」步，其 verify 锚定 '{_GROUP}' 群名，落错会话
    照样判不过，安全网仍在。
    """
    return [
        step("打开 QQ", hard(_open_qq)),
        step("聚焦全局搜索框（Ctrl+F）", hard(_focus_search)),
        step(f"搜索并进入「{_GROUP}」群会话",
             ai(f"这是 QQ Windows 客户端。目标是进入名为'{_GROUP}'的**群聊**会话。\n"
                f"**重要前提**：程序在本步之前已确定性地激活 QQ 并按过 Ctrl+F，"
                f"**全局搜索框此刻应已打开、光标已在搜索输入框里**。\n"
                f"**先判断当前画面**：如果右侧**已经就是'{_GROUP}'的群聊会话**"
                f"（顶部显示群名'{_GROUP}'、下方有聊天记录和输入框），说明已在目标会话，"
                f"**直接结束（finished）即可，无需再搜索**。否则按下面步骤操作：\n"
                f"- **不要**再去点 QQ 窗口任何位置来『激活/取消遮挡』——那会把已打开的搜索框点掉；\n"
                f"- **不要**再去点顶部的搜索放大镜图标或重新打开搜索框；\n"
                f"**严格按以下步骤做**：\n"
                f"1. **直接输入'{_GROUP}'**（中文，无需先点搜索框，光标已就位），等约 1 秒"
                f"让真实搜索结果加载出来。**严禁**直接点击浮层里「搜索历史/常用/最近」的头像或"
                f"条目——那是历史/常用列表，里面混着别的群和联系人，直接点极易认错会话。\n"
                f"2. 搜索结果出来后，在列表里找到**'{_GROUP}'这个群聊的会话条目**："
                f"群头像（多人/群组图标，不是单人头像）、名字就是'{_GROUP}'。"
                f"QQ 搜索结果可能分「联系人/群聊/聊天记录」等分组，请在**群聊**分组下找"
                f"名为'{_GROUP}'的那一条。若顶部不是该群，向下扫视结果列表找到它。\n"
                f"3. **点击一次**该群会话条目（点条目行上任意位置即可）。\n"
                f"4. 点完请先用一次 wait 等待（界面切换到会话有零点几秒延迟），再看新截图"
                f"确认——只要右侧已变成'{_GROUP}'的群聊对话区（顶部显示群名'{_GROUP}'、"
                f"有聊天记录和输入框）就 finished。\n"
                f"**严禁**：点完后因为界面还没刷新就判定'没进去'而回头再点搜索框；"
                f"已经点过一次群条目后优先 wait 观察，不要在「点条目↔点搜索框」间空转；"
                f"更不要在输入名字前先去点窗口/搜索图标。")),
    ]


def _ensure_sample_file(ctx=None) -> str:
    """确保敏感目录内存在固定样例文件（**源模板**），返回其绝对路径。

    这是用户配置的敏感文件来源（工程化换真实敏感文件时只改 _SENSITIVE_DIR /
    _SAMPLE_FILE）。它**只作模板、不直接外发**：每个 case 会从它 cp 出一个带唯一
    文件名的副本去发（见 _make_unique_copy），以便 Judge 能从文件名区分本次新发的
    气泡（见 LESSONS.md #8：同名文件反复外发时视觉模型数不出「新增」）。
    """
    os.makedirs(_SENSITIVE_DIR, exist_ok=True)
    if not os.path.isfile(_SAMPLE_FILE):
        with open(_SAMPLE_FILE, "w", encoding="utf-8") as fp:
            fp.write("dlp outbound test sample file\n")
    return _SAMPLE_FILE


# ctx.extras 里存放本次 case 外发副本绝对路径的 key（供发送话术 / 文件对话框 /
# cleanup 跨步共享；同一个 StepCtx 贯穿一个 case 的所有步骤）。
_OUTBOUND_KEY = "qq_outbound_file"


def _unique_outbound_name() -> str:
    """生成本次外发用的唯一文件名（全 ASCII，便于系统文件对话框直接输入路径）。

    形如 dlp_sample_130229_a3f.txt：本地时分秒 + 3 位随机十六进制。目的只是让 Judge
    在 before/after 截图里一眼认出「本次新发的文件」，并不追求全局绝对唯一——本地目录
    由 _purge_old_copies 保证同时只存一个副本，不存在目录内碰撞，故无需 PID/微秒。
    时分秒便于人看日志、与 DLP 日志按文件名对账；3 位随机兜底同秒极小概率重名。
    """
    ts = datetime.now().strftime("%H%M%S")
    rand = uuid.uuid4().hex[:3]
    stem, ext = os.path.splitext(os.path.basename(_SAMPLE_FILE))
    return f"{stem}_{ts}_{rand}{ext}"


def _make_unique_copy(ctx) -> None:
    """hard 步：从源模板 cp 出一个唯一文件名的副本，作为本次 case 真正外发的文件。

    确定性、无害：仅本地拷贝文件、把副本路径写入 ctx.extras[_OUTBOUND_KEY]。副本内容
    也写入同一唯一标记（文件名），万一某通道只暴露内容不暴露文件名也能区分。
    源模板保持不变；副本在 cleanup 删除，避免 .tmp 逐次积累。

    生成前先清掉目录里遗留的旧 dlp_sample_* 副本（保留源模板 dlp_sample.txt），
    使 dlp_test 目录里始终只剩「源模板 + 本次唯一副本」，让后续 AI「选那个带时间戳
    的文件」稳定无歧义，也让 Judge 的 before/after 只有一个新增文件可对比。
    """
    _purge_old_copies()
    src = _ensure_sample_file()
    dst = os.path.join(_SENSITIVE_DIR, _unique_outbound_name())
    marker = os.path.splitext(os.path.basename(dst))[0]
    with open(src, "r", encoding="utf-8") as fp:
        base = fp.read()
    with open(dst, "w", encoding="utf-8") as fp:
        fp.write(base)
        fp.write(f"\n[dlp-outbound-marker] {marker}\n")
    ctx.extras[_OUTBOUND_KEY] = dst
    # 统一约定 key：把本次外发的敏感文件名（basename）暴露给框架，runner 会搬到
    # rep.sensitive_file 并写进报告/多维表格。截图类 case 不写此 key，自然留空。
    ctx.extras["sensitive_file"] = os.path.basename(dst)
    print(f"  📄 本次外发副本：{os.path.basename(dst)}")


def _purge_old_copies() -> None:
    """删掉 dlp_test 目录里遗留的 dlp_sample_*.txt 旧副本（保留源模板 dlp_sample.txt）。

    上次 run 若异常中断、cleanup 没跑到，可能残留旧副本；这里在生成新副本前兜底清理，
    保证目录里外发候选唯一。只删匹配前缀的副本，绝不动其它文件。
    """
    if not os.path.isdir(_SENSITIVE_DIR):
        return
    stem, ext = os.path.splitext(os.path.basename(_SAMPLE_FILE))  # ("dlp_sample", ".txt")
    keep = os.path.basename(_SAMPLE_FILE)
    for fn in os.listdir(_SENSITIVE_DIR):
        if fn == keep:
            continue
        if fn.startswith(f"{stem}_") and fn.endswith(ext):
            try:
                os.remove(os.path.join(_SENSITIVE_DIR, fn))
            except OSError:
                pass


def _outbound_path(ctx) -> str:
    """取本次外发副本的绝对路径；未生成则兜底回落到源模板（不致命）。"""
    p = ctx.extras.get(_OUTBOUND_KEY) if ctx and ctx.extras else None
    return p or _SAMPLE_FILE


def _outbound_basename(ctx) -> str:
    return os.path.basename(_outbound_path(ctx))


def _fill_file_dialog(ctx) -> None:
    """hard 步：把本次外发副本的路径确定性填入系统『打开』对话框并确认。

    背景：让视觉 AI 在 Windows 系统文件对话框里输入长路径极不可靠（小字看不清、
    反复全选重输直到耗尽 max_steps，见 LESSONS.md #1）。故 AI 只负责把对话框
    「触发出来」（点文件入口），对话框一出现即由本 hard step 用 win32 直接
    WM_SETTEXT 写入路径并点『打开』，不经键盘/输入法、天然完整。
    命中失败（对话框没弹出/控件找不到）不抛异常，仅提示，后续 AI 步仍可兜底。
    """
    path = _outbound_path(ctx)
    ok = apps.fill_open_dialog(path)
    if ok:
        print(f"  📄 已向系统文件对话框填入路径并确认：{path}")
    else:
        print("  ⚠️ 未捕获到系统文件对话框（可能未弹出或控件不匹配）；"
              "后续 AI 步将尝试兜底操作")
    time.sleep(1.0)


def _copy_file_to_clipboard(ctx) -> None:
    """hard 步：把本次外发副本以「文件」形式确定性放入剪贴板（等价资源管理器 Ctrl+C）。

    方向 A 改造：复制文件本体这一环节极易被视觉 AI 搞乱（选错文件、焦点在错窗口导致
    Ctrl+C 无效、发完不认得又从头重来 → 曾滚成 30 步死循环，见 LESSONS.md）。故把
    「复制」交给 win32 剪贴板（CF_HDROP）确定性完成，AI 只需之后点输入框→Ctrl+V→发送。
    无害：仅写本机剪贴板。
    """
    path = _outbound_path(ctx)
    clipboard.set_files([path])
    print(f"  📋 已将文件放入剪贴板（可直接 Ctrl+V 粘贴发送）：{os.path.basename(path)}")
    time.sleep(0.5)


def _cleanup_copy(ctx) -> None:
    """cleanup 步：只删除本次 case 生成的外发副本，源模板保持不变。

    删本地副本不影响已外发到聊天里的那份（对方/群里已收到的是独立副本）。
    """
    p = ctx.extras.get(_OUTBOUND_KEY) if ctx and ctx.extras else None
    if p and os.path.isfile(p):
        try:
            os.remove(p)
            print(f"  🧹 已删除本次外发副本：{os.path.basename(p)}")
        except OSError as exc:
            print(f"  ⚠️ 删除外发副本失败（不致命）：{exc}")


def _open_sensitive_dir(ctx) -> None:
    """用文件资源管理器打开敏感文件目录（确定性步骤）。

    AI 不擅长逐级双击进入子目录，故直接 explorer 打开该目录，让 AI 只需专注
    『选文件 + 拖拽/复制』。先确保目录内有可操作的样例文件。
    """
    _ensure_sample_file()
    subprocess.Popen(["explorer", _SENSITIVE_DIR])
    time.sleep(2.0)


# 敏感目录的文件夹名，用于按窗口标题匹配 explorer 窗口（explorer 打开文件夹后
# 窗口标题即文件夹名）。
_DIR_NAME = os.path.basename(_SENSITIVE_DIR)


def _layout_side_by_side(ctx) -> None:
    """确定性地把 QQ 贴到左半屏、资源管理器贴到右半屏，互不遮挡。

    AI 靠视觉在任务栏切窗口时极易点错、把文件拖进 IDE 等错误窗口。这里在拖拽前
    用 win32 把两个窗口铺满工作区左右两半（也把其它窗口挡在身后），使后续 AI 只需
    『从右半屏拖到左半屏』，无需任何窗口切换。命中失败不致命，仅打印提示。
    """
    apps.activate_app(_app_name(ctx))
    time.sleep(0.5)
    # 左：QQ（拖拽目标）；右：资源管理器（按文件夹名匹配标题 + explorer.exe 进程名
    # 双条件，排除标题恰好含这些子串的浏览器标签/教程窗口）。
    ok_l, ok_r = apps.snap_side_by_side(
        _app_name(ctx),
        ([_DIR_NAME, "资源管理器", "文件资源管理器", "explorer", "file explorer"],
         ["explorer.exe"]),
    )
    if not (ok_l and ok_r):
        print(f"  ⚠️ 窗口分屏未完全命中（QQ={ok_l} 资源管理器={ok_r}）；"
              f"AI 仍可视觉操作，但可能需自行切换窗口")
    time.sleep(1.0)


def _close_explorer(ctx) -> None:
    """收尾：关闭本 case 打开的 dlp_test 资源管理器窗口（cleanup，必在 finally 执行）。

    只按**具体文件夹名**精确匹配关闭，且要求进程为 explorer.exe，QQ 等用户原有
    窗口一律不动，避免误关。
    """
    closed = apps.close_windows([_DIR_NAME], exe_names=["explorer.exe"])
    print(f"  🧹 已关闭 {closed} 个 dlp_test 资源管理器窗口")


# ══════════════════════════════════════════════════════════════════════
# ① 拖拽外发：从资源管理器拖文件到群对话框
# ══════════════════════════════════════════════════════════════════════
@case(
    id="desktop_app.im.qq.outbound_file.drag_drop",
    name="桌面应用 - 即时通信 - QQ - 外发文件 - 拖拽文件到对话框",
    channel="desktop_app.im",
    app=_APP,
    scenario="外发文件（默认任意文件）",
    action="拖拽文件到对话框",
    platforms=[Platform.WINDOWS],
    tags=["desktop_app", "im", "qq", "dlp", "outbound", "windows"],
    reflect=True,
)
def case_drag_drop() -> list[Step | None]:
    return [
        *_enter_conversation_steps(),
        step("生成本次唯一外发文件", hard(_make_unique_copy)),
        step("用文件资源管理器打开 dlp_test 目录", hard(_open_sensitive_dir)),
        step("把 QQ 与资源管理器排到左右半屏（避免遮挡）", hard(_layout_side_by_side)),
        step("从资源管理器拖拽一个文件到 QQ 群对话框发送",
             ai(f"屏幕已按左右分屏排好：**左半屏是 QQ**与'{_GROUP}'群的聊天窗口，"
                f"**右半屏是文件资源管理器**（已打开 dlp_test 文件夹，里面通常只有一个"
                f"文件，文件名形如 dlp_sample_<一串时间戳数字>.txt）。两个窗口不重叠、"
                f"都在前台，**不要去点任务栏切换窗口**。\n"
                f"直接在当前画面上按顺序操作："
                f"1) 在右半屏资源管理器中单击选中那个 dlp_sample_… 文件（不要双击打开它；"
                f"若目录里有多个，选文件名里时间戳数字最大的那个）；"
                f"2) 把这个被选中的文件从右半屏拖拽到左半屏 QQ 与'{_GROUP}'群的聊天输入框"
                f"区域内并释放（拖拽的落点必须在左半屏 QQ 窗口内）；"
                f"3) 若 QQ 弹出文件发送预览/确认框，点击其中的『发送』按钮。",
                verify=f"'{_GROUP}'群的聊天区里，相比操作前(before)新增了一条我方刚发出的"
                       f"文件消息气泡（文件卡片 dlp_sample_<时间戳>.txt，由我方发出）")),
        cleanup(_close_explorer),
        cleanup(_cleanup_copy),
    ]


# ══════════════════════════════════════════════════════════════════════
# ② 自带上传外发：加号/文件夹入口 → 文件（软件自带上传入口）
# ══════════════════════════════════════════════════════════════════════
@case(
    id="desktop_app.im.qq.outbound_file.upload",
    name="桌面应用 - 即时通信 - QQ - 外发文件 - 对话框文件上传",
    channel="desktop_app.im",
    app=_APP,
    scenario="外发文件（默认任意文件）",
    action="对话框文件上传",
    platforms=[Platform.WINDOWS],
    tags=["desktop_app", "im", "qq", "dlp", "outbound", "windows"],
    reflect=True,
)
def case_upload() -> list[Step | None]:
    """用 QQ 自带上传入口（工具栏文件夹/发送文件按钮）选择样例文件外发。

    分工（关键设计）：AI 只负责视觉导航——点工具栏的『发送文件/文件夹』入口把系统
    文件对话框触发出来、以及最后点『发送』；中间「在系统文件对话框里填完整路径并打开」
    交给确定性 hard step（_fill_file_dialog）用 win32 直接写入，不让视觉 AI 去输长路径
    （那会反复全选重输直到耗尽步数，见 LESSONS.md #1）。
    """
    return [
        *_enter_conversation_steps(),
        step("生成本次唯一外发文件", hard(_make_unique_copy)),
        step("点开文件上传入口，触发系统文件对话框",
             ai(f"当前在 QQ 与'{_GROUP}'群的聊天会话里。请打开 QQ 自带的文件上传入口："
                f"1) 点击聊天输入框上方工具栏中的『发送文件』按钮（通常是一个文件夹图标）；"
                f"2) 若弹出菜单，点击『发送文件/本地文件』项。"
                f"点完之后，系统会弹出 Windows『打开/选择文件』对话框。"
                f"**你的任务到此为止**：一旦看到这个系统文件对话框弹出（有『文件名』"
                f"输入框和『打开』按钮的那个窗口），立即结束（finished），"
                f"**不要**去输入任何路径、不要点文件列表——后续填路径由程序自动完成",
                verify="屏幕上弹出了 Windows 系统的『打开/选择文件』对话框"
                       "（含文件名输入框与『打开』按钮）")),
        step("确定性填入路径并确认打开", hard(_fill_file_dialog)),
        step("在 QQ 里确认发送该文件",
             ai(f"刚才已通过系统文件对话框选中并打开了本次的样例文件"
                f"（文件名形如 dlp_sample_<时间戳>.txt），"
                f"它应已进入 QQ 与'{_GROUP}'群的聊天输入区或弹出了文件发送预览框。"
                f"请完成发送：若出现文件发送预览/确认框，点击其中的『发送』按钮；若文件已在"
                f"输入框中但尚未发出，按回车或点发送按钮发送。"
                f"注意：不要再去点文件入口或重新选择文件——文件已经选好了，只需发送。",
                verify=f"'{_GROUP}'群的聊天区里，相比操作前(before)新增了一条我方刚发出的"
                       f"文件消息气泡（文件卡片 dlp_sample_<时间戳>.txt，由我方发出）")),
        cleanup(_cleanup_copy),
    ]


# ══════════════════════════════════════════════════════════════════════
# ③ 复制粘贴外发：复制文件本体（资源管理器 Ctrl+C → 会话输入框 Ctrl+V）
# ══════════════════════════════════════════════════════════════════════
@case(
    id="desktop_app.im.qq.outbound_file.copy_paste",
    name="桌面应用 - 即时通信 - QQ - 外发文件 - 复制粘贴文件外发",
    channel="desktop_app.im",
    app=_APP,
    scenario="外发文件（默认任意文件）",
    action="复制粘贴文件外发",
    platforms=[Platform.WINDOWS],
    tags=["desktop_app", "im", "qq", "dlp", "outbound", "windows"],
    reflect=True,
)
def case_copy_paste() -> list[Step | None]:
    """把**文件本体**放入剪贴板后，到 QQ 群会话输入框 Ctrl+V 粘贴发送。

    方向 A 设计：复制文件这一步由 hard step 确定性完成（win32 CF_HDROP 写剪贴板，
    见 _copy_file_to_clipboard），不再让视觉 AI 去资源管理器里选文件/按 Ctrl+C
    （那会选错文件、焦点错窗口导致复制失败、发完不认得又从头重来 → 30 步死循环）。
    因此也无需 explorer 打开目录、无需分屏——AI 只在 QQ 窗口内做「点输入框→Ctrl+V
    →确认文件出现→点发送」这一小段，且只做一轮。
    """
    return [
        *_enter_conversation_steps(),
        step("生成本次唯一外发文件", hard(_make_unique_copy)),
        step("把文件放入剪贴板（确定性 Ctrl+C 等价操作）", hard(_copy_file_to_clipboard)),
        step("在 QQ 群输入框粘贴并发送该文件",
             ai(f"当前在 QQ 与'{_GROUP}'群的聊天会话里，**本次要外发的文件已经由程序"
                f"确定性地复制到系统剪贴板**（等价于已在资源管理器里对该文件按过 Ctrl+C）。"
                f"你**不需要**再去复制文件、不需要打开资源管理器，只需把它粘贴到 QQ 并发送。\n"
                f"**整个任务只做一轮，严格按顺序**：\n"
                f"1) 单击 QQ**底部的文字输入框**（最下方那条横向输入条的正中央），"
                f"让输入框获得焦点（不要点聊天记录区）；\n"
                f"2) 按 **Ctrl+V** 粘贴——文件会以文件卡片/缩略图形式出现在 QQ 输入框里；\n"
                f"3) 看新截图确认输入框里已出现文件卡片；若 QQ 直接弹出文件发送预览/确认框，"
                f"点其中的『发送』按钮；若文件在输入框里未自动发出，按回车或点发送按钮发送；\n"
                f"4) **只要看到聊天区里出现了你刚发出的文件消息气泡，立即 finished**。\n"
                f"**重要**：这是一次性任务，**发出一次就结束**。发送后聊天区出现文件气泡是"
                f"正常的成功标志，那就是你刚发的——**不要因为『想再确认一下』而重新粘贴或再发"
                f"一次**，更不要回头去选文件/复制。只有当你**明确看到 Ctrl+V 后输入框仍为空**"
                f"（粘贴没生效）时，才重新点一次输入框再 Ctrl+V。",
                verify=f"'{_GROUP}'群的聊天区里，相比操作前(before)新增了一条我方刚发出的"
                       f"文件消息气泡（文件卡片 dlp_sample_<时间戳>.txt，由我方发出）")),
        cleanup(_cleanup_copy),
    ]


# ══════════════════════════════════════════════════════════════════════
# ④ 自带截图外发：聊天框工具栏截图按钮 → 框选 → 确认 → 自动进输入框 → 发送
# ══════════════════════════════════════════════════════════════════════
@case(
    id="desktop_app.im.qq.outbound_screenshot.builtin_capture",
    name="桌面应用 - 即时通信 - QQ - 外发截图 - 自带截图外发",
    channel="desktop_app.im",
    app=_APP,
    scenario="外发截图（自带截图工具）",
    action="自带截图外发",
    platforms=[Platform.WINDOWS],
    tags=["desktop_app", "im", "qq", "dlp", "outbound", "windows", "screenshot"],
    reflect=True,
)
def case_screenshot() -> list[Step | None]:
    """用 QQ 聊天框工具栏的截图按钮截图后外发到群。

    交互（用户确认）：点截图按钮 → 框选区域 → 确认 → 截图自动进入输入框 → 发送。
    """
    return [
        *_enter_conversation_steps(),
        step("用 QQ 自带截图功能截图并发送",
             ai(f"当前在 QQ 与'{_GROUP}'群的聊天会话里。请用 QQ**自带的截图功能**外发一张截图。\n"
                f"按顺序操作："
                f"1) 点击聊天输入框上方（或旁边）工具栏中的『截图』按钮（剪刀/相机样式图标）；"
                f"2) 进入截图框选模式后，在屏幕上按住鼠标左键拖出一个**较大**的矩形区域，"
                f"松开鼠标完成框选。**关键：框选区域要尽量大、并包含较多 QQ 聊天窗口以外的"
                f"屏幕画面**（例如桌面、右侧其它应用窗口、任务栏等），让截图内容丰富、色彩与"
                f"图案和 QQ 聊天背景有明显差异——这样发出后的图片缩略图辨识度高、容易被认出是"
                f"一条新消息（若只框选 QQ 聊天窗口内部，截图与聊天背景太相似，很难分辨图片是否"
                f"已发出）；"
                f"3) 在框选区域附近的小工具条上点击『完成/对勾/确认』"
                f"按钮，确认截图——此时截图会自动出现在'{_GROUP}'群的聊天输入框中；"
                f"4) 点击『发送』按钮或按回车，把这张截图发送出去。",
                verify=f"'{_GROUP}'群的聊天区里，相比操作前(before)新增了一条我方刚发出的"
                       f"图片消息气泡（图片缩略图，由我方发出）")),
    ]
