from __future__ import annotations

import random
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import DB_FILE, DATETIME_FORMAT
from app.database import connect, initialize_database
from app.exceptions import AppError
from app.seed_data import default_data

def _now() -> str:
    return datetime.now().strftime(DATETIME_FORMAT)

def _default_data() -> dict[str, Any]:
    return default_data()

def _is_all(value: str) -> bool:
    return value in {"", "全部", "鍏ㄩ儴"}

def _as_bool(value: Any) -> bool:
    return bool(int(value or 0))

def _row_to_dict(row) -> dict[str, Any]:
    item = dict(row)
    if "acknowledged" in item:
        item["acknowledged"] = _as_bool(item["acknowledged"])
    return item

class DataStore:
    def __init__(self, path: str | Path = DB_FILE) -> None:
        self.path = Path(path)
        self.load()

    def load(self) -> None:
        initialize_database(self.path)

    def save(self) -> None:
        return None

    def snapshot(self) -> dict[str, Any]:
        return {
            "chemicals": self.get_chemicals(),
            "parameters": self.get_parameters(),
            "work_orders": self.get_work_orders(),
            "audit_logs": self.get_audit_logs(),
            "alarm_history": self.get_alarm_history(),
        }

    def log_action(self, username: str, role: str, action: str, target: str, detail: str = "") -> dict[str, Any]:
        item = {
            "time": _now(),
            "username": username,
            "role": role,
            "action": action,
            "target": target,
            "detail": detail,
        }
        with connect(self.path) as conn:
            conn.execute(
                """
                INSERT INTO audit_logs(time, username, role, action, target, detail)
                VALUES (:time, :username, :role, :action, :target, :detail)
                """,
                item,
            )
            conn.execute(
                """
                DELETE FROM audit_logs
                WHERE id NOT IN (
                    SELECT id FROM audit_logs ORDER BY time DESC, id DESC LIMIT 200
                )
                """
            )
        return deepcopy(item)

    def get_audit_logs(self, limit: int = 50) -> list[dict[str, Any]]:
        with connect(self.path) as conn:
            rows = conn.execute(
                """
                SELECT time, username, role, action, target, detail
                FROM audit_logs
                ORDER BY time DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def categories(self) -> list[str]:
        with connect(self.path) as conn:
            rows = conn.execute("SELECT DISTINCT category FROM chemicals ORDER BY category").fetchall()
        return [row["category"] for row in rows]

    def hazard_levels(self) -> list[str]:
        order = {"低": 0, "中": 1, "高": 2, "极高": 3}
        with connect(self.path) as conn:
            rows = conn.execute("SELECT DISTINCT hazard_level FROM chemicals").fetchall()
        return sorted([row["hazard_level"] for row in rows], key=lambda level: order.get(level, 99))

    def get_chemicals(self) -> list[dict[str, Any]]:
        with connect(self.path) as conn:
            rows = conn.execute(
                """
                SELECT id, name, category, storage_area, inventory, unit, hazard_level, cas, supplier, updated_at
                FROM chemicals
                ORDER BY id
                """
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def search_chemicals(self, keyword: str = "", category: str = "全部", hazard_level: str = "全部") -> list[dict[str, Any]]:
        keyword = keyword.strip().lower()
        rows = self.get_chemicals()

        def matches(item: dict[str, Any]) -> bool:
            haystack = " ".join(str(item.get(key, "")) for key in ("id", "name", "category", "storage_area", "cas", "supplier")).lower()
            return (
                (not keyword or keyword in haystack)
                and (_is_all(category) or item["category"] == category)
                and (_is_all(hazard_level) or item["hazard_level"] == hazard_level)
            )

        return [deepcopy(item) for item in rows if matches(item)]

    def adjust_inventory(self, chemical_id: str, delta: float) -> dict[str, Any]:
        with connect(self.path) as conn:
            item = self._find(conn, "chemicals", chemical_id)
            before_value = float(item["inventory"])
            after_value = round(before_value + float(delta), 2)
            if after_value < 0:
                raise AppError("库存不能小于 0。")
            changed_at = _now()
            conn.execute(
                """
                UPDATE chemicals
                SET inventory = ?, updated_at = ?
                WHERE id = ?
                """,
                (after_value, changed_at, chemical_id),
            )
            conn.execute(
                """
                INSERT INTO inventory_history(chemical_id, changed_at, delta, before_value, after_value, note)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (chemical_id, changed_at, float(delta), before_value, after_value, "库存调整"),
            )
        return self._get_chemical(chemical_id)

    def get_inventory_history(self, chemical_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with connect(self.path) as conn:
            if chemical_id:
                rows = conn.execute(
                    """
                    SELECT h.changed_at, h.chemical_id, c.name, h.delta, h.before_value, h.after_value, h.note
                    FROM inventory_history h
                    JOIN chemicals c ON c.id = h.chemical_id
                    WHERE h.chemical_id = ?
                    ORDER BY h.changed_at DESC, h.id DESC
                    LIMIT ?
                    """,
                    (chemical_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT h.changed_at, h.chemical_id, c.name, h.delta, h.before_value, h.after_value, h.note
                    FROM inventory_history h
                    JOIN chemicals c ON c.id = h.chemical_id
                    ORDER BY h.changed_at DESC, h.id DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_parameters(self) -> list[dict[str, Any]]:
        with connect(self.path) as conn:
            rows = conn.execute(
                """
                SELECT id, name, area, value, unit, low, high, status, acknowledged, acknowledged_at, acknowledged_by, updated_at
                FROM parameters
                ORDER BY id
                """
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def simulate_parameter_sampling(self, rng: random.Random | None = None) -> list[dict[str, Any]]:
        rng = rng or random.Random()
        sampled_at = _now()
        with connect(self.path) as conn:
            rows = conn.execute(
                """
                SELECT id, name, area, value, unit, low, high
                FROM parameters
                ORDER BY id
                """
            ).fetchall()
            for row in rows:
                item = _row_to_dict(row)
                low = float(item["low"])
                high = float(item["high"])
                span = max(high - low, 1.0)
                value = float(item["value"]) + rng.uniform(-span * 0.06, span * 0.06)
                if rng.random() < 0.12:
                    value = rng.choice([
                        low - rng.uniform(span * 0.03, span * 0.15),
                        high + rng.uniform(span * 0.03, span * 0.15),
                    ])
                value = round(value, 2)
                status = self._status_for(value, low, high)
                conn.execute(
                    """
                    UPDATE parameters
                    SET value = ?, status = ?, acknowledged = 0, acknowledged_at = NULL, acknowledged_by = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (value, status, sampled_at, item["id"]),
                )
                conn.execute(
                    """
                    INSERT INTO parameter_samples(parameter_id, sampled_at, value, status)
                    VALUES (?, ?, ?, ?)
                    """,
                    (item["id"], sampled_at, value, status),
                )
                if status == "报警":
                    self._insert_alarm_history(conn, item, value, status, sampled_at)

            conn.execute(
                """
                DELETE FROM parameter_samples
                WHERE id NOT IN (
                    SELECT id FROM parameter_samples
                    ORDER BY sampled_at DESC, id DESC
                    LIMIT 1000
                )
                """
            )
        return self.get_parameters()

    def acknowledge_alarm(self, parameter_id: str, user_display_name: str) -> dict[str, Any]:
        acknowledged_at = _now()
        with connect(self.path) as conn:
            item = self._find(conn, "parameters", parameter_id)
            if item["status"] != "报警":
                raise AppError("该参数当前未处于报警状态，无需确认。")
            conn.execute(
                """
                UPDATE parameters
                SET acknowledged = 1, acknowledged_at = ?, acknowledged_by = ?
                WHERE id = ?
                """,
                (acknowledged_at, user_display_name, parameter_id),
            )
            conn.execute(
                """
                UPDATE alarm_history
                SET acknowledged = 1, acknowledged_at = ?, acknowledged_by = ?
                WHERE id = (
                    SELECT id FROM alarm_history
                    WHERE parameter_id = ? AND acknowledged = 0
                    ORDER BY occurred_at DESC, id DESC
                    LIMIT 1
                )
                """,
                (acknowledged_at, user_display_name, parameter_id),
            )
        return self._get_parameter(parameter_id)

    def update_parameter_threshold(self, parameter_id: str, low: float, high: float) -> dict[str, Any]:
        low = float(low)
        high = float(high)
        if low >= high:
            raise AppError("参数下限必须小于上限。")
        updated_at = _now()
        with connect(self.path) as conn:
            item = self._find(conn, "parameters", parameter_id)
            value = float(item["value"])
            status = self._status_for(value, low, high)
            conn.execute(
                """
                UPDATE parameters
                SET low = ?, high = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (round(low, 2), round(high, 2), status, updated_at, parameter_id),
            )
            if status == "报警":
                alarm_item = dict(item)
                alarm_item["low"] = low
                alarm_item["high"] = high
                self._insert_alarm_history(conn, alarm_item, value, status, updated_at)
        return self._get_parameter(parameter_id)

    def get_parameter_samples(self, parameter_id: str, limit: int = 40) -> list[dict[str, Any]]:
        with connect(self.path) as conn:
            rows = conn.execute(
                """
                SELECT sampled_at, value, status
                FROM (
                    SELECT sampled_at, value, status
                    FROM parameter_samples
                    WHERE parameter_id = ?
                    ORDER BY sampled_at DESC, id DESC
                    LIMIT ?
                )
                ORDER BY sampled_at ASC
                """,
                (parameter_id, limit),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_alarm_history(self, limit: int = 50) -> list[dict[str, Any]]:
        with connect(self.path) as conn:
            rows = conn.execute(
                """
                SELECT parameter_id, parameter_name, area, value, unit, low, high, status,
                       occurred_at, acknowledged, acknowledged_at, acknowledged_by
                FROM alarm_history
                ORDER BY occurred_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_work_orders(self) -> list[dict[str, Any]]:
        with connect(self.path) as conn:
            rows = conn.execute(
                """
                SELECT id, title, area, priority, status, owner, created_at, due_date, description
                FROM work_orders
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def filter_work_orders(self, keyword: str = "", status: str = "全部", priority: str = "全部") -> list[dict[str, Any]]:
        keyword = keyword.strip().lower()
        rows = self.get_work_orders()

        def matches(item: dict[str, Any]) -> bool:
            haystack = " ".join(str(item.get(key, "")) for key in ("id", "title", "area", "owner", "description")).lower()
            return (
                (not keyword or keyword in haystack)
                and (_is_all(status) or item["status"] == status)
                and (_is_all(priority) or item["priority"] == priority)
            )

        return [deepcopy(item) for item in rows if matches(item)]

    def add_work_order(self, payload: dict[str, Any], owner: str) -> dict[str, Any]:
        title = payload.get("title", "").strip()
        if not title:
            raise AppError("工单标题不能为空。")
        item = {
            "id": self._next_work_order_id(),
            "title": title,
            "area": payload.get("area", "A车间"),
            "priority": payload.get("priority", "中"),
            "status": payload.get("status", "待处理"),
            "owner": owner,
            "created_at": _now(),
            "due_date": payload.get("due_date", ""),
            "description": payload.get("description", "").strip(),
        }
        with connect(self.path) as conn:
            conn.execute(
                """
                INSERT INTO work_orders(id, title, area, priority, status, owner, created_at, due_date, description)
                VALUES (:id, :title, :area, :priority, :status, :owner, :created_at, :due_date, :description)
                """,
                item,
            )
        return deepcopy(item)

    def update_work_order(self, order_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        allowed_fields = {"title", "area", "priority", "status", "due_date", "description"}
        with connect(self.path) as conn:
            item = self._find(conn, "work_orders", order_id)
            updated = dict(item)
            for key in allowed_fields:
                if key in payload:
                    updated[key] = payload[key]
            if not str(updated.get("title", "")).strip():
                raise AppError("工单标题不能为空。")
            conn.execute(
                """
                UPDATE work_orders
                SET title = ?, area = ?, priority = ?, status = ?, due_date = ?, description = ?
                WHERE id = ?
                """,
                (
                    updated["title"],
                    updated["area"],
                    updated["priority"],
                    updated["status"],
                    updated["due_date"],
                    updated["description"],
                    order_id,
                ),
            )
        return self._get_work_order(order_id)

    def advance_work_order(self, order_id: str, allow_close: bool = False) -> dict[str, Any]:
        with connect(self.path) as conn:
            item = self._find(conn, "work_orders", order_id)
            flow = {
                "待处理": "处理中",
                "处理中": "已完成",
                "已完成": "已关闭" if allow_close else "已完成",
                "已关闭": "已关闭",
            }
            if item["status"] == "已完成" and not allow_close:
                raise AppError("普通操作员不能关闭已完成工单。")
            next_status = flow.get(item["status"], "待处理")
            conn.execute("UPDATE work_orders SET status = ? WHERE id = ?", (next_status, order_id))
        return self._get_work_order(order_id)

    def delete_work_order(self, order_id: str) -> None:
        with connect(self.path) as conn:
            cursor = conn.execute("DELETE FROM work_orders WHERE id = ?", (order_id,))
            if cursor.rowcount == 0:
                raise AppError("未找到要删除的工单。")

    def summary(self) -> dict[str, Any]:
        with connect(self.path) as conn:
            chemical_count = conn.execute("SELECT COUNT(*) FROM chemicals").fetchone()[0]
            high_hazard_count = conn.execute(
                "SELECT COUNT(*) FROM chemicals WHERE hazard_level IN ('高', '极高')"
            ).fetchone()[0]
            parameter_count = conn.execute("SELECT COUNT(*) FROM parameters").fetchone()[0]
            alarm_count = conn.execute("SELECT COUNT(*) FROM parameters WHERE status = '报警'").fetchone()[0]
            open_work_order_count = conn.execute(
                "SELECT COUNT(*) FROM work_orders WHERE status NOT IN ('已完成', '已关闭')"
            ).fetchone()[0]
            closed_work_order_count = conn.execute(
                "SELECT COUNT(*) FROM work_orders WHERE status IN ('已完成', '已关闭')"
            ).fetchone()[0]
        return {
            "chemical_count": chemical_count,
            "high_hazard_count": high_hazard_count,
            "parameter_count": parameter_count,
            "alarm_count": alarm_count,
            "open_work_order_count": open_work_order_count,
            "closed_work_order_count": closed_work_order_count,
        }

    def _get_chemical(self, chemical_id: str) -> dict[str, Any]:
        with connect(self.path) as conn:
            return _row_to_dict(self._find(conn, "chemicals", chemical_id))

    def _get_parameter(self, parameter_id: str) -> dict[str, Any]:
        with connect(self.path) as conn:
            return _row_to_dict(self._find(conn, "parameters", parameter_id))

    def _get_work_order(self, order_id: str) -> dict[str, Any]:
        with connect(self.path) as conn:
            return _row_to_dict(self._find(conn, "work_orders", order_id))

    def _find(self, conn, collection: str, item_id: str):
        row = conn.execute(f"SELECT * FROM {collection} WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise AppError(f"未找到编号为 {item_id} 的记录。")
        return row

    def _next_work_order_id(self) -> str:
        prefix = "WO" + datetime.now().strftime("%Y%m%d")
        with connect(self.path) as conn:
            rows = conn.execute("SELECT id FROM work_orders WHERE id LIKE ?", (prefix + "%",)).fetchall()
        numbers = [int(row["id"].removeprefix(prefix)) for row in rows if row["id"].removeprefix(prefix).isdigit()]
        return f"{prefix}{max(numbers, default=0) + 1:03d}"

    @staticmethod
    def _status_for(value: float, low: float, high: float) -> str:
        return "报警" if value < low or value > high else "正常"

    @staticmethod
    def _insert_alarm_history(conn, item: dict[str, Any], value: float, status: str, occurred_at: str) -> None:
        conn.execute(
            """
            INSERT INTO alarm_history(parameter_id, parameter_name, area, value, unit, low, high, status, occurred_at, acknowledged)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                item["id"],
                item["name"],
                item["area"],
                value,
                item["unit"],
                item["low"],
                item["high"],
                status,
                occurred_at,
            ),
        )
