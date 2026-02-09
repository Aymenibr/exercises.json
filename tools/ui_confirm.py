from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional


def prompt_accept_with_ui(exercise_name: str, figure_path: str, validation_text: str) -> bool:
    """
    Blocking UI dialog showing the verification figure and validation notes.
    Returns True if user clicks Accept.
    """
    accepted = {"value": False}

    root = tk.Tk()
    root.title(f"Confirm: {exercise_name}")

    # Layout: figure on left, text + buttons on right
    frame = ttk.Frame(root, padding=10)
    frame.grid(row=0, column=0, sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    # Figure
    try:
        from PIL import Image, ImageTk

        img = Image.open(figure_path)
        max_w, max_h = 640, 640
        img.thumbnail((max_w, max_h))
        photo = ImageTk.PhotoImage(img)
        label_img = ttk.Label(frame, image=photo)
        label_img.image = photo  # keep reference
        label_img.grid(row=0, column=0, rowspan=3, sticky="nsew", padx=(0, 10))
    except Exception as exc:  # pragma: no cover
        label_img = ttk.Label(frame, text=f"(Could not load image: {exc})")
        label_img.grid(row=0, column=0, rowspan=3, sticky="nsew", padx=(0, 10))

    # Validation text
    text = tk.Text(frame, width=60, height=25, wrap="word")
    text.insert("1.0", validation_text)
    text.configure(state="disabled")
    text.grid(row=0, column=1, sticky="nsew")

    # Buttons
    btn_frame = ttk.Frame(frame)
    btn_frame.grid(row=1, column=1, sticky="e", pady=8)

    def on_accept():
        accepted["value"] = True
        root.destroy()

    def on_reject():
        accepted["value"] = False
        root.destroy()

    ttk.Button(btn_frame, text="Accept", command=on_accept).grid(row=0, column=0, padx=5)
    ttk.Button(btn_frame, text="Reject", command=on_reject).grid(row=0, column=1, padx=5)

    # Resize behaviour
    frame.columnconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)
    frame.rowconfigure(0, weight=1)

    root.mainloop()
    return accepted["value"]

