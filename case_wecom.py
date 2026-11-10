"""桌面应用 - 即时通信 - 企业微信 - DLP 外发 case 集合（Mac 端）。

平台：macOS（本文件位于 cases/desktop_app/im/mac/，仅含 Mac 端 case）。
参照 Windows 企业微信的正式覆盖，包含拖拽、上传、复制粘贴、自带截图四类动作；
交互指令按 Mac 的 Finder、Command 快捷键和系统文件对话框独立编写。

已核实信息：
- App 注册名：企业微信。
- 外发目标：群聊「DLP测试」（可由 config/contacts.yaml 的 wecom.mac 覆盖）。
- 聊天工具栏存在文件夹上传入口和剪刀截图入口。
"""
from __future__ import annotations

import os
import subprocess
import time
import uuid
from datetime import datetime

from dlp_auto.actions import apps, clipboard, keyboard
from dlp_auto.case.contacts import outbound_target
from dlp_auto.case.spec import (
    Step,
    ai,
    case,
    cleanup,
    hard,
    register_app_teardown,
    step,
)
from dlp_auto.core.platform import Platform

_APP = "企业微信"
_APP_NAME = "企业微信"
_APP_KEY = "wecom"
_TARGET = outbound_target("desktop_app.im", _APP_KEY, default="DLP测试")
_TARGET_KIND = "群聊"
_TAGS = ["desktop_app", "im", "wecom", "dlp", "outbound", "mac"]

_REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..")
)
_SENSITIVE_DIR = os.path.join(_REPO_ROOT, ".tmp", "dlp_test_mac")
_TEMPLATE_FILE = os.path.join(_REPO_ROOT, ".tmp", "dlp_sample_template.txt")
_OUTBOUND_KEY = "im_outbound_file"
_SAMPLE_PREFIX = "dlp_sample_"
_SAMPLE_SUFFIX = ".txt"
_WECOM_BUNDLE_ID = "com.tencent.WeWorkMac"
_FINDER_BUNDLE_ID = "com.apple.finder"
_FINDER_WINDOW_TITLE = os.path.basename(_SENSITIVE_DIR)
_WINDOW_RECT_KEY = "wecom_window_rect_before_drag"


def _app_name(ctx) -> str:
    if ctx is None or ctx.settings is None:
        return _APP_NAME
    return ctx.settings.get(
        "platform", "overrides", "mac", "app_names", _APP_KEY,
        default=_APP_NAME,
    )


def _open_wecom(ctx) -> None:
    apps.open_app(_app_name(ctx), wait_sec=4.0)


def _enter_conversation_steps() -> list[Step]:
    return [
        step(f"打开{_APP}", hard(_open_wecom)),
        step(
            f"搜索并进入「{_TARGET}」{_TARGET_KIND}",
            ai(
                f"这是 {_APP} Mac 客户端。目标是进入名为「{_TARGET}」的{_TARGET_KIND}。"
                f"先检查当前会话：如果中间聊天区顶部已经显示「{_TARGET}」，下方有聊天记录"
                f"和输入框，直接 finished，不要重复搜索。否则点击左上方带放大镜的「搜索」"
                f"输入框，输入「{_TARGET}」，等待结果出现；在结果中点击名称完全匹配的"
                f"{_TARGET_KIND}条目。进入后确认聊天区顶部显示「{_TARGET}」再 finished。"
                f"不要点击名称不完全匹配的联系人或其它群聊，不要发送任何文本消息。"
            ),
        ),
    ]


def _ensure_template_file() -> str:
    os.makedirs(os.path.dirname(_TEMPLATE_FILE), exist_ok=True)
    if not os.path.isfile(_TEMPLATE_FILE):
        with open(_TEMPLATE_FILE, "w", encoding="utf-8") as stream:
            stream.write("dlp outbound test sample file\n")
    return _TEMPLATE_FILE


def _purge_old_copies() -> None:
    if not os.path.isdir(_SENSITIVE_DIR):
        return
    for name in os.listdir(_SENSITIVE_DIR):
        if name.startswith(_SAMPLE_PREFIX) and name.endswith(_SAMPLE_SUFFIX):
            try:
                os.remove(os.path.join(_SENSITIVE_DIR, name))
            except OSError:
                pass


def _make_unique_copy(ctx) -> None:
    _purge_old_copies()
    source = _ensure_template_file()
    os.makedirs(_SENSITIVE_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%H%M%S")
    name = f"{_SAMPLE_PREFIX}{timestamp}_{uuid.uuid4().hex[:3]}{_SAMPLE_SUFFIX}"
    target = os.path.join(_SENSITIVE_DIR, name)
    with open(source, "r", encoding="utf-8") as stream:
        content = stream.read()
    with open(target, "w", encoding="utf-8") as stream:
        stream.write(content)
        stream.write(f"\n[dlp-outbound-marker] {os.path.splitext(name)[0]}\n")
    ctx.extras[_OUTBOUND_KEY] = target
    ctx.extras["sensitive_file"] = name
    print(f"  📄 本次外发副本：{name}")


def _outbound_path(ctx) -> str:
    path = ctx.extras.get(_OUTBOUND_KEY) if ctx and ctx.extras else None
    if not path:
        raise RuntimeError("本次外发文件尚未生成")
    return str(path)


def _cleanup_copy(ctx) -> None:
    path = ctx.extras.get(_OUTBOUND_KEY) if ctx and ctx.extras else None
    if path and os.path.isfile(path):
        try:
            os.remove(path)
            print(f"  🧹 已删除本次外发副本：{os.path.basename(path)}")
        except OSError as exc:
            print(f"  ⚠️ 删除外发副本失败（不致命）：{exc}")


def _open_sensitive_dir(ctx) -> None:
    os.makedirs(_SENSITIVE_DIR, exist_ok=True)
    subprocess.run(["open", _SENSITIVE_DIR], check=False)
    time.sleep(2.0)


def _running_app(bundle_id: str):
    from AppKit import NSWorkspace

    for app in NSWorkspace.sharedWorkspace().runningApplications():
        if str(app.bundleIdentifier() or "") == bundle_id:
            return app
    return None


def _ax_window(bundle_id: str, *, title: str | None = None):
    import ApplicationServices as ax

    app = _running_app(bundle_id)
    if app is None:
        return None
    element = ax.AXUIElementCreateApplication(app.processIdentifier())
    error, windows = ax.AXUIElementCopyAttributeValue(
        element, ax.kAXWindowsAttribute, None
    )
    if error != 0:
        return None
    for window in windows or []:
        if title is None:
            return window
        _, value = ax.AXUIElementCopyAttributeValue(
            window, ax.kAXTitleAttribute, None
        )
        if str(value or "") == title:
            return window
    return None


def _window_rect(window) -> tuple[float, float, float, float]:
    import ApplicationServices as ax

    error_pos, pos_value = ax.AXUIElementCopyAttributeValue(
        window, ax.kAXPositionAttribute, None
    )
    error_size, size_value = ax.AXUIElementCopyAttributeValue(
        window, ax.kAXSizeAttribute, None
    )
    if error_pos != 0 or error_size != 0:
        raise RuntimeError("读取 macOS 窗口位置失败")
    ok_pos, position = ax.AXValueGetValue(
        pos_value, ax.kAXValueCGPointType, None
    )
    ok_size, size = ax.AXValueGetValue(
        size_value, ax.kAXValueCGSizeType, None
    )
    if not ok_pos or not ok_size:
        raise RuntimeError("解析 macOS 窗口位置失败")
    return position.x, position.y, size.width, size.height


def _set_window_rect(
    window,
    rect: tuple[float, float, float, float],
) -> None:
    import ApplicationServices as ax

    x, y, width, height = rect
    position = ax.AXValueCreate(ax.kAXValueCGPointType, (x, y))
    size = ax.AXValueCreate(ax.kAXValueCGSizeType, (width, height))
    error_pos = ax.AXUIElementSetAttributeValue(
        window, ax.kAXPositionAttribute, position
    )
    error_size = ax.AXUIElementSetAttributeValue(
        window, ax.kAXSizeAttribute, size
    )
    if error_pos != 0 or error_size != 0:
        raise RuntimeError(
            f"移动 macOS 窗口失败：position={error_pos}, size={error_size}"
        )


def _activate_bundle(bundle_id: str) -> None:
    from AppKit import (
        NSApplicationActivateAllWindows,
        NSApplicationActivateIgnoringOtherApps,
    )

    app = _running_app(bundle_id)
    if app is not None:
        app.activateWithOptions_(
            NSApplicationActivateAllWindows
            | NSApplicationActivateIgnoringOtherApps
        )


def _layout_drag_windows(ctx) -> None:
    """把企业微信放左侧、访达放右侧；失败时中止，禁止带风险地继续拖拽。"""
    from AppKit import NSScreen

    wecom_window = _ax_window(_WECOM_BUNDLE_ID)
    finder_window = _ax_window(
        _FINDER_BUNDLE_ID, title=_FINDER_WINDOW_TITLE
    )
    if wecom_window is None or finder_window is None:
        raise RuntimeError(
            "未能精确找到企业微信或 dlp_test_mac 访达窗口，已停止拖拽"
        )

    ctx.extras[_WINDOW_RECT_KEY] = _window_rect(wecom_window)

    screen = NSScreen.mainScreen()
    frame = screen.frame()
    visible = screen.visibleFrame()
    left = float(visible.origin.x)
    top = float(
        frame.size.height - visible.origin.y - visible.size.height
    )
    width = float(visible.size.width)
    height = float(visible.size.height)
    left_width = round(width * 0.60)

    _set_window_rect(
        wecom_window, (left, top, left_width, height)
    )
    _set_window_rect(
        finder_window,
        (left + left_width, top, width - left_width, height),
    )

    # 两个窗口都有系统级最小宽度。当前机器实测企业微信 960pt、访达 605pt，
    # 总和略宽于工作区；macOS 会静默放大，若仍沿用 60/40 的 x 坐标就会重叠。
    # 以实际宽度二次排布：让访达完整保留在右侧，超出的少量宽度只裁掉企业微信
    # 最左侧无关导航栏。聊天区与访达保持严格不重叠。
    _, _, wecom_width, wecom_height = _window_rect(wecom_window)
    _, _, finder_width, finder_height = _window_rect(finder_window)
    overflow = max(0.0, wecom_width + finder_width - width)
    wecom_left = left - overflow
    finder_left = wecom_left + wecom_width
    _set_window_rect(
        wecom_window, (wecom_left, top, wecom_width, wecom_height)
    )
    _set_window_rect(
        finder_window, (finder_left, top, finder_width, finder_height)
    )

    wx, _, ww, _ = _window_rect(wecom_window)
    fx, _, _, _ = _window_rect(finder_window)
    if fx < wx + ww - 1.0:
        raise RuntimeError("企业微信与访达仍有重叠，已停止拖拽")

    _activate_bundle(_FINDER_BUNDLE_ID)
    time.sleep(1.0)
    print("  🪟 已将企业微信放左侧、访达放右侧，两个窗口互不遮挡")


def _restore_wecom_window(ctx) -> None:
    rect = ctx.extras.get(_WINDOW_RECT_KEY) if ctx and ctx.extras else None
    if not rect:
        return
    window = _ax_window(_WECOM_BUNDLE_ID)
    if window is None:
        return
    _set_window_rect(window, rect)
    print("  🪟 已恢复企业微信运行前窗口大小")


def _close_window(bundle_id: str, *, title: str | None = None) -> bool:
    import ApplicationServices as ax

    window = _ax_window(bundle_id, title=title)
    if window is None:
        return False
    error, close_button = ax.AXUIElementCopyAttributeValue(
        window, ax.kAXCloseButtonAttribute, None
    )
    if error != 0 or close_button is None:
        return False
    return ax.AXUIElementPerformAction(
        close_button, ax.kAXPressAction
    ) == 0


def _close_sensitive_finder(ctx) -> None:
    closed = _close_window(
        _FINDER_BUNDLE_ID, title=_FINDER_WINDOW_TITLE
    )
    print(
        "  🧹 已关闭 dlp_test_mac 访达窗口"
        if closed
        else "  ⚠️ 未找到 dlp_test_mac 访达窗口，跳过关闭"
    )


def _close_wecom_after_batch() -> None:
    closed = _close_window(_WECOM_BUNDLE_ID)
    print(
        "  🧹 [企业微信] 全部 case 跑完，已关闭主窗口（保留登录态）"
        if closed
        else "  ⚠️ [企业微信] 未找到主窗口，跳过关闭"
    )


register_app_teardown(_APP, _close_wecom_after_batch)


def _copy_file_to_clipboard(ctx) -> None:
    """把文件 URL 写入 macOS Pasteboard，等价于 Finder 选中文件后 Command+C。"""
    from AppKit import NSPasteboard
    from Foundation import NSURL

    path = _outbound_path(ctx)
    pasteboard = NSPasteboard.generalPasteboard()
    pasteboard.clearContents()
    file_url = NSURL.fileURLWithPath_(path)
    if not pasteboard.writeObjects_([file_url]):
        raise RuntimeError("写入 macOS 文件剪贴板失败")
    print(f"  📋 已将文件放入剪贴板：{os.path.basename(path)}")
    time.sleep(0.5)


def _select_file_in_open_panel(ctx) -> None:
    """在 Mac 系统文件对话框中用 Command+Shift+G 精确选择本次文件。"""
    path = _outbound_path(ctx)
    keyboard.hotkey("command", "shift", "g")
    time.sleep(0.5)
    clipboard.set_text(path)
    keyboard.paste()
    time.sleep(0.3)
    keyboard.press_enter()
    time.sleep(0.8)
    keyboard.press_enter()
    time.sleep(1.0)
    print(f"  📄 已向系统文件对话框填入路径并确认：{path}")


def _send_via_enter(ctx) -> None:
    keyboard.press_enter()
    time.sleep(1.0)
    print(f"  📨 已确定性回车发送到「{_TARGET}」")


def _select_screenshot_region(ctx) -> None:
    """在截图模式中框选四周留白的区域，确保完成工具条保持可见。"""
    from AppKit import NSScreen
    from dlp_auto.core.executor import Executor

    frame = NSScreen.mainScreen().frame()
    width = int(frame.size.width)
    height = int(frame.size.height)
    start_x = int(width * 0.18)
    start_y = int(height * 0.16)
    end_x = int(width * 0.80)
    end_y = int(height * 0.70)

    Executor._drag_mac(start_x, start_y, end_x, end_y)
    time.sleep(1.0)
    print(
        "  ✂️ 已按住鼠标框选截图区域并松开"
        f"：({start_x}, {start_y}) -> ({end_x}, {end_y})"
    )


def _sent_file_verify() -> str:
    return (
        f"「{_TARGET}」聊天区存在一条由我方发出的文件消息气泡，文件名形如 "
        f"dlp_sample_<时间戳>_<随机>.txt；这是本次唯一文件名，看到该气泡即通过。"
    )


def _sent_file_presence_verify() -> str:
    return (
        f"「{_TARGET}」聊天区最底部当前可见一条由我方最新发出的文件消息气泡，"
        f"文件名形如 dlp_sample_<时间戳>_<随机>.txt，且输入框里已没有待发文件卡片。"
        f"不要用上方历史 dlp_sample_... 气泡通过验收，只认最底部最新气泡。"
    )


def _drag_drop_steps() -> list[Step]:
    return [
        *_enter_conversation_steps(),
        step("生成本次唯一外发文件", hard(_make_unique_copy)),
        step("用访达打开本次外发目录", hard(_open_sensitive_dir)),
        step(
            f"把{_APP}与访达排到左右两侧",
            hard(_layout_drag_windows),
        ),
        step(
            f"从访达拖拽文件到{_APP}输入框（暂不发送）",
            ai(
                f"屏幕已确定性分屏：左侧是{_APP}，右侧是访达 dlp_test_mac 文件夹，"
                f"两个窗口互不重叠。先确认左侧{_APP}聊天区顶部明确显示「{_TARGET}」。"
                f"如果顶部不是「{_TARGET}」，严禁拖拽，直接结束。\n"
                f"只执行一次拖拽，暂不发送：在右侧访达单击选中唯一的 "
                f"dlp_sample_<时间戳>_<随机>.txt 文件，不要双击；把它拖到左侧"
                f"{_APP}窗口中聊天区右下方的白色文字输入框内并释放。落点必须在"
                f"「{_TARGET}」标题正下方聊天区的输入框，绝不能落到左侧会话列表。"
                f"输入框出现本次文件卡片后立即 finished。不要按 Return、不要点击发送、"
                f"不要再次拖拽。",
                verify=(
                    f"左侧{_APP}聊天区顶部仍显示「{_TARGET}」，且该聊天区右下方输入框"
                    f"内出现本次 dlp_sample_...txt 文件卡片；文件尚未发出。"
                ),
            ),
        ),
        step("确定性回车发送文件卡片", hard(_send_via_enter)),
        step(
            "确认文件已发出（只读，不再操作）",
            ai(
                f"程序刚刚已在「{_TARGET}」输入框确定性按 Return 发送文件。只观察"
                f"左侧{_APP}聊天区最底部，看到我方最新 dlp_sample_...txt 文件气泡，"
                f"且输入框待发卡片已清空后立即 finished。忽略上方历史文件气泡。"
                f"不要点击会话列表、输入框或发送按钮，不要再次拖拽。",
                verify=_sent_file_presence_verify(),
                verify_mode="presence",
            ),
        ),
        cleanup(_close_sensitive_finder),
        cleanup(_restore_wecom_window),
        cleanup(_cleanup_copy),
    ]


def _upload_steps() -> list[Step]:
    return [
        *_enter_conversation_steps(),
        step("生成本次唯一外发文件", hard(_make_unique_copy)),
        step(
            "点击文件上传入口，打开系统文件对话框",
            ai(
                f"当前在{_APP}「{_TARGET}」群聊。点击聊天输入框上方工具栏的文件夹"
                f"图标；如果出现菜单，选择发送文件/本地文件，直到 Mac 系统文件选择"
                f"对话框出现。看到文件对话框后立即 finished，不要自行选择文件或发送。",
                verify="Mac 系统文件选择对话框已显示。",
            ),
        ),
        step("确定性填入路径并确认选择", hard(_select_file_in_open_panel)),
        step(
            "确认并发送已选择的文件",
            ai(
                f"程序已经在系统文件对话框中选择了本次唯一文件。回到{_APP}后，"
                f"若输入框或预览框里出现文件卡片，点击一次「发送」或按一次 Return；"
                f"若文件已经自动进入「{_TARGET}」聊天区则不要再操作。等待界面刷新，"
                f"看到本次 dlp_sample_...txt 文件气泡后立即 finished。只发一次，"
                f"不要重新打开文件入口或重复选择。",
                verify=_sent_file_verify(),
            ),
        ),
        cleanup(_cleanup_copy),
    ]


def _copy_paste_steps() -> list[Step]:
    return [
        *_enter_conversation_steps(),
        step("生成本次唯一外发文件", hard(_make_unique_copy)),
        step("把文件放入 macOS 剪贴板", hard(_copy_file_to_clipboard)),
        step(
            f"在{_APP}输入框粘贴文件卡片",
            ai(
                f"本次文件已由程序以文件本体写入 macOS 剪贴板。当前在「{_TARGET}」"
                f"群聊，只做粘贴、不发送：单击底部文字输入框中央，按一次 Command+V。"
                f"输入框出现带 dlp_sample_...txt 文件名的文件卡片后立即 finished。"
                f"不要按 Return、不要点击发送；看到卡片后不要再次粘贴。",
                verify="聊天输入区出现了本次 dlp_sample_...txt 文件卡片，但尚未发送。",
            ),
        ),
        step("确定性回车发送文件卡片", hard(_send_via_enter)),
        step(
            "确认文件已发出（只读，不再操作）",
            ai(
                f"程序刚刚已确定性按 Return 发送文件。只观察「{_TARGET}」聊天区，"
                f"看到最底部我方最新 dlp_sample_...txt 文件气泡，且输入框待发卡片"
                f"已清空后立即 finished。忽略上方历史文件气泡，不要点击输入框、"
                f"不要再次粘贴或发送。",
                verify=_sent_file_presence_verify(),
                verify_mode="presence",
            ),
        ),
        cleanup(_cleanup_copy),
    ]


def _screenshot_steps() -> list[Step]:
    return [
        *_enter_conversation_steps(),
        step(
            f"点击{_APP}自带截图入口",
            ai(
                f"当前在{_APP}「{_TARGET}」群聊。只点击一次聊天输入框工具栏里的"
                f"剪刀截图图标。看到整个屏幕进入截图模式（画面变暗，出现十字光标、"
                f"放大镜或选区提示）后立即 finished。不要拖动鼠标、不要框选、不要按"
                f"Return，也不要再次点击剪刀；框选由程序下一步完成。",
                verify=(
                    f"{_APP}截图模式已启动：屏幕出现变暗遮罩以及十字光标、放大镜"
                    f"或截图选区提示。"
                ),
            ),
        ),
        step("确定性按住鼠标框选截图区域", hard(_select_screenshot_region)),
        step(
            "点击截图工具条完成按钮（暂不发送）",
            ai(
                f"程序已经按住鼠标并框选了一块四周留白的大区域，截图工具条应显示在"
                f"选区附近。只点击一次工具条上的绿色对勾、完成或确认按钮。截图进入"
                f"{_APP}「{_TARGET}」聊天输入框后立即 finished。不要按 Return、不要"
                f"点击发送、不要再次框选或点击剪刀。",
                verify=(
                    f"截图模式已退出，{_APP}「{_TARGET}」聊天输入框中出现一张待发送"
                    f"的截图预览或图片卡片，但尚未发送。"
                ),
            ),
        ),
        step("确定性回车发送截图", hard(_send_via_enter)),
        step(
            "确认截图已发出（只读，不再操作）",
            ai(
                f"程序刚刚已在「{_TARGET}」输入框确定性按 Return 发送截图。只观察"
                f"聊天区最底部：在上方 dlp_sample_...txt 文件气泡的下方，看到我方新发"
                f"的一张较大矩形截图缩略图后立即 finished。左侧「{_TARGET}」会话摘要"
                f"通常同时显示「[图片]」和「刚刚」。不要点击剪刀、输入框、发送按钮，"
                f"不要再次截图。",
                verify=(
                    f"「{_TARGET}」聊天区最底部、已有 dlp_sample_...txt 文件气泡下方，"
                    f"当前可见一张由我方新发出的较大矩形截图缩略图；左侧「{_TARGET}」"
                    f"会话摘要可显示「[图片]」和「刚刚」。上方仍存在旧文件气泡不影响"
                    f"通过，只判断底部大图是否存在。"
                ),
                verify_mode="presence",
            ),
        ),
    ]


@case(
    id="desktop_app.im.wecom.outbound_file.drag_drop",
    name="桌面应用 - 即时通信 - 企业微信 - 外发文件 - 拖拽文件到对话框",
    channel="desktop_app.im",
    app=_APP,
    scenario="外发文件（默认任意文件）",
    action="拖拽文件到对话框",
    platforms=[Platform.MAC],
    tags=_TAGS,
    reflect=True,
)
def case_drag_drop() -> list[Step | None]:
    return _drag_drop_steps()


@case(
    id="desktop_app.im.wecom.outbound_file.upload",
    name="桌面应用 - 即时通信 - 企业微信 - 外发文件 - 对话框文件上传",
    channel="desktop_app.im",
    app=_APP,
    scenario="外发文件（默认任意文件）",
    action="对话框文件上传",
    platforms=[Platform.MAC],
    tags=_TAGS,
    reflect=True,
)
def case_upload() -> list[Step | None]:
    return _upload_steps()


@case(
    id="desktop_app.im.wecom.outbound_file.copy_paste",
    name="桌面应用 - 即时通信 - 企业微信 - 外发文件 - 复制粘贴文件外发",
    channel="desktop_app.im",
    app=_APP,
    scenario="外发文件（默认任意文件）",
    action="复制粘贴文件外发",
    platforms=[Platform.MAC],
    tags=_TAGS,
    reflect=True,
)
def case_copy_paste() -> list[Step | None]:
    return _copy_paste_steps()


@case(
    id="desktop_app.im.wecom.outbound_screenshot.builtin_capture",
    name="桌面应用 - 即时通信 - 企业微信 - 外发截图 - 自带截图外发",
    channel="desktop_app.im",
    app=_APP,
    scenario="外发截图（自带截图工具）",
    action="自带截图外发",
    platforms=[Platform.MAC],
    tags=[*_TAGS, "screenshot"],
    reflect=True,
)
def case_screenshot() -> list[Step | None]:
    return _screenshot_steps()
