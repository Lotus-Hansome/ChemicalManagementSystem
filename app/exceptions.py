import sys
from tkinter import messagebox


class AppError(Exception):
    """Base class for user-facing application errors."""


class AuthenticationError(AppError):
    pass


class PermissionDeniedError(AppError):
    pass


class DataStoreError(AppError):
    pass


def format_error(exc: BaseException) -> str:
    if isinstance(exc, AppError):
        return str(exc)
    return "系统运行时出现未知异常，请检查操作后重试。"


def handle_exception(parent, exc: BaseException) -> None:
    messagebox.showerror("系统提示", format_error(exc), parent=parent)


def install_exception_hooks(root) -> None:
    def callback(exc_type, exc, tb) -> None:
        messagebox.showerror("系统异常", format_error(exc), parent=root)

    def sys_hook(exc_type, exc, tb) -> None:
        messagebox.showerror("系统异常", format_error(exc), parent=root)

    root.report_callback_exception = callback
    sys.excepthook = sys_hook
