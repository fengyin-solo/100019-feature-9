"""出库管理业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import csv
import io
import re
from typing import Any

from app.store import store

MODULE = "outbound"
REQUIRED_FIELDS = ["出库单号", "客户名称", "货物名称"]
STATUS_ORDER = ["待拣货", "已拣货", "已发运", "已取消"]
ACTION_RULES = {"确认拣货": "已拣货", "安排发运": "已发运", "取消出库": "已取消"}
NEGATIVE_ACTIONS = []

# 批量导入相关：表头、格式规则与保护阈值。
IMPORT_REQUIRED_FIELDS = ["出库单号", "客户名称", "货物名称", "批次号"]
IMPORT_OPTIONAL_FIELDS = ["出库数量", "出库温度", "拣货人", "出库时间"]
IMPORT_FIELDS = IMPORT_REQUIRED_FIELDS + IMPORT_OPTIONAL_FIELDS
DOWNLOAD_FIELDS = IMPORT_FIELDS + ["状态"]
ENTRY_NO_PATTERN = re.compile(r"^OUTB-\d{4,}$")
BATCH_NO_PATTERN = re.compile(r"^[\w-]{1,32}$")
NAME_MAX_LENGTH = 64
# 单次请求最多新生效的行数：超限即中止，已导入的保留，重试可续上剩余部分。
MAX_IMPORT_ROWS = 1000
# 响应里最多带回的失败行明细数，避免超大文件把响应撑爆。
MAX_IMPORT_FAILURES = 500
# Excel 导出的 CSV 常见 UTF-8 与 GBK 两种编码，按顺序尝试解码。
IMPORT_ENCODINGS = ("utf-8-sig", "gb18030")


def parse_import_file(content: bytes) -> tuple[list[dict[str, str]], str | None]:
    """把上传的表格内容解析成按列名取值的行字典列表。

    返回 (已解析的行, 中断原因)；表头缺失或解析中途出错时，保留已经解析成功的部分，
    并给出可读的原因，方便上层决定是否继续落库。
    """
    text: str | None = None
    for encoding in IMPORT_ENCODINGS:
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return [], "文件编码无法识别，请使用 UTF-8 或 GBK 编码的 CSV 文件"

    reader = csv.reader(io.StringIO(text), strict=True)
    try:
        header = next(reader, None)
    except csv.Error as exc:
        return [], f"表头解析失败（{exc}），文件可能不是有效的 CSV"
    if not header:
        return [], "文件为空或缺少表头行"

    columns = [cell.strip() for cell in header]
    missing_columns = [field for field in IMPORT_REQUIRED_FIELDS if field not in columns]
    if missing_columns:
        return [], f"表头缺少必需列：{'、'.join(missing_columns)}"

    rows: list[dict[str, str]] = []
    try:
        for cells in reader:
            if not cells or all(not str(cell).strip() for cell in cells):
                continue
            row = {
                columns[i]: cells[i].strip()
                for i in range(min(len(columns), len(cells)))
            }
            rows.append(row)
    except csv.Error as exc:
        # strict 模式下引号、换行结构异常会在这里中断：保留前面解析成功的行。
        return rows, f"第 {reader.line_num} 行附近解析中断（{exc}），仅处理了此前解析成功的行"
    return rows, None


def _validate_import_row(
    values: dict[str, str],
    existing_numbers: set[str],
    seen_numbers: set[str],
) -> str | None:
    """校验单行：先看必填与格式，再查文件内重复与库内重复，命中第一条就返回原因。"""
    for field in IMPORT_REQUIRED_FIELDS:
        if not values[field]:
            return f"缺少必填字段：{field}"
    entry_no = values["出库单号"]
    if not ENTRY_NO_PATTERN.match(entry_no):
        return "出库单号格式无效（应为 OUTB-加数字编号，如 OUTB-0009）"
    if len(values["客户名称"]) > NAME_MAX_LENGTH or len(values["货物名称"]) > NAME_MAX_LENGTH:
        return f"客户名称或货物名称不能超过 {NAME_MAX_LENGTH} 个字"
    if not BATCH_NO_PATTERN.match(values["批次号"]):
        return "批次号格式无效（限 1-32 位字母、数字、汉字、-、_）"
    quantity = values["出库数量"]
    if quantity and (not quantity.isdigit() or int(quantity) <= 0):
        return "出库数量格式无效（应为正整数）"
    if entry_no in seen_numbers:
        return "出库单号在文件内重复"
    if entry_no in existing_numbers:
        # 重试同一份文件时，已生效的行不会被重复导入。
        return "出库单号已存在，本次跳过（重复导入不会重复生效）"
    return None


class OutboundService:
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
            rows = [row for row in rows if keyword in str(row.get("出库单号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def _insert(self, values: dict[str, Any], fields: list[str]) -> dict[str, Any]:
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in fields})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        fields = REQUIRED_FIELDS + IMPORT_OPTIONAL_FIELDS
        clean = {field: values.get(field) for field in fields if str(values.get(field) or "").strip()}
        return self._insert(clean, fields), []

    def import_entries(self, rows: list[dict[str, str]]) -> dict[str, Any]:
        """逐行校验、逐行落库：合法行立刻生效，问题行记原因。

        单次最多新生效 MAX_IMPORT_ROWS 条，超出即中止并保留已导入部分；已存在的行
        只做跳过、不占配额，所以重试同一份文件可以把剩余部分补完而不产生重复。
        """
        existing_numbers = {
            str(row.get("出库单号") or "").strip() for row in store.rows(MODULE)
        }
        seen_numbers: set[str] = set()
        failures: list[dict[str, Any]] = []
        imported = 0
        failed = 0
        processed = 0
        aborted = False
        abort_reason = ""

        for offset, raw in enumerate(rows):
            if imported >= MAX_IMPORT_ROWS:
                aborted = True
                abort_reason = (
                    f"单次最多导入 {MAX_IMPORT_ROWS} 条，已中止，剩余 {len(rows) - offset} 行未处理"
                    "（重试可继续导入，已生效的行不会重复）"
                )
                break
            processed += 1
            values = {field: str(raw.get(field) or "").strip() for field in IMPORT_FIELDS}
            reason = _validate_import_row(values, existing_numbers, seen_numbers)
            if reason is not None:
                failed += 1
                if len(failures) < MAX_IMPORT_FAILURES:
                    failures.append({
                        "line": offset + 2,  # 表头占第 1 行
                        "order_no": values["出库单号"],
                        "reason": reason,
                    })
                continue
            entry_no = values["出库单号"]
            seen_numbers.add(entry_no)
            existing_numbers.add(entry_no)
            clean = {field: values[field] for field in IMPORT_FIELDS if values[field]}
            if "出库数量" in clean:
                clean["出库数量"] = int(clean["出库数量"])
            self._insert(clean, IMPORT_FIELDS)
            imported += 1

        if not rows:
            message = "文件里没有可导入的数据行"
        else:
            parts = [f"成功导入 {imported} 条"]
            if failed:
                detail = f"{failed} 行未导入"
                if failed > len(failures):
                    detail += f"（失败明细仅展示前 {MAX_IMPORT_FAILURES} 条）"
                parts.append(detail)
            if abort_reason:
                parts.append(abort_reason)
            message = "，".join(parts)
        return {
            "ok": not aborted,
            "message": message,
            "total": processed,
            "imported": imported,
            "failed": failed,
            "aborted": aborted,
            "failures": failures,
        }

    def render_download(self, rows: list[dict[str, Any]]) -> str:
        """把出库清单渲染成 CSV 文本：批次号等列全部带上，导入生效的记录也在其中。"""
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow(DOWNLOAD_FIELDS)
        for row in rows:
            values = [row.get(field) for field in IMPORT_FIELDS]
            values.append(row.get("status", ""))
            writer.writerow(["" if value is None else value for value in values])
        return buffer.getvalue()

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"出库单 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于出库管理可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"出库单已{action}"
