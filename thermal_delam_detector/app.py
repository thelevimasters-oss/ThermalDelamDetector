"""Graphical front-end for the Thermal Delamination Detector."""
from __future__ import annotations

import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from PIL import Image, ImageTk

from .io_utils import discover_images, ensure_output_folder, save_with_metadata
from .processing import ImageProcessor, ProcessingResult

try:  # Optional drag-and-drop support
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:  # pragma: no cover - fallback when dependency missing
    DND_FILES = None
    TkinterDnD = None


@dataclass(slots=True)
class GUIState:
    input_folder: Optional[Path] = None
    output_folder: Optional[Path] = None
    latest_result: Optional[ProcessingResult] = None
    processing: bool = False
    status_message: str = ""


class ThermalDelamApp:
    """Tkinter based desktop application."""

    def __init__(self) -> None:
        self.root = self._create_root()
        self.state = GUIState()
        self.processor = ImageProcessor()
        self.preview_photo: Optional[ImageTk.PhotoImage] = None

        self._build_style()
        self._build_layout()
        self._bind_shortcuts()
        self._update_status("Drop a folder of RJPG images or choose one to begin.")
        try:
            self._preview_resample = Image.Resampling.LANCZOS
        except AttributeError:  # pragma: no cover - Pillow < 9
            self._preview_resample = Image.LANCZOS

    # ------------------------------------------------------------------
    # GUI construction helpers
    # ------------------------------------------------------------------

    def _create_root(self) -> tk.Tk:
        if TkinterDnD is not None:
            root = TkinterDnD.Tk()
        else:
            root = tk.Tk()
        root.title("Thermal Delamination Detector")
        root.geometry("1000x640")
        root.minsize(900, 560)
        return root

    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            self.root.tk.call("source", "sun-valley.tcl")
            style.theme_use("sun-valley-dark")
        except tk.TclError:
            style.theme_use("clam")

        style.configure("TFrame", background="#1e1f25")
        style.configure("TLabel", background="#1e1f25", foreground="#f2f2f2")
        style.configure("TButton", padding=6)
        style.configure("Horizontal.TScale", background="#1e1f25")
        style.configure("info.TLabel", foreground="#9ad1ff")
        style.configure("status.TLabel", foreground="#cccccc")

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=0)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        control_frame = ttk.Frame(self.root, padding=20)
        control_frame.grid(column=0, row=0, sticky="nsew")

        preview_frame = ttk.Frame(self.root, padding=(10, 20, 20, 20))
        preview_frame.grid(column=1, row=0, sticky="nsew")
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)

        self._build_controls(control_frame)
        self._build_preview(preview_frame)

    def _build_controls(self, frame: ttk.Frame) -> None:
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="Input folder", style="info.TLabel").grid(column=0, row=0, sticky="w")
        self.input_var = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=self.input_var, width=28)
        entry.grid(column=0, row=1, sticky="ew", pady=(0, 6))

        browse_btn = ttk.Button(frame, text="Browse…", command=self._choose_input_folder)
        browse_btn.grid(column=0, row=2, sticky="ew")

        ttk.Label(frame, text="Output folder", style="info.TLabel").grid(column=0, row=3, sticky="w", pady=(18, 0))
        self.output_var = tk.StringVar()
        output_entry = ttk.Entry(frame, textvariable=self.output_var, width=28)
        output_entry.grid(column=0, row=4, sticky="ew", pady=(0, 6))

        output_btn = ttk.Button(frame, text="Choose…", command=self._choose_output_folder)
        output_btn.grid(column=0, row=5, sticky="ew")

        sep = ttk.Separator(frame, orient="horizontal")
        sep.grid(column=0, row=6, sticky="ew", pady=18)

        self.threshold_var = tk.DoubleVar(value=self.processor.config.hotspot_percentile)
        ttk.Label(frame, text="Hotspot percentile").grid(column=0, row=7, sticky="w")
        threshold_scale = ttk.Scale(
            frame,
            from_=70,
            to=99.9,
            orient="horizontal",
            variable=self.threshold_var,
            command=lambda _: self._on_parameters_changed(),
        )
        threshold_scale.grid(column=0, row=8, sticky="ew")
        ttk.Label(frame, textvariable=self.threshold_var, style="info.TLabel").grid(column=0, row=9, sticky="w")

        self.min_cluster_var = tk.IntVar(value=self.processor.config.min_cluster_size)
        ttk.Label(frame, text="Minimum hotspot size (px)").grid(column=0, row=10, sticky="w", pady=(12, 0))
        min_cluster_spin = ttk.Spinbox(
            frame,
            from_=1,
            to=2000,
            increment=5,
            textvariable=self.min_cluster_var,
            command=self._on_parameters_changed,
        )
        min_cluster_spin.grid(column=0, row=11, sticky="ew")

        ttk.Label(frame, text="Morphology iterations").grid(column=0, row=12, sticky="w", pady=(12, 0))
        morph_frame = ttk.Frame(frame)
        morph_frame.grid(column=0, row=13, sticky="ew")
        morph_frame.columnconfigure((0, 1), weight=1)

        self.opening_var = tk.IntVar(value=self.processor.config.opening_iterations)
        self.closing_var = tk.IntVar(value=self.processor.config.closing_iterations)
        ttk.Label(morph_frame, text="Open").grid(column=0, row=0, sticky="w")
        ttk.Label(morph_frame, text="Close").grid(column=1, row=0, sticky="w")
        opening_spin = ttk.Spinbox(
            morph_frame,
            from_=0,
            to=5,
            textvariable=self.opening_var,
            command=self._on_parameters_changed,
            width=5,
        )
        opening_spin.grid(column=0, row=1, sticky="ew")
        closing_spin = ttk.Spinbox(
            morph_frame,
            from_=0,
            to=5,
            textvariable=self.closing_var,
            command=self._on_parameters_changed,
            width=5,
        )
        closing_spin.grid(column=1, row=1, sticky="ew")

        self.process_button = ttk.Button(frame, text="Process images", command=self._process_folder)
        self.process_button.grid(column=0, row=14, sticky="ew", pady=(24, 0))

        self.progress = ttk.Progressbar(frame, orient="horizontal", mode="determinate")
        self.progress.grid(column=0, row=15, sticky="ew", pady=(12, 0))

        self.status_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.status_var, style="status.TLabel", wraplength=240).grid(
            column=0,
            row=16,
            sticky="w",
            pady=(16, 0),
        )

        if TkinterDnD is not None and DND_FILES is not None:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._handle_drop)

    def _build_preview(self, frame: ttk.Frame) -> None:
        self.preview_canvas = tk.Canvas(frame, background="#101218", highlightthickness=0)
        self.preview_canvas.grid(column=0, row=0, sticky="nsew")
        self.preview_canvas.create_text(
            0,
            0,
            anchor="nw",
            text="Preview will appear here once an image is processed.",
            fill="#cccccc",
            font=("Segoe UI", 12),
            tags=("placeholder",),
        )

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-o>", lambda _: self._choose_input_folder())
        self.root.bind("<Control-s>", lambda _: self._process_folder())

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _handle_drop(self, event) -> None:  # type: ignore[override]
        if not event.data:
            return
        paths = self.root.tk.splitlist(event.data)
        if not paths:
            return
        first = Path(paths[0])
        if first.is_dir():
            self._set_input_folder(first)
        else:
            messagebox.showwarning("Unsupported item", "Please drop a folder containing RJPG files.")

    def _choose_input_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select thermal image folder")
        if folder:
            self._set_input_folder(Path(folder))

    def _choose_output_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select output folder")
        if folder:
            self.state.output_folder = Path(folder)
            self.output_var.set(str(self.state.output_folder))

    def _set_input_folder(self, folder: Path) -> None:
        if not folder.exists():
            messagebox.showerror("Folder not found", f"The folder {folder} does not exist.")
            return
        images = list(discover_images(folder))
        if not images:
            messagebox.showwarning("No images", "No supported thermal images were found in the folder.")
            return
        self.state.input_folder = folder
        self.input_var.set(str(folder))
        self._update_status(f"Loaded {len(images)} images. Adjust settings and process when ready.")
        self._update_preview(images[0])

    def _on_parameters_changed(self) -> None:
        self.processor.update_config(
            hotspot_percentile=self.threshold_var.get(),
            min_cluster_size=self.min_cluster_var.get(),
            opening_iterations=self.opening_var.get(),
            closing_iterations=self.closing_var.get(),
        )
        if self.state.input_folder:
            first_image = next(discover_images(self.state.input_folder), None)
            if first_image:
                self._update_preview(first_image)

    def _update_preview(self, image_path: Path) -> None:
        try:
            result = self.processor.process_image(image_path)
        except Exception as exc:  # pragma: no cover - user feedback
            self._update_status(f"Failed to generate preview: {exc}")
            return

        preview = result.overlay_image.copy()
        preview.thumbnail((700, 520), self._preview_resample)
        self.preview_photo = ImageTk.PhotoImage(preview)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(10, 10, anchor="nw", image=self.preview_photo)
        self.preview_canvas.create_text(
            10,
            preview.height + 20,
            anchor="nw",
            text=f"Preview: {image_path.name}",
            fill="#cccccc",
            font=("Segoe UI", 11),
        )
        self.state.latest_result = result

    def _process_folder(self) -> None:
        if self.state.processing:
            return
        if not self.state.input_folder:
            messagebox.showinfo("Choose folder", "Please choose an input folder first.")
            return

        images = list(discover_images(self.state.input_folder))
        if not images:
            messagebox.showinfo("No images", "No supported images were found in the selected folder.")
            return

        output_folder = ensure_output_folder(
            self.state.input_folder,
            Path(self.output_var.get()) if self.output_var.get() else None,
        )
        self.state.output_folder = output_folder
        self.output_var.set(str(output_folder))

        self.state.processing = True
        self.process_button.configure(state=tk.DISABLED)
        self.progress.configure(value=0, maximum=len(images))
        self._update_status("Processing images…")

        threading.Thread(
            target=self._process_images_worker,
            args=(images, output_folder),
            daemon=True,
        ).start()

    def _process_images_worker(self, images: list[Path], output_folder: Path) -> None:
        try:
            for idx, image_path in enumerate(images, start=1):
                result = self.processor.process_image(image_path)
                destination = output_folder / f"{image_path.stem}_processed.jpg"
                save_with_metadata(result.overlay_image, destination, result.exif_bytes)
                self.progress.after(
                    0, lambda value=idx: self.progress.configure(value=value)
                )
            self._update_status_async(f"Processing complete. Saved results to {output_folder}.")
        except Exception as exc:  # pragma: no cover - user feedback path
            self._update_status_async(f"Processing stopped: {exc}")
            self.root.after(0, lambda: messagebox.showerror("Processing error", str(exc)))
        finally:
            self.progress.after(0, self._processing_finished)

    def _processing_finished(self) -> None:
        self.state.processing = False
        self.process_button.configure(state=tk.NORMAL)
        self.progress.configure(value=0)

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    def _update_status(self, message: str) -> None:
        self.state.status_message = message
        self.status_var.set(message)

    def _update_status_async(self, message: str) -> None:
        self.root.after(0, self._update_status, message)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        self.root.mainloop()


def launch() -> None:
    app = ThermalDelamApp()
    app.run()


if __name__ == "__main__":  # pragma: no cover - manual execution entry point
    launch()
