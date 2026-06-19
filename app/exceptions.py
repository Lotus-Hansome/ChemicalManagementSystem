import logging
import sys
import traceback
from tkinter import messagebox

from app.config import LOG_DIR, LOG_FILE

class AppError(Exception):
    """Base class for user-facing application errors."""

class AuthenticationError(AppError):
    pass

class PermissionDeniedError(AppError):
    pass

class DataStoreError(AppError):
    pass

def setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        encoding="utf-8",
    )

def format_error(exc: BaseException) -> str:
    if isinstance(exc, AppError):
        return str(exc)
    return "系统运行时出现未知异常，请查看日志文件。"

def handle_exception(parent, exc: BaseException) -> None:
    logging.exception("Unhandled application exception", exc_info=exc)
    messagebox.showerror("系统提示", format_error(exc), parent=parent)

def install_exception_hooks(root) -> None:
    def callback(exc_type, exc, tb) -> None:
        logging.error("Tk callback exception:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        messagebox.showerror("系统异常", format_error(exc), parent=root)

    def sys_hook(exc_type, exc, tb) -> None:
        logging.error("Global exception:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        messagebox.showerror("系统异常", format_error(exc), parent=root)

    root.report_callback_exception = callback
    sys.excepthook = sys_hook