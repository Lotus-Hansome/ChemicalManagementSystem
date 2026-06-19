import tkinter as tk
from tkinter import ttk


COLORS = {
    "surface": "#F4F7F9",
    "panel": "#FFFFFF",
    "border": "#D9E1E8",
    "text": "#203040",
    "muted": "#607080",
    "primary": "#1F6FEB",
    "success": "#16794C",
    "warning": "#9A6700",
    "danger": "#C62828",
}


def configure_style(root: tk.Tk) -> ttk.Style:
    root.option_add("*Font", ("Microsoft YaHei UI", 10))
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    style.configure(".", background=COLORS["surface"], foreground=COLORS["text"])
    style.configure("TFrame", background=COLORS["surface"])
    style.configure("Panel.TFrame", background=COLORS["panel"])
    style.configure("Toolbar.TFrame", background="#E9EEF4", relief="flat")
    style.configure("Status.TFrame", background="#E9EEF4")
    style.configure("Title.TLabel", font=("Microsoft YaHei UI", 16, "bold"), background=COLORS["surface"])
    style.configure("Section.TLabel", font=("Microsoft YaHei UI", 12, "bold"), background=COLORS["surface"])
    style.configure("Hint.TLabel", foreground=COLORS["muted"], background=COLORS["surface"])
    style.configure("Toolbar.TButton", padding=(12, 7))
    style.configure("Primary.TButton", padding=(12, 7))
    style.configure("TButton", padding=(9, 6))
    style.configure("Treeview", rowheight=29, fieldbackground=COLORS["panel"], background=COLORS["panel"])
    style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 10, "bold"), background="#E6EDF5")
    style.map("Treeview", background=[("selected", "#CFE2FF")], foreground=[("selected", COLORS["text"])])
    style.configure("TLabelframe", background=COLORS["surface"], bordercolor=COLORS["border"])
    style.configure("TLabelframe.Label", background=COLORS["surface"], foreground=COLORS["muted"])
    return style
