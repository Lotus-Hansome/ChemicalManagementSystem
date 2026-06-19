from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class DashboardView(ttk.Frame):
    def __init__(self, parent, store, app) -> None:
        super().__init__(parent)
        self.store = store
        self.app = app
        self.summary_vars = {
            "chemical_count": tk.StringVar(value="0"),
            "high_hazard_count": tk.StringVar(value="0"),
            "alarm_count": tk.StringVar(value="0"),
            "open_work_order_count": tk.StringVar(value="0"),
        }
        self.audit_notice_var = tk.StringVar()
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        header = ttk.Frame(self, padding=(0, 0, 0, 10))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="运行看板", style="Section.TLabel").grid(row=0, column=0, padx=(0, 18))
        ttk.Label(header, text="综合展示库存风险、报警、工单和操作审计。", style="Hint.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Button(header, text="刷新看板", command=self.app.guarded(self.refresh)).grid(row=0, column=2)

        cards = ttk.Frame(self, padding=(0, 0, 0, 12))
        cards.grid(row=1, column=0, sticky="ew")
        for index, (label, key) in enumerate(
            [
                ("化学品总数", "chemical_count"),
                ("高风险物料", "high_hazard_count"),
                ("当前报警", "alarm_count"),
                ("未关闭工单", "open_work_order_count"),
            ]
        ):
            card = ttk.LabelFrame(cards, text=label, padding=(16, 12))
            card.grid(row=0, column=index, sticky="ew", padx=(0, 10))
            ttk.Label(card, textvariable=self.summary_vars[key], font=("Microsoft YaHei UI", 22, "bold")).pack(anchor="w")
        cards.columnconfigure(tuple(range(4)), weight=1)

        body = ttk.Frame(self)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        body.rowconfigure(1, weight=1)

        self.alarm_tree = self._make_tree(
            body,
            "当前报警",
            ("id", "name", "area", "value", "range"),
            {"id": "编号", "name": "参数", "area": "区域", "value": "当前值", "range": "阈值"},
            0,
            0,
        )
        self.order_tree = self._make_tree(
            body,
            "未关闭工单",
            ("id", "title", "priority", "status", "due"),
            {"id": "编号", "title": "标题", "priority": "优先级", "status": "状态", "due": "截止日期"},
            0,
            1,
        )
        self.audit_tree = self._make_tree(
            body,
            "操作审计",
            ("time", "user", "role", "action", "target"),
            {"time": "时间", "user": "用户", "role": "角色", "action": "操作", "target": "对象"},
            1,
            0,
            columnspan=2,
        )
        ttk.Label(body, textvariable=self.audit_notice_var, style="Hint.TLabel").grid(row=2, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def refresh(self) -> None:
        summary = self.store.summary()
        for key, variable in self.summary_vars.items():
            variable.set(str(summary[key]))

        self._populate_alarms()
        self._populate_orders()
        self._populate_audit_logs()

    def apply_permissions(self) -> None:
        self._populate_audit_logs()

    def _make_tree(self, parent, title: str, columns, headings, row: int, column: int, columnspan: int = 1):
        frame = ttk.LabelFrame(parent, text=title, padding=8)
        frame.grid(row=row, column=column, columnspan=columnspan, sticky="nsew", padx=(0, 10), pady=(0, 10))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        tree = ttk.Treeview(frame, columns=columns, show="headings", height=6)
        for key in columns:
            tree.heading(key, text=headings[key])
            tree.column(key, width=120, anchor=tk.W)
        tree.grid(row=0, column=0, sticky="nsew")

        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=scroll.set)
        return tree

    def _populate_alarms(self) -> None:
        self.alarm_tree.delete(*self.alarm_tree.get_children())
        rows = [item for item in self.store.get_parameters() if item["status"] == "报警"]
        for item in rows:
            self.alarm_tree.insert(
                "",
                tk.END,
                values=(
                    item["id"],
                    item["name"],
                    item["area"],
                    f"{item['value']}{item['unit']}",
                    f"{item['low']}~{item['high']}{item['unit']}",
                ),
            )

    def _populate_orders(self) -> None:
        self.order_tree.delete(*self.order_tree.get_children())
        rows = [item for item in self.store.get_work_orders() if item["status"] not in {"已完成", "已关闭"}]
        for item in rows:
            self.order_tree.insert(
                "",
                tk.END,
                values=(item["id"], item["title"], item["priority"], item["status"], item["due_date"]),
            )

    def _populate_audit_logs(self) -> None:
        self.audit_tree.delete(*self.audit_tree.get_children())
        if not self.app.has_permission("audit_view"):
            self.audit_notice_var.set("普通操作员无权查看操作审计，仅管理员可见。")
            return

        self.audit_notice_var.set("审计日志记录关键管理操作，最多保留最近 200 条。")
        for item in self.store.get_audit_logs(limit=20):
            self.audit_tree.insert(
                "",
                tk.END,
                values=(item["time"], item["username"], item["role"], item["action"], item["target"]),
            )
