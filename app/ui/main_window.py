from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk

from app.auth import authenticate, has_permission, list_usernames, require_permission
from app.config import APP_TITLE, APP_VERSION
from app.data_store import DataStore
from app.exceptions import (
    AuthenticationError,
    PermissionDeniedError,
    handle_exception,
    install_exception_hooks,
    setup_logging,
)
from app.ui.dashboard_view import DashboardView
from app.ui.data_query_view import DataQueryView
from app.ui.monitor_view import ParameterMonitorView
from app.ui.report_view import ReportView
from app.ui.security_view import SecurityView
from app.ui.style import configure_style
from app.ui.work_order_view import WorkOrderView


class ChemicalManagementApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        setup_logging()
        configure_style(self)
        install_exception_hooks(self)

        self.title(APP_TITLE)
        self.geometry("1180x760")
        self.minsize(980, 640)

        self.store = DataStore()
        self.current_user = None
        self.status_text = tk.StringVar()
        self.clock_text = tk.StringVar()
        self.active_view = "dashboard"
        self.toolbar_buttons: dict[str, ttk.Button] = {}
        self.views: dict[str, ttk.Frame] = {}
        self.login_username_var = tk.StringVar(value="admin")
        self.login_password_var = tk.StringVar()
        self._clock_job = None

        self._show_login_screen()

    def guarded(self, action):
        def wrapper(*args, **kwargs):
            try:
                return action(*args, **kwargs)
            except Exception as exc:
                handle_exception(self, exc)
                return None

        return wrapper

    def has_permission(self, permission: str) -> bool:
        return self.current_user is not None and has_permission(self.current_user, permission)

    def require_permission(self, permission: str) -> None:
        if self.current_user is None:
            raise PermissionDeniedError("请先登录系统。")
        require_permission(self.current_user, permission)

    def show_view(self, name: str) -> None:
        self.active_view = name
        view = self.views[name]
        view.tkraise()
        if hasattr(view, "refresh"):
            view.refresh()
        for key, button in self.toolbar_buttons.items():
            button.state(["pressed"] if key == name else ["!pressed"])

    def switch_user(self) -> None:
        self.current_user = None
        self.views.clear()
        self.toolbar_buttons.clear()
        self.login_password_var.set("")
        self._show_login_screen()

    def open_work_order_for_parameter(self, parameter: dict) -> None:
        self.show_view("work_orders")
        view = self.views["work_orders"]
        if isinstance(view, WorkOrderView):
            view.create_from_alarm(parameter)

    def audit_action(self, action: str, target: str, detail: str = "") -> None:
        if self.current_user is None:
            return
        self.store.log_action(
            username=self.current_user.display_name,
            role=self.current_user.role_name,
            action=action,
            target=target,
            detail=detail,
        )
        dashboard = self.views.get("dashboard")
        if dashboard is not None and hasattr(dashboard, "refresh"):
            dashboard.refresh()

    def _build_layout(self) -> None:
        self._clear_window()
        self.toolbar_buttons.clear()

        self._build_toolbar()
        self.content = ttk.Frame(self, padding=(12, 10, 12, 8))
        self.content.pack(fill=tk.BOTH, expand=True)
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)

        self.views = {
            "dashboard": DashboardView(self.content, self.store, self),
            "data": DataQueryView(self.content, self.store, self),
            "monitor": ParameterMonitorView(self.content, self.store, self),
            "work_orders": WorkOrderView(self.content, self.store, self),
            "reports": ReportView(self.content, self.store, self),
        }
        if self.has_permission("user_manage") or self.has_permission("role_manage"):
            self.views["security"] = SecurityView(self.content, self.store, self)
        for view in self.views.values():
            view.grid(row=0, column=0, sticky="nsew")

        self._build_menu()
        self._build_status_bar()

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        self.config(menu=menu)

        system_menu = tk.Menu(menu, tearoff=False)
        system_menu.add_command(label="切换用户", command=self.guarded(self.switch_user))
        system_menu.add_separator()
        system_menu.add_command(label="退出", command=self.destroy)
        menu.add_cascade(label="系统", menu=system_menu)

        module_menu = tk.Menu(menu, tearoff=False)
        module_menu.add_command(label="运行看板", command=self.guarded(lambda: self.show_view("dashboard")))
        module_menu.add_command(label="数据查询", command=self.guarded(lambda: self.show_view("data")))
        module_menu.add_command(label="参数监控", command=self.guarded(lambda: self.show_view("monitor")))
        module_menu.add_command(label="工单管理", command=self.guarded(lambda: self.show_view("work_orders")))
        module_menu.add_command(label="报表预览", command=self.guarded(lambda: self.show_view("reports")))
        if "security" in self.views:
            module_menu.add_command(label="权限管理", command=self.guarded(lambda: self.show_view("security")))
        menu.add_cascade(label="模块", menu=module_menu)

        manage_menu = tk.Menu(menu, tearoff=False)
        has_manage_item = False
        if self.has_permission("parameter_ack"):
            manage_menu.add_command(
                label="确认选中报警",
                command=self.guarded(lambda: self._view_action("monitor", "acknowledge_selected")),
            )
            has_manage_item = True
        if self.has_permission("workorder_delete"):
            manage_menu.add_command(
                label="删除选中工单",
                command=self.guarded(lambda: self._view_action("work_orders", "delete_selected")),
            )
            has_manage_item = True
        if self.has_permission("report_export"):
            manage_menu.add_command(
                label="导出当前报表",
                command=self.guarded(lambda: self._view_action("reports", "export_selected")),
            )
            has_manage_item = True
        if has_manage_item:
            menu.add_cascade(label="管理", menu=manage_menu)

        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="关于", command=self._about)
        menu.add_cascade(label="帮助", menu=help_menu)

    def _build_toolbar(self) -> None:
        toolbar = ttk.Frame(self, style="Toolbar.TFrame", padding=(10, 8))
        toolbar.pack(fill=tk.X)

        buttons = [
            ("dashboard", "运行看板"),
            ("data", "数据查询"),
            ("monitor", "参数监控"),
            ("work_orders", "工单管理"),
            ("reports", "报表预览"),
        ]
        if self.has_permission("user_manage") or self.has_permission("role_manage"):
            buttons.append(("security", "权限管理"))
        for key, text in buttons:
            button = ttk.Button(
                toolbar,
                text=text,
                style="Toolbar.TButton",
                command=self.guarded(lambda name=key: self.show_view(name)),
            )
            button.pack(side=tk.LEFT, padx=(0, 8))
            self.toolbar_buttons[key] = button

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=(4, 12))
        ttk.Button(toolbar, text="刷新", command=self.guarded(self._refresh_active_view)).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(toolbar, text="切换用户", command=self.guarded(self.switch_user)).pack(side=tk.LEFT)

        self.user_label = ttk.Label(toolbar, text="", style="Hint.TLabel")
        self.user_label.pack(side=tk.RIGHT)

    def _build_status_bar(self) -> None:
        status = ttk.Frame(self, style="Status.TFrame", padding=(10, 6))
        status.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Label(status, textvariable=self.status_text, style="Hint.TLabel").pack(side=tk.LEFT)
        ttk.Label(status, textvariable=self.clock_text, style="Hint.TLabel").pack(side=tk.RIGHT)

    def _refresh_permissions(self) -> None:
        access_label = "完整权限" if self.current_user.is_admin else "受限权限"
        self.user_label.configure(text=f"{self.current_user.display_name} | {self.current_user.role_name} | {access_label}")
        self.status_text.set(f"当前身份：{self.current_user.role_name}；权限：{access_label}；系统版本：{APP_VERSION}")
        self._build_menu()
        for view in self.views.values():
            if hasattr(view, "apply_permissions"):
                view.apply_permissions()

    def _refresh_active_view(self) -> None:
        view = self.views[self.active_view]
        if hasattr(view, "refresh"):
            view.refresh()

    def _view_action(self, view_name: str, method_name: str) -> None:
        self.show_view(view_name)
        view = self.views[view_name]
        getattr(view, method_name)()

    def _about(self) -> None:
        messagebox.showinfo(
            "关于",
            f"{APP_TITLE}\n版本：{APP_VERSION}\n\n题目10：综合化工桌面管理系统",
            parent=self,
        )

    def on_security_changed(self) -> None:
        self._refresh_permissions()
        if "security" in self.views:
            self.views["security"].refresh()

    def _tick(self) -> None:
        self.clock_text.set(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self._clock_job = self.after(1000, self._tick)

    def _clear_window(self) -> None:
        if self._clock_job is not None:
            self.after_cancel(self._clock_job)
            self._clock_job = None
        for child in self.winfo_children():
            child.destroy()

    def _show_login_screen(self) -> None:
        self._clear_window()
        self.config(menu=tk.Menu(self))

        shell = ttk.Frame(self, padding=32)
        shell.pack(fill=tk.BOTH, expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)

        panel = ttk.Frame(shell, padding=28, style="Panel.TFrame")
        panel.grid(row=0, column=0)
        panel.columnconfigure(1, weight=1)

        ttk.Label(panel, text=APP_TITLE, style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(panel, text="请输入账号密码进入系统", style="Hint.TLabel").grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(4, 18),
        )

        ttk.Label(panel, text="账号").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=6)
        ttk.Combobox(
            panel,
            textvariable=self.login_username_var,
            values=list_usernames(),
            state="readonly",
            width=28,
        ).grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Label(panel, text="密码").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=6)
        password_entry = ttk.Entry(panel, textvariable=self.login_password_var, show="*", width=30)
        password_entry.grid(row=3, column=1, sticky="ew", pady=6)

        ttk.Label(panel, text="管理员：admin123；操作员：operator123", style="Hint.TLabel").grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 14),
        )

        buttons = ttk.Frame(panel)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="退出", command=self.destroy).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="登录", style="Primary.TButton", command=self.guarded(self._login_from_screen)).pack(side=tk.LEFT)

        self.bind("<Return>", lambda _event: self._login_from_screen())
        password_entry.focus_set()

    def _login_from_screen(self) -> None:
        try:
            self.current_user = authenticate(self.login_username_var.get(), self.login_password_var.get())
        except AuthenticationError as exc:
            messagebox.showerror("登录失败", str(exc), parent=self)
            self.login_password_var.set("")
            return

        self.unbind("<Return>")
        self._build_layout()
        self._refresh_permissions()
        self.show_view("dashboard")
        self._tick()
