"""出库管理接口：维护出库单，覆盖确认拣货、安排发运、取消出库等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.schemas import ActionResult, EntryPayload, ImportResult, PageResult
from app.services.outbound import OutboundService, parse_import_file

router = APIRouter(prefix="/api/outbound", tags=["出库管理"])

service = OutboundService()

LIST_FIELDS = ["出库单号", "客户名称", "货物名称", "批次号", "出库数量", "出库温度", "拣货人", "出库时间"]
STATUSES = ["待拣货", "已拣货", "已发运", "已取消"]
# 上传体积上限：超过直接拒收；行数上限在导入服务里控制，超限会保留已导入部分。
MAX_IMPORT_BYTES = 2 * 1024 * 1024


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按出库单号检索"),
    status: str | None = Query(default=None, description="待拣货、已拣货、已发运、已取消"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按出库单号与状态过滤出库管理列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


# 注意：/export、/download 这类静态路径必须放在 /{entry_id} 之前，否则会被当成 id 匹配掉。
@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出出库管理清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "outbound", "total": total, "items": items}


@router.get("/download")
def download_entries() -> Response:
    """下载出库管理清单 CSV：批次号等列全部带上，刚导入生效的记录也会出现在里面。"""
    items, _ = service.list_entries(page=1, size=10000)
    content = service.render_download(items)
    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=outbound-entries.csv"},
    )


@router.post("/import", response_model=ImportResult)
async def import_entries(request: Request) -> dict[str, Any]:
    """批量导入出库单：接收 CSV 文本，逐行校验，合法行落库，问题行逐条给出原因。

    文件过大或解析中断时会中止处理，但已经导入成功的行会保留；重复导入同一份文件
    不会让已生效的行重复落库。
    """
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="未收到文件内容，请选择要导入的 CSV 文件")
    if len(body) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=400, detail="文件超过 2MB 上限，请拆分后分批导入")
    rows, parse_error = parse_import_file(body)
    result = service.import_entries(rows)
    if parse_error:
        result["aborted"] = True
        result["ok"] = False
        result["message"] = f"{result['message']}；{parse_error}"
    return result


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条出库单明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"出库单 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条出库单，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="出库单已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条出库单执行确认拣货、安排发运、取消出库；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
