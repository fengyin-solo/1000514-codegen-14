"""状态评估业务规则：状态流转、字段校验、风险定位与复评口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "assess"
REQUIRED_FIELDS = ["评估编号", "评估对象", "评估周期"]
STATUS_ORDER = ["待评估", "评估中", "已定级", "已复评"]
ACTION_RULES = {"开始评估": "评估中", "确认定级": "已定级", "发起复评": "已复评"}
NEGATIVE_ACTIONS = []

# 风险等级口径：全平台以健康分值为准，其他入口的风险等级/评估结论都按它对齐
RISK_LEVELS = ["高风险", "中风险", "低风险"]
RISK_CONCLUSIONS = {
    "高风险": "评估结论：高风险，建议立即整治",
    "中风险": "评估结论：中风险，建议限期整改",
    "低风险": "评估结论：低风险，按计划维护",
}
SCORE_MIN = 0
SCORE_MAX = 100
FINISHED_STATUS = "已定级"  # 首次定级结论
REVIEWED_STATUS = "已复评"  # 复评结论（已出复评结论的对象从风险定位里过滤掉）


def _parse_score(value: Any) -> float | None:
    """健康分值只接受 0~100 的数值；空值、文字、越界都按缺失处理。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        score = float(value)
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            score = float(text)
        except ValueError:
            return None
    if score < SCORE_MIN or score > SCORE_MAX:
        return None
    return score


def risk_level_of(score: float) -> str:
    """分值到风险等级的唯一映射，风险定位与复评提交共用同一套口径。"""
    if score < 60:
        return "高风险"
    if score < 85:
        return "中风险"
    return "低风险"


def _risk_rank(row: dict[str, Any]) -> int:
    score = _parse_score(row.get("健康分值"))
    return RISK_LEVELS.index(risk_level_of(score)) if score is not None else len(RISK_LEVELS)


def _period_sort_key(period: str) -> str:
    """周期按文本倒序（如 2026-Q3 > 2026-Q2 > 2026-06）。"""
    return period


class AssessService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("评估编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"评估记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于状态评估可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"评估记录已{action}"

    # ------------------------------------------------------------------
    # 风险定位
    # ------------------------------------------------------------------
    def list_periods(self) -> list[str]:
        periods = {str(row.get("评估周期") or "").strip() for row in store.rows(MODULE)}
        return sorted((p for p in periods if p), key=_period_sort_key, reverse=True)

    def risk_overview(self, period: str | None = None) -> dict[str, Any]:
        """汇总风险定位口径。

        - 已复评（已出复评结论）的对象不参与风险定位；
        - 跨周期（period 为空）时同一台设备只保留最新周期的一条；
        - 风险对象按风险等级、健康分值排序，高风险在前；
        - 首次定级与已复评分开统计；
        - 健康分值不可用的对象单独列出并说明原因。
        """
        all_rows = store.rows(MODULE)

        if period:
            scoped = [row for row in all_rows if str(row.get("评估周期") or "").strip() == period]
            cross_deduped = False
        else:
            # 跨周期定位：每台设备只取最新周期的记录，旧周期记录不重复出现
            latest: dict[str, dict[str, Any]] = {}
            for row in all_rows:
                name = str(row.get("评估对象") or "").strip()
                if not name:
                    continue
                current = latest.get(name)
                if current is None or _period_sort_key(str(row.get("评估周期") or "")) > _period_sort_key(
                    str(current.get("评估周期") or "")
                ):
                    latest[name] = row
            scoped = list(latest.values())
            cross_deduped = True

        # 已出复评结论的对象从风险定位中过滤，复评数量仍单独统计
        reviewed = [row for row in scoped if row.get("status") == REVIEWED_STATUS]
        candidates = [row for row in scoped if row.get("status") != REVIEWED_STATUS]

        missing_score: list[dict[str, Any]] = []
        located: list[dict[str, Any]] = []
        for row in candidates:
            reason = self._missing_score_reason(row)
            if reason:
                missing_score.append({
                    "id": row.get("id"),
                    "评估编号": row.get("评估编号"),
                    "评估对象": row.get("评估对象"),
                    "评估周期": row.get("评估周期"),
                    "健康分值": row.get("健康分值"),
                    "评估状态": row.get("status"),
                    "缺失原因": reason,
                })
            else:
                located.append(row)

        located.sort(key=lambda row: (_risk_rank(row), _parse_score(row.get("健康分值")) or 0.0, -int(row.get("id", 0))))

        first_levels = [row for row in located if row.get("status") == FINISHED_STATUS]
        risk_items = [self._risk_item(row) for row in located]

        return {
            "periods": self.list_periods(),
            "selected_period": period or "",
            "cross_deduped": cross_deduped,
            "located_total": len(risk_items),
            "first_level_stats": self._level_stats(first_levels),
            "reviewed_stats": self._level_stats(reviewed),
            "risk_items": risk_items,
            "missing_score": missing_score,
            "consistency": self.consistency_check(),
        }

    def _missing_score_reason(self, row: dict[str, Any]) -> str:
        """说明健康分值为什么不可用；返回空串表示分值可用。"""
        raw = row.get("健康分值")
        if raw is None or not str(raw).strip():
            return "健康分值未填报，无法计算风险等级"
        if isinstance(raw, bool):
            return "健康分值格式不是数值，需补录 0~100 的分值"
        if not isinstance(raw, (int, float)):
            try:
                float(str(raw).strip())
            except ValueError:
                return f"健康分值「{raw}」不是有效数值，需补录 0~100 的分值"
        score = _parse_score(raw)
        if score is None:
            return f"健康分值「{raw}」超出 0~100 范围，需核实后重新填报"
        if row.get("status") != FINISHED_STATUS:
            status_label = row.get("status") or "未完成"
            return f"评估状态为{status_label}，风险等级尚未定级确认"
        return ""

    def _risk_item(self, row: dict[str, Any]) -> dict[str, Any]:
        score = _parse_score(row.get("健康分值"))
        level = risk_level_of(score) if score is not None else None
        issues = self._row_issues(row, score, level)
        return {
            "id": row.get("id"),
            "评估编号": row.get("评估编号"),
            "评估对象": row.get("评估对象"),
            "评估周期": row.get("评估周期"),
            "健康分值": score,
            "风险等级": level,
            "评估人员": row.get("评估人员"),
            "评估结论": row.get("评估结论"),
            "评估状态": row.get("status"),
            "首次定级": row.get("status") == FINISHED_STATUS,
            "口径一致": not issues,
            "差异说明": issues,
        }

    def _row_issues(self, row: dict[str, Any], score: float | None, level: str | None) -> list[str]:
        """其他入口登记的风险等级/评估结论要和分值口径对得上，对不上就标出来。"""
        issues: list[str] = []
        if score is None or level is None:
            return issues
        stored_level = str(row.get("风险等级") or "").strip()
        if stored_level and stored_level in RISK_LEVELS and stored_level != level:
            issues.append(f"登记风险等级为{stored_level}，按健康分值应为{level}")
        stored_conclusion = str(row.get("评估结论") or "").strip()
        expected_conclusion = RISK_CONCLUSIONS[level]
        if stored_conclusion and stored_conclusion != expected_conclusion:
            issues.append(f"评估结论与{level}口径不一致，应为「{expected_conclusion}」")
        return issues

    def _level_stats(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        stats = {level: 0 for level in RISK_LEVELS}
        for row in rows:
            score = _parse_score(row.get("健康分值"))
            if score is None:
                continue
            stats[risk_level_of(score)] += 1
        stats["合计"] = sum(stats.values())
        return stats

    def consistency_check(self) -> dict[str, Any]:
        """全量口径巡检：分值、风险等级、评估结论三者对得上的才算一致。"""
        mismatches: list[dict[str, Any]] = []
        checked = 0
        for row in store.rows(MODULE):
            score = _parse_score(row.get("健康分值"))
            if score is None:
                continue
            checked += 1
            level = risk_level_of(score)
            issues = self._row_issues(row, score, level)
            if issues:
                mismatches.append({
                    "id": row.get("id"),
                    "评估编号": row.get("评估编号"),
                    "评估对象": row.get("评估对象"),
                    "差异说明": issues,
                })
        return {
            "checked": checked,
            "mismatch_count": len(mismatches),
            "mismatches": mismatches,
        }

    # ------------------------------------------------------------------
    # 复评提交（老的「发起复评」快捷动作保留在 run_action，这里做带校验的提交）
    # ------------------------------------------------------------------
    def submit_review(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, dict[str, str], str]:
        """复评提交：逐字段校验，不通过时把字段名和原因一并返回。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, {}, f"评估记录 {entry_id} 不存在或已归档"
        if entry.get("status") == REVIEWED_STATUS:
            return None, {}, "该对象已完成复评，不能重复提交"
        if entry.get("status") != FINISHED_STATUS:
            return None, {}, "仅已定级的对象允许发起复评，请先完成首次定级"

        errors: dict[str, str] = {}
        raw_score = values.get("健康分值")
        score = _parse_score(raw_score)
        if raw_score is None or not str(raw_score).strip():
            errors["健康分值"] = "请填写复评健康分值"
        elif score is None:
            errors["健康分值"] = "健康分值需为 0~100 的数值"

        conclusion = str(values.get("评估结论") or "").strip()
        if not conclusion:
            errors["评估结论"] = "请填写复评评估结论"

        reviewer = str(values.get("评估人员") or "").strip()
        if not reviewer:
            errors["评估人员"] = "请填写复评评估人员"

        level = risk_level_of(score) if score is not None else None
        if score is not None and conclusion and level is not None and conclusion != RISK_CONCLUSIONS[level]:
            errors["评估结论"] = (
                f"评估结论与分值口径不一致：分值 {score:g} 对应{level}，"
                f"结论应选「{RISK_CONCLUSIONS[level]}」"
            )

        if errors:
            return None, errors, "复评提交校验未通过，请按提示修正后再提交"

        entry["健康分值"] = score
        entry["风险等级"] = level
        entry["评估结论"] = conclusion
        entry["评估人员"] = reviewer
        entry["status"] = REVIEWED_STATUS
        entry["pending"] = False
        entry["abnormal"] = level == "高风险"
        return entry, {}, "复评结论已提交"
