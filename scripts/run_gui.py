"""Minimal local GUI prototype for the multi-stage modeling workflow."""

import json
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ai_3d_modeling_agent.gui.prototype import (
    build_round_inspector_sections,
    GuiLaunchConfig,
    GuiSavedSettings,
    build_multi_stage_command,
    extract_assembly_round_rows,
    extract_part_round_rows,
    extract_part_task_rows,
    find_assembly_round_detail,
    find_part_round_detail,
    format_history_detail,
    format_round_detail,
    generate_session_id,
    load_gui_settings,
    save_gui_settings,
    session_progress_path,
    summarize_progress,
)


class MultiStageGuiApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("AI 3D Modeling Agent Prototype")
        self.root.geometry("1400x860")
        self.runtime_root = REPO_ROOT / "data" / "runtime"

        self.process: subprocess.Popen | None = None
        self.progress_after_id: str | None = None
        self.log_after_id: str | None = None
        self.preview_image: tk.PhotoImage | None = None
        self.final_image: tk.PhotoImage | None = None
        self.reference_images: list[str] = []
        self.last_stdout_length = 0
        self.latest_progress_data: dict = {}
        self.selected_task_id = ""
        self.settings_visible = False
        self.last_stage_signature = ""
        self.last_feedback_seen = ""

        self.task_var = tk.StringVar(value="build a wooden chair")
        self.session_var = tk.StringVar(value=generate_session_id("gui"))
        self.endpoint_var = tk.StringVar(value="http://127.0.0.1:8080")
        self.model_var = tk.StringVar(value="local-model")
        self.part_rounds_var = tk.IntVar(value=3)
        self.assembly_rounds_var = tk.IntVar(value=3)
        self.use_blender_mcp_var = tk.BooleanVar(value=False)
        self.use_yolo_var = tk.BooleanVar(value=False)
        self.yolo_model_var = tk.StringVar(value="")
        self.yolo_viewpoints_var = tk.StringVar(value="front")

        self.status_var = tk.StringVar(value="idle")
        self.stage_var = tk.StringVar(value="")
        self.active_task_var = tk.StringVar(value="")
        self.completed_tasks_var = tk.StringVar(value="")
        self.detected_parts_var = tk.StringVar(value="")
        self.stop_reason_var = tk.StringVar(value="")
        self.capture_path_var = tk.StringVar(value="")
        self.final_capture_path_var = tk.StringVar(value="")

        self._build_layout()
        self._load_saved_settings()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(container)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        toolbar.columnconfigure(1, weight=1)

        ttk.Label(toolbar, text="AI 3D Modeling Agent", font=("Segoe UI", 14, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        session_bar = ttk.Frame(toolbar)
        session_bar.grid(row=0, column=1, sticky="w", padx=(18, 0))
        ttk.Label(session_bar, text="Session").pack(side=tk.LEFT)
        ttk.Label(session_bar, textvariable=self.session_var).pack(side=tk.LEFT, padx=(8, 12))
        ttk.Button(session_bar, text="New Session", command=self.create_new_session).pack(side=tk.LEFT)

        action_bar = ttk.Frame(toolbar)
        action_bar.grid(row=0, column=2, sticky="e")
        ttk.Button(action_bar, text="Start", command=self.start_run).pack(side=tk.LEFT)
        ttk.Button(action_bar, text="Stop", command=self.stop_run).pack(side=tk.LEFT, padx=8)
        self.settings_toggle_button = ttk.Button(action_bar, text="Show Settings", command=self.toggle_settings_panel)
        self.settings_toggle_button.pack(side=tk.LEFT)
        ttk.Label(action_bar, text="Status").pack(side=tk.LEFT, padx=(16, 6))
        ttk.Label(action_bar, textvariable=self.status_var).pack(side=tk.LEFT)

        main = ttk.Frame(container)
        main.grid(row=1, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=0)
        main.rowconfigure(0, weight=1)

        left_panel = ttk.Frame(main)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_panel.columnconfigure(0, weight=1)
        left_panel.rowconfigure(1, weight=3)
        left_panel.rowconfigure(2, weight=2)

        composer = ttk.LabelFrame(left_panel, text="Prompt", padding=10)
        composer.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        composer.columnconfigure(0, weight=1)
        composer.columnconfigure(1, weight=0)
        ttk.Entry(composer, textvariable=self.task_var).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Button(composer, text="Add Reference Images", command=self.add_reference_images).grid(
            row=0, column=1, sticky="e"
        )
        self.reference_images_var = tk.StringVar(value="")
        ttk.Label(composer, textvariable=self.reference_images_var, wraplength=520, justify=tk.LEFT).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )
        self.reference_text_box = scrolledtext.ScrolledText(composer, height=4, wrap=tk.WORD)
        self.reference_text_box.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        output_frame = ttk.LabelFrame(left_panel, text="Activity", padding=10)
        output_frame.grid(row=1, column=0, sticky="nsew")
        output_frame.rowconfigure(0, weight=1)
        output_frame.columnconfigure(0, weight=1)
        self.output_box = scrolledtext.ScrolledText(output_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.output_box.grid(row=0, column=0, sticky="nsew")
        self._configure_output_styles()

        notebook = ttk.Notebook(left_panel)
        notebook.grid(row=2, column=0, sticky="nsew", pady=(10, 0))

        progress_frame = ttk.Frame(notebook, padding=10)
        progress_frame.columnconfigure(1, weight=1)
        progress_frame.rowconfigure(8, weight=1)
        notebook.add(progress_frame, text="Progress")

        self._add_value(progress_frame, 0, "Status", self.status_var)
        self._add_value(progress_frame, 1, "Stage", self.stage_var)
        self._add_value(progress_frame, 2, "Active Task", self.active_task_var)
        self._add_value(progress_frame, 3, "Completed", self.completed_tasks_var)
        self._add_value(progress_frame, 4, "Detected Parts", self.detected_parts_var)
        self._add_value(progress_frame, 5, "Latest Capture", self.capture_path_var)
        self._add_value(progress_frame, 6, "Final Capture", self.final_capture_path_var)

        ttk.Label(progress_frame, text="Stop Reason").grid(row=7, column=0, sticky="nw", pady=4)
        ttk.Label(progress_frame, textvariable=self.stop_reason_var, wraplength=360, justify=tk.LEFT).grid(
            row=7, column=1, sticky="nw", pady=4
        )

        ttk.Label(progress_frame, text="Latest Feedback").grid(row=8, column=0, sticky="nw", pady=4)
        self.feedback_box = scrolledtext.ScrolledText(progress_frame, height=8, wrap=tk.WORD, state=tk.DISABLED)
        self.feedback_box.grid(row=8, column=1, sticky="nsew", pady=4)

        history_frame = ttk.Frame(notebook, padding=10)
        history_frame.columnconfigure(0, weight=1)
        history_frame.rowconfigure(1, weight=1)
        history_frame.rowconfigure(3, weight=1)
        history_frame.rowconfigure(5, weight=1)
        history_frame.rowconfigure(7, weight=1)
        notebook.add(history_frame, text="History")

        ttk.Label(history_frame, text="Part Tasks").grid(row=0, column=0, sticky="w")
        self.part_task_tree = ttk.Treeview(
            history_frame,
            columns=("title", "status", "round", "approved"),
            show="headings",
            height=5,
        )
        self.part_task_tree.heading("title", text="Title")
        self.part_task_tree.heading("status", text="Status")
        self.part_task_tree.heading("round", text="Round")
        self.part_task_tree.heading("approved", text="Approved")
        self.part_task_tree.column("title", width=180)
        self.part_task_tree.column("status", width=80, anchor="center")
        self.part_task_tree.column("round", width=60, anchor="center")
        self.part_task_tree.column("approved", width=70, anchor="center")
        self.part_task_tree.grid(row=1, column=0, sticky="nsew", pady=(4, 10))
        self.part_task_tree.bind("<<TreeviewSelect>>", self._on_part_task_selected)

        ttk.Label(history_frame, text="Selected Task Rounds").grid(row=2, column=0, sticky="w")
        self.part_round_tree = ttk.Treeview(
            history_frame,
            columns=("approved", "viewpoint", "action"),
            show="headings",
            height=5,
        )
        self.part_round_tree.heading("approved", text="Approved")
        self.part_round_tree.heading("viewpoint", text="View")
        self.part_round_tree.heading("action", text="Action")
        self.part_round_tree.column("approved", width=70, anchor="center")
        self.part_round_tree.column("viewpoint", width=80, anchor="center")
        self.part_round_tree.column("action", width=180)
        self.part_round_tree.grid(row=3, column=0, sticky="nsew", pady=(4, 10))
        self.part_round_tree.bind("<<TreeviewSelect>>", self._on_part_round_selected)

        ttk.Label(history_frame, text="Assembly Rounds").grid(row=4, column=0, sticky="w")
        self.assembly_round_tree = ttk.Treeview(
            history_frame,
            columns=("approved", "actions", "first_action"),
            show="headings",
            height=5,
        )
        self.assembly_round_tree.heading("approved", text="Approved")
        self.assembly_round_tree.heading("actions", text="Actions")
        self.assembly_round_tree.heading("first_action", text="First Action")
        self.assembly_round_tree.column("approved", width=70, anchor="center")
        self.assembly_round_tree.column("actions", width=70, anchor="center")
        self.assembly_round_tree.column("first_action", width=180)
        self.assembly_round_tree.grid(row=5, column=0, sticky="nsew", pady=(4, 10))
        self.assembly_round_tree.bind("<<TreeviewSelect>>", self._on_assembly_round_selected)

        ttk.Label(history_frame, text="History Detail").grid(row=6, column=0, sticky="w")
        self.history_detail_box = scrolledtext.ScrolledText(history_frame, height=8, wrap=tk.WORD, state=tk.DISABLED)
        self.history_detail_box.grid(row=7, column=0, sticky="nsew", pady=(4, 10))
        self._configure_history_detail_styles()

        captures_frame = ttk.Frame(notebook, padding=10)
        captures_frame.columnconfigure(0, weight=1)
        captures_frame.columnconfigure(1, weight=1)
        captures_frame.rowconfigure(1, weight=1)
        notebook.add(captures_frame, text="Captures")

        ttk.Label(captures_frame, text="Preview Capture").grid(row=0, column=0, sticky="w")
        ttk.Label(captures_frame, text="Final Validation Capture").grid(row=0, column=1, sticky="w")
        self.preview_label = ttk.Label(captures_frame, text="No capture yet", anchor="center")
        self.preview_label.grid(row=1, column=0, sticky="nsew", pady=(4, 0), padx=(0, 6))
        self.final_label = ttk.Label(captures_frame, text="No final capture yet", anchor="center")
        self.final_label.grid(row=1, column=1, sticky="nsew", pady=(4, 0), padx=(6, 0))

        self.settings_panel = ttk.LabelFrame(main, text="Settings", padding=10)
        self.settings_panel.grid(row=0, column=1, sticky="ns")
        self.settings_panel.columnconfigure(1, weight=1)
        self.settings_panel.columnconfigure(3, weight=1)

        self._add_entry(self.settings_panel, 0, "LLM Endpoint", self.endpoint_var)
        self._add_entry(self.settings_panel, 1, "LLM Model", self.model_var)

        ttk.Label(self.settings_panel, text="Part Rounds").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Spinbox(self.settings_panel, from_=1, to=10, textvariable=self.part_rounds_var, width=8).grid(
            row=2, column=1, sticky="w", pady=4
        )
        ttk.Label(self.settings_panel, text="Assembly Rounds").grid(row=2, column=2, sticky="w", pady=4)
        ttk.Spinbox(self.settings_panel, from_=1, to=10, textvariable=self.assembly_rounds_var, width=8).grid(
            row=2, column=3, sticky="w", pady=4
        )
        ttk.Checkbutton(self.settings_panel, text="Use Blender MCP", variable=self.use_blender_mcp_var).grid(
            row=3, column=0, sticky="w", pady=4
        )
        ttk.Checkbutton(self.settings_panel, text="Use YOLO Validation", variable=self.use_yolo_var).grid(
            row=3, column=1, sticky="w", pady=4
        )
        self._add_yolo_model_row(self.settings_panel, 4)
        self._add_entry(self.settings_panel, 5, "YOLO Views", self.yolo_viewpoints_var)
        settings_actions = ttk.Frame(self.settings_panel)
        settings_actions.grid(row=6, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Button(settings_actions, text="Save Settings", command=self.save_settings).pack(side=tk.LEFT)
        self.settings_panel.grid_remove()

    def _add_entry(self, parent: ttk.Frame, row: int, label: str, variable: tk.Variable, column_offset: int = 0) -> None:
        col = column_offset
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=col + 1, sticky="ew", pady=4, padx=(8, 12))

    def _add_session_row(self, parent: ttk.Frame, row: int) -> None:
        ttk.Label(parent, text="Session ID").grid(row=row, column=0, sticky="w", pady=4)
        session_entry = ttk.Entry(parent, textvariable=self.session_var, state="readonly")
        session_entry.grid(row=row, column=1, sticky="ew", pady=4, padx=(8, 8))
        ttk.Button(parent, text="New Session", command=self.create_new_session).grid(
            row=row, column=2, sticky="w", pady=4
        )

    def _add_yolo_model_row(self, parent: ttk.Frame, row: int) -> None:
        ttk.Label(parent, text="YOLO Model").grid(row=row, column=2, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.yolo_model_var).grid(
            row=row, column=3, sticky="ew", pady=4, padx=(8, 8)
        )
        ttk.Button(parent, text="Browse...", command=self.browse_yolo_model).grid(
            row=row, column=4, sticky="w", pady=4
        )

    def _add_value(self, parent: ttk.Frame, row: int, label: str, variable: tk.Variable) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        ttk.Label(parent, textvariable=variable, wraplength=360, justify=tk.LEFT).grid(
            row=row, column=1, sticky="w", pady=4
        )

    def create_new_session(self) -> None:
        if self.process is not None and self.process.poll() is None:
            messagebox.showinfo("Run Active", "Stop the current workflow before creating a new session.")
            return
        self.session_var.set(generate_session_id("gui"))
        self._append_activity("system", f"Created new session: {self.session_var.get()}")

    def browse_yolo_model(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select YOLO model",
            filetypes=[
                ("YOLO model files", "*.pt *.onnx *.engine"),
                ("All files", "*.*"),
            ],
        )
        if selected:
            self.yolo_model_var.set(selected)

    def save_settings(self) -> None:
        settings = GuiSavedSettings(
            llm_endpoint_url=self.endpoint_var.get().strip() or "http://127.0.0.1:8080",
            llm_model=self.model_var.get().strip() or "local-model",
            max_part_refinement_rounds=int(self.part_rounds_var.get()),
            max_assembly_rounds=int(self.assembly_rounds_var.get()),
            use_yolo_perception=bool(self.use_yolo_var.get()),
            yolo_model_path=self.yolo_model_var.get().strip(),
            yolo_viewpoints=[item.strip() for item in self.yolo_viewpoints_var.get().split(",") if item.strip()],
        )
        path = save_gui_settings(self.runtime_root, settings)
        self._append_activity("system", f"Saved settings to {path}")

    def toggle_settings_panel(self) -> None:
        self.settings_visible = not self.settings_visible
        if self.settings_visible:
            self.settings_panel.grid()
            self.settings_toggle_button.configure(text="Hide Settings")
        else:
            self.settings_panel.grid_remove()
            self.settings_toggle_button.configure(text="Show Settings")

    def add_reference_images(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Select reference images",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif"), ("All files", "*.*")],
        )
        if not selected:
            return
        for item in selected:
            if item not in self.reference_images:
                self.reference_images.append(item)
        self.reference_images_var.set(", ".join(Path(item).name for item in self.reference_images))

    def start_run(self) -> None:
        if self.process is not None and self.process.poll() is None:
            messagebox.showinfo("Run Active", "A workflow is already running.")
            return
        if not self.task_var.get().strip():
            messagebox.showerror("Missing Task", "Task is required.")
            return
        if not self.endpoint_var.get().strip():
            messagebox.showerror("Missing Endpoint", "LLM endpoint URL is required.")
            return

        config = GuiLaunchConfig(
            task=self.task_var.get().strip(),
            session_id=self.session_var.get().strip() or "gui-session",
            llm_endpoint_url=self.endpoint_var.get().strip(),
            llm_model=self.model_var.get().strip() or "local-model",
            reference_texts=self._reference_texts(),
            reference_images=list(self.reference_images),
            max_part_refinement_rounds=int(self.part_rounds_var.get()),
            max_assembly_rounds=int(self.assembly_rounds_var.get()),
            use_blender_mcp=True,
            use_yolo_perception=bool(self.use_yolo_var.get()),
            yolo_model_path=self.yolo_model_var.get().strip(),
            yolo_viewpoints=[item.strip() for item in self.yolo_viewpoints_var.get().split(",") if item.strip()],
        )

        if config.use_yolo_perception and not config.yolo_model_path:
            messagebox.showerror("Missing YOLO Model", "YOLO model path is required when YOLO validation is enabled.")
            return

        command = build_multi_stage_command(REPO_ROOT, config)
        self._append_output(f"$ {' '.join(command)}\n")
        self._append_activity("user", self.task_var.get().strip())
        self.status_var.set("starting")
        self.stop_reason_var.set("")
        self.detected_parts_var.set("")
        self.capture_path_var.set("")
        self.final_capture_path_var.set("")
        self._set_feedback("")
        self._set_history_detail("")
        self.latest_progress_data = {}
        self.selected_task_id = ""
        self._clear_tree(self.part_task_tree)
        self._clear_tree(self.part_round_tree)
        self._clear_tree(self.assembly_round_tree)
        self._clear_preview(self.preview_label, latest=True)
        self._clear_preview(self.final_label, latest=False)
        self.last_stdout_length = 0
        self.last_stage_signature = ""
        self.last_feedback_seen = ""

        self.process = subprocess.Popen(
            command,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self._schedule_progress_poll()
        self._schedule_log_poll()

    def stop_run(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        self.status_var.set("stopping")
        self.stop_reason_var.set("Run terminated from GUI.")
        self._append_activity("status", "Run terminated from GUI.")

    def on_close(self) -> None:
        self.stop_run()
        if self.progress_after_id is not None:
            self.root.after_cancel(self.progress_after_id)
        if self.log_after_id is not None:
            self.root.after_cancel(self.log_after_id)
        self.root.destroy()

    def _load_saved_settings(self) -> None:
        settings = load_gui_settings(self.runtime_root)
        self.endpoint_var.set(settings.llm_endpoint_url)
        self.model_var.set(settings.llm_model)
        self.part_rounds_var.set(settings.max_part_refinement_rounds)
        self.assembly_rounds_var.set(settings.max_assembly_rounds)
        self.use_yolo_var.set(settings.use_yolo_perception)
        self.yolo_model_var.set(settings.yolo_model_path)
        self.yolo_viewpoints_var.set(", ".join(settings.yolo_viewpoints))

    def _reference_texts(self) -> list[str]:
        raw = self.reference_text_box.get("1.0", tk.END)
        return [line.strip() for line in raw.splitlines() if line.strip()]

    def _schedule_progress_poll(self) -> None:
        self._poll_progress()
        self.progress_after_id = self.root.after(1000, self._schedule_progress_poll)

    def _schedule_log_poll(self) -> None:
        self._poll_process_output()
        self.log_after_id = self.root.after(500, self._schedule_log_poll)

    def _poll_process_output(self) -> None:
        if self.process is None or self.process.stdout is None:
            return
        while True:
            line = self.process.stdout.readline()
            if not line:
                break
            self._append_output(line)
        if self.process.poll() is not None:
            self.status_var.set("completed" if self.process.returncode == 0 else "failed")

    def _poll_progress(self) -> None:
        progress_path = session_progress_path(REPO_ROOT / "data" / "runtime", self.session_var.get().strip())
        if not progress_path.exists():
            return
        try:
            with progress_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            return

        summary = summarize_progress(data)
        self.latest_progress_data = data
        self.status_var.set(summary["status"])
        self.stage_var.set(f'{summary["stage"]} / {summary["stage_status"]}'.strip(" /"))
        self.active_task_var.set(summary["active_task_id"])
        self.completed_tasks_var.set(summary["completed_task_ids"])
        self.detected_parts_var.set(summary["final_detected_parts"])
        self.stop_reason_var.set(summary["stop_reason"])
        self.capture_path_var.set(summary["latest_capture_path"])
        self.final_capture_path_var.set(summary["final_capture_path"])
        self._set_feedback(summary["latest_feedback"])
        self._refresh_history_views(data)
        self._update_preview(self.preview_label, summary["latest_capture_path"], latest=True)
        self._update_preview(self.final_label, summary["final_capture_path"], latest=False)
        self._emit_progress_activity(summary)

    def _set_feedback(self, text: str) -> None:
        self.feedback_box.configure(state=tk.NORMAL)
        self.feedback_box.delete("1.0", tk.END)
        if text:
            self.feedback_box.insert(tk.END, text)
        self.feedback_box.configure(state=tk.DISABLED)

    def _append_output(self, text: str) -> None:
        self.output_box.configure(state=tk.NORMAL)
        self.output_box.insert(tk.END, text)
        self.output_box.see(tk.END)
        self.output_box.configure(state=tk.DISABLED)

    def _append_activity(self, kind: str, text: str) -> None:
        if not text.strip():
            return
        prefixes = {
            "user": ("You", "activity_user"),
            "system": ("System", "activity_system"),
            "status": ("Status", "activity_status"),
            "feedback": ("Feedback", "activity_feedback"),
        }
        label, tag = prefixes.get(kind, ("Log", "activity_system"))
        self.output_box.configure(state=tk.NORMAL)
        self.output_box.insert(tk.END, f"{label}\n", (tag, "activity_label"))
        self.output_box.insert(tk.END, f"{text.strip()}\n\n", (tag,))
        self.output_box.see(tk.END)
        self.output_box.configure(state=tk.DISABLED)

    def _configure_output_styles(self) -> None:
        self.output_box.tag_configure("activity_label", font=("Segoe UI", 9, "bold"))
        self.output_box.tag_configure("activity_user", font=("Segoe UI", 10), lmargin1=8, lmargin2=8)
        self.output_box.tag_configure("activity_system", font=("Segoe UI", 10), lmargin1=8, lmargin2=8)
        self.output_box.tag_configure("activity_status", font=("Segoe UI", 10), foreground="#8b5c00", lmargin1=8, lmargin2=8)
        self.output_box.tag_configure("activity_feedback", font=("Segoe UI", 10), foreground="#0b5a7a", lmargin1=8, lmargin2=8)

    def _emit_progress_activity(self, summary: dict) -> None:
        stage_signature = f"{summary['status']}|{summary['stage']}|{summary['stage_status']}|{summary['active_task_id']}"
        if stage_signature != self.last_stage_signature:
            self.last_stage_signature = stage_signature
            message = f"{summary['stage']} / {summary['stage_status']}"
            if summary["active_task_id"]:
                message += f" | active task: {summary['active_task_id']}"
            self._append_activity("status", message)
        if summary["latest_feedback"] and summary["latest_feedback"] != self.last_feedback_seen:
            self.last_feedback_seen = summary["latest_feedback"]
            self._append_activity("feedback", summary["latest_feedback"])

    def _set_history_detail(self, text: str) -> None:
        self.history_detail_box.configure(state=tk.NORMAL)
        self.history_detail_box.delete("1.0", tk.END)
        if text:
            self.history_detail_box.insert(tk.END, text)
        self.history_detail_box.configure(state=tk.DISABLED)

    def _render_history_sections(self, sections: list[dict]) -> None:
        self.history_detail_box.configure(state=tk.NORMAL)
        self.history_detail_box.delete("1.0", tk.END)
        for section in sections:
            self.history_detail_box.insert(tk.END, f"{section['title']}\n", ("section_title",))
            for item in section.get("items", []):
                self.history_detail_box.insert(tk.END, "  ", ())
                self.history_detail_box.insert(tk.END, f"{item['label']}: ", ("field_label",))
                self.history_detail_box.insert(tk.END, f"{item['value']}\n", ("field_value",))
            self.history_detail_box.insert(tk.END, "\n")
        self.history_detail_box.configure(state=tk.DISABLED)

    def _configure_history_detail_styles(self) -> None:
        self.history_detail_box.tag_configure("section_title", font=("Segoe UI", 10, "bold"), spacing1=6, spacing3=2)
        self.history_detail_box.tag_configure("field_label", font=("Consolas", 9, "bold"))
        self.history_detail_box.tag_configure("field_value", font=("Consolas", 9))

    def _refresh_history_views(self, progress_data: dict) -> None:
        part_rows = extract_part_task_rows(progress_data)
        self._replace_tree_rows(
            self.part_task_tree,
            [(row["task_id"], row["title"], row["status"], row["current_round"], row["approved"]) for row in part_rows],
        )
        if not self.selected_task_id or not any(row["task_id"] == self.selected_task_id for row in part_rows):
            self.selected_task_id = str(progress_data.get("active_task_id", "")) or (part_rows[0]["task_id"] if part_rows else "")
        self._select_tree_item(self.part_task_tree, self.selected_task_id)
        self._refresh_part_rounds(progress_data)
        assembly_rows = extract_assembly_round_rows(progress_data)
        self._replace_tree_rows(
            self.assembly_round_tree,
            [
                (
                    row["round_index"],
                    row["approved"],
                    row["action_count"],
                    row["first_action_type"],
                )
                for row in assembly_rows
            ],
        )

    def _refresh_part_rounds(self, progress_data: dict) -> None:
        round_rows = extract_part_round_rows(progress_data, self.selected_task_id)
        self._replace_tree_rows(
            self.part_round_tree,
            [
                (
                    row["round_index"],
                    row["approved"],
                    row["viewpoint"],
                    row["action_type"],
                )
                for row in round_rows
            ],
        )

    def _replace_tree_rows(self, tree: ttk.Treeview, rows: list[tuple]) -> None:
        self._clear_tree(tree)
        for row in rows:
            tree.insert("", tk.END, iid=str(row[0]), values=row[1:])

    def _clear_tree(self, tree: ttk.Treeview) -> None:
        for item in tree.get_children():
            tree.delete(item)

    def _select_tree_item(self, tree: ttk.Treeview, item_id: str) -> None:
        if item_id and tree.exists(item_id):
            tree.selection_set(item_id)
            tree.focus(item_id)

    def _on_part_task_selected(self, _event=None) -> None:
        selection = self.part_task_tree.selection()
        if not selection:
            return
        self.selected_task_id = selection[0]
        self._refresh_part_rounds(self.latest_progress_data)
        for row in extract_part_task_rows(self.latest_progress_data):
            if row["task_id"] != self.selected_task_id:
                continue
            self._set_history_detail(format_history_detail("Part Task", row))
            break

    def _on_part_round_selected(self, _event=None) -> None:
        selection = self.part_round_tree.selection()
        if not selection:
            return
        round_index = selection[0]
        round_detail = find_part_round_detail(self.latest_progress_data, self.selected_task_id, round_index)
        if not round_detail:
            return
        self._render_history_sections(
            build_round_inspector_sections("Part Round", round_detail, multi_action=False)
        )
        self._update_preview(self.preview_label, str(round_detail.get("capture_path", "")), latest=True)

    def _on_assembly_round_selected(self, _event=None) -> None:
        selection = self.assembly_round_tree.selection()
        if not selection:
            return
        round_index = selection[0]
        round_detail = find_assembly_round_detail(self.latest_progress_data, round_index)
        if not round_detail:
            return
        self._render_history_sections(
            build_round_inspector_sections("Assembly Round", round_detail, multi_action=True)
        )
        self._update_preview(self.preview_label, str(round_detail.get("capture_path", "")), latest=True)

    def _update_preview(self, label: ttk.Label, path_text: str, latest: bool) -> None:
        if not path_text:
            return
        path = Path(path_text)
        if not path.exists() or path.suffix.lower() not in {".png", ".gif"}:
            label.configure(text=path_text, image="")
            return
        try:
            image = tk.PhotoImage(file=str(path))
        except tk.TclError:
            label.configure(text=path_text, image="")
            return

        width = image.width()
        height = image.height()
        scale = max(1, max(width // 480, height // 320))
        preview = image.subsample(scale, scale) if scale > 1 else image
        if latest:
            self.preview_image = preview
        else:
            self.final_image = preview
        label.configure(image=preview, text="")

    def _clear_preview(self, label: ttk.Label, latest: bool) -> None:
        label.configure(image="", text="No capture yet")
        if latest:
            self.preview_image = None
        else:
            self.final_image = None


def main() -> int:
    root = tk.Tk()
    MultiStageGuiApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
