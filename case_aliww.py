"""桌面应用 - 即时通信 - 阿里旺旺 - DLP 外发 case 集合（Windows 端）。

阿里旺旺与普通 IM 的关键差异（真机实测/用户确认）：
- 主进程 AliIM.exe，主窗标题「淘宝旺旺」，外发目标群「DLP测试」。
- 文件外发只支持图片。前三类从 assets/samples 图片池生成唯一名副本。
- 图片气泡不展示文件名，共享脚手架的“让 AI 发送并识别文件名气泡”话术不适用；真机已复现
  AI 看不出图片是否发出，重新打开文件对话框并选中桌面残留错图，最终重复发送两次。

因此四类 case 在本文件使用阿里旺旺专属编排和提示词，不调用共享四类工厂：
1. 先把本次唯一文件名（截图类使用唯一的文件名样式标识）粘贴进输入框；
2. 再把图片加入输入框，AI 只做到“输入框出现图片预览”，绝不负责发送；
3. 程序只按一次回车确定性发送；
4. 末步只读验收聊天区是否出现本次唯一文字 + 图片气泡，不允许重选、重贴或重发。

共享模块仍只复用生成唯一图片、填系统对话框、写文件剪贴板、进会话和 cleanup 等确定性原子能力，
阿里旺旺专有话术不会影响其它 IM。
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime

from dlp_auto.actions import apps, clipboard, keyboard
from dlp_auto.case.contacts import outbound_target
from dlp_auto.case.im_windows_common import (
    ImApp, _DIR_NAME, _app_name, _cleanup_copy, _close_explorer,
    _copy_file_to_clipboard, _copy_step, _enter_conversation_steps,
    _fill_file_dialog, _maybe_maximize_steps, _maybe_restore_cleanups,
    _open_sensitive_dir, _outbound_path, make_app_teardown,
)
from dlp_auto.case.spec import (
    Step, ai, case, cleanup, hard, register_app_teardown, step,
)
from dlp_auto.core.platform import Platform

# 入库的图片池（随仓库走）：阿里旺旺只发图片，每次外发从池里随机取一张复制唯一名 .png 副本。
# 从本文件位置推导绝对路径（cases/desktop_app/im/windows/ 上溯 4 层到仓库根），
# 避免硬编码机器相关的绝对路径，保证 Mac/Windows/换机可移植。
_SAMPLES_DIR = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "..", "..", "assets", "samples",
))
_SAMPLE_POOL = (
    os.path.join(_SAMPLES_DIR, "dlp_image_qq.png"),
    os.path.join(_SAMPLES_DIR, "dlp_image_trae.png"),
)

_APP = ImApp(
    report_name="阿里旺旺",
    app_key="aliww",
    contacts_app="aliww",
    target=outbound_target("desktop_app.im", "aliww", default="DLP测试"),
    target_kind="群聊",
    id_slug="aliww",
    sample_pool=_SAMPLE_POOL,          # 只发图片：走图片池随机取一张二进制复制分支
    open_wake_tray=True,               # 阿里旺旺常缩系统托盘：打开时自动点托盘图标唤主窗
)
_TAGS = ["desktop_app", "im", "aliww", "dlp", "outbound", "windows"]
_CAPTION_KEY = "aliww_outbound_caption"
_FILE_CAPTION_PATTERN = "dlp_sample_<时间戳>_<随机字符>.png"
_SCREENSHOT_CAPTION_PATTERN = "dlp_screenshot_<时间戳>_<随机字符>.png"
_DRAG_WINDOW_RECT_KEY = "aliww_drag_window_rect"
_EXPLORER_MATCH = (
    [_DIR_NAME, "资源管理器", "文件资源管理器", "explorer", "file explorer"],
    ["explorer.exe"],
)

# 整款阿里旺旺全部 case 跑完后关闭其窗口（不退登录）——app 级 teardown，见 runner。
register_app_teardown(_APP.report_name, make_app_teardown(_APP))


def _put_caption_on_clipboard(ctx, caption: str) -> None:
    """登记并复制 caption；不写 sensitive_file，避免截图类被误当成文件类验收。"""
    ctx.extras[_CAPTION_KEY] = caption
    clipboard.set_text(caption)
    print(f"  📋 已将本次图片文件名文字放入剪贴板：{caption}")
    time.sleep(0.4)


def _prepare_file_caption(ctx) -> None:
    """前三类使用实际生成图片副本的文件名作为 caption。"""
    _put_caption_on_clipboard(ctx, os.path.basename(_outbound_path(ctx)))


def _prepare_screenshot_caption(ctx) -> None:
    """截图没有预先生成的源文件，用唯一文件名样式标识制造可读锚点。

    此处只登记 _CAPTION_KEY，不设置 sensitive_file；DLP 日志仍按截图类的图片扩展名匹配。
    """
    stamp = datetime.now().strftime("%H%M%S")
    caption = f"dlp_screenshot_{stamp}_{uuid.uuid4().hex[:3]}.png"
    _put_caption_on_clipboard(ctx, caption)


def _paste_caption_step(pattern: str) -> Step:
    """AI 做“点输入框 + 粘贴文字”，文字出现是明确可见的收敛信号。"""
    return step(
        "先把本次图片文件名粘贴到阿里旺旺输入框",
        ai(
            f"当前在阿里旺旺与'{_APP.target}'的群聊中。程序已把本次唯一的图片文件名文字"
            f"（形如 {pattern}）放进系统剪贴板。\n"
            f"你只做这两个动作：\n"
            f"1. 单击一次底部**文字输入框**的空白处；\n"
            f"2. 按一次 Ctrl+V，把文件名文字粘贴进去。\n"
            f"看到输入框内出现 dlp_ 开头、.png 结尾的文件名文字后，立即 finished。"
            f"不要按回车、不要点发送、不要上传/拖拽/截图；也不要重复粘贴。"
            f"若输入框原本有其它未发送内容，或一次 Ctrl+V 后仍看不到该文字，直接 call_user，"
            f"不要自行清空或重试。",
            action_limits={"click": 1, "hotkey": 1},
        ),
    )


def _stage_upload_steps() -> list[Step]:
    """通过阿里旺旺上传入口把唯一图片加入输入框，不在 AI 步里发送。"""
    return [
        step(
            "点开阿里旺旺图片上传入口",
            ai(
                f"输入框里已经有本次 dlp_*.png 文件名文字。现在只打开阿里旺旺自带的"
                f"图片/文件上传入口：点击输入框上方工具栏中的发送图片或发送文件按钮；若出现菜单，"
                f"只点一次“发送图片/本地图片/发送文件”对应项。看到 Windows“打开/选择文件”"
                f"对话框后立即 finished。不要在对话框里选任何文件，也不要按回车或点发送。",
                verify="屏幕上新增了 Windows『打开/选择文件』对话框，含文件名输入框和『打开』按钮",
                action_limits={"click": 2},
            ),
        ),
        step("确定性填入本次图片路径并确认打开", hard(_fill_file_dialog)),
        step(
            "确认本次图片已进入输入框（只读，不发送）",
            ai(
                f"程序刚才只向系统文件对话框填入了本次生成的唯一图片 dlp_sample_*.png。"
                f"现在只观察阿里旺旺底部输入区：应同时保留 dlp_sample_*.png 文件名文字，并出现"
                f"一张待发送图片的缩略图/预览。两者都在输入区就立即 finished。"
                f"不要点击任何位置，不要按键，不要重新打开文件对话框，更不要发送。"
                f"若图片预览没有出现，直接 call_user，禁止改选桌面或其它目录里的图片。"
            ),
        ),
    ]


def _stage_clipboard_image_step() -> Step:
    """剪贴板已换成唯一图片文件；AI 只粘贴一次并看到预览，不发送。"""
    return step(
        "把本次图片粘贴进输入框（看到预览即停）",
        ai(
            f"输入框里已有本次 dlp_sample_*.png 文件名文字，程序又把对应的唯一图片文件放进了"
            f"系统剪贴板，输入焦点仍在该输入框。现在只按一次 Ctrl+V。看到输入区新增一张待发送"
            f"图片的缩略图/预览后立即 finished。不要点发送、不要按回车、不要再次 Ctrl+V。"
            f"若一次 Ctrl+V 后没有出现预览，直接 call_user，不要重贴。",
            action_limits={"hotkey": 1},
        ),
    )


def _layout_for_drag(ctx) -> None:
    """记录阿里旺旺原窗口矩形，再与资源管理器排成左右半屏。"""
    name = _app_name(ctx, _APP)
    apps.activate_app(name)
    time.sleep(0.5)
    hwnd = apps._resolve_hwnd(name)
    if hwnd:
        import win32gui  # type: ignore

        ctx.extras[_DRAG_WINDOW_RECT_KEY] = tuple(win32gui.GetWindowRect(hwnd))
    ok_l, ok_r = apps.snap_side_by_side(name, _EXPLORER_MATCH)
    if not (ok_l and ok_r):
        print(f"  ⚠️ 窗口分屏未完全命中（阿里旺旺={ok_l} 资源管理器={ok_r}）")
    hwnd = apps._resolve_hwnd(_EXPLORER_MATCH)
    if hwnd:
        apps._bring_to_front(hwnd)
    time.sleep(0.8)


def _restore_after_drag(ctx) -> None:
    """关闭资源管理器后，把阿里旺旺精确恢复到分屏前的位置和大小并置前。"""
    name = _app_name(ctx, _APP)
    rect = ctx.extras.get(_DRAG_WINDOW_RECT_KEY)
    if isinstance(rect, tuple) and len(rect) == 4:
        left, top, right, bottom = rect
        restored = apps.move_resize(
            name, left, top, right - left, bottom - top, front=True
        )
    else:
        restored = apps.restore_app(name)
        if restored:
            apps.activate_app(name)
    print("  🪟 已恢复阿里旺旺分屏前窗口尺寸并置前" if restored
          else "  ⚠️ 未找到阿里旺旺窗口，无法恢复分屏前尺寸")
    time.sleep(0.8)


def _stage_drag_step() -> Step:
    """AI 只负责选一次、拖一次；窄窗里不要求判断被遮住的输入区预览。"""
    return step(
        "拖拽本次唯一图片到阿里旺旺输入区（只拖一次）",
        ai(
            f"屏幕已分屏：左侧是阿里旺旺与'{_APP.target}'的群聊，右侧是 dlp_test 资源管理器，"
            f"目录里只有一个本次生成的 dlp_sample_*.png 图片。阿里旺旺输入框里已经先粘贴了"
            f"同名文件名文字。\n"
            f"只做一轮：在右侧单击选中唯一图片（不要双击），再把它拖到左侧阿里旺旺**底部输入区**"
            f"并松开。分屏后的阿里旺旺输入区较窄，图片预览可能被遮住或不显示在当前可见区域；"
            f"这不代表拖拽失败。完成一次拖放后立即 finished，后续程序会关闭资源管理器、恢复"
            f"阿里旺旺分屏前尺寸，再单独确认预览。不要按回车、不要点发送、不要再次拖拽，"
            f"也不要因为看不到预览而 call_user。",
            action_limits={"click": 1, "drag": 1},
        ),
    )


def _confirm_drag_preview_step() -> Step:
    """窗口恢复后只读确认 caption 和图片预览都在输入区。"""
    return step(
        "恢复窗口后确认文件名和图片预览都在输入区（只读）",
        ai(
            f"资源管理器已关闭，阿里旺旺已恢复到分屏前的窗口尺寸并置前。现在只观察底部输入区："
            f"应同时看到 dlp_sample_*.png 文件名文字和一张待发送图片缩略图/预览。"
            f"两者都在输入区就立即 finished。不要点击、不要按键、不要重新拖拽，更不要发送。"
            f"如果恢复窗口后仍缺少图片预览，直接 call_user，由用户判断；禁止自行重试拖拽。"
        ),
    )


def _stage_screenshot_step() -> Step:
    """使用阿里旺旺自带截图工具生成一次截图，只放入输入区。"""
    return step(
        "用阿里旺旺自带截图功能截一次图并放入输入框（不发送）",
        ai(
            f"输入框里已经先粘贴了本次唯一截图文件名标识 dlp_screenshot_*.png。现在只生成一次"
            f"阿里旺旺自带截图并让它进入输入区：\n"
            f"1. 点击输入框工具栏里的截图按钮；\n"
            f"2. 框选一个较大区域，包含较多阿里旺旺窗口外的桌面/其它窗口/任务栏画面，"
            f"但拖拽起止点不要贴屏幕四角；\n"
            f"3. 点击截图工具条的完成/对勾，让截图缩略图进入输入区。\n"
            f"看到输入区同时有 dlp_screenshot_*.png 文字和截图预览后立即 finished。"
            f"不要按回车、不要点发送、不要再次截图。若一次截图后没有预览，直接 call_user。",
            action_limits={"click": 2, "drag": 1},
        ),
    )


def _send_once(ctx) -> None:
    """只按一次回车发送当前输入区内容，发送权不交给 AI。"""
    keyboard.press_enter()
    print(f"  📨 已确定性按一次回车发送当前输入区内容到「{_APP.target}」（阿里旺旺专属）")
    time.sleep(1.5)


def _sent_pair_verify(pattern: str) -> str:
    return (
        f"after 截图中，'{_APP.target}'聊天记录区（不是底部输入框）存在本次最新的一组我方消息："
        f"一条包含形如 {pattern} 的唯一文字气泡，且紧邻一条我方图片缩略图气泡。"
        f"文字和图片二者缺一不可；若内容仍在输入框、只有文字没有图片、或出现两组相同的新消息，"
        f"均不通过。该 dlp_ 文件名每次唯一，因此它与图片同时出现在聊天记录区即可证明本次新增。"
    )


def _observe_sent_step(pattern: str) -> Step:
    """hard 发送后的只读 presence 验收，绝不提供补发分支。"""
    return step(
        f"确认文字和图片气泡已新增到「{_APP.target}」（只读）",
        ai(
            f"程序刚才已把输入区中的唯一文件名文字和图片**确定性按一次回车发送**。"
            f"你现在只观察聊天记录区：应看到一条我方的 {pattern} 文件名文字气泡，"
            f"并紧邻一条我方图片缩略图气泡。两者都出现就立即 finished。"
            f"绝对不要点击、输入、按回车、重新上传/拖拽/粘贴/截图或再次发送。"
            f"若没有同时看到文字和图片，直接 call_user；本步骤没有任何补发权限。",
            verify=_sent_pair_verify(pattern),
            verify_mode="presence",
        ),
    )


def _file_prefix_steps() -> list[Step | None]:
    return [
        *_enter_conversation_steps(_APP),
        *_maybe_maximize_steps(_APP),
        _copy_step(_APP),
        step("把本次图片文件名放入文字剪贴板", hard(_prepare_file_caption)),
        _paste_caption_step(_FILE_CAPTION_PATTERN),
    ]


def _file_suffix_steps(*, close_explorer: bool = False) -> list[Step | None]:
    trailing: list[Step | None] = [
        step("确定性回车发送文字和图片（只发送一次）", hard(_send_once)),
        _observe_sent_step(_FILE_CAPTION_PATTERN),
    ]
    if close_explorer:
        trailing.append(cleanup(_close_explorer))
    trailing.extend([
        cleanup(_cleanup_copy),
        *_maybe_restore_cleanups(_APP),
    ])
    return trailing


@case(
    id="desktop_app.im.aliww.outbound_image.drag_drop",
    name="桌面应用 - 即时通信 - 阿里旺旺 - 外发图片 - 拖拽图片到对话框",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发图片（仅支持图片）", action="拖拽图片到对话框",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_drag_drop() -> list[Step | None]:
    return [
        *_file_prefix_steps(),
        step("用文件资源管理器打开只含本次图片的 dlp_test 目录", hard(_open_sensitive_dir)),
        step("把阿里旺旺与资源管理器排到左右半屏", hard(_layout_for_drag)),
        _stage_drag_step(),
        step("拖拽后关闭 dlp_test 资源管理器", hard(_close_explorer)),
        step("恢复阿里旺旺分屏前窗口尺寸并置前", hard(_restore_after_drag)),
        _confirm_drag_preview_step(),
        *_file_suffix_steps(close_explorer=True),
    ]


@case(
    id="desktop_app.im.aliww.outbound_image.upload",
    name="桌面应用 - 即时通信 - 阿里旺旺 - 外发图片 - 对话框图片上传",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发图片（仅支持图片）", action="对话框图片上传",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_upload() -> list[Step | None]:
    return [
        *_file_prefix_steps(),
        *_stage_upload_steps(),
        *_file_suffix_steps(),
    ]


@case(
    id="desktop_app.im.aliww.outbound_image.copy_paste",
    name="桌面应用 - 即时通信 - 阿里旺旺 - 外发图片 - 复制粘贴图片外发",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发图片（仅支持图片）", action="复制粘贴图片外发",
    platforms=[Platform.WINDOWS], tags=_TAGS, reflect=True,
)
def case_copy_paste() -> list[Step | None]:
    return [
        *_file_prefix_steps(),
        step("把本次唯一图片放入文件剪贴板", hard(_copy_file_to_clipboard)),
        _stage_clipboard_image_step(),
        *_file_suffix_steps(),
    ]


@case(
    id="desktop_app.im.aliww.outbound_screenshot.builtin_capture",
    name="桌面应用 - 即时通信 - 阿里旺旺 - 外发截图 - 自带截图外发",
    channel="desktop_app.im", app=_APP.report_name,
    scenario="外发截图（自带截图工具）", action="自带截图外发",
    platforms=[Platform.WINDOWS], tags=[*_TAGS, "screenshot"], reflect=True,
)
def case_screenshot() -> list[Step | None]:
    return [
        *_enter_conversation_steps(_APP),
        step("生成本次截图的唯一文件名文字标识", hard(_prepare_screenshot_caption)),
        _paste_caption_step(_SCREENSHOT_CAPTION_PATTERN),
        _stage_screenshot_step(),
        step("确定性回车发送文字和截图（只发送一次）", hard(_send_once)),
        _observe_sent_step(_SCREENSHOT_CAPTION_PATTERN),
        *_maybe_restore_cleanups(_APP),
    ]
