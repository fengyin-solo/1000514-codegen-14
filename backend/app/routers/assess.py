"""状态评估接口：维护评估记录，覆盖开始评估、确认定级、发起复评、提交复评与风险定位。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.assess import RISK_ORDER, STATUS_ORDER, AssessService

router = APIRouter(prefix="/api/assess", tags=["状态评估"])

service = AssessService()

LIST_FIELDS = ["评估编号", "评估对象", "评估周期", "健康分值", "风险等级", "评估人员", "评估结论", "评估状态"]
STATUSES = STATUS_ORDER


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按评估编号检索"),
    status: str | None = Query(default=None, description="待评估、评估中、已定级、已复评"),
    period: str | None = Query(default=None, description="按评估周期过滤，如 2026年第3期"),
    risk: str | None = Query(default=None, description="按风险等级过滤：重大/较大/一般/低风险"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按评估编号、状态、周期与风险等级过滤状态评估列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword, status=status, period=period, risk=risk, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/risk-board")
def risk_board(
    period: str | None = Query(default=None, description="按评估周期过滤；不传则跨周期定位，同设备只取最新结论"),
) -> dict[str, Any]:
    """风险定位：高风险设备排序在前、首评与复评分开统计、分值缺失单列。"""
    return service.risk_board(period=period)


@router.get("/periods")
def list_periods() -> dict[str, Any]:
    """评估周期下拉选项，按时间倒序。"""
    return {"items": service.list_periods(), "risk_levels": RISK_ORDER}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条评估记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"评估记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条评估记录，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="评估记录已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """开始评估、发起复评等无表单动作照旧直达；确认定级、提交复评走带校验的专用接口。"""
    action = str(payload.values.get("action") or "").strip()
    if action in {"确认定级", "提交复评"}:
        return ActionResult(
            ok=False,
            message=f"「{action}」需要提交评估信息，请使用定级/复评提交入口",
        )
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/grade", response_model=ActionResult)
def confirm_grade(entry_id: int, payload: EntryPayload) -> ActionResult:
    """确认首次定级：校验健康分值、风险等级、评估结论与评估人员，不过逐字段标出。"""
    entry, message, field_errors = service.confirm_grade(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message, field_errors=field_errors)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/review", response_model=ActionResult)
def submit_review(entry_id: int, payload: EntryPayload) -> ActionResult:
    """提交复评：校验口径与首次定级一致，不过逐字段标出且不覆盖原结论。"""
    entry, message, field_errors = service.submit_review(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message, field_errors=field_errors)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries(
    period: str | None = None,
) -> dict[str, Any]:
    """导出状态评估清单：可按周期过滤，返回当前条件下的全量数据。"""
    items, total = service.list_entries(period=period, page=1, size=10000)
    return {"module": "assess", "total": total, "items": items}
