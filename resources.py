"""回归 run 级资源：在 case 间共享，统一在 run 结束时释放。"""

from __future__ import annotations

from typing import Any


class RegressionRunResources:
    def __init__(self, *, keep_browser_open: bool = False):
        self.keep_browser_open = keep_browser_open
        self._admin_browsers: dict[str, Any] = {}

    def open_or_reuse_admin_browser(
        self,
        ctx: Any,
        app: Any,
        url: str,
    ) -> bool:
        """打开或复用管理后台窗口；返回本次是否创建了新会话。"""
        from dlp_auto.case.web_mac_common import (
            browser_session_alive,
            navigate_browser,
            open_or_reset_browser,
        )

        current = self._admin_browsers.get(app.app_key)
        if current is not None and browser_session_alive(current):
            navigate_browser(current, url)
            print(f"     复用本次 run 的{app.report_name}管理后台会话")
            return False

        open_or_reset_browser(ctx, app, url)
        self._admin_browsers[app.app_key] = app
        print(f"     新建本次 run 的{app.report_name}管理后台会话")
        return True

    def activate_admin_browser(self, app: Any) -> None:
        from dlp_auto.case.web_mac_common import activate_browser

        activate_browser(app)

    def navigate_admin_browser(self, app: Any, url: str) -> None:
        from dlp_auto.case.web_mac_common import navigate_browser

        navigate_browser(app, url)

    def finalize(self) -> None:
        if not self._admin_browsers:
            return
        if self.keep_browser_open:
            print("[regression] --keep-browser-open 已启用，保留本次 run 的管理后台浏览器窗口")
            return

        from dlp_auto.case.web_mac_common import close_browser_session

        for app in reversed(list(self._admin_browsers.values())):
            try:
                close_browser_session(app)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"[regression] 关闭{app.report_name}管理后台会话失败："
                    f"{type(exc).__name__}: {exc}"
                )
        self._admin_browsers.clear()
