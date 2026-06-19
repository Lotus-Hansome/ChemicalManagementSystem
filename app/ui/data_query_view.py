from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk


class DataQueryView(ttk.Frame):
    def __init__(self, parent, store, app) -> None:
        super().__init__(parent)
        self.store = store
        self.app = app
        self.keyword_var = tk.StringVar()
        self.category_var = tk.StringVar(value="全部")
        self.hazard_var = tk.StringVar(value="全部")
        self.detail_vars = {
            "name": tk.StringVar(value="-"),
            "cas": tk.StringVar(value="-"),
            "supplier": tk.StringVar(value="-"),
            "inventory": tk.StringVar(value="-"),
            "updated": tk.StringVar(value="-"),
        }
        self.rows_by_id = {}
        self._build()

    def _build(self) -> None:
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        header = ttk.Frame(self, padding=(0, 0, 0, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(7, weight=1)

        ttk.Label(header, text="数据查询", style="Section.TLabel").grid(row=0, column=0, padx=(0, 16))
        ttk.Label(header, text="关键字").grid(row=0, column=1, padx=(0, 6))
        ttk.Entry(header, textvariable=self.keyword_var, width=20).grid(row=0, column=2, padx=(0, 12))
        ttk.Label(header, text="类别").grid(row=0, column=3, padx=(0, 6))
        self.category_combo = ttk.Combobox(header, textvariable=self.category_var, state="readonly", width=16)
        self.category_combo.grid(row=0, column=4, padx=(0, 12))
        ttk.Label(header, text="危险等级").grid(row=0, column=5, padx=(0, 6))
        self.hazard_combo = ttk.Combobox(header, textvariable=self.hazard_var, state="readonly", width=10)
        self.hazard_combo.grid(row=0, column=6, padx=(0, 12))
        ttk.Button(header, text="搜索", command=self.app.guarded(self.refresh)).grid(row=0, column=8, padx=(0, 8))
        ttk.Button(header, text="重置", command=self.app.guarded(self._reset)).grid(row=0, column=9)

        table_frame = ttk.Frame(self)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        columns = ("id", "name", "category", "area", "inventory", "unit", "hazard", "supplier", "updated")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "id": "编号",
            "name": "名称",
            "category": "类别",
            "area": "库位",
            "inventory": "库存",
            "unit": "单位",
            "hazard": "危险等级",
            "supplier": "供应商",
            "updated": "更新时间",
        }
        widths = {
            "id": 70,
            "name": 90,
            "category": 110,
            "area": 150,
            "inventory": 80,
            "unit": 60,
            "hazard": 85,
            "supplier": 150,
            "updated": 145,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], anchor=tk.W)
        self.tree.tag_configure("danger", background="#FCE8E6")
        self.tree.tag_configure("warning", background="#FFF4CE")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        y_scroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=self.tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=y_scroll.set)

        bottom = ttk.Frame(self, padding=(0, 10, 0, 0))
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)

        detail = ttk.LabelFrame(bottom, text="选中物料信息", padding=10)
        detail.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        for index, (label, key) in enumerate(
            [
                ("名称", "name"),
                ("CAS", "cas"),
                ("供应商", "supplier"),
                ("库存", "inventory"),
                ("更新时间", "updated"),
            ]
        ):
            ttk.Label(detail, text=f"{label}：").grid(row=0, column=index * 2, sticky="w", padx=(0, 4))
            ttk.Label(detail, textvariable=self.detail_vars[key]).grid(row=0, column=index * 2 + 1, sticky="w", padx=(0, 18))

        actions = ttk.Frame(bottom)
        actions.grid(row=0, column=1, sticky="e")
        self.in_button = ttk.Button(actions, text="入库", command=self.app.guarded(lambda: self._adjust_inventory(1)))
        self.in_button.pack(side=tk.LEFT, padx=(0, 8))
        self.out_button = ttk.Button(actions, text="出库", command=self.app.guarded(lambda: self._adjust_inventory(-1)))
        self.out_button.pack(side=tk.LEFT)

    def refresh(self) -> None:
        self.category_combo.configure(values=["全部", *self.store.categories()])
        self.hazard_combo.configure(values=["全部", *self.store.hazard_levels()])
        rows = self.store.search_chemicals(self.keyword_var.get(), self.category_var.get(), self.hazard_var.get())
        self._populate(rows)

    def apply_permissions(self) -> None:
        if self.app.has_permission("chemical_manage"):
            if not self.in_button.winfo_manager():
                self.in_button.pack(side=tk.LEFT, padx=(0, 8))
            if not self.out_button.winfo_manager():
                self.out_button.pack(side=tk.LEFT)
        else:
            self.in_button.pack_forget()
            self.out_button.pack_forget()

    def _populate(self, rows) -> None:
        self.tree.delete(*self.tree.get_children())
        self.rows_by_id = {item["id"]: item for item in rows}
        for item in rows:
            tag = "danger" if item["hazard_level"] in {"高", "极高"} else "warning" if item["hazard_level"] == "中" else ""
            self.tree.insert(
                "",
                tk.END,
                iid=item["id"],
                values=(
                    item["id"],
                    item["name"],
                    item["category"],
                    item["storage_area"],
                    item["inventory"],
                    item["unit"],
                    item["hazard_level"],
                    item["supplier"],
                    item["updated_at"],
                ),
                tags=(tag,) if tag else (),
            )
        if rows:
            self.tree.selection_set(rows[0]["id"])
            self.tree.focus(rows[0]["id"])
            self._show_detail(rows[0])
        else:
            self._clear_detail()

    def _reset(self) -> None:
        self.keyword_var.set("")
        self.category_var.set("全部")
        self.hazard_var.set("全部")
        self.refresh()

    def _selected_record(self):
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning("系统提示", "请先选择一条化学品记录。", parent=self)
            return None
        return self.rows_by_id.get(selection[0])

    def _adjust_inventory(self, direction: int) -> None:
        self.app.require_permission("chemical_manage")
        record = self._selected_record()
        if record is None:
            return
        action = "入库" if direction > 0 else "出库"
        amount = simpledialog.askfloat(action, f"请输入{record['name']}的{action}数量：", minvalue=0.01, parent=self)
        if amount is None:
            return
        updated = self.store.adjust_inventory(record["id"], amount * direction)
        self.app.audit_action(action, record["id"], f"{record['name']} 数量：{amount}，当前库存：{updated['inventory']}{updated['unit']}")
        messagebox.showinfo("库存更新", f"{updated['name']} 当前库存：{updated['inventory']}{updated['unit']}", parent=self)
        self.refresh()

    def _on_select(self, _event=None) -> None:
        record = self._selected_record()
        if record:
            self._show_detail(record)

    def _show_detail(self, item: dict) -> None:
        self.detail_vars["name"].set(item["name"])
        self.detail_vars["cas"].set(item["cas"])
        self.detail_vars["supplier"].set(item["supplier"])
        self.detail_vars["inventory"].set(f"{item['inventory']}{item['unit']}")
        self.detail_vars["updated"].set(item["updated_at"])

    def _clear_detail(self) -> None:
        for variable in self.detail_vars.values():
            variable.set("-")
