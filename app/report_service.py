from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import REPORT_DIR

REPORT_TYPES = {
    "summary": "综合简报",
    "inventory": "化学品库存",
    "parameters": "参数监控",
    "work_orders": "工单台账",
}

class ReportService:
    def __init__(self, store, output_dir: str | Path = REPORT_DIR) -> None:
        self.store = store
        self.output_dir = Path(output_dir)

    def build_preview(self, report_type: str) -> str:
        if report_type == "inventory":
            rows = self.store.get_chemicals()
            return self._format_inventory(rows)
        if report_type == "parameters":
            rows = self.store.get_parameters()
            return self._format_parameters(rows)
        if report_type == "work_orders":
            rows = self.store.get_work_orders()
            return self._format_work_orders(rows)
        return self._format_summary()

    def export(self, report_type: str) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        label = REPORT_TYPES.get(report_type, "report")
        path = self.output_dir / f"{label}_{timestamp}.csv"

        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.writer(file)
            if report_type == "inventory":
                self._write_inventory(writer)
            elif report_type == "parameters":
                self._write_parameters(writer)
            elif report_type == "work_orders":
                self._write_work_orders(writer)
            else:
                self._write_summary(writer)
        return path

    def _write_inventory(self, writer: csv.writer) -> None:
        writer.writerow(["编号", "名称", "类别", "库位", "库存", "单位", "危险等级", "CAS", "供应商", "更新时间"])
        for item in self.store.get_chemicals():
            writer.writerow([
                item["id"],
                item["name"],
                item["category"],
                item["storage_area"],
                item["inventory"],
                item["unit"],
                item["hazard_level"],
                item["cas"],
                item["supplier"],
                item["updated_at"],
            ])

    def _write_parameters(self, writer: csv.writer) -> None:
        writer.writerow(["编号", "参数", "区域", "当前值", "单位", "下限", "上限", "状态", "确认状态", "更新时间"])
        for item in self.store.get_parameters():
            writer.writerow([
                item["id"],
                item["name"],
                item["area"],
                item["value"],
                item["unit"],
                item["low"],
                item["high"],
                item["status"],
                "已确认" if item.get("acknowledged") else "待确认" if item["status"] == "报警" else "-",
                item["updated_at"],
            ])

    def _write_work_orders(self, writer: csv.writer) -> None:
        writer.writerow(["编号", "标题", "区域", "优先级", "状态", "负责人", "创建时间", "截止日期", "描述"])
        for item in self.store.get_work_orders():
            writer.writerow([
                item["id"],
                item["title"],
                item["area"],
                item["priority"],
                item["status"],
                item["owner"],
                item["created_at"],
                item["due_date"],
                item["description"],
            ])

    def _write_summary(self, writer: csv.writer) -> None:
        summary = self.store.summary()
        writer.writerow(["模块", "指标", "数值"])
        writer.writerow(["数据查询", "化学品总数", summary["chemical_count"]])
        writer.writerow(["数据查询", "高风险物料", summary["high_hazard_count"]])
        writer.writerow(["参数监控", "监控点位", summary["parameter_count"]])
        writer.writerow(["参数监控", "报警点位", summary["alarm_count"]])
        writer.writerow(["工单管理", "未关闭工单", summary["open_work_order_count"]])
        writer.writerow(["工单管理", "已完成/关闭工单", summary["closed_work_order_count"]])
        writer.writerow([])
        self._write_inventory(writer)
        writer.writerow([])
        self._write_parameters(writer)
        writer.writerow([])
        self._write_work_orders(writer)

    def _format_summary(self) -> str:
        summary = self.store.summary()
        return "\n".join(
            [
                "综合运行简报",
                "",
                f"化学品总数：{summary['chemical_count']}",
                f"高风险物料：{summary['high_hazard_count']}",
                f"监控点位：{summary['parameter_count']}",
                f"当前报警：{summary['alarm_count']}",
                f"未关闭工单：{summary['open_work_order_count']}",
                f"已完成/关闭工单：{summary['closed_work_order_count']}",
            ]
        )

    @staticmethod
    def _format_inventory(rows: list[dict[str, Any]]) -> str:
        lines = ["化学品库存报表", "", "编号 | 名称 | 类别 | 库位 | 库存 | 危险等级"]
        lines.extend(
            f"{item['id']} | {item['name']} | {item['category']} | {item['storage_area']} | {item['inventory']}{item['unit']} | {item['hazard_level']}"
            for item in rows
        )
        return "\n".join(lines)

    @staticmethod
    def _format_parameters(rows: list[dict[str, Any]]) -> str:
        lines = ["参数监控报表", "", "编号 | 参数 | 区域 | 当前值 | 阈值范围 | 状态"]
        lines.extend(
            f"{item['id']} | {item['name']} | {item['area']} | {item['value']}{item['unit']} | {item['low']}~{item['high']} | {item['status']}"
            for item in rows
        )
        return "\n".join(lines)

    @staticmethod
    def _format_work_orders(rows: list[dict[str, Any]]) -> str:
        lines = ["工单台账报表", "", "编号 | 标题 | 区域 | 优先级 | 状态 | 负责人 | 截止日期"]
        lines.extend(
            f"{item['id']} | {item['title']} | {item['area']} | {item['priority']} | {item['status']} | {item['owner']} | {item['due_date']}"
            for item in rows
        )
        return "\n".join(lines)
