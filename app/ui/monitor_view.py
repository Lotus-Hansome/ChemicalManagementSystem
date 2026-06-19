from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk


class ParameterMonitorView(ttk.Frame):
    def __init__(self, parent, store, app) -> None:
        super().__init__(parent)
        self.store = store
        self.app = app
        self.rows_by_id = {}
        self.summary_var = tk.StringVar()
        self.auto_refresh_var = tk.BooleanVar(value=True)
        self.interval_var = tk.IntVar(value=5)
        self.auto_job = None
        self.seen_alarm_events: set[tuple[str, str]] = set()
        self._build()
        self.bind("<Destroy>", self._on_destroy)
        self._schedule_auto_refresh()

    def _build(self) -> None:
        self.rowconfigure(1, weight=3)
        self.rowconfigure(2, weight=2)
        self.columnconfigure(0, weight=1)

        header = ttk.Frame(self, padding=(0, 0, 0, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="参数监控", style="Section.TLabel").grid(row=0, column=0, padx=(0, 18))
        ttk.Label(header, textvariable=self.summary_var, style="Hint.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(header, text="自动刷新", variable=self.auto_refresh_var, command=self._schedule_auto_refresh).grid(row=0, column=2, padx=(0, 8))
        ttk.Label(header, text="间隔").grid(row=0, column=3, padx=(0, 4))
        ttk.Spinbox(header, from_=3, to=60, textvariable=self.interval_var, width=4, command=self._schedule_auto_refresh).grid(row=0, column=4, padx=(0, 4))
        ttk.Label(header, text="秒").grid(row=0, column=5, padx=(0, 10))
        ttk.Button(header, text="立即采样", command=self.app.guarded(self.simulate_sampling)).grid(row=0, column=6, padx=(0, 8))
        self.ack_button = ttk.Button(header, text="确认报警", command=self.app.guarded(self.acknowledge_selected))
        self.ack_button.grid(row=0, column=7, padx=(0, 8))
        self.threshold_button = ttk.Button(header, text="修改阈值", command=self.app.guarded(self.edit_threshold))
        self.threshold_button.grid(row=0, column=8, padx=(0, 8))
        ttk.Button(header, text="生成工单", command=self.app.guarded(self.create_order_for_selected)).grid(row=0, column=9)

        table_frame = ttk.Frame(self)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = ("id", "name", "area", "value", "range", "status", "ack", "updated")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "id": "编号",
            "name": "参数",
            "area": "区域",
            "value": "当前值",
            "range": "阈值范围",
            "status": "状态",
            "ack": "确认状态",
            "updated": "更新时间",
        }
        widths = {
            "id": 80,
            "name": 140,
            "area": 110,
            "value": 110,
            "range": 140,
            "status": 90,
            "ack": 110,
            "updated": 150,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=tk.W)
        self.tree.tag_configure("alarm", background="#FCE8E6")
        self.tree.tag_configure("normal", background="#EAF6ED")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._draw_selected_trend())

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=y_scroll.set)

        lower = ttk.Frame(self, padding=(0, 10, 0, 0))
        lower.grid(row=2, column=0, sticky="nsew")
        lower.columnconfigure(0, weight=1)
        lower.columnconfigure(1, weight=1)
        lower.rowconfigure(0, weight=1)

        trend_box = ttk.LabelFrame(lower, text="实时趋势", padding=8)
        trend_box.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        trend_box.columnconfigure(0, weight=1)
        trend_box.rowconfigure(0, weight=1)
        self.trend_canvas = tk.Canvas(trend_box, height=180, background="#FFFFFF", highlightthickness=1, highlightbackground="#D9E1E8")
        self.trend_canvas.grid(row=0, column=0, sticky="nsew")

        history_box = ttk.LabelFrame(lower, text="报警历史", padding=8)
        history_box.grid(row=0, column=1, sticky="nsew")
        history_box.columnconfigure(0, weight=1)
        history_box.rowconfigure(0, weight=1)
        history_columns = ("time", "parameter", "value", "range", "ack")
        self.history_tree = ttk.Treeview(history_box, columns=history_columns, show="headings", height=6)
        history_headings = {"time": "时间", "parameter": "参数", "value": "报警值", "range": "阈值", "ack": "确认"}
        for column in history_columns:
            self.history_tree.heading(column, text=history_headings[column])
            self.history_tree.column(column, width=110, anchor=tk.W)
        self.history_tree.grid(row=0, column=0, sticky="nsew")
        history_scroll = ttk.Scrollbar(history_box, orient=tk.VERTICAL, command=self.history_tree.yview)
        history_scroll.grid(row=0, column=1, sticky="ns")
        self.history_tree.configure(yscrollcommand=history_scroll.set)

    def refresh(self) -> None:
        rows = self.store.get_parameters()
        self.rows_by_id = {item["id"]: item for item in rows}
        current_selection = self.tree.selection()[0] if self.tree.selection() else None
        self.tree.delete(*self.tree.get_children())
        for item in rows:
            ack_text = "已确认" if item.get("acknowledged") else "待确认" if item["status"] == "报警" else "-"
            tag = "alarm" if item["status"] == "报警" else "normal"
            self.tree.insert(
                "",
                tk.END,
                iid=item["id"],
                values=(
                    item["id"],
                    item["name"],
                    item["area"],
                    f"{item['value']}{item['unit']}",
                    f"{item['low']} ~ {item['high']}{item['unit']}",
                    item["status"],
                    ack_text,
                    item["updated_at"],
                ),
                tags=(tag,),
            )
        alarm_count = sum(1 for item in rows if item["status"] == "报警")
        self.summary_var.set(f"监控点位：{len(rows)}；当前报警：{alarm_count}；自动刷新：{'开启' if self.auto_refresh_var.get() else '关闭'}")
        if rows:
            selected = current_selection if current_selection in self.rows_by_id else next((item["id"] for item in rows if item["status"] == "报警"), rows[0]["id"])
            self.tree.selection_set(selected)
            self.tree.focus(selected)
        self._populate_alarm_history()
        self._draw_selected_trend()

    def apply_permissions(self) -> None:
        if self.app.has_permission("parameter_ack"):
            self.ack_button.grid()
        else:
            self.ack_button.grid_remove()
        if self.app.has_permission("parameter_config"):
            self.threshold_button.grid()
        else:
            self.threshold_button.grid_remove()

    def simulate_sampling(self) -> None:
        self._sample_and_refresh(show_popup=True)

    def acknowledge_selected(self) -> None:
        self.app.require_permission("parameter_ack")
        record = self._selected_record()
        if record is None:
            return
        self.store.acknowledge_alarm(record["id"], self.app.current_user.display_name)
        self.app.audit_action("确认报警", record["id"], f"{record['name']} 当前值：{record['value']}{record['unit']}")
        self.refresh()

    def edit_threshold(self) -> None:
        self.app.require_permission("parameter_config")
        record = self._selected_record()
        if record is None:
            return
        low = simpledialog.askfloat("修改阈值", f"{record['name']} 下限：", initialvalue=record["low"], parent=self)
        if low is None:
            return
        high = simpledialog.askfloat("修改阈值", f"{record['name']} 上限：", initialvalue=record["high"], parent=self)
        if high is None:
            return
        self.store.update_parameter_threshold(record["id"], low, high)
        self.app.audit_action("修改阈值", record["id"], f"{record['name']}：{record['low']}~{record['high']} 调整为 {low}~{high}")
        self.refresh()

    def create_order_for_selected(self) -> None:
        record = self._selected_record()
        if record is None:
            return
        if record["status"] != "报警":
            messagebox.showwarning("系统提示", "只有报警参数才能生成处理工单。", parent=self)
            return
        self.app.open_work_order_for_parameter(record)

    def _selected_record(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("系统提示", "请先选择一个监控参数。", parent=self)
            return None
        return self.rows_by_id.get(selection[0])

    def _sample_and_refresh(self, show_popup: bool) -> None:
        self.store.simulate_parameter_sampling()
        self.refresh()
        alarms = [item for item in self.rows_by_id.values() if item["status"] == "报警" and not item.get("acknowledged")]
        new_alarms = []
        for item in alarms:
            signature = (item["id"], item["updated_at"])
            if signature not in self.seen_alarm_events:
                self.seen_alarm_events.add(signature)
                new_alarms.append(item)
        if show_popup and new_alarms:
            text = "\n".join(f"{item['name']}：{item['value']}{item['unit']}，阈值 {item['low']}~{item['high']}{item['unit']}" for item in new_alarms[:5])
            messagebox.showwarning("参数报警", text, parent=self)

    def _schedule_auto_refresh(self) -> None:
        if self.auto_job is not None:
            self.after_cancel(self.auto_job)
            self.auto_job = None
        if self.auto_refresh_var.get():
            interval_ms = max(int(self.interval_var.get() or 5), 3) * 1000
            self.auto_job = self.after(interval_ms, self._auto_refresh_tick)
        self.refresh()

    def _auto_refresh_tick(self) -> None:
        self.auto_job = None
        if self.auto_refresh_var.get() and self.app.active_view == "monitor":
            self._sample_and_refresh(show_popup=True)
        if self.auto_refresh_var.get():
            self._schedule_auto_refresh()

    def _populate_alarm_history(self) -> None:
        self.history_tree.delete(*self.history_tree.get_children())
        for item in self.store.get_alarm_history(limit=30):
            ack_text = "已确认" if item.get("acknowledged") else "待确认"
            self.history_tree.insert(
                "",
                tk.END,
                values=(
                    item["occurred_at"],
                    item["parameter_name"],
                    f"{item['value']}{item['unit']}",
                    f"{item['low']}~{item['high']}{item['unit']}",
                    ack_text,
                ),
            )

    def _draw_selected_trend(self) -> None:
        self.trend_canvas.delete("all")
        record = self._selected_record_silent()
        if record is None:
            self.trend_canvas.create_text(20, 20, text="请选择参数查看趋势", anchor="nw", fill="#607080")
            return
        samples = self.store.get_parameter_samples(record["id"], limit=40)
        width = max(self.trend_canvas.winfo_width(), 360)
        height = max(self.trend_canvas.winfo_height(), 160)
        padding = 28
        self.trend_canvas.create_line(padding, height - padding, width - padding, height - padding, fill="#D9E1E8")
        self.trend_canvas.create_line(padding, padding, padding, height - padding, fill="#D9E1E8")
        self.trend_canvas.create_text(padding, 10, text=f"{record['name']} 最近趋势", anchor="nw", fill="#203040")
        if len(samples) < 2:
            self.trend_canvas.create_text(padding, height // 2, text="采样点不足，等待自动刷新或点击立即采样。", anchor="w", fill="#607080")
            return

        values = [float(item["value"]) for item in samples]
        low = min(values + [float(record["low"])])
        high = max(values + [float(record["high"])])
        span = max(high - low, 1.0)

        def xy(index: int, value: float) -> tuple[float, float]:
            x = padding + index * (width - padding * 2) / max(len(samples) - 1, 1)
            y = height - padding - (value - low) * (height - padding * 2) / span
            return x, y

        low_y = xy(0, float(record["low"]))[1]
        high_y = xy(0, float(record["high"]))[1]
        self.trend_canvas.create_line(padding, low_y, width - padding, low_y, fill="#9A6700", dash=(4, 3))
        self.trend_canvas.create_line(padding, high_y, width - padding, high_y, fill="#C62828", dash=(4, 3))

        points = []
        for index, item in enumerate(samples):
            points.extend(xy(index, float(item["value"])))
        self.trend_canvas.create_line(*points, fill="#1F6FEB", width=2, smooth=True)
        for index, item in enumerate(samples):
            x, y = xy(index, float(item["value"]))
            color = "#C62828" if item["status"] == "报警" else "#16794C"
            self.trend_canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=color, outline=color)

        self.trend_canvas.create_text(width - padding, high_y - 8, text="上限", anchor="e", fill="#C62828")
        self.trend_canvas.create_text(width - padding, low_y + 8, text="下限", anchor="e", fill="#9A6700")

    def _selected_record_silent(self):
        selection = self.tree.selection()
        if not selection:
            return None
        return self.rows_by_id.get(selection[0])

    def _on_destroy(self, event) -> None:
        if event.widget is self and self.auto_job is not None:
            self.after_cancel(self.auto_job)
            self.auto_job = None
