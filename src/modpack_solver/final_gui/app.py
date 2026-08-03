"""Tkinter application for the focused modpack repair workflow."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from modpack_solver.solver.profiles import get_weight_profile, list_weight_profiles
from modpack_solver.final_gui.exports import save_json_report, save_text_report
from modpack_solver.final_gui.presenter import (
    DEFAULT_CACHE,
    analyze_loaded_case,
    build_result_summary,
    format_explanation,
    format_graph_summary,
    format_issues,
    format_repair_plan,
    format_repair_trace,
    list_builtin_samples,
    load_builtin_sample,
    load_json_into_state,
    load_modrinth_url_into_state,
    load_mrpack_into_state,
    load_project_list_into_state,
)
from modpack_solver.final_gui.state import FinalGuiState
from modpack_solver.final_gui.theme import COLORS, configure_ttk_style
from modpack_solver.final_gui.widgets import create_output_text, set_output_text


class FinalGuiApplication:
    """Coordinate input, analysis, concise results, and optional technical details."""

    def __init__(
        self,
        root: tk.Tk,
        *,
        offline: bool = True,
        cache_dir: str | Path = DEFAULT_CACHE,
        sample: str | None = None,
    ) -> None:
        self.root = root
        self.cache_dir = Path(cache_dir)
        self.state = FinalGuiState(offline_mode=offline)
        self.output_widgets: dict[str, tk.Text] = {}
        self._busy = False

        root.title("Minecraft Modpack Repair Solver")
        root.geometry("980x760")
        root.minsize(760, 600)
        root.configure(background=COLORS["parchment"])
        configure_ttk_style(ttk.Style(root))
        self._build_header()
        self._build_scrollable_workspace()
        self._build_status_bar()
        self._bind_shortcuts()
        self._refresh_controls()
        if sample:
            fixture = sample if sample.endswith(".json") else f"{sample}.json"
            root.after(50, lambda: self._load_sample(fixture))

    def _build_header(self) -> None:
        frame = ttk.Frame(self.root, padding=(22, 16, 22, 8))
        frame.pack(fill="x")
        ttk.Label(frame, text="Modpack Repair Solver", style="Header.TLabel").pack(anchor="w")
        ttk.Label(
            frame,
            text="Load a Fabric modpack, check its metadata, and receive a minimum-disruption repair plan.",
        ).pack(anchor="w", pady=(3, 0))

    def _build_scrollable_workspace(self) -> None:
        container = ttk.Frame(self.root)
        container.pack(fill="both", expand=True, padx=18, pady=6)
        canvas = tk.Canvas(container, background=COLORS["parchment"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        self.workspace = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=self.workspace, anchor="nw")
        self.workspace.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window, width=event.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._build_input_section()
        self._build_analysis_section()
        self._build_result_section()
        self._build_advanced_section()
        self._build_limitation()

    def _build_input_section(self) -> None:
        frame = ttk.LabelFrame(self.workspace, text="1. Choose a modpack", padding=14)
        frame.pack(fill="x", pady=(0, 10))
        row = ttk.Frame(frame)
        row.pack(fill="x")
        ttk.Button(row, text="Choose .mrpack", command=self._open_mrpack, style="Primary.TButton").pack(side="left")
        ttk.Button(row, text="Open JSON Case", command=self._open_json).pack(side="left", padx=7)
        samples = list_builtin_samples()
        self.sample_var = tk.StringVar(value="missing_required_dependency.json")
        ttk.Combobox(row, textvariable=self.sample_var, values=samples, state="readonly", width=31).pack(side="left", padx=(12, 5))
        ttk.Button(row, text="Load Sample", command=lambda: self._load_sample()).pack(side="left")

        self.source_var = tk.StringVar(value="No modpack loaded yet.")
        ttk.Label(frame, textvariable=self.source_var, style="Status.TLabel", wraplength=860).pack(anchor="w", pady=(10, 5))

        self.other_methods_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame,
            text="Other input methods",
            variable=self.other_methods_var,
            command=self._toggle_other_methods,
        ).pack(anchor="w", pady=(4, 0))
        self.other_methods = ttk.Frame(frame, padding=(0, 8, 0, 0))
        self._build_other_input_methods(self.other_methods)

    def _build_other_input_methods(self, frame: ttk.Frame) -> None:
        ttk.Label(frame, text="Modrinth URL").grid(row=0, column=0, sticky="w")
        self.url_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.url_var).grid(row=0, column=1, sticky="ew", padx=7)
        ttk.Button(frame, text="Load URL", command=self._load_url).grid(row=0, column=2)
        ttk.Label(frame, text="Project IDs or slugs").grid(row=1, column=0, sticky="nw", pady=(8, 0))
        self.project_text = tk.Text(frame, height=3, width=45, font=("Consolas", 10))
        self.project_text.grid(row=1, column=1, sticky="ew", padx=7, pady=(8, 0))
        ttk.Button(frame, text="Load Project List", command=self._load_project_list).grid(row=1, column=2, pady=(8, 0))
        settings = ttk.Frame(frame)
        settings.grid(row=2, column=1, sticky="w", padx=7, pady=(7, 0))
        ttk.Label(settings, text="Minecraft version").pack(side="left")
        self.minecraft_var = tk.StringVar(value="1.20.1")
        ttk.Entry(settings, textvariable=self.minecraft_var, width=10).pack(side="left", padx=(5, 12))
        ttk.Label(settings, text="Loader").pack(side="left")
        self.loader_var = tk.StringVar(value="fabric")
        ttk.Combobox(settings, textvariable=self.loader_var, values=["fabric"], state="readonly", width=9).pack(side="left", padx=5)
        frame.columnconfigure(1, weight=1)

    def _build_analysis_section(self) -> None:
        frame = ttk.LabelFrame(self.workspace, text="2. Analyze", padding=14)
        frame.pack(fill="x", pady=(0, 10))
        self.analyze_button = ttk.Button(frame, text="Analyze Modpack", command=self._analyze, style="Primary.TButton")
        self.analyze_button.pack(side="left")
        self.progress = ttk.Progressbar(frame, mode="indeterminate", length=190)
        self.progress.pack(side="left", padx=12)
        self.analysis_var = tk.StringVar(value="Choose an input to begin.")
        ttk.Label(frame, textvariable=self.analysis_var).pack(side="left", fill="x", expand=True)

    def _build_result_section(self) -> None:
        self.result_frame = ttk.LabelFrame(self.workspace, text="3. Result", padding=14)
        self.result_frame.pack(fill="both", expand=True, pady=(0, 10))
        self.banner = tk.Label(
            self.result_frame,
            text="Ready for a modpack",
            anchor="w",
            padx=12,
            pady=9,
            font=("Segoe UI", 13, "bold"),
            background=COLORS["stone_light"],
            foreground=COLORS["text"],
        )
        self.banner.pack(fill="x")
        self.result_message_var = tk.StringVar(value="The recommended repair plan will appear here after analysis.")
        ttk.Label(self.result_frame, textvariable=self.result_message_var, wraplength=850).pack(anchor="w", pady=(10, 8))
        self.metrics_var = tk.StringVar(value="Cost: -     Preserved: -     Removals: -     Version changes: -")
        ttk.Label(self.result_frame, textvariable=self.metrics_var, style="Status.TLabel").pack(anchor="w", pady=(0, 8))
        self.actions_text = create_output_text(self.result_frame, font_size=11)
        self.actions_text.configure(height=7)
        self.actions_text.pack(fill="both", expand=True)
        buttons = ttk.Frame(self.result_frame)
        buttons.pack(fill="x", pady=(10, 0))
        self.export_text_button = ttk.Button(buttons, text="Export Text Report", command=self._export_text)
        self.export_text_button.pack(side="left")
        self.export_json_button = ttk.Button(buttons, text="Export JSON Report", command=self._export_json)
        self.export_json_button.pack(side="left", padx=6)
        self.copy_button = ttk.Button(buttons, text="Copy Repair Plan", command=self._copy_plan)
        self.copy_button.pack(side="left")
        ttk.Button(buttons, text="Clear / Analyze Another", command=self._clear).pack(side="right")

    def _build_advanced_section(self) -> None:
        control = ttk.Frame(self.workspace)
        control.pack(fill="x")
        self.advanced_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            control,
            text="Show advanced details",
            variable=self.advanced_var,
            command=self._toggle_advanced,
        ).pack(anchor="w")
        self.advanced_frame = ttk.Frame(self.workspace)
        self.advanced_notebook = ttk.Notebook(self.advanced_frame)
        self.advanced_notebook.pack(fill="both", expand=True)
        for title, key in (
            ("Compatibility Issues", "issues"),
            ("Full Explanation", "explanation"),
            ("Repair Trace", "trace"),
            ("Dependency Graph Summary", "graph"),
        ):
            tab = ttk.Frame(self.advanced_notebook, padding=8)
            self.advanced_notebook.add(tab, text=title)
            output = create_output_text(tab, font_size=10)
            output.pack(fill="both", expand=True)
            self.output_widgets[key] = output
        settings = ttk.Frame(self.advanced_notebook, padding=14)
        self.advanced_notebook.add(settings, text="Weight Profile / Metadata")
        ttk.Label(settings, text="Repair weight profile", style="Subheader.TLabel").pack(anchor="w")
        self.profile_var = tk.StringVar(value=self.state.selected_profile_id)
        profiles = [profile.profile_id for profile in list_weight_profiles()]
        box = ttk.Combobox(settings, textvariable=self.profile_var, values=profiles, state="readonly", width=24)
        box.pack(anchor="w", pady=(6, 10))
        box.bind("<<ComboboxSelected>>", self._profile_changed)
        self.profile_description_var = tk.StringVar()
        ttk.Label(settings, textvariable=self.profile_description_var, wraplength=780).pack(anchor="w")
        self.live_var = tk.BooleanVar(value=not self.state.offline_mode)
        ttk.Checkbutton(
            settings,
            text="Allow live Modrinth metadata when cache entries are missing",
            variable=self.live_var,
            command=self._toggle_live_mode,
        ).pack(anchor="w", pady=(14, 0))
        self._profile_changed()

    def _build_limitation(self) -> None:
        ttk.Label(
            self.workspace,
            text=(
                "This tool analyzes metadata and recommends changes; it does not install mods or "
                "guarantee that Minecraft will launch."
            ),
            wraplength=880,
        ).pack(anchor="w", pady=(10, 14))

    def _build_status_bar(self) -> None:
        frame = ttk.Frame(self.root, padding=(20, 4, 20, 10))
        frame.pack(fill="x")
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self.status_var, style="Status.TLabel").pack(side="left")
        self.mode_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.mode_var).pack(side="right")
        self._refresh_mode_label()

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-o>", lambda _event: self._open_mrpack())
        self.root.bind("<Control-Return>", lambda _event: self._analyze())
        self.root.bind("<Control-s>", lambda _event: self._export_text())

    def _open_mrpack(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Modrinth modpacks", "*.mrpack"), ("ZIP archives", "*.zip")])
        if path:
            self._start_load(lambda: load_mrpack_into_state(self.state, path, cache_dir=self.cache_dir, allow_live=self.live_var.get()))

    def _open_json(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON cases", "*.json"), ("All files", "*.*")])
        if path:
            self._start_load(lambda: load_json_into_state(self.state, path))

    def _load_sample(self, fixture: str | None = None) -> None:
        name = fixture or self.sample_var.get()
        if name:
            self._start_load(lambda: load_builtin_sample(self.state, name))

    def _load_url(self) -> None:
        self._start_load(
            lambda: load_modrinth_url_into_state(
                self.state,
                self.url_var.get(),
                minecraft_version=self.minecraft_var.get(),
                loader=self.loader_var.get(),
                cache_dir=self.cache_dir,
                allow_live=self.live_var.get(),
            )
        )

    def _load_project_list(self) -> None:
        text = self.project_text.get("1.0", "end")
        self._start_load(
            lambda: load_project_list_into_state(
                self.state,
                text,
                self.minecraft_var.get(),
                self.loader_var.get(),
                cache_dir=self.cache_dir,
                allow_live=self.live_var.get(),
            )
        )

    def _start_load(self, operation: Callable[[], object]) -> None:
        self._run_background(operation, "Loading and resolving metadata...", self._after_load)

    def _after_load(self) -> None:
        case = self.state.loaded_case
        if case is None:
            return
        self.source_var.set(
            f"Loaded: {self.state.loaded_pack_name or self.state.loaded_source_label} | "
            f"{len(case.config.selected_mods)} entries | Minecraft {case.config.minecraft_version} | {case.config.loader}"
        )
        self.analysis_var.set("Input is ready for analysis.")
        self.status_var.set("Modpack loaded")
        self._reset_result()

    def _analyze(self) -> None:
        if not self.state.can_analyze or self._busy:
            return
        self.state.selected_profile_id = self.profile_var.get()
        self.state.begin_analysis()
        self._run_background(lambda: analyze_loaded_case(self.state), "Analyzing dependency metadata...", self._after_analysis)

    def _after_analysis(self) -> None:
        self.state.finish_analysis()
        summary = build_result_summary(self.state)
        colors = {
            "compatible": COLORS["success"],
            "repair_found": COLORS["technical"],
            "no_solution": COLORS["error"],
        }
        self.banner.configure(text=summary.title, background=colors[summary.status], foreground="white")
        self.result_message_var.set(summary.message)
        self.metrics_var.set(
            f"Cost: {summary.total_cost}     Preserved: {summary.preserved}     "
            f"Removals: {summary.removals}     Version changes: {summary.version_changes}"
        )
        set_output_text(self.actions_text, "\n".join(f"{index}. {action}" for index, action in enumerate(summary.actions, 1)))
        set_output_text(self.output_widgets["issues"], format_issues(self.state))
        set_output_text(self.output_widgets["explanation"], format_explanation(self.state))
        set_output_text(self.output_widgets["trace"], format_repair_trace(self.state))
        set_output_text(self.output_widgets["graph"], format_graph_summary(self.state))
        self.analysis_var.set("Analysis complete.")
        self.status_var.set("Repair analysis complete")

    def _run_background(self, operation: Callable[[], object], status: str, on_success: Callable[[], None]) -> None:
        if self._busy:
            return
        self._set_busy(True, status)

        def worker() -> None:
            try:
                operation()
            except Exception as exc:
                self.root.after(0, lambda error=exc: self._show_error(error))
            else:
                self.root.after(0, on_success)
            finally:
                self.root.after(0, lambda: self._set_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _set_busy(self, busy: bool, status: str | None = None) -> None:
        self._busy = busy
        if busy:
            self.progress.start(12)
            self.status_var.set(status or "Working...")
        else:
            self.progress.stop()
            if self.state.analysis_in_progress:
                self.state.finish_analysis()
        self._refresh_controls()

    def _show_error(self, error: Exception) -> None:
        self.state.analysis_in_progress = False
        self.analysis_var.set("The operation could not be completed.")
        self.status_var.set("Error")
        messagebox.showerror("Modpack Solver", str(error))

    def _refresh_controls(self) -> None:
        self.analyze_button.configure(state="normal" if self.state.can_analyze and not self._busy else "disabled")
        export_state = "normal" if self.state.can_export and not self._busy else "disabled"
        self.export_text_button.configure(state=export_state)
        self.export_json_button.configure(state=export_state)
        self.copy_button.configure(state=export_state)

    def _toggle_other_methods(self) -> None:
        if self.other_methods_var.get():
            self.other_methods.pack(fill="x")
        else:
            self.other_methods.pack_forget()

    def _toggle_advanced(self) -> None:
        visible = self.advanced_var.get()
        self.state.set_advanced_details_visible(visible)
        if visible:
            self.advanced_frame.pack(fill="both", expand=True, pady=(6, 0))
        else:
            self.advanced_frame.pack_forget()

    def _profile_changed(self, _event=None) -> None:
        profile = get_weight_profile(self.profile_var.get())
        self.state.selected_profile_id = profile.profile_id
        weights = profile.weights.model_dump(mode="json")
        values = ", ".join(f"{key.replace('_', ' ')}={value}" for key, value in weights.items())
        self.profile_description_var.set(f"{profile.description}\n\n{values}")

    def _toggle_live_mode(self) -> None:
        self.state.offline_mode = not self.live_var.get()
        self._refresh_mode_label()

    def _refresh_mode_label(self) -> None:
        self.mode_var.set("Metadata: offline cache" if self.state.offline_mode else "Metadata: live/cache-first")

    def _copy_plan(self) -> None:
        if not self.state.can_export:
            return
        text = format_repair_plan(self.state)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set("Repair plan copied to clipboard")

    def _export_text(self) -> None:
        if not self.state.can_export:
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text report", "*.txt")])
        if path:
            save_text_report(self.state, path)
            self.status_var.set(f"Text report saved: {path}")

    def _export_json(self) -> None:
        if not self.state.can_export:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON report", "*.json")])
        if path:
            save_json_report(self.state, path)
            self.status_var.set(f"JSON report saved: {path}")

    def _reset_result(self) -> None:
        self.banner.configure(text="Ready to analyze", background=COLORS["stone_light"], foreground=COLORS["text"])
        self.result_message_var.set("Select Analyze Modpack to check compatibility and search for a repair.")
        self.metrics_var.set("Cost: -     Preserved: -     Removals: -     Version changes: -")
        set_output_text(self.actions_text, "No repair actions yet.")
        for widget in self.output_widgets.values():
            set_output_text(widget, "Run an analysis to view these details.")

    def _clear(self) -> None:
        if self._busy:
            return
        self.state.clear()
        self.source_var.set("No modpack loaded yet.")
        self.analysis_var.set("Choose an input to begin.")
        self.status_var.set("Ready")
        self._reset_result()
        self._refresh_controls()


def launch_final_gui(*, offline: bool = True, cache_dir: str | Path = DEFAULT_CACHE, sample: str | None = None) -> None:
    root = tk.Tk()
    FinalGuiApplication(root, offline=offline, cache_dir=cache_dir, sample=sample)
    root.mainloop()
