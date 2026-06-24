import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


MODULES = [
    "Activity",
    "Apps",
    "Capacity",
    "CapacityMetrics",
    "Catalog",
    "Domains",
    "FabricItems",
    "Gateway",
    "Graph",
    "Refreshables",
    "RefreshHistory",
    "Roles",
    "Tenant",
    "Workspaces",
]

STORAGE_MODES = (
    "Local files",
    "Blob Storage URL",
    "Blob Storage connection string",
    "Fabric Lakehouse",
)


class MonitorUi(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Fabric Monitor")
        self.geometry("980x760")
        self.minsize(900, 680)

        self.project_root = Path(__file__).resolve().parents[1]
        self.process: subprocess.Popen | None = None
        self.reader_thread: threading.Thread | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.temp_profile: Path | None = None

        self.fields: dict[str, tk.StringVar] = {}
        self.storage_frames: dict[str, ttk.LabelFrame] = {}
        self.module_vars = {module: tk.BooleanVar(value=module in self.default_modules()) for module in MODULES}
        self.include_secret_var = tk.BooleanVar(value=False)
        self.base_scan_var = tk.BooleanVar(value=False)
        self.dry_run_var = tk.BooleanVar(value=False)
        self.exclude_personal_var = tk.BooleanVar(value=True)
        self.exclude_inactive_var = tk.BooleanVar(value=True)

        self._build_ui()
        self._poll_log_queue()

    @staticmethod
    def default_modules() -> set[str]:
        return {"Activity", "Apps", "Catalog", "Graph", "Tenant", "RefreshHistory", "Gateway"}

    def _build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill=tk.BOTH, expand=True)

        notebook = ttk.Notebook(root)
        notebook.pack(fill=tk.BOTH, expand=True)

        config_tab = ttk.Frame(notebook, padding=10)
        modules_tab = ttk.Frame(notebook, padding=10)
        log_tab = ttk.Frame(notebook, padding=10)
        notebook.add(config_tab, text="Configuration")
        notebook.add(modules_tab, text="Modules")
        notebook.add(log_tab, text="Run Log")

        self._build_config_tab(config_tab)
        self._build_modules_tab(modules_tab)
        self._build_log_tab(log_tab)
        self._build_buttons(root)

    def _add_field(self, parent, row: int, label: str, key: str, show: str | None = None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=3)
        value = self.fields.get(key) or tk.StringVar()
        entry = ttk.Entry(parent, textvariable=value, show=show)
        entry.grid(row=row, column=1, sticky=tk.EW, pady=3)
        self.fields[key] = value
        return entry

    def _add_storage_frame(self, parent, mode: str, title: str):
        frame = ttk.LabelFrame(parent, text=title, padding=10)
        frame.columnconfigure(1, weight=1)
        self.storage_frames[mode] = frame
        return frame

    def _build_config_tab(self, parent):
        parent.columnconfigure(1, weight=1)

        required = ttk.LabelFrame(parent, text="Service principal", padding=10)
        required.grid(row=0, column=0, sticky=tk.NSEW, padx=4, pady=4)
        required.columnconfigure(1, weight=1)
        self._add_field(required, 0, "Tenant ID", "TENANT_ID")
        self._add_field(required, 1, "Client ID", "CLIENT_ID")
        self._add_field(required, 2, "Client secret", "CLIENT_SECRET", show="*")

        storage = ttk.LabelFrame(parent, text="Output storage", padding=10)
        storage.grid(row=1, column=0, sticky=tk.NSEW, padx=4, pady=4)
        storage.columnconfigure(1, weight=1)
        self.fields["STORAGE_MODE"] = tk.StringVar(value=STORAGE_MODES[0])
        ttk.Label(storage, text="Storage mode").grid(row=0, column=0, sticky=tk.W, pady=3)
        storage_selector = ttk.Combobox(
            storage,
            textvariable=self.fields["STORAGE_MODE"],
            values=STORAGE_MODES,
            state="readonly",
        )
        storage_selector.grid(row=0, column=1, sticky=tk.EW, pady=3)
        storage_selector.bind("<<ComboboxSelected>>", lambda _event: self.update_storage_fields())

        local_frame = self._add_storage_frame(storage, "Local files", "Local files")
        self._add_field(local_frame, 0, "Local output path", "OUTPUT_PATH").insert(0, "Data")

        blob_url_frame = self._add_storage_frame(storage, "Blob Storage URL", "Blob Storage URL")
        self._add_field(blob_url_frame, 0, "Blob account URL", "STORAGE_ACCOUNT_URL")
        self._add_field(blob_url_frame, 1, "Blob container", "STORAGE_ACCOUNT_CONTAINER_NAME")
        self._add_field(blob_url_frame, 2, "Blob root path", "STORAGE_ACCOUNT_CONTAINER_ROOT_PATH")

        blob_connection_frame = self._add_storage_frame(
            storage,
            "Blob Storage connection string",
            "Blob Storage connection string",
        )
        self._add_field(blob_connection_frame, 0, "Blob connection string", "STORAGE_ACCOUNT_CONNECTION_STRING", show="*")
        self._add_field(blob_connection_frame, 1, "Blob container", "STORAGE_ACCOUNT_CONTAINER_NAME")
        self._add_field(blob_connection_frame, 2, "Blob root path", "STORAGE_ACCOUNT_CONTAINER_ROOT_PATH")

        lakehouse_frame = self._add_storage_frame(storage, "Fabric Lakehouse", "Fabric Lakehouse")
        self._add_field(lakehouse_frame, 0, "Lakehouse name", "LAKEHOUSE_NAME")
        self._add_field(lakehouse_frame, 1, "Workspace name", "WORKSPACE_NAME")
        self._add_field(lakehouse_frame, 2, "Path in lakehouse", "PATH_IN_LAKEHOUSE")
        self.update_storage_fields()

        options = ttk.LabelFrame(parent, text="Run options", padding=10)
        options.grid(row=2, column=0, sticky=tk.NSEW, padx=4, pady=4)
        ttk.Checkbutton(options, text="Full catalog workspace scan (--base)", variable=self.base_scan_var).grid(row=0, column=0, sticky=tk.W)
        ttk.Checkbutton(options, text="Dry run for Blob Storage writes", variable=self.dry_run_var).grid(row=1, column=0, sticky=tk.W)
        ttk.Checkbutton(options, text="Exclude personal workspaces", variable=self.exclude_personal_var).grid(row=2, column=0, sticky=tk.W)
        ttk.Checkbutton(options, text="Exclude inactive workspaces", variable=self.exclude_inactive_var).grid(row=3, column=0, sticky=tk.W)
        ttk.Checkbutton(
            options,
            text="Include client secret when saving profile",
            variable=self.include_secret_var,
        ).grid(row=4, column=0, sticky=tk.W)

        parent.columnconfigure(0, weight=1)

    def update_storage_fields(self):
        selected_mode = self.fields["STORAGE_MODE"].get()
        for mode, frame in self.storage_frames.items():
            if mode == selected_mode:
                frame.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(8, 0))
            else:
                frame.grid_remove()

    def _build_modules_tab(self, parent):
        ttk.Label(parent, text="Select the modules to run. These map to APPLICATION_MODULES.").pack(anchor=tk.W)
        grid = ttk.Frame(parent)
        grid.pack(fill=tk.X, pady=10)
        for index, module in enumerate(MODULES):
            row = index // 3
            column = index % 3
            ttk.Checkbutton(grid, text=module, variable=self.module_vars[module]).grid(
                row=row,
                column=column,
                sticky=tk.W,
                padx=16,
                pady=4,
            )

    def _build_log_tab(self, parent):
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        self.log_text = tk.Text(parent, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.grid(row=0, column=0, sticky=tk.NSEW)
        scrollbar = ttk.Scrollbar(parent, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky=tk.NS)
        self.log_text.configure(yscrollcommand=scrollbar.set)

    def _build_buttons(self, parent):
        buttons = ttk.Frame(parent)
        buttons.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(buttons, text="Load Profile", command=self.load_profile).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Save Profile", command=self.save_profile).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Run Monitor", command=self.run_monitor).pack(side=tk.RIGHT, padx=4)
        ttk.Button(buttons, text="Stop", command=self.stop_monitor).pack(side=tk.RIGHT, padx=4)
        ttk.Button(buttons, text="Clear Log", command=self.clear_log).pack(side=tk.RIGHT, padx=4)

    def selected_modules(self) -> list[str]:
        return [module for module, selected in self.module_vars.items() if selected.get()]

    def build_profile(self, *, include_secret: bool = True) -> dict[str, str | bool]:
        modules = self.selected_modules()
        if not modules:
            raise ValueError("Select at least one module to run.")

        profile: dict[str, str | bool] = {
            "TENANT_ID": self.fields["TENANT_ID"].get().strip(),
            "CLIENT_ID": self.fields["CLIENT_ID"].get().strip(),
            "APPLICATION_MODULES": ",".join(modules),
            "ALL_WORKSPACES": self.base_scan_var.get(),
            "EXCLUDE_PERSONAL_WORKSPACES": self.exclude_personal_var.get(),
            "EXCLUDE_INACTIVE_WORKSPACES": self.exclude_inactive_var.get(),
        }
        if include_secret:
            profile["CLIENT_SECRET"] = self.fields["CLIENT_SECRET"].get()

        mode = self.fields["STORAGE_MODE"].get()
        if mode == "Local files":
            profile["OUTPUT_PATH"] = self.fields["OUTPUT_PATH"].get().strip() or "Data"
        elif mode == "Blob Storage URL":
            profile["STORAGE_ACCOUNT_URL"] = self.fields["STORAGE_ACCOUNT_URL"].get().strip()
            profile["STORAGE_ACCOUNT_CONTAINER_NAME"] = self.fields["STORAGE_ACCOUNT_CONTAINER_NAME"].get().strip()
            profile["STORAGE_ACCOUNT_CONTAINER_ROOT_PATH"] = self.fields["STORAGE_ACCOUNT_CONTAINER_ROOT_PATH"].get().strip()
        elif mode == "Blob Storage connection string":
            profile["STORAGE_ACCOUNT_CONNECTION_STRING"] = self.fields["STORAGE_ACCOUNT_CONNECTION_STRING"].get()
            profile["STORAGE_ACCOUNT_CONTAINER_NAME"] = self.fields["STORAGE_ACCOUNT_CONTAINER_NAME"].get().strip()
            profile["STORAGE_ACCOUNT_CONTAINER_ROOT_PATH"] = self.fields["STORAGE_ACCOUNT_CONTAINER_ROOT_PATH"].get().strip()
        elif mode == "Fabric Lakehouse":
            profile["LAKEHOUSE_NAME"] = self.fields["LAKEHOUSE_NAME"].get().strip()
            profile["WORKSPACE_NAME"] = self.fields["WORKSPACE_NAME"].get().strip()
            profile["PATH_IN_LAKEHOUSE"] = self.fields["PATH_IN_LAKEHOUSE"].get().strip()
            profile["ON_FABRIC"] = True

        return {key: value for key, value in profile.items() if value not in ("", None)}

    def load_profile(self):
        path = filedialog.askopenfilename(
            title="Load Fabric Monitor profile",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as profile_file:
                profile = json.load(profile_file)
            if not isinstance(profile, dict):
                raise ValueError("Profile must contain a JSON object.")
            self.apply_profile(profile)
            self.append_log(f"Loaded profile: {path}\n")
        except Exception as error:
            messagebox.showerror("Load profile failed", str(error))

    def save_profile(self):
        try:
            profile = self.build_profile(include_secret=self.include_secret_var.get())
        except Exception as error:
            messagebox.showerror("Save profile failed", str(error))
            return

        path = filedialog.asksaveasfilename(
            title="Save Fabric Monitor profile",
            defaultextension=".json",
            filetypes=(("JSON files", "*.json"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as profile_file:
                json.dump(profile, profile_file, indent=2)
            self.append_log(f"Saved profile: {path}\n")
        except Exception as error:
            messagebox.showerror("Save profile failed", str(error))

    def apply_profile(self, profile: dict):
        for key, value in profile.items():
            if key in self.fields:
                self.fields[key].set(str(value))

        modules = str(profile.get("APPLICATION_MODULES", "")).replace(" ", "").split(",")
        if modules and modules != [""]:
            selected = set(modules)
            for module, variable in self.module_vars.items():
                variable.set(module in selected)

        self.base_scan_var.set(self._as_bool(profile.get("ALL_WORKSPACES", False)))
        self.exclude_personal_var.set(self._as_bool(profile.get("EXCLUDE_PERSONAL_WORKSPACES", True)))
        self.exclude_inactive_var.set(self._as_bool(profile.get("EXCLUDE_INACTIVE_WORKSPACES", True)))

        if profile.get("OUTPUT_PATH"):
            self.fields["STORAGE_MODE"].set("Local files")
        elif profile.get("STORAGE_ACCOUNT_URL"):
            self.fields["STORAGE_MODE"].set("Blob Storage URL")
        elif profile.get("STORAGE_ACCOUNT_CONNECTION_STRING") or profile.get("STORAGE_ACCOUNT_CONN_STR"):
            self.fields["STORAGE_MODE"].set("Blob Storage connection string")
            self.fields["STORAGE_ACCOUNT_CONNECTION_STRING"].set(
                str(profile.get("STORAGE_ACCOUNT_CONNECTION_STRING") or profile.get("STORAGE_ACCOUNT_CONN_STR"))
            )
        elif profile.get("LAKEHOUSE_NAME"):
            self.fields["STORAGE_MODE"].set("Fabric Lakehouse")

    @staticmethod
    def _as_bool(value) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "y", "on")

    def run_monitor(self):
        if self.process and self.process.poll() is None:
            messagebox.showinfo("Fabric Monitor", "A monitor run is already in progress.")
            return

        try:
            profile = self.build_profile(include_secret=True)
            self.validate_profile(profile)
        except Exception as error:
            messagebox.showerror("Run monitor failed", str(error))
            return

        profile_file = tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            suffix=".json",
            prefix="fabric-monitor-",
            delete=False,
        )
        with profile_file:
            json.dump(profile, profile_file)
        self.temp_profile = Path(profile_file.name)

        command = [
            sys.executable,
            "-u",
            "-m",
            "app.monitor",
            "--profile",
            str(self.temp_profile),
        ]
        if self.dry_run_var.get():
            command.append("--dry-run")

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        self.append_log("\nStarting Fabric Monitor...\n")
        self.append_log(f"Command: {' '.join(command)}\n\n")

        try:
            self.process = subprocess.Popen(
                command,
                cwd=self.project_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
            )
        except Exception as error:
            self.cleanup_temp_profile()
            messagebox.showerror("Run monitor failed", str(error))
            return

        self.reader_thread = threading.Thread(target=self._read_process_output, daemon=True)
        self.reader_thread.start()

    @staticmethod
    def validate_profile(profile: dict):
        for key in ("TENANT_ID", "CLIENT_ID", "CLIENT_SECRET"):
            if not profile.get(key):
                raise ValueError(f"{key} is required.")

        has_storage = any(
            profile.get(key)
            for key in (
                "OUTPUT_PATH",
                "STORAGE_ACCOUNT_URL",
                "STORAGE_ACCOUNT_CONNECTION_STRING",
                "STORAGE_ACCOUNT_CONN_STR",
                "LAKEHOUSE_NAME",
            )
        )
        if not has_storage:
            raise ValueError("Choose an output storage mode and fill in its required fields.")

    def stop_monitor(self):
        if self.process and self.process.poll() is None:
            self.append_log("\nStopping Fabric Monitor...\n")
            self.process.terminate()

    def _read_process_output(self):
        assert self.process is not None
        if self.process.stdout:
            for line in self.process.stdout:
                self.log_queue.put(line)
        return_code = self.process.wait()
        self.log_queue.put(f"\nFabric Monitor exited with code {return_code}.\n")
        self.log_queue.put("__PROCESS_DONE__")

    def _poll_log_queue(self):
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            if message == "__PROCESS_DONE__":
                self.cleanup_temp_profile()
            else:
                self.append_log(message)
        self.after(100, self._poll_log_queue)

    def append_log(self, message: str):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, message)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def clear_log(self):
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def cleanup_temp_profile(self):
        if self.temp_profile and self.temp_profile.exists():
            try:
                self.temp_profile.unlink()
            except OSError:
                pass
        self.temp_profile = None


def main():
    app = MonitorUi()
    app.mainloop()


if __name__ == "__main__":
    main()
