"""provision 层单元测试（P1 catalog + P2 provisioner + 默认关不影响主流程）。

见 docs/app_provisioning_design.md。核心校验点：
- catalog 解析 mode / credential_ref，清单出现明文凭据即报错；
- provisioner 探测优先、mode=none 跳过、manual 不阻断、未登记放行；
- CaseRunner 默认 provisioner=None 时，app 分组前置阶段完全不触发。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dlp_auto.core.platform import Platform
from dlp_auto.provision import AppProvisioner, load_catalog
from dlp_auto.provision.catalog import AppCatalog, AppSpec, AuthSpec, InstallSpec


def _write(tmp: Path, name: str, text: str) -> Path:
    p = tmp / name
    p.write_text(text, encoding="utf-8")
    return p


class CatalogLoadTests(unittest.TestCase):
    def test_parses_modes_and_credential_ref(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "apps.yaml", """
apps:
  feishu:
    display_name: "飞书"
    install: {mode: download, detect: {mac: "TODO"}, download: {mac: "TODO"}}
    auth: {mode: manual, credential_ref: "feishu"}
  chrome:
    install: {mode: none}
    auth: {mode: none}
""")
            cat = load_catalog(tmp / "apps.yaml")
            self.assertEqual(set(cat.apps), {"feishu", "chrome"})
            self.assertEqual(cat.get("feishu").auth.mode, "manual")
            self.assertEqual(cat.get("feishu").auth.credential_ref, "feishu")
            self.assertEqual(cat.get("chrome").install.mode, "none")
            self.assertEqual(cat.get("chrome").auth.mode, "none")

    def test_missing_file_returns_empty_catalog(self):
        with tempfile.TemporaryDirectory() as d:
            cat = load_catalog(Path(d) / "nope.yaml")
            self.assertFalse(cat)              # __bool__ == False
            self.assertEqual(cat.apps, {})

    def test_rejects_plaintext_credentials_in_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "apps.yaml", """
apps:
  feishu:
    auth: {mode: password, password: "123456"}
""")
            with self.assertRaises(ValueError):
                load_catalog(tmp / "apps.yaml")

    def test_rejects_illegal_mode(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "apps.yaml", """
apps:
  x:
    install: {mode: rm-rf}
""")
            with self.assertRaises(ValueError):
                load_catalog(tmp / "apps.yaml")

    def test_credentials_resolved_from_secret_file(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            _write(tmp, "apps.yaml", """
apps:
  feishu:
    auth: {mode: password, credential_ref: "feishu"}
""")
            _write(tmp, "apps.secret.yaml", """
credentials:
  feishu: {username: "u", password: "p"}
""")
            cat = load_catalog(tmp / "apps.yaml")
            cred = cat.credential("feishu")
            self.assertEqual(cred.username, "u")
            self.assertEqual(cred.password, "p")
            self.assertIsNone(cat.credential(None))
            self.assertIsNone(cat.credential("missing"))


def _catalog(**specs: AppSpec) -> AppCatalog:
    return AppCatalog(apps=dict(specs))


def _spec(key: str, *, install_mode="none", detect=None, auth_mode="none",
          hint=None, ref=None) -> AppSpec:
    return AppSpec(
        key=key, display_name=key,
        install=InstallSpec(mode=install_mode, detect=detect or {}),
        auth=AuthSpec(mode=auth_mode, logged_in_hint=hint, credential_ref=ref),
    )


class ProvisionerTests(unittest.TestCase):
    def test_none_modes_are_ready(self):
        cat = _catalog(chrome=_spec("chrome", install_mode="none", auth_mode="none"))
        prov = AppProvisioner(cat, Platform.MAC)
        r = prov.ensure_ready("chrome")
        self.assertTrue(r.ok)
        self.assertEqual(r.installed, "skipped")
        self.assertEqual(r.logged_in, "skipped")

    def test_unregistered_app_passes_through(self):
        prov = AppProvisioner(_catalog(), Platform.MAC)
        r = prov.ensure_ready("whatever")
        self.assertTrue(r.ok)          # 未登记不臆测、不阻断

    def test_manual_login_not_blocking(self):
        cat = _catalog(feishu=_spec("feishu", install_mode="none",
                                    auth_mode="manual", ref="feishu"))
        prov = AppProvisioner(cat, Platform.MAC)
        r = prov.ensure_ready("feishu")
        self.assertTrue(r.ok)          # 第一阶段人工登录：探测不到也放行
        self.assertEqual(r.logged_in, "manual")

    def test_detect_installed_hits_existing_path(self):
        with tempfile.TemporaryDirectory() as d:
            cat = _catalog(app=_spec("app", install_mode="download",
                                     detect={"mac": d}, auth_mode="none"))
            prov = AppProvisioner(cat, Platform.MAC)
            r = prov.ensure_ready("app")
            self.assertEqual(r.installed, "already")

    def test_todo_detect_path_treated_as_not_installed(self):
        cat = _catalog(app=_spec("app", install_mode="download",
                                 detect={"mac": "TODO"}, auth_mode="none"))
        prov = AppProvisioner(cat, Platform.MAC)
        r = prov.ensure_ready("app")
        # 第一阶段未实装安装：未探测到只记 skipped（人工安装），不判失败
        self.assertEqual(r.installed, "skipped")
        self.assertTrue(r.ok)

    def test_detail_never_contains_credentials(self):
        cat = _catalog(feishu=_spec("feishu", auth_mode="manual", ref="feishu"))
        cat = AppCatalog(apps=cat.apps,
                         _credentials={"feishu": __import__(
                             "dlp_auto.provision.catalog", fromlist=["Credential"]
                         ).Credential(username="secret_user", password="secret_pass")})
        prov = AppProvisioner(cat, Platform.MAC)
        r = prov.ensure_ready("feishu")
        self.assertNotIn("secret_pass", r.detail)
        self.assertNotIn("secret_user", r.detail)


if __name__ == "__main__":
    unittest.main()
