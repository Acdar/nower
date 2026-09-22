"""可选依赖缺失时的导入健壮性。

回归背景：打包环境没有安装可选的 tinify / markdownify，而
``arknights_mower.utils.email`` 顶层无条件 import 它们，导致
``from arknights_mower.__main__ import main`` 在「开始执行」时抛
ModuleNotFoundError：/start 返回 500、界面没有任何日志、几秒后自动变回未运行。
"""

import builtins
import importlib
import sys

import numpy as np
import pytest

EMAIL_MODULE = "arknights_mower.utils.email"
MISSING = ("tinify", "markdownify")


@pytest.fixture
def email_module_without_optional_deps():
    """在「tinify / markdownify 都不可用」的进程状态下重新导入 email 模块。"""
    saved = {name: sys.modules.pop(name, None) for name in MISSING}
    sys.modules.pop(EMAIL_MODULE, None)
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.split(".")[0] in MISSING:
            raise ImportError(f"No module named '{name}'")
        return real_import(name, *args, **kwargs)

    builtins.__import__ = fake_import
    try:
        yield importlib.import_module(EMAIL_MODULE)
    finally:
        builtins.__import__ = real_import
        sys.modules.pop(EMAIL_MODULE, None)
        for name, module in saved.items():
            if module is not None:
                sys.modules[name] = module
        # 还原成真实依赖环境下的模块，避免污染其它测试
        importlib.import_module(EMAIL_MODULE)


def test_email_import_survives_missing_optional_deps(
    email_module_without_optional_deps,
):
    module = email_module_without_optional_deps
    assert module.tinify is None
    assert module.md is None


def test_upload_message_skips_image_without_tinify(email_module_without_optional_deps):
    image = np.zeros((4, 4, 3), dtype=np.uint8)
    assert email_module_without_optional_deps.upload_message(image) is None


def test_send_message_without_optional_deps(
    email_module_without_optional_deps, monkeypatch
):
    """缺可选依赖时 send_message 仍应能走完（不联网、不发邮件/推送）。"""
    module = email_module_without_optional_deps
    conf = module.config.conf
    monkeypatch.setattr(conf, "mail_enable", False, raising=False)
    monkeypatch.setattr(conf, "server_push_enable", False, raising=False)
    module.send_message(body="<p>hello</p>", subject="测试")
