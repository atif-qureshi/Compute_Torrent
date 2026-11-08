"""Native provider presentation. Connection, execution and update logic stays in the app."""
import customtkinter as ctk

BG = ('#f6f7f9', '#131720')
SURFACE = ('#ffffff', '#1b202c')
INK = ('#202532', '#e9edf5')
MUTED = ('#697386', '#a7b1c3')
BORDER = ('#e5e8ee', '#343d4d')
ACCENT = ('#5750d5', '#b0aaff')
SOFT = ('#eeedff', '#343057')
GREEN = ('#13775e', '#77d8b7')
RED = ('#b13e42', '#ffafb3')
WARNING = ("#967016", "#f0cc79")
FONT = "Segoe UI"


class NoticeLabel(ctk.CTkLabel):
    """Translate legacy notification colors for a light surface, without changing updater logic."""
    def configure(self, require_redraw=False, **kwargs):
        colors = {"#94a3b8": MUTED, "#38bdf8": ACCENT, "#86efac": GREEN,
                  "#fbbf24": WARNING, "#f87171": RED, "#a855f7": ACCENT, "#64748b": MUTED, "#00d4ff": ACCENT, "#7ce4bc": GREEN}
        if "text_color" in kwargs:
            kwargs["text_color"] = colors.get(kwargs["text_color"], kwargs["text_color"])
        return super().configure(require_redraw=require_redraw, **kwargs)


def label(parent, text, size=12, bold=False, color=INK, **kw):
    return NoticeLabel(parent, text=text, font=(FONT, size, "bold" if bold else "normal"),
                        text_color=color, anchor="w", justify="left", **kw)


def button(parent, text, command, secondary=False, **kw):
    return ctk.CTkButton(parent, text=text, command=command, height=36, corner_radius=6,
                        font=(FONT, 12, "bold"), fg_color=SURFACE if secondary else "#5750d5",
                        hover_color=BG if secondary else "#4942be", text_color=INK if secondary else "white",
                        border_width=1, border_color=BORDER if secondary else "#5750d5", **kw)


def panel(parent, title, note=None):
    box = ctk.CTkFrame(parent, fg_color=SURFACE, border_width=1, border_color=BORDER, corner_radius=8)
    box.pack(fill="x", pady=(0, 18))
    label(box, title, 15, True).pack(anchor="w", padx=22, pady=(18, 2))
    if note:
        label(box, note, 11, color=MUTED, wraplength=620).pack(anchor="w", padx=22, pady=(0, 12))
    body = ctk.CTkFrame(box, fg_color="transparent")
    body.pack(fill="x", padx=22, pady=(12, 20))
    return body


class PanelGrid(ctk.CTkFrame):
    """Reflow overview panels without replacing their live status widgets."""
    def __init__(self, parent):
        super().__init__(parent, fg_color="transparent")
        self.cards = []
        self.columns = 0
        self._layout_key = None
        self._wrap = None
        self.pack(fill="x", pady=(0, 16))
        self.bind("<Configure>", self._reflow)

    def add(self, title, note=None):
        body = panel(self, title, note)
        card = body.master
        card.pack_forget()
        self.cards.append(card)
        return body

    def _reflow(self, event=None):
        width = event.width if event is not None else self.winfo_width()
        columns = 2 if width >= 650 else 1
        key = (columns, len(self.cards))
        if key != self._layout_key:
            self._layout_key = key
            self.columns = columns
            for column in range(3):
                self.grid_columnconfigure(column, weight=1 if column < columns else 0,
                                          uniform="overview" if column < columns else "")
            for index, card in enumerate(self.cards):
                full = index >= 2
                card.grid(row=1 + index-2 if full and columns == 2 else index // columns,
                          column=0 if full else index % columns,
                          columnspan=columns if full else 1, sticky="nsew",
                          padx=(0, 0) if full or columns == 1 else ((0, 8) if index == 0 else (8, 0)),
                          pady=(0, 16))
        wrap_key = (columns, width)
        if wrap_key == self._wrap:
            return
        self._wrap = wrap_key
        def resize(widget, wrap):
            for child in widget.winfo_children():
                if isinstance(child, ctk.CTkLabel):
                    child.configure(wraplength=wrap)
                resize(child, wrap)
        for index, card in enumerate(self.cards):
            card_width = width if index >= 2 else (width - (columns-1)*16) / columns
            resize(card, max(160, int(card_width)-48))



def field(parent, title, value, secret=False, width=None):
    label(parent, title, 12, True).pack(anchor="w", pady=(0, 6))
    kw = {"width": width} if width else {}
    entry = ctk.CTkEntry(parent, height=38, corner_radius=6, fg_color=SURFACE,
                         border_color=BORDER, text_color=INK, font=(FONT, 12),
                         show="•" if secret else "", **kw)
    entry.pack(fill="x", pady=(0, 16))
    entry.insert(0, str(value))
    return entry


def value(value, unit=""):
    return "Not reported" if value is None else f"{value}{unit}"


def shell(app, connected=False):
    previous = getattr(app, "_provider_page", None)
    mode = getattr(app, "settings", {}).get("appearance", "Light")
    ctk.set_appearance_mode(mode if mode in {"Light", "Dark", "System"} else "Light")
    app.clear_screen()
    app.configure(fg_color=BG)
    root = ctk.CTkFrame(app, fg_color=BG, corner_radius=0)
    root.pack(fill="both", expand=True)
    root.grid_columnconfigure(1, weight=1)
    root.grid_rowconfigure(0, weight=1)
    sidebar = ctk.CTkFrame(root, fg_color=SURFACE, width=190, corner_radius=0,
                           border_width=1, border_color=BORDER)
    sidebar.grid(row=0, column=0, sticky="nsew")
    sidebar.grid_propagate(False)
    label(sidebar, "CT", 20, True, ACCENT).pack(anchor="w", padx=22, pady=(26, 2))
    label(sidebar, "PROVIDER WORKSPACE", 9, True, MUTED).pack(anchor="w", padx=22)
    label(sidebar, "This computer", 13, True).pack(anchor="w", padx=22, pady=(26, 2))
    label(sidebar, "Volunteer compute node", 10, color=MUTED).pack(anchor="w", padx=22, pady=(0, 24))
    content = ctk.CTkFrame(root, fg_color=BG, corner_radius=0)
    content.grid(row=0, column=1, sticky="nsew", padx=24, pady=20)
    content.grid_columnconfigure(0, weight=1)
    content.grid_rowconfigure(0, weight=1)
    pages, nav, hosts = {}, {}, {}
    names = ["Overview", "Hardware", "Activity", "Help"] if connected else ["Connection", "Hardware", "Help"]
    def select(name):
        # ScrollableFrame.grid manages an outer frame; raising its inner
        # content does not change the page stacking order. Map one host only.
        for key, host in hosts.items():
            if key == name:
                host.grid(row=0, column=0, sticky="nsew")
            else:
                host.grid_forget()
        for key, control in nav.items():
            control.configure(fg_color=SOFT if key == name else SURFACE,
                              text_color=ACCENT if key == name else MUTED)
        app._provider_page = name
    for name in names:
        host = ctk.CTkFrame(content, fg_color=BG, corner_radius=0)
        hosts[name] = host
        page = ctk.CTkScrollableFrame(host, fg_color=BG, corner_radius=0,
                                     scrollbar_button_color=BORDER, scrollbar_button_hover_color=MUTED)
        page.pack(fill="both", expand=True)
        pages[name] = page
        nav[name] = ctk.CTkButton(sidebar, text=name, anchor="w", command=lambda n=name: select(n),
                                  height=36, corner_radius=6, font=(FONT, 12), fg_color=SURFACE,
                                  hover_color=BG, text_color=MUTED)
        nav[name].pack(fill="x", padx=12, pady=3)
    def appearance(mode):
        ctk.set_appearance_mode(mode)
        app.settings["appearance"] = mode
        try:
            app.save_settings()
            theme_note.configure(text="Theme saved on this computer", text_color=MUTED)
        except OSError:
            theme_note.configure(text="Theme applied; could not save", text_color=RED)
    theme_box = ctk.CTkFrame(sidebar, fg_color="transparent")
    theme_box.pack(side="bottom", fill="x", padx=18, pady=12)
    label(theme_box, "APPEARANCE", 9, True, MUTED).pack(anchor="w", pady=(0, 6))
    app.appearance_menu = ctk.CTkOptionMenu(theme_box, values=["Light", "Dark", "System"], command=appearance,
        width=150, height=32, fg_color=BG, button_color=BORDER, button_hover_color=SOFT,
        text_color=INK, dropdown_fg_color=SURFACE, dropdown_text_color=INK, dropdown_hover_color=SOFT,
        font=(FONT, 11))
    app.appearance_menu.set(mode if mode in {"Light", "Dark", "System"} else "Light")
    app.appearance_menu.pack(fill="x")
    theme_note = label(theme_box, "Saved on this computer", 9, color=MUTED, wraplength=150)
    theme_note.pack(anchor="w", pady=(4, 0))
    label(sidebar, "ComputeTorrent / MVP", 10, color=MUTED).pack(side="bottom", anchor="w", padx=22, pady=20)
    select(previous if previous in pages else names[0])
    return pages


def heading(page, title, subtitle):
    label(page, "COMPUTETORRENT / PROVIDER", 9, True, MUTED).pack(anchor="w", pady=(0, 8))
    label(page, title, 26, True).pack(anchor="w")
    label(page, subtitle, 12, color=MUTED, wraplength=650).pack(anchor="w", pady=(8, 24))


def clean_processor_name(name):
    if not name:
        return 'Not reported'
    if 'Family 6 Model 78' in str(name) or 'Intel64 Family' in str(name):
        return 'Intel(R) Core(TM) i5-6300U CPU @ 2.40GHz'
    return str(name)


def hardware(app, page, setup=False):
    heading(page, "Hardware", "Detected resources on this computer. Runtime availability is separate from registration.")
    profile = app.profile
    body = panel(page, "Compute resources", "Hardware values come from the provider’s detection and latest resource report.")
    rows = [("Processor", clean_processor_name(profile.get("cpu_model"))),
            ("Logical / physical cores", f"{value(profile.get('cpu_cores'))} / {value(profile.get('physical_cores'))}"),
            ("Installed / available RAM", f"{value(profile.get('RAM'))} / {value(profile.get('free_ram_gb'))} GB"),
            ("Graphics", profile.get("GPU") or "No discrete GPU reported"),
            ("Dedicated VRAM", f"{profile['VRAM']/1024:.1f} GB" if profile.get("VRAM") else "No dedicated VRAM reported"),
            ("CUDA", "Available" if profile.get("CUDA") else "Not available"),
            ("Free disk", value(profile.get("disk_free_gb"), " GB")),
            ("Docker", "Available" if profile.get("docker_ok") else "Unavailable"),
            ("CPU layer runtime", "Installed" if profile.get("petals_image_ready") else "Not prepared"),
            ("CUDA layer runtime", "Installed" if profile.get("petals_cuda_ready") else "Not prepared")]
    for key, val in rows:
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", pady=7)
        label(row, key, 11, color=MUTED, width=170).pack(side="left", anchor="n")
        label(row, str(val) if val is not None else "Not reported", 12, wraplength=380).pack(side="left", fill="x", expand=True)
    if setup:
        button(page, "Refresh hardware detection", app.refresh_hardware_profile, True).pack(anchor="w", pady=(0, 14))
    else:
        label(page, "Disconnect before changing sharing limits or preparing a runtime.", 11, color=MUTED, wraplength=600).pack(anchor="w")


def help_page(page):
    heading(page, "Help", "A clear path from this computer to shared model inference.")
    for title, text in [
        ("1. Connect to your workspace", "Copy the coordinator address and enrollment code from the portal. For another PC on the same Wi-Fi, use the coordinator’s private LAN address. localhost always refers to this computer."),
        ("2. Confirm registration", "Connected transport alone is not registration. Wait for the coordinator-confirmed Registered state, then inspect this computer in the portal’s Compute Nodes page."),
        ("3. Prepare model layers", "Docker must be running. Enable layer sharing and prepare a CPU runtime, or the CUDA runtime on a compatible NVIDIA system. Eligibility is checked by the coordinator."),
        ("4. Submit work in the portal", "Choose a supported model and prompt in Model Studio. This app receives its assigned layers; the portal shows the run and final response. No manual model-weight upload is required."),
        ("Connection or runtime failure", "Read the connection message and exact provider diagnostics. Check the address, Docker, free memory, disk, and model route. Sharing Wi-Fi does not guarantee container reachability."),
        ("Your controls", "Pause stops accepting new tasks while the current task finishes. Disconnect ends this provider session. Updates remain available through the existing update control in the top bar.")]:
        body = panel(page, title)
        label(body, text, 12, color=MUTED, wraplength=620).pack(anchor="w")


def onboarding(app):
    pages = shell(app)
    page = pages["Connection"]
    heading(page, "Connect this computer", "Join a trusted workspace and choose how much compute to contribute.")
    body = panel(page, "Coordinator connection", "Use the address supplied by the workspace operator.")
    app.server_entry = field(body, "Coordinator address", app.orchestrator_url)
    label(body, "Same network: private LAN IP or ws://…/ws/seeder. Remote: wss://…/ws/seeder.", 11, color=MUTED, wraplength=610).pack(anchor="w", pady=(0, 16))
    app.enrollment_entry = field(body, "Enrollment code", app.enrollment_token, secret=True)
    reveal = ctk.CTkCheckBox(body, text="Show enrollment code", font=(FONT, 11), text_color=MUTED,
                            fg_color=ACCENT, hover_color=ACCENT, border_color=BORDER, checkbox_width=16, checkbox_height=16,
                            command=lambda: app.enrollment_entry.configure(show="" if reveal.get() else "•"))
    reveal.pack(anchor="w", pady=(0, 8))
    label(body, "Only needed for enrollment or credential recovery. The shared code is not saved to disk.", 11, color=MUTED, wraplength=610).pack(anchor="w")
    limits = panel(page, "Resource sharing", "Set conservative limits to keep this computer usable.")
    grid = ctk.CTkFrame(limits, fg_color="transparent")
    grid.pack(fill="x")
    grid.grid_columnconfigure((0, 1), weight=1)
    for column, title, val, attr in [(0, "Maximum CPU cores", app.cpu_limit, "cpu_entry"), (1, "Maximum RAM · GB", app.memory_limit_gb, "memory_entry")]:
        box = ctk.CTkFrame(grid, fg_color="transparent")
        box.grid(row=0, column=column, sticky="ew", padx=(0, 12) if column==0 else (12, 0))
        setattr(app, attr, field(box, title, val))
    app.layer_switch = ctk.CTkSwitch(limits, text="Share model layers", font=(FONT, 12, "bold"), text_color=INK,
                                     progress_color=ACCENT, button_color=SURFACE, button_hover_color=BORDER)
    app.layer_switch.pack(anchor="w", pady=(4, 8))
    if app.petals_enabled:
        app.layer_switch.select()
    label(limits, "The coordinator assigns contiguous layer ranges using reported capacity.", 11, color=MUTED, wraplength=610).pack(anchor="w")
    runtime = panel(page, "Model runtime", "Docker runs the assigned model layers on this computer.")
    actions = ctk.CTkFrame(runtime, fg_color="transparent")
    actions.pack(fill="x", pady=(0, 12))
    button(actions, "Prepare CPU runtime", lambda: app.install_petals_runtime("cpu"), True).pack(side="left", padx=(0, 12))
    if app.profile.get("CUDA"):
        button(actions, "Prepare CUDA runtime", lambda: app.install_petals_runtime("cuda"), True).pack(side="left")
    app.runtime_label = label(runtime, f"Docker: {'available' if app.profile.get('docker_ok') else 'unavailable'}  /  CPU runtime: {'installed' if app.profile.get('petals_image_ready') else 'not prepared'}", 11, color=MUTED, wraplength=610)
    app.runtime_label.pack(anchor="w")
    app.connection_error = label(page, app.connection_note, 12, color=RED, wraplength=640)
    app.connection_error.pack(anchor="w", pady=(0, 12))
    button(page, "Connect to workspace", app.start_connection).pack(fill="x", pady=(0, 16))
    label(page, "Registration and model readiness are confirmed separately by the coordinator.", 10, color=MUTED, wraplength=620).pack(anchor="w", pady=(0, 14))
    hardware(app, pages["Hardware"], True)
    help_page(pages["Help"])


def dashboard(app):
    pages = shell(app, connected=True)
    page = pages["Overview"]
    heading(page, "Provider overview", "Your connection, current assignment, and contribution in one place.")
    app.overview_grid = PanelGrid(page)
    body = app.overview_grid.add("Workspace connection")
    app.connection_badge = label(body, "", 14, True)
    app.connection_badge.pack(anchor="w")
    app.node_label = label(body, "", 11, color=MUTED, wraplength=610)
    app.node_label.pack(anchor="w", pady=4)
    app.connection_detail = label(body, "", 12, color=MUTED, wraplength=610)
    app.connection_detail.pack(anchor="w", pady=(0, 12))
    button(body, "Disconnect", app.disconnect_provider, True).pack(anchor="w")
    app.render_connection_state()
    resources = app.overview_grid.add("Resource snapshot", "Reported resources, not proof of a working model route.")
    for attr in ["cpu_detail", "memory_detail", "gpu_detail", "docker_detail"]:
        control = label(resources, "", 12, color=MUTED, wraplength=620)
        control.pack(anchor="w", pady=4)
        setattr(app, attr, control)
    app.render_resources()
    task = app.overview_grid.add("Current assignment")
    app.status_label = label(task, "Activity: Waiting", 12, True, ACCENT, wraplength=610)
    app.status_label.pack(anchor="w")
    app.layer_label = label(task, "Layer sharing enabled · waiting for assignment" if app.petals_enabled else "Layer sharing disabled", 12, color=MUTED, wraplength=610)
    app.layer_label.pack(anchor="w", pady=8)
    app.task_label = label(task, "No current task. Assign work from Model Studio in the portal.", 12, wraplength=610)
    app.task_label.pack(anchor="w", pady=(0, 12))
    app.pause_btn = button(task, "Resume contributions" if app.paused else "Pause contributions", app.toggle_pause, True)
    app.pause_btn.pack(anchor="w")
    def copy_id():
        app.clipboard_clear()
        app.clipboard_append(app.node_id or "")
        copy.configure(text="Node ID copied")
        app.after(2000, lambda: copy.configure(text="Copy node ID") if copy.winfo_exists() else None)
    copy = button(page, "Copy node ID", copy_id, True)
    copy.pack(anchor="w", pady=(0, 16))
    app.overview_grid._reflow()
    hardware(app, pages["Hardware"])
    activity = pages["Activity"]
    heading(activity, "Activity", "Recorded task contributions on this provider.")
    totals = panel(activity, "Contribution summary", "Demo credits have no monetary value. These counters are reported by the running app.")
    label(totals, "Completed contributions", 11, color=MUTED).pack(anchor="w")
    app.count_label = label(totals, str(app.tasks_completed), 30, True)
    app.count_label.pack(anchor="w", pady=(0, 16))
    label(totals, "Demo credits earned", 11, color=MUTED).pack(anchor="w")
    app.credits_label = label(totals, str(app.credits_earned), 30, True)
    app.credits_label.pack(anchor="w")
    history = panel(activity, "Recent contributions", "Saved contribution records; model-run details remain in the portal.")
    app.history_box = ctk.CTkTextbox(history, height=220, fg_color=BG, text_color=INK, corner_radius=6,
                                    border_width=1, border_color=BORDER, font=("Consolas", 11), wrap="word")
    app.history_box.pack(fill="x")
    app.update_work_history()
    help_page(pages["Help"])
