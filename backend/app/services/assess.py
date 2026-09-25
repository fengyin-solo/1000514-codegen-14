"""状态评估业务规则：状态流转、风险定位、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import re
from typing import Any

from app.store import store

MODULE = "assess"
REQUIRED_FIELDS = ["评估编号", "评估对象", "评估周期"]
STATUS_ORDER = ["待评估", "评估中", "已定级", "已复评"]
ACTION_RULES = {"开始评估": "评估中", "确认定级": "已定级", "发起复评": "已复评"}
NEGATIVE_ACTIONS = []

# 风险等级口径：分值越低风险越高，排序与统计都以这里为准。
RISK_ORDER = ["重大风险", "较大风险", "一般风险", "低风险"]
RISK_BANDS = [
    (0, 60, "重大风险"),
    (60, 75, "较大风险"),
    (75, 90, "一般风险"),
    (90, 101, "低风险"),
]
GRADED_STATUSES = {"已定级", "已复评"}
# 已复评记录允许再次提交复评，形成多轮复评；首次定级只能走“确认定级”。
RESUBMIT_STATUSES = {"已定级", "已复评"}


def parse_score(value: Any) -> float | None:
    """健康分值只接受 0~100 的数值；空值、文字、越界都视为缺失。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        score = float(text)
    except ValueError:
        return None
    if score < 0 or score > 100:
        return None
    return score


def risk_of_score(score: float) -> str:
    """按健康分值推导风险等级，是全平台风险口径的唯一来源。"""
    for low, high, label in RISK_BANDS:
        if low <= score < high:
            return label
    return "低风险"


def expected_conclusion(score: float) -> str:
    """评估结论须以风险等级开头，保证结论与等级对得上。"""
    return f"{risk_of_score(score)}，"


def _period_key(value: Any) -> tuple:
    """评估周期按“年-期别”排序，无法解析的排到最后。"""
    text = str(value or "").strip()
    match = re.search(r"(\d{4}).*?(\d+)", text)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    return (-1, -1)


def _missing_reason(row: dict[str, Any]) -> str | None:
    """健康分值缺失分两种原因：还没出结论，或分值录了但无法采信。"""
    status = row.get("status")
    raw = str(row.get("健康分值") or "").strip()
    if not raw:
        if status in GRADED_STATUSES:
            return "已定级但未录入健康分值，无法定位风险"
        return "评估尚未出结论，健康分值待评定"
    if parse_score(raw) is None:
        return f"健康分值「{raw}」不是 0~100 的有效数值，无法采信"
    return None


def _risk_rank(row: dict[str, Any]) -> tuple:
    score = parse_score(row.get("健康分值"))
    level = str(row.get("风险等级") or "").strip() or risk_of_score(score or 0)
    level_index = RISK_ORDER.index(level) if level in RISK_ORDER else len(RISK_ORDER)
    # 等级越严重越靠前；同等级健康分值低的在前；再用评估编号兜底稳定排序。
    return (level_index, score if score is not None else 999, str(row.get("评估编号") or ""))


def _supplement(row: dict[str, Any], *, with_consistency: bool = False) -> dict[str, Any]:
    """列表/看板统一补展示字段，避免各入口各算各的导致口径漂移。"""
    row["评估状态"] = row.get("status")
    score = parse_score(row.get("健康分值"))
    reason = _missing_reason(row)
    row["健康分值缺失原因"] = reason
    if with_consistency and score is not None:
        want_level = risk_of_score(score)
        want_prefix = expected_conclusion(score)
        level = str(row.get("风险等级") or "").strip()
        conclusion = str(row.get("评估结论") or "").strip()
        row["风险等级一致"] = (not level) or level == want_level
        row["评估结论一致"] = (not conclusion) or conclusion.startswith(want_prefix)
    return row


class AssessService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        period: str | None = None,
        risk: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("评估编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if period:
            rows = [row for row in rows if str(row.get("评估周期") or "").strip() == period]
        if risk:
            rows = [row for row in rows if str(row.get("风险等级") or "").strip() == risk]
        rows = [_supplement(dict(row)) for row in rows]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def list_periods(self) -> list[str]:
        """评估周期筛选选项：按时间倒序，最新周期在前。"""
        periods = {
            str(row.get("评估周期") or "").strip()
            for row in store.rows(MODULE)
            if str(row.get("评估周期") or "").strip()
        }
        return sorted(periods, key=_period_key, reverse=True)

    def risk_board(self, period: str | None = None) -> dict[str, Any]:
        """风险定位：已出结论的设备按风险排序，缺失分值单列，同设备跨周期去重。"""
        rows = [_supplement(dict(row), with_consistency=True) for row in store.rows(MODULE)]
        if period:
            rows = [row for row in rows if str(row.get("评估周期") or "").strip() == period]

        # 健康分值缺失（含未出结论、空值、脏数据）单独列出并说明原因。
        missing = [
            {field: row.get(field) for field in ("id", "评估编号", "评估对象", "评估周期", "status", "健康分值")}
            | {"评估状态": row.get("status"), "缺失原因": row["健康分值缺失原因"]}
            for row in rows
            if row["健康分值缺失原因"]
        ]
        missing.sort(key=lambda row: (_period_key(row.get("评估周期")), str(row.get("评估对象") or "")), reverse=True)

        # 只对出了结论且分值有效的对象做风险定位。
        graded = [
            row for row in rows
            if row.get("status") in GRADED_STATUSES and parse_score(row.get("健康分值")) is not None
        ]

        # 同一台设备跨周期只保留最新周期的一条结论，定位结果不重复出现。
        latest: dict[str, dict[str, Any]] = {}
        for row in sorted(graded, key=lambda row: _period_key(row.get("评估周期"))):
            key = str(row.get("评估对象") or "").strip()
            if key and (key not in latest or _period_key(row.get("评估周期")) >= _period_key(latest[key].get("评估周期"))):
                latest[key] = row
        ranked = sorted(latest.values(), key=_risk_rank)

        scores = [parse_score(row.get("健康分值")) for row in graded]
        scores = [score for score in scores if score is not None]
        high_risk = sum(1 for row in ranked if row.get("风险等级") == "重大风险")
        stats = {
            # 首次定级与复评分开统计：复评轮次计入“已复评”，首评结果计入“首次定级”。
            "首次定级": sum(1 for row in graded if row.get("status") == "已定级"),
            "已复评": sum(1 for row in graded if row.get("status") == "已复评"),
            "高风险设备": high_risk,
            "健康分值均值": round(sum(scores) / len(scores), 1) if scores else None,
            "风险分布": {
                label: sum(1 for row in ranked if row.get("风险等级") == label)
                for label in RISK_ORDER
            },
            "健康分值缺失": len(missing),
        }

        inconsistencies: list[dict[str, Any]] = []
        for row in graded:
            score = parse_score(row.get("健康分值"))
            assert score is not None
            if row.get("风险等级一致") and row.get("评估结论一致"):
                continue
            inconsistencies.append(
                {field: row.get(field) for field in ("id", "评估编号", "评估对象", "评估周期", "风险等级", "评估结论")}
                | {"健康分值": score, "应有风险等级": risk_of_score(score)}
            )

        return {
            "周期选项": self.list_periods(),
            "当前周期": period,
            "统计": stats,
            "风险定位": ranked,
            "分值缺失": missing,
            "口径不一致": inconsistencies,
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return _supplement(dict(entry), with_consistency=True) if entry else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        for field in ("健康分值", "风险等级", "评估人员", "评估结论"):
            if str(values.get(field) or "").strip():
                entry[field] = values.get(field)
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return _supplement(dict(entry)), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"评估记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于状态评估可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        current_index = STATUS_ORDER.index(entry["status"]) if entry.get("status") in STATUS_ORDER else -1
        target_index = STATUS_ORDER.index(target)
        # 老的“发起复评”照旧：沿用原有直达流转，不加额外校验。
        if action != "发起复评" and target_index <= current_index:
            return None, f"当前状态「{entry.get('status')}」不允许执行「{action}」"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        entry["评估状态"] = target
        return _supplement(dict(entry), with_consistency=True), f"评估记录已{action}"

    def confirm_grade(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str, dict[str, str]]:
        """确认定级（首次定级）：分值、等级、结论、人员校验不过逐字段标出。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"评估记录 {entry_id} 不存在或已归档", {}
        if entry.get("status") not in {"评估中"}:
            return None, f"当前状态「{entry.get('status')}」不允许确认定级", {}
        field_errors = self._validate_grade_fields(entry, values)
        if field_errors:
            return None, "定级信息校验未通过，请按标注补正后再提交", field_errors
        self._apply_grade(entry, values)
        entry["status"] = "已定级"
        entry["评估状态"] = "已定级"
        entry["pending"] = False
        return _supplement(dict(entry), with_consistency=True), "首次定级已确认", {}

    def submit_review(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str, dict[str, str]]:
        """提交复评：只有已定过级的对象能复评；校验不过逐字段标出，不改变原结论。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"评估记录 {entry_id} 不存在或已归档", {}
        if entry.get("status") not in RESUBMIT_STATUSES:
            return None, f"当前状态「{entry.get('status')}」尚未定级，不能提交复评", {}
        field_errors = self._validate_grade_fields(entry, values)
        if field_errors:
            return None, "复评信息校验未通过，请按标注补正后再提交", field_errors
        self._apply_grade(entry, values)
        entry["status"] = "已复评"
        entry["评估状态"] = "已复评"
        entry["pending"] = False
        entry["复评轮次"] = int(entry.get("复评轮次") or 0) + 1
        return _supplement(dict(entry), with_consistency=True), "复评结果已提交", {}

    def _validate_grade_fields(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> dict[str, str]:
        """定级/复评共用校验：分值缺失要标出，等级与结论必须和分值口径对得上。"""
        errors: dict[str, str] = {}
        raw_score = values.get("健康分值", entry.get("健康分值"))
        score = parse_score(raw_score)
        if score is None:
            shown = str(raw_score or "").strip()
            errors["健康分值"] = (
                "健康分值缺失，无法定级" if not shown
                else f"健康分值「{shown}」不是 0~100 的有效数值"
            )
        else:
            want_level = risk_of_score(score)
            # 风险等级由分值自动推导；只有表单显式提交了等级且与口径不符才拦下，
            # 复评时记录里的旧等级不参与校验（它本来就要被新结论覆盖）。
            if "风险等级" in values:
                level = str(values.get("风险等级") or "").strip()
                if level and level != want_level:
                    errors["风险等级"] = f"健康分值 {score:g} 对应风险等级应为「{want_level}」"
            want_prefix = expected_conclusion(score)
            conclusion = str(values.get("评估结论") or "").strip()
            if not conclusion:
                errors["评估结论"] = "评估结论不能为空，须写明风险判定与处置意见"
            elif not conclusion.startswith(want_prefix):
                errors["评估结论"] = f"评估结论须以「{want_prefix}」开头，与风险等级保持一致"
        person = str(values.get("评估人员") or "").strip()
        if not person:
            errors["评估人员"] = "评估人员不能为空"
        return errors

    def _apply_grade(self, entry: dict[str, Any], values: dict[str, Any]) -> None:
        """把定级结果落进记录：等级由分值统一推导，避免各入口口径不一致。"""
        score = parse_score(values.get("健康分值", entry.get("健康分值")))
        assert score is not None
        entry["健康分值"] = score
        entry["风险等级"] = risk_of_score(score)
        conclusion = str(values.get("评估结论") or "").strip()
        if conclusion:
            entry["评估结论"] = conclusion
        person = str(values.get("评估人员") or "").strip()
        if person:
            entry["评估人员"] = person
