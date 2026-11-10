"""被测软件清单（catalog）数据模型与加载。

见 docs/app_provisioning_design.md §3/§4。

职责边界（呼应设计 §1.1「与主流程完全解耦」）：
    本模块只负责把 config/apps.yaml + config/apps.secret.yaml 解析成只读数据结构，
    不触碰安装 / 登录动作，也不被主流程默认引用。删除本包不影响现有 case。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dlp_auto.config import _load_yaml, _resolve_env  # 复用同包的 yaml 读取与 ${VAR} 展开

APPS_FILENAME = "apps.yaml"
APPS_SECRET_FILENAME = "apps.secret.yaml"

_INSTALL_MODES = {"none", "download"}
_AUTH_MODES = {"none", "password", "manual"}


@dataclass(frozen=True)
class InstallSpec:
    mode: str = "none"                       # none | download
    detect: dict[str, str] = field(default_factory=dict)   # {mac, windows}
    download: dict[str, str] = field(default_factory=dict)  # {mac, windows}


@dataclass(frozen=True)
class AuthSpec:
    mode: str = "none"                       # none | password | manual
    logged_in_hint: str | None = None
    login_nav_hint: str | None = None
    credential_ref: str | None = None


@dataclass(frozen=True)
class AppSpec:
    key: str
    display_name: str
    install: InstallSpec
    auth: AuthSpec


@dataclass(frozen=True)
class Credential:
    """凭据实体，仅存在于内存；不得写入日志 / 报告 / 截图（设计 §6）。"""

    username: str | None = None
    password: str | None = None
    download_token: str | None = None


@dataclass(frozen=True)
class AppCatalog:
    apps: dict[str, AppSpec] = field(default_factory=dict)
    # 凭据独立保存，仅通过 credential() 按 ref 取用，避免与清单混在一起被误打印
    _credentials: dict[str, Credential] = field(default_factory=dict)

    def get(self, key: str) -> AppSpec | None:
        return self.apps.get(key)

    def credential(self, ref: str | None) -> Credential | None:
        if not ref:
            return None
        return self._credentials.get(ref)

    def __bool__(self) -> bool:
        return bool(self.apps)


def _parse_install(raw: dict) -> InstallSpec:
    mode = raw.get("mode", "none")
    if mode not in _INSTALL_MODES:
        raise ValueError(f"install.mode 非法：{mode!r}（允许 {sorted(_INSTALL_MODES)}）")
    return InstallSpec(
        mode=mode,
        detect=dict(raw.get("detect") or {}),
        download=dict(raw.get("download") or {}),
    )


def _parse_auth(raw: dict) -> AuthSpec:
    mode = raw.get("mode", "none")
    if mode not in _AUTH_MODES:
        raise ValueError(f"auth.mode 非法：{mode!r}（允许 {sorted(_AUTH_MODES)}）")
    return AuthSpec(
        mode=mode,
        logged_in_hint=raw.get("logged_in_hint"),
        login_nav_hint=raw.get("login_nav_hint"),
        credential_ref=raw.get("credential_ref"),
    )


def _parse_apps(data: dict) -> dict[str, AppSpec]:
    apps: dict[str, AppSpec] = {}
    for key, raw in (data.get("apps") or {}).items():
        raw = raw or {}
        # 清单里出现真实凭据字段视为违规（设计 §6 硬约束 #1）
        for banned in ("username", "password", "token", "download_token"):
            if banned in (raw.get("auth") or {}):
                raise ValueError(
                    f"app {key!r} 的 auth 段出现敏感字段 {banned!r}；"
                    f"凭据只能放 apps.secret.yaml，清单里仅允许 credential_ref"
                )
        apps[key] = AppSpec(
            key=key,
            display_name=raw.get("display_name", key),
            install=_parse_install(raw.get("install") or {}),
            auth=_parse_auth(raw.get("auth") or {}),
        )
    return apps


def _parse_credentials(data: dict) -> dict[str, Credential]:
    creds: dict[str, Credential] = {}
    for ref, raw in (data.get("credentials") or {}).items():
        raw = raw or {}
        creds[ref] = Credential(
            username=raw.get("username"),
            password=raw.get("password"),
            download_token=raw.get("download_token"),
        )
    return creds


def load_catalog(path: str | Path = "config/apps.yaml") -> AppCatalog:
    """加载软件清单 + 凭据。

    - apps.secret.yaml 与 apps.yaml 同目录（相对 path.parent 推导），gitignore 不入库；
      缺失时返回空凭据表。
    - 统一展开 ${VAR} 占位（复用 config 的 env 解析），凭据明文只存在于内存。
    - 缺失 apps.yaml：返回空 catalog（本能力默认不启用，主流程不受影响）。
    """
    p = Path(path)
    apps_data = _resolve_env(_load_yaml(p))
    secret_data = _resolve_env(_load_yaml(p.parent / APPS_SECRET_FILENAME))
    return AppCatalog(
        apps=_parse_apps(apps_data),
        _credentials=_parse_credentials(secret_data),
    )
