"""飞连（Feilian）DLP 管理后台 HTTP 客户端：管理员登录 + 按 event_id 查询外发事件。

仅供 server_event 的 run 级服务端回查在 mock=false 时调用（阶段二真实接口）。
与判定逻辑解耦：本模块只负责「登录拿会话」「按 event_id 查、返回命中详情」，
是否 passed/inconclusive 的裁决在 server_event.check_run 里做。

安全（硬约束 #4/#11）：账号密码 / 会话凭据只从 Settings（config.secret.yaml /
环境变量）读，绝不写入日志/报告/异常信息；本模块的 print/异常一律不带出明文。

鉴权两种来源（**cookie 优先、账号密码回退**，见 build_client）：
- 直传 session_cookie + csrf_token → 跳过登录（不必存长期明文密码，更安全）；
- 否则 admin_user + admin_pwd 走 AES 登录（无现成会话时的回退）。

依赖（requests / pycryptodome）在本模块顶部导入——server_event 只在 mock=false
分支里 **懒加载** 本模块，故 mock 跑通不需要装这两个依赖。

接口契约来源（用户 2026-08-06 提供，改写自其 admin_login.py 与查询 curl）：
- 登录：POST https://{host}:{portal_port}/api/v1/login?language=zh-CN&os=web
        body: {login_scene, account_type=email, account, password=<AES 加密>}
        从响应 Set-Cookie 取 csrf-token + session。
- 查询：GET  https://{host}:{admin_port}/api/admin/v2/dynamic_security/edlp/events
        ?event_ids=<uuid>&start=&end=&os=web&tab=edlp/event/alarm&limit=&offset=0
        鉴权用登录拿到的 cookie + csrf-token 头。
"""
from __future__ import annotations

import hashlib
from typing import Any

import requests
import urllib3
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

# 内网测试环境多为自签名证书：关闭 InsecureRequestWarning，请求侧 verify=False。
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_LOGIN_PATH = "/api/v1/login?language=zh-CN&os=web"
_EVENTS_PATH = "/api/admin/v2/dynamic_security/edlp/events"
_EVENTS_TAB = "edlp/event/alarm"


def _aes_encrypt_password(message: str) -> str:
    """与前端一致的密码加密：AES-256-CBC，key/iv 由固定 salt 派生，返回 hex。

    salt = md5(2^53-1)（JS 最大安全整数），key = salt（32 字节 → AES-256），
    iv = sha1(key)[:16]。改写自用户 admin_login.py，逻辑等价。
    """
    key = hashlib.md5(str(2 ** 53 - 1).encode()).hexdigest()
    iv = hashlib.sha1(key.encode()).hexdigest()[:16]
    cipher = AES.new(key.encode(), AES.MODE_CBC, iv.encode())
    return cipher.encrypt(pad(message.encode(), AES.block_size)).hex()


class FeilianAuthError(Exception):
    """登录失败的信号；调用方（server_event）据此降级 inconclusive，不打断 run。"""


class FeilianClient:
    """一次 run 级回查用的短生命周期客户端：login() 一次，query_events() 一次。"""

    def __init__(self, *, host: str, admin_port: int = 8443,
                 portal_port: int = 10443, admin_user: str | None = None,
                 admin_pwd: str | None = None, session_cookie: str | None = None,
                 csrf_token: str | None = None, timeout_sec: float = 10.0):
        self.host = host
        self.admin_port = int(admin_port)
        self.portal_port = int(portal_port)
        self._admin_user = admin_user
        self._admin_pwd = admin_pwd          # 明文仅驻留内存，绝不外泄
        self.timeout = float(timeout_sec)
        # 会话凭据：优先由外部直接注入（跳过登录）；否则由 login() 换取后填入。
        # 直传时同样只驻留内存、绝不落日志/报告（硬约束 #4/#11）。
        self._cookie: str | None = session_cookie or None
        self._csrf: str | None = csrf_token or None

    # ── 登录：换取 cookie + csrf-token ────────────────────────────────
    def login(self) -> None:
        """执行管理员登录并缓存会话。失败抛 FeilianAuthError（不含明文密码）。

        若已注入现成会话（cookie+csrf 直传），直接跳过——省一次登录往返，
        也不要求配置长期明文密码（会话凭据权限更小、可随时失效）。
        """
        if self._cookie and self._csrf:
            return
        if not self._admin_user or not self._admin_pwd:
            raise FeilianAuthError(
                "既未注入会话凭据（session_cookie/csrf_token），也未配置管理员"
                "账号/密码，无法登录回查。")
        url = f"https://{self.host}:{self.portal_port}{_LOGIN_PATH}"
        data = {
            "login_scene": "feilian",
            "account_type": "email",
            "account": self._admin_user,
            "password": _aes_encrypt_password(self._admin_pwd),
        }
        try:
            resp = requests.post(url, json=data, timeout=self.timeout, verify=False)
        except requests.RequestException as e:
            raise FeilianAuthError(f"登录网络请求失败：{e}") from e

        csrf = None
        for c in resp.cookies:
            if c.name == "csrf-token":
                csrf = c.value
                break
        if csrf is None:
            # 只暴露状态码，绝不带出 body（可能含敏感信息），也不带出密码。
            raise FeilianAuthError(
                f"登录未返回 csrf-token（status={resp.status_code}）；"
                "请核对 config.secret.yaml 的 verify.server 账号/密码与目标环境。")
        self._csrf = csrf
        self._cookie = "; ".join(f"{c.name}={c.value}" for c in resp.cookies)

    # ── 查询：按 event_id 批量查（内部逐个查，避免臆测批量分隔符）─────
    def query_events(self, event_ids: list[str], *, start: int,
                     end: int) -> dict[str, list[dict[str, Any]]]:
        """返回 {event_id: 命中事件列表}，仅含**查到真实数据**的 id。

        start/end 为 unix 秒时间窗（按 event_id 精确查，窗口只作兜底）。
        逐个 id 查询：curl 观测到的 event_ids 是单值，批量分隔符未确认，
        故不臆测批量传参（硬约束 #1）；每 run 事件数不多（数十条），可接受。

        返回**完整列表**而非取首条：条数（是否恰好 1 条）与处置动作的裁决权归
        server_event.check_run（分层：client 只取数、不裁决）。查到 0 条的 id 不入表。
        """
        if self._cookie is None or self._csrf is None:
            raise FeilianAuthError("尚未登录（请先调用 login()）。")
        hits: dict[str, list[dict[str, Any]]] = {}
        for eid in event_ids:
            events = self._query_one(eid, start=start, end=end)
            if events:
                hits[eid] = events
        return hits

    def _query_one(self, event_id: str, *, start: int, end: int) -> list[dict]:
        url = f"https://{self.host}:{self.admin_port}{_EVENTS_PATH}"
        params = {
            "event_ids": event_id,
            "start": start,
            "end": end,
            "os": "web",
            "tab": _EVENTS_TAB,
            "limit": 10,
            "offset": 0,
        }
        headers = {
            "accept": "*/*",
            "accept-language": "zh-CN",
            "cookie": self._cookie,
            "csrf-token": self._csrf,
        }
        resp = requests.get(url, params=params, headers=headers,
                            timeout=self.timeout, verify=False)
        resp.raise_for_status()
        return _extract_events(resp.json())


def _extract_events(payload: Any) -> list[dict]:
    """从查询响应里抽出事件列表（真机联调时按实际返回结构收紧）。

    响应 JSON 结构尚未真机核对（用户确认「查到真实数据即算命中」，返回体联调时看）。
    这里做保守兼容：尝试若干常见形状，取到的第一个非空列表即视为命中数据。
    TODO(真机联调核对)：确认返回结构后，替换为精确取值并按需要校验状态字段。
    """
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    # data 可能直接是 list，或嵌 events/list/items
    data = payload.get("data", payload)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("events", "list", "items", "rows"):
            v = data.get(key)
            if isinstance(v, list):
                return v
    return []


def build_client(settings) -> "FeilianClient":
    """从 Settings 装配客户端：host/端口读 config，凭据读 secret（硬约束 #1/#11）。

    鉴权两种来源，**cookie 优先、账号密码回退**：
    - 配了 `verify.server.session_cookie` + `csrf_token` → 直传会话、跳过登录
      （不必存长期明文管理员密码，会话权限更小、可随时失效——更安全）；
    - 否则用 `admin_user` + `admin_pwd` 走 AES 登录（回退，兼容无现成会话时）。
    两者都没配时抛 FeilianAuthError，由 server_event 降级 inconclusive 并提示补哪项。
    """
    host = settings.get("verify", "server", "host", default=None)
    if not host:
        raise FeilianAuthError(
            "未配置 verify.server.host（服务端环境域名），无法回查。")
    session_cookie = settings.get("verify", "server", "session_cookie", default=None)
    csrf_token = settings.get("verify", "server", "csrf_token", default=None)
    admin_user = settings.get("verify", "server", "admin_user", default=None)
    admin_pwd = settings.get("verify", "server", "admin_pwd", default=None)
    has_session = bool(session_cookie and csrf_token)
    has_login = bool(admin_user and admin_pwd)
    if not has_session and not has_login:
        raise FeilianAuthError(
            "未配置服务端回查凭据：请在 config.secret.yaml 的 verify.server 下"
            "二选一——①会话直传 session_cookie + csrf_token（推荐，跳过登录）；"
            "②管理员 admin_user + admin_pwd（AES 登录回退），否则无法回查。")
    return FeilianClient(
        host=host,
        admin_port=int(settings.get("verify", "server", "admin_port", default=8443)),
        portal_port=int(settings.get("verify", "server", "portal_port", default=10443)),
        admin_user=admin_user,
        admin_pwd=admin_pwd,
        session_cookie=session_cookie,
        csrf_token=csrf_token,
        timeout_sec=float(settings.get("verify", "server", "timeout_sec", default=10.0)),
    )
