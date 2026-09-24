"""接口出入参模型：列表分页、动作结果与各模块的明细结构。"""
from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PageResult(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int = 1
    size: int = 20


class ActionResult(BaseModel):
    ok: bool
    message: str
    entry: dict[str, Any] | None = None


class EntryPayload(BaseModel):
    """登记或修改一条业务记录时提交的字段集合。"""

    values: dict[str, Any] = Field(default_factory=dict)
    remark: str | None = None


class ImportFailure(BaseModel):
    """批量导入中未通过校验的一行：行号、原因与关键字段，方便前端单独列出。"""

    line: int
    reason: str
    values: dict[str, Any] = Field(default_factory=dict)


class ImportResult(BaseModel):
    """批量导入结果：成功条数、失败明细，以及是否因超限或解析中断而提前停止。"""

    ok: bool
    message: str
    imported: int = 0
    failed: list[ImportFailure] = Field(default_factory=list)
    aborted: bool = False



class OrderEntry(BaseModel):
    """冷链订单明细结构。"""

    field_0: str | None = None  # 订单编号
    field_1: str | None = None  # 客户名称
    field_2: str | None = None  # 货物名称
    field_3: str | None = None  # 货物类别
    field_4: str | None = None  # 起始冷库
    field_5: str | None = None  # 目的冷库
    field_6: str | None = None  # 要求温度区间
    field_7: str | None = None  # 下单时间

class WaybillEntry(BaseModel):
    """冷链运单明细结构。"""

    field_0: str | None = None  # 运单号
    field_1: str | None = None  # 关联订单
    field_2: str | None = None  # 承运车辆
    field_3: str | None = None  # 司机姓名
    field_4: str | None = None  # 装车时间
    field_5: str | None = None  # 卸货时间
    field_6: str | None = None  # 运单状态

class VehicleEntry(BaseModel):
    """冷藏车辆明细结构。"""

    field_0: str | None = None  # 车牌号码
    field_1: str | None = None  # 车辆类型
    field_2: str | None = None  # 制冷机组型号
    field_3: str | None = None  # 车厢容积
    field_4: str | None = None  # 温区数量
    field_5: str | None = None  # 所属车队
    field_6: str | None = None  # 年检到期日

class DriverEntry(BaseModel):
    """司机档案明细结构。"""

    field_0: str | None = None  # 司机工号
    field_1: str | None = None  # 司机姓名
    field_2: str | None = None  # 联系电话
    field_3: str | None = None  # 驾驶证号
    field_4: str | None = None  # 从业资格证号
    field_5: str | None = None  # 所属车队
    field_6: str | None = None  # 在途状态

class TemperatureEntry(BaseModel):
    """温控记录明细结构。"""

    field_0: str | None = None  # 记录编号
    field_1: str | None = None  # 关联运单
    field_2: str | None = None  # 测点编号
    field_3: str | None = None  # 实时温度
    field_4: str | None = None  # 温度上限
    field_5: str | None = None  # 温度下限
    field_6: str | None = None  # 采集时间

class ExcursionEntry(BaseModel):
    """温度异常事件明细结构。"""

    field_0: str | None = None  # 事件编号
    field_1: str | None = None  # 关联运单
    field_2: str | None = None  # 异常类型
    field_3: str | None = None  # 超限时长
    field_4: str | None = None  # 最高温度
    field_5: str | None = None  # 发生时间
    field_6: str | None = None  # 处置人

class WarehouseEntry(BaseModel):
    """冷库档案明细结构。"""

    field_0: str | None = None  # 冷库编码
    field_1: str | None = None  # 冷库名称
    field_2: str | None = None  # 库区温区
    field_3: str | None = None  # 设定温度
    field_4: str | None = None  # 库容吨位
    field_5: str | None = None  # 责任人
    field_6: str | None = None  # 启用状态

class InboundEntry(BaseModel):
    """入库单明细结构。"""

    field_0: str | None = None  # 入库单号
    field_1: str | None = None  # 供应商名称
    field_2: str | None = None  # 货物名称
    field_3: str | None = None  # 批次号
    field_4: str | None = None  # 入库数量
    field_5: str | None = None  # 到货温度
    field_6: str | None = None  # 收货人
    field_7: str | None = None  # 入库时间

class OutboundEntry(BaseModel):
    """出库单明细结构。"""

    field_0: str | None = None  # 出库单号
    field_1: str | None = None  # 客户名称
    field_2: str | None = None  # 货物名称
    field_3: str | None = None  # 批次号
    field_4: str | None = None  # 出库数量
    field_5: str | None = None  # 出库温度
    field_6: str | None = None  # 拣货人
    field_7: str | None = None  # 出库时间

class InventoryEntry(BaseModel):
    """库存批次明细结构。"""

    field_0: str | None = None  # 库存编码
    field_1: str | None = None  # 货物名称
    field_2: str | None = None  # 批次号
    field_3: str | None = None  # 库位编号
    field_4: str | None = None  # 在库数量
    field_5: str | None = None  # 锁定量
    field_6: str | None = None  # 保质期至
    field_7: str | None = None  # 入库日期

class TraceEntry(BaseModel):
    """追溯记录明细结构。"""

    field_0: str | None = None  # 追溯码
    field_1: str | None = None  # 货物名称
    field_2: str | None = None  # 生产批次
    field_3: str | None = None  # 上游供应商
    field_4: str | None = None  # 入库单号
    field_5: str | None = None  # 全程温度区间
    field_6: str | None = None  # 追溯状态

class QualityEntry(BaseModel):
    """质检单明细结构。"""

    field_0: str | None = None  # 质检单号
    field_1: str | None = None  # 关联批次
    field_2: str | None = None  # 检测项目
    field_3: str | None = None  # 检测值
    field_4: str | None = None  # 标准限值
    field_5: str | None = None  # 检测结论
    field_6: str | None = None  # 检测员
    field_7: str | None = None  # 检测时间

class RouteEntry(BaseModel):
    """配送线路明细结构。"""

    field_0: str | None = None  # 线路编码
    field_1: str | None = None  # 线路名称
    field_2: str | None = None  # 起点冷库
    field_3: str | None = None  # 终点冷库
    field_4: str | None = None  # 途经站点
    field_5: str | None = None  # 预计时长
    field_6: str | None = None  # 线路里程

class DispatchEntry(BaseModel):
    """调度单明细结构。"""

    field_0: str | None = None  # 调度单号
    field_1: str | None = None  # 关联订单
    field_2: str | None = None  # 配送线路
    field_3: str | None = None  # 指派车辆
    field_4: str | None = None  # 指派司机
    field_5: str | None = None  # 计划发车时间
    field_6: str | None = None  # 调度状态

class DeviceEntry(BaseModel):
    """温控设备明细结构。"""

    field_0: str | None = None  # 设备编号
    field_1: str | None = None  # 设备名称
    field_2: str | None = None  # 设备型号
    field_3: str | None = None  # 安装位置
    field_4: str | None = None  # 采集精度
    field_5: str | None = None  # 校准到期日
    field_6: str | None = None  # 责任人

class MaintEntry(BaseModel):
    """维保工单明细结构。"""

    field_0: str | None = None  # 工单编号
    field_1: str | None = None  # 关联设备
    field_2: str | None = None  # 故障现象
    field_3: str | None = None  # 紧急程度
    field_4: str | None = None  # 报修人
    field_5: str | None = None  # 受理班组
    field_6: str | None = None  # 期望完成时间

class AlarmEntry(BaseModel):
    """告警事件明细结构。"""

    field_0: str | None = None  # 告警编号
    field_1: str | None = None  # 告警类型
    field_2: str | None = None  # 告警等级
    field_3: str | None = None  # 触发设备
    field_4: str | None = None  # 触发时间
    field_5: str | None = None  # 处理状态
    field_6: str | None = None  # 处理人

class CustomerEntry(BaseModel):
    """客户档案明细结构。"""

    field_0: str | None = None  # 客户编码
    field_1: str | None = None  # 客户名称
    field_2: str | None = None  # 客户类型
    field_3: str | None = None  # 联系人
    field_4: str | None = None  # 联系电话
    field_5: str | None = None  # 结算方式
    field_6: str | None = None  # 合作状态

class BillingEntry(BaseModel):
    """计费单明细结构。"""

    field_0: str | None = None  # 计费单号
    field_1: str | None = None  # 客户名称
    field_2: str | None = None  # 计费周期
    field_3: str | None = None  # 运输里程
    field_4: str | None = None  # 计费金额
    field_5: str | None = None  # 计费规则
    field_6: str | None = None  # 结算状态

class ReportEntry(BaseModel):
    """报表任务明细结构。"""

    field_0: str | None = None  # 报表名称
    field_1: str | None = None  # 统计范围
    field_2: str | None = None  # 统计周期
    field_3: str | None = None  # 导出格式
    field_4: str | None = None  # 任务状态
    field_5: str | None = None  # 生成时间

class SettingEntry(BaseModel):
    """系统参数明细结构。"""

    field_0: str | None = None  # 参数编码
    field_1: str | None = None  # 参数名称
    field_2: str | None = None  # 参数值
    field_3: str | None = None  # 参数类型
    field_4: str | None = None  # 生效范围
    field_5: str | None = None  # 修改人
