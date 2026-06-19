from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from app import auth


class SecurityView(ttk.Frame):
    def __init__(self, parent, store, app) -> None:
        super().__init__(parent)
        self.store = store
        self.app = app
        self.role_var = tk.StringVar()
        self.assign_role_var = tk.StringVar()
        self.permission_vars: dict[str, tk.BooleanVar] = {}
        self.roles: list[dict] = []
        self.permissions: list[dict] = []
        self._build()

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self, padding=(0, 0, 0, 10))
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="权限管理", style="Section.TLabel").grid(row=0, column=0, padx=(0, 18))
        ttk.Label(header, text="用户、角色和权限均来自 SQLite 配置表。", style="Hint.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Button(header, text="刷新", command=self.app.guarded(self.refresh)).grid(row=0, column=2)

        user_box = ttk.LabelFrame(self, text="用户管理", padding=10)
        user_box.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        user_box.columnconfigure(0, weight=1)
        user_box.rowconfigure(0, weight=1)

        columns = ("username", "display", "role", "active")
        self.user_tree = ttk.Treeview(user_box, columns=columns, show="headings", selectmode="browse")
        headings = {"username": "账号", "display": "显示名称", "role": "角色", "active": "状态"}
        widths = {"username": 110, "display": 130, "role": 120, "active": 80}
        for key in columns:
            self.user_tree.heading(key, text=headings[key])
            self.user_tree.column(key, width=widths[key], anchor=tk.W)
        self.user_tree.grid(row=0, column=0, sticky="nsew")

        user_actions = ttk.Frame(user_box, padding=(0, 10, 0, 0))
        user_actions.grid(row=1, column=0, sticky="ew")
        self.new_user_button = ttk.Button(user_actions, text="新建用户", command=self.app.guarded(self.create_user))
        self.new_user_button.pack(side=tk.LEFT, padx=(0, 8))
        self.reset_button = ttk.Button(user_actions, text="重置密码", command=self.app.guarded(self.reset_password))
        self.reset_button.pack(side=tk.LEFT, padx=(0, 8))
        self.toggle_button = ttk.Button(user_actions, text="启用/停用", command=self.app.guarded(self.toggle_active))
        self.toggle_button.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Combobox(user_actions, textvariable=self.assign_role_var, state="readonly", width=14).pack(side=tk.LEFT, padx=(8, 6))
        self.role_button = ttk.Button(user_actions, text="分配角色", command=self.app.guarded(self.assign_role))
        self.role_button.pack(side=tk.LEFT)

        role_box = ttk.LabelFrame(self, text="角色权限配置", padding=10)
        role_box.grid(row=1, column=1, sticky="nsew")
        role_box.columnconfigure(0, weight=1)
        role_box.rowconfigure(2, weight=1)

        role_header = ttk.Frame(role_box)
        role_header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(role_header, text="角色").pack(side=tk.LEFT, padx=(0, 6))
        self.role_combo = ttk.Combobox(role_header, textvariable=self.role_var, state="readonly", width=18)
        self.role_combo.pack(side=tk.LEFT, padx=(0, 8))
        self.role_combo.bind("<<ComboboxSelected>>", lambda _event: self.load_role_permissions())
        self.new_role_button = ttk.Button(role_header, text="新增角色", command=self.app.guarded(self.create_role))
        self.new_role_button.pack(side=tk.LEFT, padx=(0, 8))
        self.save_role_button = ttk.Button(role_header, text="保存权限", command=self.app.guarded(self.save_role_permissions))
        self.save_role_button.pack(side=tk.LEFT)

        ttk.Label(role_box, text="勾选后该角色即可获得对应操作入口和后台权限。", style="Hint.TLabel").grid(row=1, column=0, sticky="w", pady=(0, 8))

        self.permission_canvas = tk.Canvas(role_box, highlightthickness=0, height=360)
        self.permission_canvas.grid(row=2, column=0, sticky="nsew")
        self.permission_frame = ttk.Frame(self.permission_canvas)
        self.permission_window = self.permission_canvas.create_window((0, 0), window=self.permission_frame, anchor="nw")
        scroll = ttk.Scrollbar(role_box, orient=tk.VERTICAL, command=self.permission_canvas.yview)
        scroll.grid(row=2, column=1, sticky="ns")
        self.permission_canvas.configure(yscrollcommand=scroll.set)
        self.permission_frame.bind("<Configure>", self._update_scroll_region)
        self.permission_canvas.bind("<Configure>", self._resize_permission_frame)

    def refresh(self) -> None:
        self.roles = auth.list_roles()
        self.permissions = auth.list_permissions()
        role_labels = [self._role_label(role) for role in self.roles]
        self.role_combo.configure(values=role_labels)
        for child in self.winfo_children():
            for widget in child.winfo_children():
                if isinstance(widget, ttk.Frame):
                    for sub in widget.winfo_children():
                        if isinstance(sub, ttk.Combobox):
                            sub.configure(values=role_labels)
        if role_labels and self.role_var.get() not in role_labels:
            self.role_var.set(role_labels[0])
        self.assign_role_var.set(role_labels[0] if role_labels and not self.assign_role_var.get() else self.assign_role_var.get())
        self._populate_users()
        self.load_role_permissions()

    def apply_permissions(self) -> None:
        state = tk.NORMAL if self.app.has_permission("user_manage") else tk.DISABLED
        for button in (self.new_user_button, self.reset_button, self.toggle_button, self.role_button):
            button.configure(state=state)
        role_state = tk.NORMAL if self.app.has_permission("role_manage") else tk.DISABLED
        self.new_role_button.configure(state=role_state)
        self.save_role_button.configure(state=role_state)

    def create_user(self) -> None:
        self.app.require_permission("user_manage")
        payload = UserDialog.ask(self, self.roles)
        if payload is None:
            return
        auth.create_user(**payload)
        self.app.audit_action("新建用户", payload["username"], payload["display_name"])
        self.refresh()

    def reset_password(self) -> None:
        self.app.require_permission("user_manage")
        user = self._selected_user()
        if user is None:
            return
        password = simpledialog.askstring("重置密码", f"请输入 {user['username']} 的新密码：", show="*", parent=self)
        if not password:
            return
        auth.reset_password(user["username"], password)
        self.app.audit_action("重置密码", user["username"])
        messagebox.showinfo("系统提示", "密码已重置。", parent=self)

    def toggle_active(self) -> None:
        self.app.require_permission("user_manage")
        user = self._selected_user()
        if user is None:
            return
        active = not bool(user["active"])
        auth.set_user_active(user["username"], active)
        self.app.audit_action("启停用户", user["username"], "启用" if active else "停用")
        self.refresh()

    def assign_role(self) -> None:
        self.app.require_permission("user_manage")
        user = self._selected_user()
        if user is None:
            return
        role_code = self._role_code_from_label(self.assign_role_var.get())
        auth.update_user_role(user["username"], role_code)
        self.app.audit_action("分配角色", user["username"], role_code)
        self.refresh()
        self.app.on_security_changed()

    def create_role(self) -> None:
        self.app.require_permission("role_manage")
        code = simpledialog.askstring("新增角色", "角色编码（英文/数字）：", parent=self)
        if not code:
            return
        name = simpledialog.askstring("新增角色", "角色名称：", parent=self)
        if not name:
            return
        description = simpledialog.askstring("新增角色", "角色说明：", parent=self) or ""
        auth.create_role(code, name, description)
        self.app.audit_action("新增角色", code, name)
        self.refresh()

    def load_role_permissions(self) -> None:
        for child in self.permission_frame.winfo_children():
            child.destroy()
        self.permission_vars.clear()
        role_code = self._role_code_from_label(self.role_var.get())
        enabled = auth.permissions_for_role(role_code) if role_code else set()

        row = 0
        current_module = None
        for permission in self.permissions:
            if permission["module"] != current_module:
                current_module = permission["module"]
                ttk.Label(self.permission_frame, text=current_module, style="Section.TLabel").grid(row=row, column=0, sticky="w", pady=(8, 4))
                row += 1
            variable = tk.BooleanVar(value=permission["code"] in enabled)
            self.permission_vars[permission["code"]] = variable
            text = f"{permission['name']}：{permission['description']}"
            ttk.Checkbutton(self.permission_frame, text=text, variable=variable).grid(row=row, column=0, sticky="w", pady=2)
            row += 1

    def save_role_permissions(self) -> None:
        self.app.require_permission("role_manage")
        role_code = self._role_code_from_label(self.role_var.get())
        if not role_code:
            return
        for permission_code, variable in self.permission_vars.items():
            auth.set_role_permission(role_code, permission_code, variable.get())
        self.app.audit_action("保存角色权限", role_code)
        self.app.on_security_changed()
        messagebox.showinfo("系统提示", "角色权限已保存。", parent=self)

    def _populate_users(self) -> None:
        self.user_tree.delete(*self.user_tree.get_children())
        for user in auth.list_users():
            self.user_tree.insert(
                "",
                tk.END,
                iid=user["username"],
                values=(
                    user["username"],
                    user["display_name"],
                    user["role_name"],
                    "启用" if user["active"] else "停用",
                ),
            )

    def _selected_user(self):
        selection = self.user_tree.selection()
        if not selection:
            messagebox.showwarning("系统提示", "请先选择一个用户。", parent=self)
            return None
        username = selection[0]
        for user in auth.list_users():
            if user["username"] == username:
                return user
        return None

    def _role_label(self, role: dict) -> str:
        return f"{role['name']} ({role['code']})"

    def _role_code_from_label(self, label: str) -> str:
        if "(" in label and label.endswith(")"):
            return label.rsplit("(", 1)[1][:-1]
        for role in self.roles:
            if role["name"] == label or role["code"] == label:
                return role["code"]
        return ""

    def _update_scroll_region(self, _event=None) -> None:
        self.permission_canvas.configure(scrollregion=self.permission_canvas.bbox("all"))

    def _resize_permission_frame(self, event) -> None:
        self.permission_canvas.itemconfigure(self.permission_window, width=event.width)


class UserDialog(tk.Toplevel):
    def __init__(self, parent, roles: list[dict]) -> None:
        super().__init__(parent)
        self.result = None
        self.roles = roles
        self.title("新建用户")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.username_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.display_name_var = tk.StringVar()
        self.role_var = tk.StringVar(value=self._role_label(roles[0]) if roles else "")
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._cancel)

    @classmethod
    def ask(cls, parent, roles: list[dict]):
        dialog = cls(parent, roles)
        parent.wait_window(dialog)
        return dialog.result

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=18)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        fields = [
            ("账号", ttk.Entry(frame, textvariable=self.username_var, width=28)),
            ("密码", ttk.Entry(frame, textvariable=self.password_var, show="*", width=28)),
            ("显示名称", ttk.Entry(frame, textvariable=self.display_name_var, width=28)),
            ("角色", ttk.Combobox(frame, textvariable=self.role_var, values=[self._role_label(role) for role in self.roles], state="readonly", width=26)),
        ]
        for row, (label, widget) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=6)
            widget.grid(row=row, column=1, sticky="ew", pady=6)

        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="取消", command=self._cancel).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="确定", command=self._ok).pack(side=tk.LEFT)

    def _ok(self) -> None:
        role_code = self.role_var.get().rsplit("(", 1)[1][:-1]
        self.result = {
            "username": self.username_var.get().strip(),
            "password": self.password_var.get(),
            "display_name": self.display_name_var.get().strip(),
            "role_code": role_code,
        }
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()

    @staticmethod
    def _role_label(role: dict) -> str:
        return f"{role['name']} ({role['code']})"
