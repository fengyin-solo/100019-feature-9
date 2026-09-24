"""出库管理业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from typing import Any

from app.store import store

MODULE = "outbound"
REQUIRED_FIELDS = ["出库单号", "客户名称", "货物名称"]
STATUS_ORDER = ["待拣货", "已拣货", "已发运", "已取消"]
ACTION_RULES = {"确认拣货": "已拣货", "安排发运": "已发运", "取消出库": "已取消"}
NEGATIVE_ACTIONS = []

# 批量导入：表头需与列表字段对齐，前四列逐行必填校验
IMPORT_FIELDS = ["出库单号", "客户名称", "货物名称", "批次号", "出库数量", "出库温度", "拣货人", "出库时间"]
IMPORT_REQUIRED = ["出库单号", "客户名称", "货物名称", "批次号"]
MAX_IMPORT_ROWS = 500
ORDER_NO_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{2,31}$")
BATCH_NO_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{1,31}$")


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

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        return self._new_entry(values), []

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

    def import_entries(self, text: str, *, max_rows: int = MAX_IMPORT_ROWS) -> dict[str, Any]:
        """按表格文本逐行导入出库单。

        合法行立即落库；格式无效或重复的行记入 failed 并说明原因；
        超过行数上限或解析中断时停止，已成功的部分保留。
        重复导入同一文件时，已生效的出库单号会被跳过，不会重复落库。
        """
        summary: dict[str, Any] = {"ok": True, "message": "", "imported": 0, "failed": [], "aborted": False}
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        try:
            header = next(reader, None)
        except csv.Error:
            header = None
        if header is None:
            summary.update(ok=False, message="表格内容为空或表头无法解析")
            return summary
        columns = [str(cell).strip() for cell in header]
        missing = [field for field in IMPORT_REQUIRED if field not in columns]
        if missing:
            summary.update(ok=False, message=f"表头缺少必需列：{'、'.join(missing)}")
            return summary

        existing = {str(row.get("出库单号", "")).strip() for row in store.rows(MODULE)}
        seen: set[str] = set()
        imported = 0
        failed: list[dict[str, Any]] = []
        abort_reason: str | None = None
        processed = 0
        line_no = 1  # 表头占第 1 行
        while True:
            try:
                row = next(reader, None)
            except csv.Error as exc:
                abort_reason = f"第 {line_no + 1} 行附近解析中断（{exc}），已保留成功导入的 {imported} 条"
                break
            if row is None:
                break
            line_no += 1
            if not any(str(cell).strip() for cell in row):
                continue  # 空行不算数据行，直接跳过
            if processed >= max_rows:
                abort_reason = f"超过单次导入上限 {max_rows} 行，后续行未处理，已保留成功导入的 {imported} 条"
                break
            processed += 1
            values = {columns[i]: str(row[i]).strip() for i in range(min(len(columns), len(row)))}
            reason = self._validate_import_row(values, seen, existing)
            if reason:
                failed.append({
                    "line": line_no,
                    "reason": reason,
                    "values": {field: values.get(field, "") for field in IMPORT_REQUIRED},
                })
                continue
            order_no = values["出库单号"]
            seen.add(order_no)
            existing.add(order_no)
            if values.get("出库数量"):
                values["出库数量"] = int(values["出库数量"])
            self._new_entry(values)
            imported += 1

        if abort_reason:
            summary["aborted"] = True
        if processed == 0 and not abort_reason:
            summary.update(ok=False, message="表格中没有可导入的数据行")
            return summary
        parts = [f"成功导入 {imported} 条"]
        if failed:
            parts.append(f"{len(failed)} 行未通过校验")
        if abort_reason:
            parts.append(abort_reason)
        summary.update(message="；".join(parts), imported=imported, failed=failed)
        return summary

    def _validate_import_row(self, values: dict[str, str], seen: set[str], existing: set[str]) -> str | None:
        """校验一行导入数据，返回未通过原因；通过时返回 None。"""
        order_no = values.get("出库单号", "")
        if not order_no:
            return "出库单号为空"
        if not ORDER_NO_PATTERN.match(order_no):
            return f"出库单号「{order_no}」格式无效（需为 3-32 位字母、数字或短横线）"
        if order_no in seen:
            return f"出库单号「{order_no}」在文件内重复"
        if order_no in existing:
            return f"出库单号「{order_no}」已存在，为避免重复导入已跳过"
        for field in ("客户名称", "货物名称"):
            if not values.get(field):
                return f"{field}为空"
            if len(values[field]) > 50:
                return f"{field}超过 50 字上限"
        batch_no = values.get("批次号", "")
        if not batch_no:
            return "批次号为空"
        if not BATCH_NO_PATTERN.match(batch_no):
            return f"批次号「{batch_no}」格式无效（需为 2-32 位字母、数字或短横线）"
        quantity = values.get("出库数量", "")
        if quantity and (not quantity.isdigit() or int(quantity) <= 0):
            return f"出库数量「{quantity}」需为正整数"
        shipped_at = values.get("出库时间", "")
        if shipped_at:
            try:
                datetime.strptime(shipped_at, "%Y-%m-%d")
            except ValueError:
                return f"出库时间「{shipped_at}」格式应为 YYYY-MM-DD"
        return None

    def _new_entry(self, values: dict[str, Any]) -> dict[str, Any]:
        """按当前最大 id 生成一条待拣货出库单，保留提交上来的有效字段（含批次号）。"""
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in IMPORT_FIELDS:
            value = values.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            entry[field] = value
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry
