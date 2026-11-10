"""桌面应用 - 即时通信 - 飞书 - demo case（骨架占位）。

层级对齐 DLP 管理后台分级（详见 docs/stage2_plan.md §4）。
本 case 故意不调用 need_human()，用以演示 D14：human/ 不会被实例化。
"""
from __future__ import annotations

from dlp_auto.case.spec import (
    Step,
    ai,
    case,
    cleanup,
    hard,
    on_platform,
    setup,
    step,
)
from dlp_auto.core.platform import Platform


def _setup_env(ctx) -> None:
    pass


def _cleanup_env(ctx) -> None:
    pass


def _create_sensitive_file(ctx):
    pass


@case(
    id="desktop_app.im.feishu.send_sensitive_file",
    name="桌面应用 - 即时通信 - 飞书 - 发送敏感文件被拦截",
    channel="desktop_app.im",
    platforms=[Platform.MAC],
    tags=["desktop_app", "im", "feishu", "sensitive", "demo"],
)
def define() -> list[Step | None]:
    return [
        setup(_setup_env),
        on_platform(Platform.MAC, step("准备敏感文件", hard(_create_sensitive_file))),
        step("打开飞书并进入指定会话", ai("打开飞书并进入名为 'dlp-test' 的会话")),
        step("拖拽文件到聊天框并发送", ai("将剪贴板里的敏感文件拖到聊天框并点击发送")),
        cleanup(_cleanup_env),
    ]
