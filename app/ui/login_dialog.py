import tkinter as tk
from tkinter import messagebox, ttk

from app.auth import USERS, authenticate
from app.exceptions import AuthenticationError


class LoginDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk) -> None:
        super().__init__(parent)
        self.parent = parent
        self.user = None
        self.title("用户登录")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.username_var = tk.StringVar(value="admin")
        self.password_var = tk.StringVar()

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Return>", lambda _event: self._login())
        self.bind("<Escape>", lambda _event: self._cancel())

        self.update_idletasks()
        x = parent.winfo_screenwidth() // 2 - self.winfo_width() // 2
        y = parent.winfo_screenheight() // 2 - self.winfo_height() // 2
        self.geometry(f"+{x}+{y}")
        self.password_entry.focus_set()
        self._bring_to_front()

    @classmethod
    def ask(cls, parent: tk.Tk):
        dialog = cls(parent)
        parent.wait_window(dialog)
        return dialog.user

    def _build(self) -> None:
        frame = ttk.Frame(self, padding=24)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="综合化工桌面管理系统", style="Title.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text="请选择身份并输入密码", style="Hint.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 18))

        ttk.Label(frame, text="账号").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=6)
        ttk.Combobox(
            frame,
            textvariable=self.username_var,
            values=list(USERS.keys()),
            state="readonly",
            width=24,
        ).grid(row=2, column=1, sticky="ew", pady=6)

        ttk.Label(frame, text="密码").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=6)
        self.password_entry = ttk.Entry(frame, textvariable=self.password_var, show="*", width=26)
        self.password_entry.grid(row=3, column=1, sticky="ew", pady=6)

        ttk.Label(frame, text="管理员：admin123；操作员：operator123", style="Hint.TLabel").grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 14),
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="取消", command=self._cancel).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="登录", style="Primary.TButton", command=self._login).pack(side=tk.LEFT)

    def _login(self) -> None:
        try:
            self.user = authenticate(self.username_var.get(), self.password_var.get())
        except AuthenticationError as exc:
            messagebox.showerror("登录失败", str(exc), parent=self)
            self.password_var.set("")
            self.password_entry.focus_set()
            return
        self.destroy()

    def _cancel(self) -> None:
        self.user = None
        self.destroy()

    def _bring_to_front(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()
        try:
            self.attributes("-topmost", True)
            self.after(600, lambda: self.attributes("-topmost", False))
        except tk.TclError:
            pass
