from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from app.report_service import REPORT_TYPES, ReportService


class ReportView(ttk.Frame):
    def __init__(self, parent, store, app) -> None:
        super().__init__(parent)
        self.store = store
        self.app = app
        self.service = ReportService(store)
        self.report_label_var = tk.StringVar(value=REPORT_TYPES["summary"])
        self.summary_vars = {
            "chemical_count": tk.StringVar(value="0"),
            "alarm_count": tk.StringVar(value="0"),
            "open_work_order_count": tk.StringVar(value="0"),
            "high_hazard_count": tk.StringVar(value="0"),
        }
        self._build()

    def _build(self) -> None:
        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)

        header = ttk.Frame(self, padding=(0, 0, 0, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(4, weight=1)
        ttk.Label(header, text="报表导出", style="Section.TLabel").grid(row=0, column=0, padx=(0, 18))
        ttk.Label(header, text="报表类型").grid(row=0, column=1, padx=(0, 6))
        self.type_combo = ttk.Combobox(header, textvariable=self.report_label_var, values=list(REPORT_TYPES.values()), state="readonly", width=16)
        self.type_combo.grid(row=0, column=2, padx=(0, 10))
        ttk.Button(header, text="生成预览", command=self.app.guarded(self.generate_preview)).grid(row=0, column=3, padx=(0, 8))
        self.export_button = ttk.Button(header, text="导出CSV", command=self.app.guarded(self.export_selected))
        self.export_button.grid(row=0, column=4, sticky="w")

        summary = ttk.Frame(self, padding=(0, 4, 0, 12))
        summary.grid(row=1, column=0, sticky="ew")
        cards = [
            ("化学品", "chemical_count"),
            ("高风险物料", "high_hazard_count"),
            ("当前报警", "alarm_count"),
            ("未关闭工单", "open_work_order_count"),
        ]
        for index, (label, key) in enumerate(cards):
            box = ttk.LabelFrame(summary, text=label, padding=(14, 10))
            box.grid(row=0, column=index, sticky="ew", padx=(0, 10))
            ttk.Label(box, textvariable=self.summary_vars[key], font=("Microsoft YaHei UI", 18, "bold")).pack(anchor="w")
        summary.columnconfigure(tuple(range(len(cards))), weight=1)

        self.preview = scrolledtext.ScrolledText(self, wrap=tk.WORD, height=18, font=("Consolas", 10))
        self.preview.grid(row=2, column=0, sticky="nsew")
        self.preview.configure(state=tk.DISABLED)

    def refresh(self) -> None:
        summary = self.store.summary()
        for key, variable in self.summary_vars.items():
            variable.set(str(summary[key]))
        if not self.preview.get("1.0", tk.END).strip():
            self.generate_preview()

    def apply_permissions(self) -> None:
        if self.app.has_permission("report_export"):
            self.export_button.grid()
        else:
            self.export_button.grid_remove()

    def generate_preview(self) -> None:
        text = self.service.build_preview(self._selected_key())
        self.preview.configure(state=tk.NORMAL)
        self.preview.delete("1.0", tk.END)
        self.preview.insert("1.0", text)
        self.preview.configure(state=tk.DISABLED)

    def export_selected(self) -> None:
        self.app.require_permission("report_export")
        path = self.service.export(self._selected_key())
        self.app.audit_action("导出报表", self._selected_key(), str(path))
        messagebox.showinfo("导出成功", f"报表已导出：\n{path}", parent=self)

    def _selected_key(self) -> str:
        label = self.report_label_var.get()
        for key, value in REPORT_TYPES.items():
            if value == label:
                return key
        return "summary"
