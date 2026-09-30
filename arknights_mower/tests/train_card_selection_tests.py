"""训练室选人页已有待确认选择时，不能再次点击同一张卡。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from arknights_mower.solvers import base_mixin
from arknights_mower.solvers.base_mixin import (
    AgentSelectionNotReady,
    BaseMixin,
    agent_card_selected,
    train_card_selected,
)
from arknights_mower.utils import config

pytestmark = pytest.mark.usefixtures("legacy_selection_conf")

SCOPE = ((584, 479), (759, 506))
NORMAL_SCOPE = ((631, 488), (820, 520))


def card_frame(selected):
    img = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    if selected:
        cv2.rectangle(img, (565, 113), (766, 522), (0, 180, 230), 7)
    return img


def normal_card_frame(selected):
    img = np.full((1080, 1920, 3), 50, dtype=np.uint8)
    if selected:
        cv2.rectangle(img, (609, 113), (830, 532), (0, 180, 230), 7)
    return img


@pytest.mark.parametrize("low_frame_rate", [False, True])
@pytest.mark.parametrize("already_selected", [False, True])
def test_train_scan_only_clicks_unselected_card(
    monkeypatch, low_frame_rate, already_selected
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", low_frame_rate)
    frame = card_frame(already_selected)
    page = (("予愿安洁莉娜", SCOPE),)
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    solver.tap = MagicMock()
    solver.wait_for_agent_page = MagicMock(return_value=page)
    monkeypatch.setattr(base_mixin, "operator_list_train", lambda img: page)

    targets = ["予愿安洁莉娜"]
    selected, _ = solver.scan_agent(targets, train=True, respect_train_selection=True)

    assert train_card_selected(frame, SCOPE) is already_selected
    assert selected == ["予愿安洁莉娜"]
    assert targets == []
    assert solver.tap.call_count == (0 if already_selected else 1)


def test_train_verification_reads_blue_frame_instead_of_first_card(monkeypatch):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", False)
    frame = card_frame(False)
    cv2.rectangle(frame, (565, 529), (766, 938), (0, 180, 230), 7)
    page = (
        ("结城理", SCOPE),
        ("予愿安洁莉娜", ((584, 895), (759, 922))),
    )
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    monkeypatch.setattr(base_mixin, "operator_list_train", lambda img: page)

    assert solver.wait_for_arranged_agents(["予愿安洁莉娜"], train=True) == [
        "予愿安洁莉娜"
    ]


@pytest.mark.parametrize(
    "expected,verified",
    [
        (["褐果", "凯尔希"], ["褐果", "凯尔希"]),
        (["褐果"], None),
    ],
)
def test_train_verification_accounts_for_multiple_blue_frames(
    monkeypatch, expected, verified
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", False)
    frame = card_frame(True)
    cv2.rectangle(frame, (565, 529), (766, 938), (0, 180, 230), 7)
    page = (
        ("褐果", SCOPE),
        ("凯尔希", ((584, 895), (759, 922))),
    )
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    monkeypatch.setattr(base_mixin, "operator_list_train", lambda img: page)

    if verified is None:
        with pytest.raises(AgentSelectionNotReady):
            solver.wait_for_arranged_agents(expected, train=True)
    else:
        assert solver.wait_for_arranged_agents(expected, train=True) == verified


@pytest.mark.parametrize("low_frame_rate", [False, True])
@pytest.mark.parametrize("already_selected", [False, True])
def test_normal_scan_checks_blue_frame_without_another_capture(
    monkeypatch, low_frame_rate, already_selected
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", low_frame_rate)
    frame = normal_card_frame(already_selected)
    page = (("褐果", NORMAL_SCOPE),)
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    solver.tap = MagicMock()
    solver.wait_for_agent_page = MagicMock(return_value=page)
    monkeypatch.setattr(base_mixin, "operator_list", lambda img, **kwargs: page)

    targets = ["褐果"]
    selected, _ = solver.scan_agent(targets)

    assert agent_card_selected(frame, NORMAL_SCOPE) is already_selected
    assert selected == ["褐果"]
    assert targets == []
    assert solver.tap.call_count == (0 if already_selected else 1)
    assert solver.recog.update.call_count == (0 if low_frame_rate else 1)


@pytest.mark.parametrize(
    "expected,verified", [(["褐果", "凯尔希"], True), (["褐果"], False)]
)
def test_normal_pre_reorder_verification_uses_all_blue_frames(
    monkeypatch, expected, verified
):
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", False)
    frame = normal_card_frame(True)
    cv2.rectangle(frame, (609, 534), (830, 953), (0, 180, 230), 7)
    page = (
        ("褐果", NORMAL_SCOPE),
        ("凯尔希", ((631, 909), (820, 941))),
    )
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=frame, update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    monkeypatch.setattr(base_mixin, "operator_list", lambda img, **kwargs: page)

    if verified:
        assert solver.wait_for_arranged_agents(expected) == expected
    else:
        with pytest.raises(AgentSelectionNotReady):
            solver.wait_for_arranged_agents(expected)


def test_unselected_card_below_blue_frame_is_not_ambiguous():
    frame = normal_card_frame(True)
    lower_scope = ((631, 909), (820, 941))
    assert agent_card_selected(frame, NORMAL_SCOPE) is True
    assert agent_card_selected(frame, lower_scope) is False


def test_unselected_card_above_blue_frame_with_top_icon_is_not_ambiguous():
    """上方未选卡下沿擦到下方蓝框、上沿又命中自带青色图标时仍判未选中。

    实机复现：裁切框与下方卡片重叠 2px（bottom8 行有 2 行全蓝），卡片右上的
    青色技能图标（H≈96，贴 inRange 边界）落在 top8 行内，两条长边都不满足
    「另一条边明显缺失」时旧判定返回 None，整帧被静默丢弃。
    """
    frame = normal_card_frame(False)
    cv2.rectangle(frame, (609, 534), (830, 953), (0, 180, 230), 7)
    cv2.rectangle(frame, (760, 113), (817, 120), (12, 146, 183), -1)
    assert agent_card_selected(frame, NORMAL_SCOPE) is False


def test_unselected_card_beside_and_above_blue_frames_is_not_ambiguous():
    """左右相邻卡的竖边框会污染侧带，侧带不能用来反推未选中。"""
    frame = normal_card_frame(False)
    # 右侧卡片选中：它的左边框落进本卡裁切框的右侧带
    cv2.rectangle(frame, (825, 113), (1050, 532), (0, 180, 230), 7)
    # 下方卡片选中：它的上边框擦到本卡裁切框最外侧两行
    cv2.rectangle(frame, (609, 534), (830, 953), (0, 180, 230), 7)
    # 本卡右上的青色技能图标
    cv2.rectangle(frame, (760, 113), (817, 120), (12, 146, 183), -1)
    assert agent_card_selected(frame, NORMAL_SCOPE) is False


def test_all_ambiguous_frames_report_discard_reason(monkeypatch):
    """所有帧都被丢弃时，报错要说明未得到可用读取，而不是「读取到空名单」。"""
    monkeypatch.setattr(config.conf, "low_frame_rate_mode", False)
    page = (
        ("褐果", NORMAL_SCOPE),
        ("凯尔希", ((631, 909), (820, 941))),
    )
    solver = BaseMixin()
    solver.recog = SimpleNamespace(img=normal_card_frame(False), update=MagicMock())
    solver.find = MagicMock(return_value=False)
    solver.sleep = MagicMock()
    monkeypatch.setattr(base_mixin, "operator_list", lambda img, **kwargs: page)
    monkeypatch.setattr(base_mixin, "agent_card_selected", lambda *args, **kwargs: None)

    with pytest.raises(AgentSelectionNotReady, match="蓝框判定不明确被丢弃"):
        solver.wait_for_arranged_agents(["褐果"])
