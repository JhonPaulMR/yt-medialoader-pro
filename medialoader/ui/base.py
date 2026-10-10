import customtkinter as ctk


class Screen(ctk.CTkFrame):
    """Tela da área principal. `app` é o MediaLoaderApp."""

    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app

    def on_show(self):
        pass
