from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

from app.config import DATE_FORMAT

AREAS = ["A车间", "A-01 原料罐区", "A-02 溶剂库", "B-01 危化品库", "B-03 固体库", "C罐区", "D环保站", "E动力站"]
PRIORITIES = ["低", "中", "高"]
STATUSES = ["待处理", "处理中", "已完成", "已关闭"]

class WorkOrderView(ttk.Frame):
    def __init__(self, parent, store, app) -> None:
        super().__init__(parent)
        self.store = store
        self.app = app
        self.keyword_var = tk.StringVar()
        self.status_var = tk.StringVar(value="全部")
        self.priority_var = tk.StringVar(value="全部")
        self.rows_by_id = {}
        self._build()

    def _build(self) -> None:
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        header = ttk.Frame(self, padding=(0, 0, 0, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(7, weight=1)
        ttk.Label(header, text="工单管理", style="Section.TLabel").grid(row=0, column=0, padx=(0, 18))
        ttk.Label(header, text="关键字").grid(row=0, column=1, padx=(0, 6))
        ttk.Entry(header, textvariable=self.keyword_var, width=18).grid(row=0, column=2, padx=(0, 10))
        ttk.Label(header, text="状态").grid(row=0, column=3, padx=(0, 6))
        ttk.Combobox(header, textvariable=self.status_var, values=["全部", *STATUSES], state="readonly", width=10).grid(row=0, column=4, padx=(0, 10))
        ttk.Label(header, text="优先级").grid(row=0, column=5, padx=(0, 6))
        ttk.Combobox(header, textvariable=self.priority_var, values=["全部", *PRIORITIES], state="readonly", width=8).grid(row=0, column=6, padx=(0, 10))
        ttk.Button(header, text="筛选", command=self.app.guarded(self.refresh)).grid(row=0, column=8, padx=(0, 8))
        ttk.Button(header, text="重置", command=self.app.guarded(self._reset)).grid(row=0, column=9)

        table_frame = ttk.Frame(self)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = ("id", "title", "area", "priority", "status", "owner", "created", "due")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "id": "编号",
            "title": "标题",
            "area": "区域",
            "priority": "优先级",
            "status": "状态",
            "owner": "负责人",
            "created": "创建时间",
            "due": "截止日期",
        }
        widths = {
            "id": 130,
            "title": 230,
            "area": 130,
            "priority": 70,
            "status": 85,
            "owner": 100,
            "created": 150,
            "due": 100,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=tk.W)
        self.tree.tag_configure("high", background="#FCE8E6")
        self.tree.tag_configure("done", background="#EAF6ED")
        self.tree.grid(row=0, column=0, sticky="nsew")

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=y_scroll.set)

        actions = ttk.Frame(self, padding=(0, 10, 0, 0))
        actions.grid(row=2, column=0, sticky="e")
        self.new_button = ttk.Button(actions, text="新建", command=self.app.guarded(self.create_order))
        self.new_button.pack(side=tk.LEFT, padx=(0, 8))
        self.edit_button = ttk.Button(actions, text="编辑", command=self.app.guarded(self.edit_selected))
        self.edit_button.pack(side=tk.LEFT, padx=(0, 8))
        self.advance_button = ttk.Button(actions, text="状态流转", command=self.app.guarded(self.advance_selected))
        self.advance_button.pack(side=tk.LEFT, padx=(0, 8))
        self.delete_button = ttk.Button(actions, text="删除", command=self.app.guarded(self.delete_selected))
        self.delete_button.pack(side=tk.LEFT)

    def refresh(self) -> None:
        rows = self.store.filter_work_orders(self.keyword_var.get(), self.status_var.get(), self.priority_var.get())
        self.rows_by_id = {item["id"]: item for item in rows}
        self.tree.delete(*self.tree.get_children())
        for item in rows:
            tag = "done" if item["status"] in {"已完成", "已关闭"} else "high" if item["priority"] == "高" else ""
            self.tree.insert(
                "",
                tk.END,
                iid=item["id"],
                values=(
                    item["id"],
                    item["title"],
                    item["area"],
                    item["priority"],
                    item["status"],
                    item["owner"],
                    item["created_at"],
                    item["due_date"],
                ),
                tags=(tag,) if tag else (),
            )
        if rows:
            self.tree.selection_set(rows[0]["id"])
            self.tree.focus(rows[0]["id"])

    def apply_permissions(self) -> None:
        self.new_button.configure(state=tk.NORMAL if self.app.has_permission("workorder_create") else tk.DISABLED)
        self.edit_button.configure(state=tk.NORMAL if self.app.has_permission("workorder_update") else tk.DISABLED)
        self.advance_button.configure(state=tk.NORMAL if self.app.has_permission("workorder_update") else tk.DISABLED)
        if self.app.has_permission("workorder_delete"):
            if not self.delete_button.winfo_manager():
                self.delete_button.pack(side=tk.LEFT)
        else:
            self.delete_button.pack_forget()

    def create_order(self, prefill: dict | None = None) -> None:
        self.app.require_permission("workorder_create")
        payload = WorkOrderDialog.ask(self, "新建工单", data=prefill, allow_closed=self.app.has_permission("workorder_close"))
        if payload is None:
            return
        created = self.store.add_work_order(payload, owner=self.app.current_user.display_name)
        self.app.audit_action("新建工单", created["id"], created["title"])
        self.refresh()

    def create_from_alarm(self, parameter: dict) -> None:
        prefill = {
            "title": f"{parameter['name']}报警处理",
            "area": parameter["area"],
            "priority": "高",
            "status": "待处理",
            "due_date": (datetime.now() + timedelta(days=1)).strftime(DATE_FORMAT),
            "description": f"{parameter['name']}当前值 {parameter['value']}{parameter['unit']}，超出阈值 {parameter['low']}~{parameter['high']}{parameter['unit']}，请现场复核并处理。",
        }
        self.create_order(prefill)

    def edit_selected(self) -> None:
        self.app.require_permission("workorder_update")
        record = self._selected_record()
        if record is None:
            return
        payload = WorkOrderDialog.ask(self, "编辑工单", data=record, allow_closed=self.app.has_permission("workorder_close"))
        if payload is None:
            return
        if payload.get("status") == "已关闭":
            self.app.require_permission("workorder_close")
        updated = self.store.update_work_order(record["id"], payload)
        self.app.audit_action("编辑工单", updated["id"], updated["title"])
        self.refresh()

    def advance_selected(self) -> None:
        self.app.require_permission("workorder_update")
        record = self._selected_record()
        if record is None:
            return
        updated = self.store.advance_work_order(record["id"], allow_close=self.app.has_permission("workorder_close"))
        self.app.audit_action("状态流转", updated["id"], f"{record['status']} -> {updated['status']}")
        self.refresh()

    def delete_selected(self) -> None:
        self.app.require_permission("workorder_delete")
        record = self._selected_record()
        if record is None:
            return
        if not messagebox.askyesno("删除确认", f"确定删除工单 {record['id']}？", parent=self):
            return
        self.store.delete_work_order(record["id"])
        self.app.audit_action("删除工单", record["id"], record["title"])
        self.refresh()

    def _reset(self) -> None:
        self.keyword_var.set("")
        self.status_var.set("全部")
        self.priority_var.set("全部")
        self.refresh()

    def _selected_record(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("系统提示", "请先选择一条工单。", parent=self)
            return None
        return self.rows_by_id.get(selection[0])


class WorkOrderDialog(tk.Toplevel):
    def __init__(self, parent, title: str, data: dict | None = None, allow_closed: bool = False) -> None:
        super().__init__(parent)
        self.result = None
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        data = data or {}
        default_due = (datetime.now() + timedelta(days=3)).strftime(DATE_FORMAT)
        allowed_statuses = STATUSES if allow_closed else [status for status in STATUSES if status != "已关闭"]

        self.title_var = tk.StringVar(value=data.get("title", ""))
        self.area_var = tk.StringVar(value=data.get("area", AREAS[0]))
        self.priority_var = tk.StringVar(value=data.get("priority", "中"))
        self.status_var = tk.StringVar(value=data.get("status", "待处理"))
        self.due_var = tk.StringVar(value=data.get("due_date", default_due))
        self.allowed_statuses = allowed_statuses

        self._build(data.get("description", ""))
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _event: self._cancel())
        self.update_idletasks()
        x = parent.winfo_rootx() + max(parent.winfo_width() // 2 - self.winfo_width() // 2, 20)
        y = parent.winfo_rooty() + max(parent.winfo_height() // 2 - self.winfo_height() // 2, 20)
        self.geometry(f"+{x}+{y}")

    @classmethod
    def ask(cls, parent, title: str, data: dict | None = None, allow_closed: bool = False):
        dialog = cls(parent, title, data, allow_closed)
        parent.wait_window(dialog)
        return dialog.result

    def _build(self, description: str) -> None:
        frame = ttk.Frame(self, padding=18)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        fields = [
            ("标题", ttk.Entry(frame, textvariable=self.title_var, width=46)),
            ("区域", ttk.Combobox(frame, textvariable=self.area_var, values=AREAS, state="readonly", width=44)),
            ("优先级", ttk.Combobox(frame, textvariable=self.priority_var, values=PRIORITIES, state="readonly", width=44)),
            ("状态", ttk.Combobox(frame, textvariable=self.status_var, values=self.allowed_statuses, state="readonly", width=44)),
            ("截止日期", ttk.Entry(frame, textvariable=self.due_var, width=46)),
        ]
        for row, (label, widget) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)
            widget.grid(row=row, column=1, sticky="ew", pady=6)

        ttk.Label(frame, text="描述").grid(row=5, column=0, sticky="nw", padx=(0, 12), pady=6)
        self.description_text = tk.Text(frame, width=46, height=7, wrap=tk.WORD)
        self.description_text.grid(row=5, column=1, sticky="ew", pady=6)
        self.description_text.insert("1.0", description)

        buttons = ttk.Frame(frame)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="取消", command=self._cancel).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="确定", command=self._ok).pack(side=tk.LEFT)

    def _ok(self) -> None:
        title = self.title_var.get().strip()
        if not title:
            messagebox.showwarning("系统提示", "工单标题不能为空。", parent=self)
            return
        due_date = self.due_var.get().strip()
        if due_date:
            try:
                datetime.strptime(due_date, DATE_FORMAT)
            except ValueError:
                messagebox.showwarning("系统提示", "截止日期格式应为 YYYY-MM-DD。", parent=self)
                return
        self.result = {
            "title": title,
            "area": self.area_var.get(),
            "priority": self.priority_var.get(),
            "status": self.status_var.get(),
            "due_date": due_date,
            "description": self.description_text.get("1.0", tk.END).strip(),
        }
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()
