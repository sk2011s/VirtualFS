import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
from os import name, environ, path
from tkinter import ttk
from tkinter.filedialog import askopenfiles, askdirectory, asksaveasfilename
from tkinter.messagebox import askokcancel
from tkinter.simpledialog import askstring
from datetime import datetime

from fileSystem import fs, ftp
from fileSystem.zip import export_root_to_zip, export_selection_to_zip

# ---------- Color palette ----------
BG = "#f3f3f3"
PANEL = "#fafafa"
BORDER = "#e5e5e5"
TEXT = "#1f1f1f"
TEXT_DIM = "#6b6b6b"
ACCENT = "#0067c0"
ACCENT_HOV = "#1a7fd4"
SEL_BG = "#cce4f7"
RIBBON_BG = "#ffffff"
TOOLBAR_BG = "#f3f3f3"
STATUS_BG = "#f3f3f3"


def apply_theme(root):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.configure(bg=BG)

    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("Ribbon.TFrame", background=RIBBON_BG)
    style.configure("Toolbar.TFrame", background=TOOLBAR_BG)
    style.configure("Status.TFrame", background=STATUS_BG)

    style.configure("TLabel", background=BG, foreground=TEXT,
                    font=("Segoe UI", 9))
    style.configure("Dim.TLabel", background=STATUS_BG,
                    foreground=TEXT_DIM, font=("Segoe UI", 9))

    style.configure("Tool.TButton",
                    background=TOOLBAR_BG, foreground=TEXT,
                    borderwidth=0, focuscolor=TOOLBAR_BG,
                    padding=(8, 4), font=("Segoe UI Symbol", 11))
    style.map("Tool.TButton",
              background=[("active", "#e5e5e5"), ("pressed", "#dcdcdc")])

    style.configure("Accent.TButton",
                    background=ACCENT, foreground="white",
                    borderwidth=0, focuscolor=ACCENT,
                    padding=(12, 5), font=("Segoe UI", 9, "bold"))
    style.map("Accent.TButton",
              background=[("active", ACCENT_HOV), ("pressed", "#005aa8")])

    style.configure("Explorer.Treeview",
                    background="white", fieldbackground="white",
                    foreground=TEXT, borderwidth=0, rowheight=28,
                    font=("Segoe UI", 9))
    style.map("Explorer.Treeview",
              background=[("selected", SEL_BG)],
              foreground=[("selected", TEXT)])
    style.configure("Explorer.Treeview.Heading",
                    background=TOOLBAR_BG, foreground=TEXT_DIM,
                    relief="flat", font=("Segoe UI", 9), padding=(8, 6))
    style.map("Explorer.Treeview.Heading",
              background=[("active", "#e8e8e8")])

    style.configure("TSeparator", background=BORDER)


# ---------- Text icons ----------
ICON = {
    "back": "←", "up": "↑", "refresh": "⟳",
    "search": "🔍",
    "folder": "📁", "file": "📄",
    "image": "🖼", "doc": "📃", "pdf": "📕", "zip": "🗜",
    "video": "🎬", "audio": "🎵", "code": "📜", "vhd": "💾",
    "new": "＋", "upload": "↥", "trash": "🗑",
    "root": "🗂",
}

# Map file extension -> icon key. Extend as needed.
EXT_ICON = {
    "png": "image", "jpg": "image", "jpeg": "image", "gif": "image",
    "svg": "image", "webp": "image", "bmp": "image", "ico": "image",
    "pdf": "pdf",
    "zip": "zip", "rar": "zip", "7z": "zip", "tar": "zip", "gz": "zip",
    "mp4": "video", "mkv": "video", "avi": "video", "mov": "video",
    "mp3": "audio", "wav": "audio", "ogg": "audio", "flac": "audio",
    "py": "code", "js": "code", "ts": "code", "c": "code",
    "cpp": "code", "h": "code", "java": "code", "rs": "code",
    "go": "code", "rb": "code", "php": "code", "html": "code",
    "css": "code", "json": "code", "xml": "code", "yml": "code",
    "vhd": "vhd", "vhdx": "vhd", "iso": "vhd", "img": "vhd",
    "txt": "doc", "md": "doc", "log": "doc",
}


def human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024.0
        if n < 1024:
            return f"{n:.1f} {unit}"
    return f"{n:.1f} PB"


def icon_for(node) -> str:
    # isinstance checks against your actual classes
    if isinstance(node, fs.Directory):
        return ICON["root"] if isinstance(node, fs.Root) else ICON["folder"]
    ext = node.format.lower()
    return ICON.get(EXT_ICON.get(ext, "file"), ICON["file"])


# =========================================================
#  Ribbon: virtual app tabs + file actions + Export
# =========================================================
class Ribbon(ttk.Frame):
    def __init__(self, master, on_new=None, on_import=None,
                 on_delete=None):
        super().__init__(master, style="Ribbon.TFrame",
                         padding=(10, 8, 10, 6))

        row = ttk.Frame(self, style="Ribbon.TFrame")
        row.pack(fill="x")

        tabs = ttk.Frame(row, style="Ribbon.TFrame")
        tabs.pack(side="left")

        actions = ttk.Frame(row, style="Ribbon.TFrame")
        actions.pack(side="right")

        # Each action button now receives a callback
        for icon, label, cb in [
            (ICON["new"], "New Folder", on_new),
            (ICON["upload"], "Import", on_import),
            (ICON["trash"], "Delete", on_delete),
        ]:
            self._action_button(actions, icon, label, cb)

    def _action_button(self, parent, icon, label, command=None):
        box = tk.Frame(parent, bg=RIBBON_BG, cursor="hand2")
        box.pack(side="left", padx=2)

        ico = tk.Label(box, text=icon, bg=RIBBON_BG, fg=TEXT,
                       font=("Segoe UI Symbol", 14))
        ico.pack(side="top")

        txt = tk.Label(box, text=label, bg=RIBBON_BG, fg=TEXT,
                       font=("Segoe UI", 8))
        txt.pack(side="top")

        def on_enter(_):
            for w in (box, ico, txt):
                w.configure(bg="#eef4fb")

        def on_leave(_):
            for w in (box, ico, txt):
                w.configure(bg=RIBBON_BG)

        # Click handler -> calls the user-provided command
        def on_click(_):
            if command is not None:
                command()

        for w in (box, ico, txt):
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", on_click)


# =========================================================
#  Address bar: navigation + breadcrumb + search
# =========================================================
class AddressBar(ttk.Frame):
    """Breadcrumb is driven by the actual parent chain of the current fs.Directory."""

    def __init__(self, master, on_back=None, on_up=None, on_reload=None):
        super().__init__(master, style="Toolbar.TFrame", padding=(10, 6))

        nav = ttk.Frame(self, style="Toolbar.TFrame")
        nav.pack(side="left")

        # Back / Forward / Up with callbacks
        self.btn_back = ttk.Button(nav, text=ICON["back"],
                                   style="Tool.TButton", width=3,
                                   command=on_back)
        self.btn_back.pack(side="left", padx=(0, 2))

        self.btn_up = ttk.Button(nav, text=ICON["up"],
                                 style="Tool.TButton", width=3,
                                 command=on_up)
        self.btn_up.pack(side="left", padx=(0, 2))

        ttk.Separator(nav, orient="vertical").pack(
            side="left", fill="y", padx=6, pady=4)

        ttk.Button(nav, text=ICON["refresh"], style="Tool.TButton",
                   width=3, command=on_reload).pack(side="left")

        addr = ttk.Frame(self, style="Toolbar.TFrame")
        addr.pack(side="left", fill="x", expand=True, padx=8)

        # breadcrumb container; contents rebuilt by set_path()
        self.bc = tk.Frame(addr, bg="white", highlightthickness=1,
                           highlightbackground=BORDER)
        self.bc.pack(fill="x")

        search = tk.Frame(self, bg="white", highlightthickness=1,
                          highlightbackground=BORDER)
        search.pack(side="right", padx=(0, 4))

    def set_path(self, node):
        """Rebuild breadcrumb from a fs.Directory node upward."""
        for w in self.bc.winfo_children():
            w.destroy()

        # Walk up via .parent to build the chain
        chain = []
        cur = node
        while cur is not None:
            chain.append(cur)
            cur = cur.parent
        chain.reverse()

        for i, d in enumerate(chain):
            is_last = i == len(chain) - 1
            label = (ICON["root"] + " ") if isinstance(d, fs.Root) else ""
            label += d.name
            sep = "  ›  " if not is_last else ""
            tk.Label(self.bc, text=label + sep, bg="white",
                     fg=TEXT if is_last else TEXT_DIM,
                     font=("Segoe UI", 9, "bold" if is_last else "normal"),
                     padx=2, pady=5).pack(side="left")

        # Filler
        tk.Label(self.bc, text="", bg="white").pack(
            side="left", fill="x", expand=True)


# =========================================================
#  Sort bar: shows current fs.Directory name + item count
# =========================================================
class SortBar(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=(12, 8))

        self.title = tk.Label(self, text="", bg=PANEL, fg=TEXT,
                              font=("Segoe UI", 10, "bold"))
        self.title.pack(side="left")

        self.count = tk.Label(self, text="", bg=PANEL, fg=TEXT_DIM,
                              font=("Segoe UI", 8))
        self.count.pack(side="left", padx=(10, 0))

        right = tk.Frame(self)
        right.pack(side="right")

    def set_dir(self, node):
        self.title.configure(text=f"{icon_for(node)}  {node.name}")
        n = len(node.files)
        self.count.configure(text=f"·   {n} item{'s' if n != 1 else ''}")


# =========================================================
#  fs.File list: renders one fs.Directory's children via .ls()
# =========================================================
class FileList(ttk.Frame):
    """Displays the children of a fs.Directory using its .ls() method."""

    def __init__(self, master, on_open_dir=None, on_open_file=None):
        super().__init__(master)
        self.on_open_dir = on_open_dir
        self.on_open_file = on_open_file
        self.current = None  # current fs.Directory

        columns = ("name", "date", "type", "size")
        self.tree = ttk.Treeview(self, columns=columns, show="headings",
                                 style="Explorer.Treeview",
                                 selectmode="extended")

        self.tree.heading("name", text="Name", anchor="w")
        self.tree.heading("date", text="Date modified", anchor="w")
        self.tree.heading("type", text="Type", anchor="w")
        self.tree.heading("size", text="Size", anchor="e")

        self.tree.column("name", width=360, anchor="w")
        self.tree.column("date", width=160, anchor="w")
        self.tree.column("type", width=110, anchor="w")
        self.tree.column("size", width=100, anchor="e")

        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.tag_configure("dir", foreground="#155a9c")
        self.tree.tag_configure("even", background="white")
        self.tree.tag_configure("odd", background="#fbfcfd")

        # Double-click: open folder
        self.tree.bind("<Double-1>", self._on_double_click)
        # Keep a mapping from row id -> node for later lookup
        self._row_to_node = {}

    # ---------- public API ----------
    def show(self, directory):
        """Render a fs.Directory's contents using its .ls() method."""
        self.current = directory
        self.tree.delete(*self.tree.get_children())
        self._row_to_node.clear()

        # .ls() already returns a name-sorted dict
        items = directory.ls()

        # Folders first, then files (both already alpha-sorted inside groups)
        dirs = [(k, v) for k, v in items.items() if isinstance(v, fs.Directory)]
        files = [(k, v) for k, v in items.items() if isinstance(v, fs.File)]

        for i, (name, node) in enumerate(dirs + files):
            is_dir = isinstance(node, fs.Directory)
            row_type = "Folder" if is_dir else (
                node.format.upper() if node.format else "fs.File")
            size = "" if is_dir else human_size(len(node.content))
            date = ""  # your VFS has no timestamp field

            iid = self.tree.insert(
                "", "end",
                values=(f"{icon_for(node)}   {name}", date, row_type, size),
                tags=("dir" if is_dir else "file",
                      "odd" if i % 2 else "even"),
            )
            self._row_to_node[iid] = node

    def selected_nodes(self) -> list[fs.Directory | fs.File]:
        """Return the model nodes for the current selection."""
        return [self._row_to_node[iid] for iid in self.tree.selection()
                if iid in self._row_to_node]

    # ---------- internals ----------
    def _on_double_click(self, _evt):
        nodes = self.selected_nodes()
        if not nodes:
            return
        node = nodes[0]
        if isinstance(node, fs.Directory):
            if self.on_open_dir:
                self.on_open_dir(node)
        else:
            if self.on_open_file:
                self.on_open_file(node)


# =========================================================
#  Status bar
# =========================================================
class StatusBar(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, style="Status.TFrame", padding=(12, 5))

        self.left = tk.Label(self, text="", bg=STATUS_BG, fg=TEXT_DIM,
                             font=("Segoe UI", 9))
        self.left.pack(side="left")

        self.mid = tk.Label(self, text="FTP OFF", font=("Segoe UI", 9))
        self.mid.pack(side="right")

        self.right = tk.Label(self, text="Ready",
                              font=("Segoe UI", 9))
        self.right.pack(side="right")


    def set_info(self, directory, selected=0):
        n_dirs = sum(1 for v in directory.files.values()
                     if isinstance(v, fs.Directory))
        n_files = sum(1 for v in directory.files.values()
                      if isinstance(v, fs.File))
        total = sum(len(v.content) for v in directory.files.values()
                    if isinstance(v, fs.File))
        text = (f"{ICON['folder']}  {n_dirs} folder(s)  ·  "
                f"{n_files} file(s)  ·  {human_size(total)}")
        if selected:
            text += f"   ·   {selected} selected"
        self.left.configure(text=text)

    def set_size(self, root):
        # Total size across the whole VFS
        def walk(d):
            t = 0
            for v in d.files.values():
                if isinstance(v, fs.Directory):
                    t += walk(v)
                else:
                    t += len(v.content)
            return t

        self.right.configure(text=f"VFS · {human_size(walk(root))} | ")


# =========================================================
#  Main window: wires the UI to the VFS model
# =========================================================
class Explorer(tk.Tk):
    def __init__(self, root_node):
        super().__init__()
        self.root_node: fs.Root = root_node  # your fs.Root() instance
        self.current: fs.Directory = root_node  # current fs.Directory
        self.history: list[fs.Directory] = [root_node]  # navigation history
        self.hist_idx: int = 0

        self.title("VFS Explorer")
        self.geometry("1100x640")
        self.minsize(860, 520)
        apply_theme(self)

        self.ftp_server: ftp.VFSFTPServer | None = None
        self.ftp_running = False

        # Events
        self.bind("<KeyPress-Delete>", func=lambda e: self.delete())
        self.bind("<Control-o>", func=lambda e: self.import_f())
        self.bind("<Control-n>", func=lambda e: self.new_folder())
        self.bind("<Control-s>", func=lambda e: self.save())

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Menu
        self.menu = tk.Menu(self)
        self.config(menu=self.menu)

        self.filemenu = tk.Menu(self.menu)
        self.menu.add_cascade(label="File", menu=self.filemenu)

        self.filemenu.add_command(label="Save", command=self.save)
        self.filemenu.add_command(label="Import", command=self.import_f)

        self.filemenu.add_separator()
        self.filemenu.add_command(label="Toggle FTP",
                                  command=self.toggle_ftp)

        self.filemenu.add_command(label="Export ZIP",
                                  command=self.export_zip)

        # Ribbon
        Ribbon(self, self.new_folder, self.import_f, self.delete).pack(fill="x")
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Address bar
        self.address = AddressBar(self, on_back=self.back, on_up=self.up, on_reload=self._render)
        self.address.pack(fill="x")
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Content
        content = tk.Frame(self, bg=PANEL)
        content.pack(fill="both", expand=True)

        self.sortbar = SortBar(content)
        self.sortbar.pack(fill="x")
        tk.Frame(content, bg=BORDER, height=1).pack(fill="x")

        self.filelist = FileList(
            content,
            on_open_dir=self.open_dir,
            on_open_file=self.open_file,
        )
        self.filelist.pack(fill="both", expand=True)

        # Status bar
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        self.status = StatusBar(self)
        self.status.pack(fill="x")

        # Initial render
        self._render()

    # ---------- export ----------
    def export_zip(self):
        """Ask for a path, then write either the whole VFS or the
        current selection as a ZIP archive."""
        selected = self.filelist.selected_nodes()

        out = asksaveasfilename(
            title="Export to ZIP",
            defaultextension=".zip",
            filetypes=[("ZIP archive", "*.zip"), ("All files", "*.*")],
            initialfile="vfs.zip",
        )
        if not out:
            return

        self.status.right.configure(text="Building ZIP…")
        self.update_idletasks()

        try:
            if selected:
                size = export_selection_to_zip(selected, out)
            else:
                size = export_root_to_zip(self.root_node, out)
        except Exception as e:
            self.status.right.configure(text="Export failed")
            self._err("Export to ZIP failed", e)
            return

        self.status.right.configure(
            text=f"ZIP written · {human_size(size)} → {out}")

    # ---------- FTP server ----------
    def toggle_ftp(self):
        """Start the FTP server if stopped, stop it if running."""
        if self.ftp_running:
            self.stop_ftp()
        else:
            self.start_ftp()

    def start_ftp(self):
        if self.ftp_running:
            return
        try:
            self.ftp_server = ftp.VFSFTPServer(
                root=self.root_node,
                on_change=lambda: self.after(0, self._render),
                host="127.0.0.1",
                port=2121,
                user="user",
                password="pass",
            )
            self.ftp_server.start()
            self.ftp_running = True
            self.status.mid.configure(text="FTP RUN ON: 127.0.0.1:2121")
        except OSError as e:
            self.ftp_server = None
            self.ftp_running = False
            self._err("Failed to start FTP", e)

    def stop_ftp(self):
        if not self.ftp_running:
            return
        try:
            if self.ftp_server:
                self.ftp_server.stop()
        finally:
            self.ftp_server = None
            self.ftp_running = False
            self.status.mid.configure(text="FTP OFF")

    # ---------- operation ----------

    def delete(self):
        selected = self.filelist.selected_nodes()
        if not selected: return
        if askokcancel("Delete?", f"Are you sure you want permanetly delete {len(selected)} File/Folder(s)?"):
            for f in selected:
                f.rm()

            self._render()

    def import_f(self):
        files = askopenfiles('rb')
        for f in files:
            self.current.touch(path.basename(f.name), f.read())

        self._render()

    def new_folder(self):
        name = askstring("New Folder", "Folder Name:")
        if not name: return
        self.current.mkdir(name)
        self._render()

    def save(self):
        selected = self.filelist.selected_nodes()
        dir = askdirectory(mustexist=True)
        for f in selected:
            p = path.join(dir, f.name)
            if isinstance(f, fs.File):
                if path.exists(p):
                    if not askokcancel("File already exists",
                                       f"file {f.name} is already exists, do you want replace it?"):
                        continue
                with open(p, "wb") as fi:
                    fi.write(f.content)
            else:
                continue

    # ---------- open file with default app ----------
    def open_file(self, node: fs.File):
        """Async version: opens file in a worker thread so the UI stays alive."""
        tmp_dir = tempfile.mkdtemp(prefix="vfs_")
        tmp_path = path.join(tmp_dir, node.name)
        try:
            with open(tmp_path, "wb") as fh:
                fh.write(node.content)
        except OSError as e:
            self._err("Failed to write temp file", e)
            return

        before = node.content
        self.status.right.configure(text=f"Opening {node.name}…")

        def worker():
            try:
                self._launch_and_wait(tmp_path)
                with open(tmp_path, "rb") as fh:
                    after = fh.read()
            except Exception as e:
                self.after(0, lambda: self._err("Open failed", e))
                self.after(0, lambda: shutil.rmtree(tmp_dir, ignore_errors=True))
                return

            def finish():
                if after != before:
                    node.content = after
                    self.status.right.configure(
                        text=f"Saved changes to {node.name} "
                             f"({human_size(len(after))})")
                else:
                    self.status.right.configure(text="No changes")
                shutil.rmtree(tmp_dir, ignore_errors=True)
                self._render()

            self.after(0, finish)

        import threading
        threading.Thread(target=worker, daemon=True).start()

        # 4. Refresh the UI (size column may have changed)
        self._render()

    @staticmethod
    def _launch_and_wait(path: str):
        """Open `path` with the OS default application and block
        until the user closes it (best-effort)."""
        if name == "nt":
            # Windows: `start /wait` blocks until the app exits.
            # os.startfile doesn't block, so use subprocess.
            subprocess.run(["cmd", "/c", "start", "/wait", "",
                            path], check=False)
        elif sys.platform == "darwin":
            # macOS: `open -W` waits for the app to exit
            subprocess.run(["open", "-W", path], check=False)
        else:
            # Linux: xdg-open doesn't reliably wait; try a common editor first
            editor = (environ.get("VISUAL")
                      or environ.get("EDITOR")
                      or "xdg-open")
            subprocess.run([editor, path], check=False)

    def _err(self, title, exc):
        from tkinter.messagebox import showerror
        showerror(title, str(exc))

    # ---------- navigation ----------
    def open_dir(self, node):
        """Called when user double-clicks a folder."""
        # Drop forward history when branching
        self.history = self.history[:self.hist_idx + 1]
        self.history.append(node)
        self.hist_idx = len(self.history) - 1
        self.current = node
        self._render()

    def back(self):
        self.history.pop()
        self.hist_idx = len(self.history) - 1
        self.current = self.history[self.hist_idx]
        self._render()

    def up(self):
        self.history = self.history[:self.hist_idx + 1]
        self.history.append(self.current.parent)
        self.hist_idx = len(self.history) - 1
        self.current = self.current.parent
        self._render()

    def _render(self):
        """Refresh the whole UI for the current fs.Directory."""
        self.address.set_path(self.current)
        self.sortbar.set_dir(self.current)
        self.filelist.show(self.current)
        self.status.set_info(self.current, selected=0)
        self.status.set_size(self.root_node)

    def _on_close(self):
        self.stop_ftp()
        self.destroy()

# =========================================================
#  Demo: plug in your VFS classes and populate some data
# =========================================================
if __name__ == "__main__":
    # --- Build a sample VFS ---
    root = fs.Root()
    root.touch("INFO.txt", f"# VFS\ndate: {datetime.now()}".encode())

    # --- Launch UI ---
    app = Explorer(root)
    app.mainloop()
