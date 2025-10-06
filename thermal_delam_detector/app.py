"""Graphical front-end for the Thermal Delamination Detector."""
from __future__ import annotations

import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

import sys

try:
    from PIL import Image, ImageTk
except ModuleNotFoundError as exc:  # pragma: no cover - handled at runtime
    Image = None  # type: ignore[assignment]
    ImageTk = None  # type: ignore[assignment]
    _PIL_IMPORT_ERROR: ModuleNotFoundError | None = exc
else:
    _PIL_IMPORT_ERROR = None

_DEPENDENCY_ERROR: ModuleNotFoundError | None = None
_DISPLAY_AVAILABLE: bool | None = None

if _PIL_IMPORT_ERROR is None:
    try:
        from .io_utils import discover_images, ensure_output_folder, save_with_metadata
        from .processing import ImageProcessor, ProcessingResult
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency missing path
        discover_images = ensure_output_folder = save_with_metadata = None  # type: ignore[assignment]
        ImageProcessor = ProcessingResult = None  # type: ignore[assignment]
        _DEPENDENCY_ERROR = exc
else:  # pragma: no cover - dependency missing path
    discover_images = ensure_output_folder = save_with_metadata = None  # type: ignore[assignment]
    ImageProcessor = ProcessingResult = None  # type: ignore[assignment]

try:  # Optional drag-and-drop support
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:  # pragma: no cover - fallback when dependency missing
    DND_FILES = None
    TkinterDnD = None


class Tooltip:
    """Simple tooltip helper for Tkinter widgets."""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tipwindow: Optional[tk.Toplevel] = None
        self.background = "#0F3320"
        self.foreground = "#f5f7f2"

        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)
        widget.bind("<ButtonPress>", self._hide)
        widget.bind("<Destroy>", self._hide)

    def _show(self, _event: tk.Event) -> None:  # type: ignore[name-defined]
        if self.tipwindow or not self.text:
            return
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 12

        self.tipwindow = tk.Toplevel(self.widget)
        self.tipwindow.wm_overrideredirect(True)
        self.tipwindow.wm_attributes("-topmost", True)
        self.tipwindow.configure(background=self.background)

        label = tk.Label(
            self.tipwindow,
            text=self.text,
            justify=tk.LEFT,
            background=self.background,
            foreground=self.foreground,
            borderwidth=0,
            font=("Segoe UI", 10),
            padx=10,
            pady=6,
        )
        label.pack()

        self.tipwindow.update_idletasks()
        width = self.tipwindow.winfo_width()
        height = self.tipwindow.winfo_height()
        self.tipwindow.geometry(f"+{x - width // 2}+{y}")

    def _hide(self, _event: tk.Event | None = None) -> None:  # type: ignore[name-defined]
        if self.tipwindow is not None:
            self.tipwindow.destroy()
            self.tipwindow = None


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
        self.root, self._dnd_available = self._create_root()
        self.state = GUIState()
        self.processor = ImageProcessor()
        self.preview_photo: Optional[ImageTk.PhotoImage] = None
        self.settings_window: Optional[tk.Toplevel] = None
        self.tooltips: list[Tooltip] = []
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None

        self.threshold_var = tk.DoubleVar(value=self.processor.config.hotspot_percentile)
        self.min_cluster_var = tk.IntVar(value=self.processor.config.min_cluster_size)
        self.opening_var = tk.IntVar(value=self.processor.config.opening_iterations)
        self.closing_var = tk.IntVar(value=self.processor.config.closing_iterations)

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()

        self.threshold_display_var = tk.StringVar()
        self.min_cluster_display_var = tk.StringVar()
        self.opening_display_var = tk.StringVar()
        self.closing_display_var = tk.StringVar()

        self.preview_caption_var = tk.StringVar(value="Preview will appear after processing an image.")
        self.preview_hint_var = tk.StringVar(
            value="Adjust settings to refine detection. Use Settings to view recommended ranges."
        )
        self.status_var = tk.StringVar()

        self._build_style()
        self._build_layout()
        self._refresh_settings_labels()
        self._bind_shortcuts()
        self._update_status("Drop a folder of RJPG images or choose one to begin.")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        try:
            self._preview_resample = Image.Resampling.LANCZOS
        except AttributeError:  # pragma: no cover - Pillow < 9
            self._preview_resample = Image.LANCZOS

    # ------------------------------------------------------------------
    # GUI construction helpers
    # ------------------------------------------------------------------

    def _create_root(self) -> tuple[tk.Tk, bool]:
        dnd_available = False
        if TkinterDnD is not None:
            try:
                root = TkinterDnD.Tk()
            except Exception as exc:
                print(
                    "Warning: TkinterDnD could not be initialised. Drag-and-drop support will be disabled.",
                    file=sys.stderr,
                )
                print(f"Reason: {exc}", file=sys.stderr)
                root = tk.Tk()
            else:
                dnd_available = DND_FILES is not None
        else:
            root = tk.Tk()
        root.title("Thermal Delamination Detector")
        root.geometry("1200x720")
        root.minsize(1100, 640)
        return root, dnd_available

    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.root.configure(background="#eef1eb")
        self.root.option_add("*Font", "Segoe UI 11")
        self.root.option_add("*TButton.padding", 10)
        self.root.option_add("*TEntry*FieldBackground", "#ffffff")

        style.configure("TFrame", background="#eef1eb")
        style.configure("TLabel", background="#eef1eb", foreground="#0F3320")

        style.configure(
            "Header.TFrame",
            background="#0F3320",
            padding=(24, 18),
        )
        style.configure(
            "Header.TLabel",
            background="#0F3320",
            foreground="#f5f7f2",
            font=("Segoe UI", 20, "bold"),
        )
        style.configure(
            "Subheader.TLabel",
            background="#0F3320",
            foreground="#dcebd2",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Card.TFrame",
            background="#f7f9f5",
            relief="flat",
            padding=18,
        )
        style.configure(
            "CardTitle.TLabel",
            background="#f7f9f5",
            foreground="#0F3320",
            font=("Segoe UI", 14, "bold"),
        )
        style.configure(
            "StepNumber.TLabel",
            background="#f7f9f5",
            foreground="#84BD00",
            font=("Segoe UI", 10, "bold"),
        )
        style.configure(
            "Hint.TLabel",
            background="#f7f9f5",
            foreground="#427829",
            font=("Segoe UI", 10),
            wraplength=320,
        )
        style.configure(
            "PreviewCaption.TLabel",
            background="#f7f9f5",
            foreground="#0F3320",
            font=("Segoe UI", 12, "bold"),
        )
        style.configure(
            "Status.TLabel",
            background="#f7f9f5",
            foreground="#0F3320",
            font=("Segoe UI", 10),
            wraplength=260,
        )

        style.configure(
            "TButton",
            background="#427829",
            foreground="#f5f7f2",
            padding=10,
        )
        style.map(
            "TButton",
            background=[("active", "#2f581e"), ("disabled", "#9fb39f")],
            foreground=[("disabled", "#e0e0e0")],
        )

        style.configure(
            "Accent.TButton",
            background="#84BD00",
            foreground="#0F3320",
            padding=12,
            font=("Segoe UI", 11, "bold"),
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#6ea200"), ("disabled", "#c5dca0")],
            foreground=[("disabled", "#4f5b47")],
        )

        style.configure("Horizontal.TScale", background="#f7f9f5")
        style.configure("Horizontal.TProgressbar", troughcolor="#dbe4d7", background="#84BD00")

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, style="Header.TFrame")
        header.grid(column=0, row=0, sticky="ew")
        header.columnconfigure(0, weight=1)

        title = ttk.Label(header, text="Thermal Delamination Detector", style="Header.TLabel")
        title.grid(column=0, row=0, sticky="w")

        subtitle = ttk.Label(
            header,
            text="Guided workflow: choose your thermal set, inspect the preview, then export annotated results.",
            style="Subheader.TLabel",
        )
        subtitle.grid(column=0, row=1, sticky="w", pady=(4, 0))

        self.settings_button = ttk.Button(
            header,
            text="Processing Settings",
            style="Accent.TButton",
            command=self._open_settings_window,
        )
        self.settings_button.grid(column=1, row=0, rowspan=2, sticky="e", padx=(12, 0))
        self._add_tooltip(
            self.settings_button,
            "Open processing settings to tweak detection sensitivity with recommended ranges.",
        )

        main = ttk.Frame(self.root, padding=(24, 20, 24, 24))
        main.grid(column=0, row=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=3)
        main.columnconfigure(2, weight=1)
        main.rowconfigure(0, weight=1)

        self._build_step_one(main)
        self._build_step_two(main)
        self._build_step_three(main)

    def _build_step_one(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.grid(column=0, row=0, sticky="nsew", padx=(0, 16))
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="Step 1", style="StepNumber.TLabel").grid(column=0, row=0, sticky="w")
        ttk.Label(frame, text="Choose thermal input", style="CardTitle.TLabel").grid(
            column=0, row=1, sticky="w", pady=(4, 10)
        )
        ttk.Label(
            frame,
            text="Select the folder that contains your RJPG thermal captures. You can also drag and drop a folder anywhere in the window.",
            style="Hint.TLabel",
        ).grid(column=0, row=2, sticky="w")

        self.input_entry = ttk.Entry(frame, textvariable=self.input_var)
        self.input_entry.grid(column=0, row=3, sticky="ew", pady=(12, 6))
        self._add_tooltip(self.input_entry, "Folder containing the thermal RJPG images you want to analyse.")

        browse_btn = ttk.Button(frame, text="Browse for folder", command=self._choose_input_folder)
        browse_btn.grid(column=0, row=4, sticky="ew")
        self._add_tooltip(browse_btn, "Browse your computer to pick the folder of thermal images.")

        next_btn = ttk.Button(frame, text="Next → Preview", command=lambda: self.preview_canvas.focus_set())
        next_btn.grid(column=0, row=5, sticky="ew", pady=(18, 0))
        self._add_tooltip(
            next_btn,
            "Move to the preview area. The first image will be processed automatically once selected.",
        )

        ttk.Label(
            frame,
            text="Ideal input: a consistent inspection set with similar exposure for best hotspot comparison.",
            style="Hint.TLabel",
        ).grid(column=0, row=6, sticky="w", pady=(10, 0))

        if self._dnd_available and DND_FILES is not None:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._handle_drop)

    def _build_step_two(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.grid(column=1, row=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(3, weight=1)

        ttk.Label(frame, text="Step 2", style="StepNumber.TLabel").grid(column=0, row=0, sticky="w")
        ttk.Label(frame, text="Review detection preview", style="CardTitle.TLabel").grid(
            column=0, row=1, sticky="w", pady=(4, 6)
        )
        self.preview_hint_label = ttk.Label(frame, textvariable=self.preview_hint_var, style="Hint.TLabel")
        self.preview_hint_label.grid(column=0, row=2, sticky="w")

        self.preview_canvas = tk.Canvas(frame, background="#dbe4d7", highlightthickness=0)
        self.preview_canvas.grid(column=0, row=3, sticky="nsew", pady=(12, 12))
        self.preview_canvas.create_text(
            24,
            24,
            anchor="nw",
            text="Preview will appear here once an image is processed.",
            fill="#0F3320",
            font=("Segoe UI", 12),
            width=540,
            tags=("placeholder",),
        )
        self._add_tooltip(
            self.preview_canvas,
            "Displays the most recent processed thermal image with detected hotspots highlighted.",
        )

        caption = ttk.Label(frame, textvariable=self.preview_caption_var, style="PreviewCaption.TLabel")
        caption.grid(column=0, row=4, sticky="w")

        controls = ttk.Frame(frame, style="Card.TFrame")
        controls.grid(column=0, row=5, sticky="ew", pady=(8, 0))
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)

        refresh_btn = ttk.Button(controls, text="Refresh preview", command=self._refresh_preview)
        refresh_btn.grid(column=0, row=0, sticky="ew", padx=(0, 8))
        self._add_tooltip(
            refresh_btn,
            "Re-run preview processing using the first image in the selected folder with the current settings.",
        )

        next_export_btn = ttk.Button(controls, text="Next → Export", command=lambda: self.export_button.focus_set())
        next_export_btn.grid(column=1, row=0, sticky="ew")
        self._add_tooltip(next_export_btn, "Continue to export your annotated results to a folder.")

    def _build_step_three(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.grid(column=2, row=0, sticky="nsew", padx=(16, 0))
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="Step 3", style="StepNumber.TLabel").grid(column=0, row=0, sticky="w")
        ttk.Label(frame, text="Export annotated images", style="CardTitle.TLabel").grid(
            column=0, row=1, sticky="w", pady=(4, 6)
        )
        ttk.Label(
            frame,
            text="Choose where the processed overlays should be saved. Leave blank to create an \"output\" folder next to your input images.",
            style="Hint.TLabel",
        ).grid(column=0, row=2, sticky="w")

        self.output_entry = ttk.Entry(frame, textvariable=self.output_var)
        self.output_entry.grid(column=0, row=3, sticky="ew", pady=(12, 6))
        self._add_tooltip(self.output_entry, "Optional destination for exported overlays. Leave empty to use an auto-created folder.")

        choose_btn = ttk.Button(frame, text="Choose export location", command=self._choose_output_folder)
        choose_btn.grid(column=0, row=4, sticky="ew")
        self._add_tooltip(choose_btn, "Pick a folder where annotated results should be written.")

        self.export_button = ttk.Button(
            frame,
            text="Export annotated images",
            style="Accent.TButton",
            command=self._process_folder,
        )
        self.export_button.grid(column=0, row=5, sticky="ew", pady=(24, 0))
        self._add_tooltip(
            self.export_button,
            "Run detection on the entire folder and save annotated copies plus metadata into the export folder.",
        )

        ttk.Label(
            frame,
            text="Ideal: export to a dedicated project folder for easier QA and traceability.",
            style="Hint.TLabel",
        ).grid(column=0, row=6, sticky="w", pady=(10, 0))

        self.progress = ttk.Progressbar(frame, orient="horizontal", mode="determinate")
        self.progress.grid(column=0, row=7, sticky="ew", pady=(16, 0))
        self._add_tooltip(self.progress, "Visual indicator of export progress across your image set.")

        ttk.Label(frame, textvariable=self.status_var, style="Status.TLabel").grid(
            column=0,
            row=8,
            sticky="w",
            pady=(16, 0),
        )

    def _add_tooltip(self, widget: tk.Widget, text: str) -> None:
        tooltip = Tooltip(widget, text)
        self.tooltips.append(tooltip)

    def _refresh_preview(self) -> None:
        if not self.state.input_folder:
            messagebox.showinfo("Select images", "Choose an input folder before refreshing the preview.")
            return
        first_image = next(discover_images(self.state.input_folder), None)
        if first_image:
            self._update_preview(first_image)
            self._update_status("Preview updated. Adjust settings if hotspots are too loose or too strict.")
        else:
            self._update_status("No supported images found in the selected folder.")

    def _open_settings_window(self) -> None:
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.focus_set()
            return

        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title("Processing Settings")
        self.settings_window.configure(background="#eef1eb")
        self.settings_window.resizable(False, False)
        self.settings_window.transient(self.root)
        self.settings_window.grab_set()
        self.settings_window.protocol("WM_DELETE_WINDOW", self._close_settings_window)

        container = ttk.Frame(self.settings_window, style="Card.TFrame")
        container.grid(column=0, row=0, sticky="nsew", padx=16, pady=16)
        container.columnconfigure(0, weight=1)

        ttk.Label(container, text="Processing settings", style="CardTitle.TLabel").grid(
            column=0, row=0, sticky="w"
        )
        ttk.Label(
            container,
            text="Fine-tune detection sensitivity. Ideal ranges are noted beside each control.",
            style="Hint.TLabel",
        ).grid(column=0, row=1, sticky="w", pady=(6, 12))

        ttk.Label(container, textvariable=self.threshold_display_var, style="PreviewCaption.TLabel").grid(
            column=0, row=2, sticky="w"
        )
        threshold_scale = ttk.Scale(
            container,
            from_=70,
            to=99.9,
            orient="horizontal",
            variable=self.threshold_var,
            command=lambda _: self._on_parameters_changed(),
        )
        threshold_scale.grid(column=0, row=3, sticky="ew", pady=(4, 12))
        self._add_tooltip(
            threshold_scale,
            "Percentile cutoff: higher values isolate only the hottest 2–15% of pixels (ideal 85–97%).",
        )

        ttk.Label(container, textvariable=self.min_cluster_display_var, style="PreviewCaption.TLabel").grid(
            column=0, row=4, sticky="w"
        )
        min_cluster_spin = ttk.Spinbox(
            container,
            from_=10,
            to=5000,
            increment=10,
            textvariable=self.min_cluster_var,
            command=self._on_parameters_changed,
            width=8,
        )
        min_cluster_spin.grid(column=0, row=5, sticky="ew", pady=(4, 12))
        self._bind_spinbox_updates(min_cluster_spin)
        self._add_tooltip(
            min_cluster_spin,
            "Minimum connected hotspot size in pixels. Ideal range: 50–400 px depending on sensor resolution.",
        )

        ttk.Label(container, text="Morphological clean-up", style="PreviewCaption.TLabel").grid(
            column=0, row=6, sticky="w", pady=(0, 4)
        )
        ttk.Label(
            container,
            text="Opening removes isolated noise; closing fills small gaps. Ideal: 1–2 iterations for each.",
            style="Hint.TLabel",
        ).grid(column=0, row=7, sticky="w")

        morph_frame = ttk.Frame(container, style="Card.TFrame")
        morph_frame.grid(column=0, row=8, sticky="ew", pady=(10, 12))
        morph_frame.columnconfigure((0, 1), weight=1)

        ttk.Label(morph_frame, textvariable=self.opening_display_var, style="Hint.TLabel").grid(
            column=0, row=0, sticky="w"
        )
        ttk.Label(morph_frame, textvariable=self.closing_display_var, style="Hint.TLabel").grid(
            column=1, row=0, sticky="w"
        )

        opening_spin = ttk.Spinbox(
            morph_frame,
            from_=0,
            to=5,
            textvariable=self.opening_var,
            command=self._on_parameters_changed,
            width=5,
        )
        opening_spin.grid(column=0, row=1, sticky="ew", pady=(4, 0), padx=(0, 6))
        self._bind_spinbox_updates(opening_spin)
        self._add_tooltip(opening_spin, "Opening iterations remove salt noise. Ideal range: 0–2.")

        closing_spin = ttk.Spinbox(
            morph_frame,
            from_=0,
            to=5,
            textvariable=self.closing_var,
            command=self._on_parameters_changed,
            width=5,
        )
        closing_spin.grid(column=1, row=1, sticky="ew", pady=(4, 0), padx=(6, 0))
        self._bind_spinbox_updates(closing_spin)
        self._add_tooltip(closing_spin, "Closing iterations seal pinholes in hotspots. Ideal range: 1–3.")

        done_btn = ttk.Button(container, text="Done", command=self._close_settings_window)
        done_btn.grid(column=0, row=9, sticky="e", pady=(12, 0))
        self._add_tooltip(done_btn, "Close settings and continue with the guided workflow.")

        self._refresh_settings_labels()

    def _close_settings_window(self) -> None:
        if self.settings_window is not None:
            self.settings_window.destroy()
            self.settings_window = None

    def _bind_spinbox_updates(self, widget: ttk.Spinbox) -> None:
        widget.bind("<FocusOut>", lambda _event: self._on_parameters_changed())
        widget.bind("<Return>", lambda _event: self._on_parameters_changed())

    def _refresh_settings_labels(self) -> None:
        self.threshold_display_var.set(
            f"Hotspot percentile: {self.threshold_var.get():.1f}% (Ideal 85–97%)"
        )
        self.min_cluster_display_var.set(
            f"Minimum hotspot size: {self.min_cluster_var.get()} px (Ideal 50–400 px)"
        )
        self.opening_display_var.set(
            f"Opening {self.opening_var.get()}× (Ideal 0–2)"
        )
        self.closing_display_var.set(
            f"Closing {self.closing_var.get()}× (Ideal 1–3)"
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
        self._update_status(
            f"Loaded {len(images)} images. Review the preview in Step 2 and export when satisfied."
        )
        self.preview_caption_var.set("Generating preview…")
        self.preview_hint_var.set("Creating a quick preview with the current settings.")
        self._update_preview(images[0])

    def _on_parameters_changed(self) -> None:
        self._refresh_settings_labels()
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
            self.preview_caption_var.set("Preview unavailable")
            self.preview_hint_var.set("Preview unavailable. Check the console for details and adjust settings if needed.")
            return

        preview = result.overlay_image.copy()
        preview.thumbnail((700, 520), self._preview_resample)
        self.preview_photo = ImageTk.PhotoImage(preview)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(20, 20, anchor="nw", image=self.preview_photo)
        self.preview_caption_var.set(f"Preview • {image_path.name}")
        self.preview_hint_var.set(
            "Lime overlays highlight pixels above the percentile threshold. Adjust the settings if areas look over- or under-detected."
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
        self.export_button.configure(state=tk.DISABLED)
        self.progress.configure(value=0, maximum=len(images))
        self._update_status("Exporting annotated images…")
        self.preview_hint_var.set("Export in progress. You can monitor progress from the status panel on the right.")

        self._stop_event.clear()
        self._worker_thread = threading.Thread(
            target=self._process_images_worker,
            args=(images, output_folder),
            daemon=True,
        )
        self._worker_thread.start()

    def _process_images_worker(self, images: list[Path], output_folder: Path) -> None:
        completed = False
        try:
            for idx, image_path in enumerate(images, start=1):
                if self._stop_event.is_set():
                    break
                result = self.processor.process_image(image_path)
                if self._stop_event.is_set():
                    break
                destination = output_folder / f"{image_path.stem}_processed.jpg"
                save_with_metadata(result.overlay_image, destination, result.exif_bytes)
                self._schedule_ui(self.progress.configure, value=idx)
            else:
                completed = True
            if self._stop_event.is_set():
                self._update_status_async("Processing cancelled.")
            elif completed:
                self._update_status_async(
                    f"Export complete. Annotated images saved to {output_folder}."
                )
        except Exception as exc:  # pragma: no cover - user feedback path
            self._update_status_async(f"Processing stopped: {exc}")
            self._schedule_ui(lambda: messagebox.showerror("Processing error", str(exc)))
        finally:
            self._schedule_ui(self._processing_finished)

    def _processing_finished(self) -> None:
        try:
            self.state.processing = False
            self.export_button.configure(state=tk.NORMAL)
            self.progress.configure(value=0)
            if self.state.latest_result is not None and not self._stop_event.is_set():
                self.preview_hint_var.set(
                    "Export finished. Adjust settings if needed and refresh the preview to validate the changes."
                )
        except tk.TclError:
            pass
        finally:
            self._worker_thread = None
            if not self.state.processing and not self._stop_event.is_set():
                self._stop_event.clear()

    # ------------------------------------------------------------------
    # Status helpers
    # ------------------------------------------------------------------

    def _update_status(self, message: str) -> None:
        self.state.status_message = message
        self.status_var.set(message)

    def _update_status_async(self, message: str) -> None:
        self._schedule_ui(self._update_status, message)

    def _schedule_ui(self, func: Callable[..., object], *args, **kwargs) -> None:
        def _callback() -> None:
            try:
                func(*args, **kwargs)
            except tk.TclError:
                pass

        try:
            self.root.after(0, _callback)
        except tk.TclError:
            pass

    def _on_close(self) -> None:
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._update_status("Shutting down…")
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        self.root.mainloop()


def _display_available() -> bool:
    """Return ``True`` if Tk can successfully open a display."""

    global _DISPLAY_AVAILABLE
    if _DISPLAY_AVAILABLE is not None:
        return _DISPLAY_AVAILABLE

    try:
        root = tk.Tk()
    except tk.TclError:
        _DISPLAY_AVAILABLE = False
        return _DISPLAY_AVAILABLE
    else:
        try:
            root.withdraw()
        finally:
            root.destroy()
            # ``tk`` caches the default root. Reset it so the real GUI
            # instance created later does not interact with this probe.
            try:  # pragma: no cover - attribute may not exist
                tk._default_root = None  # type: ignore[attr-defined]
            except Exception:  # pragma: no cover - defensive safety net
                pass
        _DISPLAY_AVAILABLE = True
        return _DISPLAY_AVAILABLE


def _show_dependency_error(
    title: str, message: str, *, display_available: bool | None = None
) -> None:
    if display_available is None:
        display_available = _display_available()

    if not display_available:
        print(f"ERROR: {message}", file=sys.stderr)
        return

    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except tk.TclError:
        print(f"ERROR: {message}", file=sys.stderr)


def _format_dependency_message(exc: ModuleNotFoundError) -> str:
    missing = exc.name or "a required library"
    if missing in {"numpy", "PIL", "Pillow"}:
        package = "pillow" if missing in {"PIL", "Pillow"} else missing
        return (
            f"The {missing} library is required to run the Thermal Delamination Detector. "
            f"Install it with `pip install {package}` and restart the application."
        )
    return (
        "A required dependency could not be imported. "
        "Install the missing package and restart the application."
    )


def launch() -> None:
    if _PIL_IMPORT_ERROR is not None:
        message = _format_dependency_message(_PIL_IMPORT_ERROR)
        _show_dependency_error("Missing dependency", message)
        raise SystemExit(1) from _PIL_IMPORT_ERROR

    if _DEPENDENCY_ERROR is not None:
        message = _format_dependency_message(_DEPENDENCY_ERROR)
        _show_dependency_error("Missing dependency", message)
        raise SystemExit(1) from _DEPENDENCY_ERROR

    if not _display_available():
        message = (
            "The graphical interface could not be started because Tk was unable to initialise. "
            "Ensure that a display server is available (for example by setting the DISPLAY "
            "environment variable) before launching the application.\n\n"
            "If you are running the tool on a headless machine, launch the batch processor instead "
            "with `python main.py --input <folder-with-images>` (optionally add --output to choose "
            "the destination)."
        )
        _show_dependency_error(
            "Display unavailable", message, display_available=False
        )
        raise SystemExit(1)

    try:
        app = ThermalDelamApp()
    except tk.TclError as exc:  # pragma: no cover - depends on runtime environment
        message = (
            "The graphical interface could not be started because Tk was unable to initialise. "
            "Ensure that a display server is available (for example by setting the DISPLAY "
            "environment variable) before launching the application.\n\n"
            "If you are running the tool on a headless machine, launch the batch processor instead "
            "with `python main.py --input <folder-with-images>` (optionally add --output to choose "
            "the destination)."
        )
        _show_dependency_error("Display unavailable", message)
        raise SystemExit(1) from exc

    app.run()


if __name__ == "__main__":  # pragma: no cover - manual execution entry point
    launch()
