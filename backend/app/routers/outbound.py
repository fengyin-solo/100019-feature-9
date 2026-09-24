"""出库管理接口：维护出库单，覆盖确认拣货、安排发运、取消出库等动作。"""
from __future__ import annotations

import csv
import io
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.schemas import ActionResult, EntryPayload, ImportResult, PageResult
from app.services.outbound import OutboundService

router = APIRouter(prefix="/api/outbound", tags=["出库管理"])

service = OutboundService()

LIST_FIELDS = ["出库单号", "客户名称", "货物名称", "批次号", "出库数量", "出库温度", "拣货人", "出库时间"]
STATUSES = ["待拣货", "已拣货", "已发运", "已取消"]
MAX_IMPORT_BYTES = 2 * 1024 * 1024  # 单次导入文件上限 2MB


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


@router.post("/import", response_model=ImportResult)
async def import_entries(file: UploadFile = File(...)) -> ImportResult:
    """批量导入出库单：上传 CSV 表格，逐行校验出库单号、客户名称、货物名称与批次号。

    合法行立即落库，问题行带原因返回；文件过大或解析中断时中止并保留已成功的部分，
    重试时已经生效的出库单号会被跳过，不会重复导入。
    """
    data = await file.read(MAX_IMPORT_BYTES + 1)
    oversized = len(data) > MAX_IMPORT_BYTES
    if oversized:
        data = data[:MAX_IMPORT_BYTES]
    text = _decode_upload(data, oversized)
    if text is None:
        return ImportResult(ok=False, message="文件编码无法识别，请上传 UTF-8 或 GBK 编码的 CSV 表格")
    if oversized:
        # 截断可能切坏最后一行，丢弃末尾不完整的一段再解析
        text = text[: text.rfind("\n") + 1] if "\n" in text else ""
    summary = service.import_entries(text)
    if oversized:
        summary["aborted"] = True
        limit = MAX_IMPORT_BYTES // 1024 // 1024
        tail = f"文件超过 {limit}MB 上限，超出部分未处理，已保留成功导入的记录"
        summary["message"] = f"{summary['message']}；{tail}" if summary["message"] else tail
    return ImportResult(**summary)


def _decode_upload(data: bytes, oversized: bool) -> str | None:
    """按 UTF-8（含 BOM）优先、GBK 兜底解码上传内容；截断文件允许丢弃末尾坏字符。"""
    for encoding in ("utf-8-sig", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    if oversized:
        return data.decode("utf-8-sig", errors="ignore")
    return None


@router.get("/export")
def export_entries() -> StreamingResponse:
    """下载出库管理清单 CSV：包含批次号在内的全部列表字段，新导入的记录同样在列。"""
    items, _ = service.list_entries(page=1, size=10000)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(LIST_FIELDS)
    for item in items:
        writer.writerow([item.get(field, "") for field in LIST_FIELDS])
    payload = buffer.getvalue().encode("utf-8-sig")
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote('出库单清单.csv')}"}
    return StreamingResponse(iter([payload]), media_type="text/csv; charset=utf-8", headers=headers)


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
