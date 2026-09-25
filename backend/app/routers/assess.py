"""状态评估接口：维护评估记录，覆盖开始评估、确认定级、发起复评，以及风险定位与复评提交。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.assess import RISK_CONCLUSIONS, RISK_LEVELS, AssessService

router = APIRouter(prefix="/api/assess", tags=["状态评估"])

service = AssessService()


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按评估编号检索"),
    status: str | None = Query(default=None, description="待评估、评估中、已定级、已复评"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按评估编号与状态过滤状态评估列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/risk/overview")
def risk_overview(
    period: str | None = Query(default=None, description="评估周期过滤；不传时跨周期定位，同一设备只保留最新周期"),
) -> dict[str, Any]:
    """风险定位：高风险设备按风险等级与健康分值置顶，已复评对象过滤，缺失分值单列。"""
    return service.risk_overview(period=period)


@router.get("/risk/options")
def risk_options() -> dict[str, Any]:
    """复评表单的口径选项：保证各入口的风险等级与评估结论对得上。"""
    return {
        "risk_levels": RISK_LEVELS,
        "conclusions": [RISK_CONCLUSIONS[level] for level in RISK_LEVELS],
        "conclusion_by_level": RISK_CONCLUSIONS,
    }


@router.post("/{entry_id}/review", response_model=ActionResult)
def submit_review(entry_id: int, payload: EntryPayload) -> ActionResult:
    """提交复评结论：逐字段校验，不通过时把字段与原因带回去标出来。"""
    entry, errors, message = service.submit_review(entry_id, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message, entry={"errors": errors} if errors else None)
    return ActionResult(ok=True, message=message, entry=entry)


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
    """对单条评估记录执行开始评估、确认定级、发起复评；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出状态评估清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "assess", "total": total, "items": items}
