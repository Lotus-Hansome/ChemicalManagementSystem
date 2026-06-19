from app import create_app

def main() -> None:
    app = create_app()
    if app.winfo_exists():
        app.mainloop()

if __name__ == "__main__":
    main()