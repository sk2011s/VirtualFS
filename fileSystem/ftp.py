import socket
import threading
import time
from typing import Callable, Optional

from fileSystem import fs


class VFSFTPServer:
    """A tiny FTP server whose filesystem is a `fs.Root` instance."""

    def __init__(
        self,
        root,
        on_change: Optional[Callable[[], None]] = None,
        host: str = "127.0.0.1",
        port: int = 2121,
        user: str = "user",
        password: str = "pass",
        passive_ports: range = range(50000, 50010),
    ):
        self.root = root
        self.on_change = on_change
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.passive_ports = list(passive_ports)

        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._clients: list[threading.Thread] = []

    # ---------- lifecycle ----------
    def start(self):
        """Bind and start accepting clients in a background thread."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(8)
        self._sock.settimeout(0.5)
        self._stop.clear()
        self._thread = threading.Thread(target=self._accept_loop,
                                        daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the server and close all connections."""
        self._stop.set()
        try:
            if self._sock:
                self._sock.close()
        except OSError:
            pass
        if self._thread:
            self._thread.join(timeout=1.0)

    def _accept_loop(self):
        while not self._stop.is_set():
            try:
                conn, addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            t = threading.Thread(target=self._handle_client,
                                 args=(conn, addr), daemon=True)
            t.start()
            self._clients.append(t)

    # ---------- per-client handler ----------
    def _handle_client(self, conn: socket.socket, addr):
        session = _Session(self, conn, addr)
        try:
            session.run()
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    # ---------- helpers used by _Session ----------
    def notify_change(self):
        if self.on_change:
            try:
                self.on_change()
            except Exception:
                pass


class _Session:
    """One connected FTP client."""

    def __init__(self, server: VFSFTPServer, conn: socket.socket, addr):
        self.srv = server
        self.conn = conn
        self.addr = addr
        self.cwd = server.root              # fs.Directory
        self.authed = False
        self.rename_from = None
        self.transfer_type = "I"            # binary by default
        self.data_listener: Optional[socket.socket] = None
        self.pasv_port: Optional[int] = None
        self.active_addr: Optional[tuple[str, int]] = None
        self.conn.settimeout(None)

    # ---------- IO helpers ----------
    def send(self, line: str):

        self.conn.sendall((line + "\r\n").encode("utf-8", "replace"))

    def recv_line(self) -> Optional[str]:
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = self.conn.recv(1)
            if not chunk:
                return None
            buf += chunk
            if len(buf) > 4096:
                return None
        return buf.decode("utf-8", "replace").rstrip("\r\n")

    def open_data(self) -> Optional[socket.socket]:
        """Return a data socket for PASV or PORT mode."""
        if self.pasv_port is not None:
            # passive: we opened a listener, client connects to it
            assert self.data_listener is not None
            self.data_listener.settimeout(10)
            try:
                data, _ = self.data_listener.accept()
            except (socket.timeout, OSError):
                return None
            finally:
                try:
                    self.data_listener.close()
                except OSError:
                    pass
                self.data_listener = None
            return data
        if self.active_addr is not None:
            # active: we connect back to the client
            try:
                data = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                data.settimeout(10)
                data.connect(self.active_addr)
                return data
            except OSError:
                return None
        return None

    def close_data(self, data: Optional[socket.socket]):
        if data is not None:
            try:
                data.close()
            except OSError:
                pass

    # ---------- path helpers ----------
    def resolve(self, arg: str):
        """Resolve a client-supplied path against cwd. Returns
        (parent_dir, name) for the target, or None if invalid."""
        arg = arg.strip()
        if not arg:
            return None
        if arg.startswith("/"):
            # absolute from root
            parts = [p for p in arg.split("/") if p]
            base = self.srv.root
        else:
            parts = [p for p in arg.split("/") if p]
            base = self.cwd
        # walk; allow "." and ".."
        cur = base
        if not parts:
            return (cur.parent or cur, cur.name)  # "/" -> root itself
        for p in parts[:-1]:
            if p == ".":
                continue
            if p == "..":
                cur = cur.parent or cur
                continue
            nxt = cur.files.get(p)
            if not isinstance(nxt, fs.Directory):
                return None
            cur = nxt
        name = parts[-1]
        return (cur, name)

    def path_string(self, node) -> str:
        """Return FTP-style absolute path for a node."""
        chain = []
        cur = node
        while cur is not None and cur is not self.srv.root:
            chain.append(cur.name)
            cur = cur.parent
        chain.reverse()
        return "/" + "/".join(chain) if chain else "/"

    # ---------- main loop ----------
    def run(self):
        self.send("220 VFS-FTP ready")
        while True:
            line = self.recv_line()
            if line is None:
                return
            if not line:
                continue
            cmd, _, arg = line.partition(" ")
            cmd = cmd.upper()
            try:
                keep = self.dispatch(cmd, arg)
            except Exception as e:
                self.send("451 Requested action aborted")
                continue
            if not keep:
                return

    # ---------- command dispatcher ----------
    def dispatch(self, cmd: str, arg: str) -> bool:
        handler = getattr(self, f"cmd_{cmd}", None)
        if handler is None:
            self.send("502 Command not implemented")
            return True
        return handler(arg)

    # ---------- auth ----------

    def cmd_OPTS(self, arg):
        # Windows Explorer sends "OPTS UTF8 ON". Acknowledge it
        # in the exact format Windows expects.
        a = arg.strip().lower()
        if a in ("utf8 on", "utf-8 on", "utf8", "utf-8"):
            self.send("200 UTF8 set to on")
        else:
            self.send("200 OK")
        return True

    def cmd_USER(self, arg):
        # Anonymous-only server: accept any user, ask for a password
        # (clients always send one; some send an empty string).
        self.send("331 Anonymous login ok, send your email as password")
        return True

    def cmd_PASS(self, arg):
        # Accept anything. No authentication.
        self.authed = True
        self.send("230 Anonymous login ok")
        return True

    def cmd_SYST(self, arg):
        self.send("215 UNIX Type: L8")
        return True

    def cmd_FEAT(self, arg):
        self.send("211-Features")
        self.send(" SIZE")
        self.send(" UTF8")
        self.send("211 End")
        return True

    def cmd_NOOP(self, arg):
        self.send("200 OK")
        return True

    def cmd_SYST(self, arg):
        self.send("215 Windows_NT version 10.0")
        return True

    def cmd_QUIT(self, arg):
        self.send("221 Bye")
        return False

    # ---------- navigation ----------
    def cmd_PWD(self, arg):
        p = self.path_string(self.cwd)
        self.send(f'257 "{p}" is the current directory')
        return True

    def cmd_CWD(self, arg):
        arg = arg.strip()
        if arg in ("/", ""):
            self.cwd = self.srv.root
            self.send("250 CWD command successful")
            return True
        r = self.resolve(arg)
        if not r:
            self.send("550 No such directory")
            return True
        parent, name = r
        node = parent.files.get(name)
        if isinstance(node, fs.Directory):
            self.cwd = node
            self.send("250 CWD command successful")
        else:
            self.send("550 No such directory")
        return True

    def cmd_PORT(self, arg):
        try:
            nums = [int(x) for x in arg.split(",")]
            if len(nums) != 6:
                raise ValueError
            host = ".".join(str(n) for n in nums[:4])
            port = nums[4] * 256 + nums[5]
            self.active_addr = (host, port)
            self.pasv_port = None
            if self.data_listener:
                try:
                    self.data_listener.close()
                except OSError:
                    pass
                self.data_listener = None
            self.send("200 PORT command successful")
        except ValueError:
            self.send("501 Bad PORT syntax")
        return True

    def cmd_CDUP(self, arg):
        if self.cwd.parent is not None:
            self.cwd = self.cwd.parent
        self.send("250 CWD command successful")
        return True

    # ---------- listing ----------
    def _format_list_line(self, name, node) -> str:
        if isinstance(node, fs.Directory):
            size = 0
            kind = "d"
        else:
            size = len(node.content)
            kind = "-"
        # fixed perms; we don't model permissions in the VFS
        perms = kind + "rwxr-xr-x"
        # use "now" since the VFS has no timestamps
        ts = time.strftime("%b %d %H:%M")
        return f"{perms} 1 owner group {size:>12} {ts} {name}"

    def cmd_LIST(self, arg):
        self.send("150 Opening data connection")
        data = self.open_data()
        if data is None:
            self.send("425 Can't open data connection")
            return True
        # If arg is a dir, list it; if a file, list just that file
        target = None
        if arg.strip():
            r = self.resolve(arg)
            if r:
                parent, name = r
                target = parent.files.get(name)
        if target is None:
            entries = self.cwd.ls()
            for name, node in entries.items():
                data.sendall((self._format_list_line(name, node)
                              + "\r\n").encode())
        elif isinstance(target, fs.Directory):
            for name, node in target.ls().items():
                data.sendall((self._format_list_line(name, node)
                              + "\r\n").encode())
        else:
            data.sendall((self._format_list_line(target.name, target)
                          + "\r\n").encode())
        self.close_data(data)
        self.send("226 Transfer complete")

    def cmd_NLST(self, arg):
        self.send("150 Opening data connection")
        data = self.open_data()
        if data is None:
            self.send("425 Can't open data connection")
            return True
        for name in self.cwd.ls().keys():
            data.sendall((name + "\r\n").encode())
        self.close_data(data)
        self.send("226 Transfer complete")

    def cmd_SIZE(self, arg):
        r = self.resolve(arg)
        if not r:
            self.send("550 Not found")
            return True
        parent, name = r
        node = parent.files.get(name)
        if isinstance(node, fs.File):
            self.send(f"213 {len(node.content)}")
        else:
            self.send("550 Not a regular file")
        return True

    def cmd_TYPE(self, arg):
        t = arg.strip().upper()[:1] or "I"
        self.transfer_type = t
        self.send(f"200 Type set to {t}")
        return True

    # ---------- transfer ----------
    def cmd_RETR(self, arg):
        r = self.resolve(arg)
        if not r:
            self.send("550 Not found")
            return True
        parent, name = r
        node = parent.files.get(name)
        if not isinstance(node, fs.File):
            self.send("550 Not a regular file")
            return True
        self.send("150 Opening data connection")
        data = self.open_data()
        if data is None:
            self.send("425 Can't open data connection")
            return True
        try:
            data.sendall(node.content)
        finally:
            self.close_data(data)
        self.send("226 Transfer complete")
        return True

    def cmd_STOR(self, arg):
        r = self.resolve(arg)
        if not r:
            self.send("550 Bad path")
            return True
        parent, name = r
        if not isinstance(parent, fs.Directory):
            self.send("550 Not a directory")
            return True
        self.send("150 Ready to receive")
        data = self.open_data()
        if data is None:
            self.send("425 Can't open data connection")
            return True
        chunks = []
        try:
            while True:
                buf = data.recv(65536)
                if not buf:
                    break
                chunks.append(buf)
        finally:
            self.close_data(data)
        content = b"".join(chunks)
        if name in parent.files and isinstance(parent.files[name], fs.File):
            parent.files[name].content = content
        else:
            parent.touch(name, content)
        self.srv.notify_change()
        self.send("226 Transfer complete")
        return True

    # ---------- mutations ----------
    def cmd_DELE(self, arg):
        r = self.resolve(arg)
        if not r:
            self.send("550 Not found")
            return True
        parent, name = r
        node = parent.files.get(name)
        if not isinstance(node, fs.File):
            self.send("550 Not a regular file")
            return True
        parent.files.pop(name)
        self.srv.notify_change()
        self.send("250 Deleted")
        return True

    def cmd_MKD(self, arg):
        r = self.resolve(arg)
        if not r:
            self.send("550 Bad path")
            return True
        parent, name = r
        if not isinstance(parent, fs.Directory):
            self.send("550 Not a directory")
            return True
        if name in parent.files:
            self.send("550 Already exists")
            return True
        parent.mkdir(name)
        self.srv.notify_change()
        self.send(f'257 "{self.path_string(parent.files[name])}" created')
        return True

    def cmd_RMD(self, arg):
        r = self.resolve(arg)
        if not r:
            self.send("550 Not found")
            return True
        parent, name = r
        node = parent.files.get(name)
        if not isinstance(node, fs.Directory):
            self.send("550 Not a directory")
            return True
        if node.files:
            self.send("550 Directory not empty")
            return True
        parent.files.pop(name)
        self.srv.notify_change()
        self.send("250 Removed")
        return True

    # ---------- data connection modes ----------
    def cmd_PASV(self, arg):
        # Pick a free port from the pool and listen on it
        port = self._pick_pasv_port()
        if port is None:
            self.send("425 No free passive port")
            return True
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.srv.host, port))
        listener.listen(1)
        self.data_listener = listener
        self.pasv_port = port
        self.active_addr = None
        host = self.srv.host.replace(".", ",")
        self.send(f"227 Entering Passive Mode ({host},{port // 256},{port % 256})")
        return True

    def _pick_pasv_port(self) -> Optional[int]:
        for p in self.srv.passive_ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.bind((self.srv.host, p))
                s.close()
                return p
            except OSError:
                s.close()
                continue
        return None

    def cmd_PORT(self, arg):
        # arg: h1,h2,h3,h4,p1,p2
        try:
            nums = [int(x) for x in arg.split(",")]
            if len(nums) != 6:
                raise ValueError
            host = ".".join(str(n) for n in nums[:4])
            port = nums[4] * 256 + nums[5]
            self.active_addr = (host, port)
            self.pasv_port = None
            if self.data_listener:
                try:
                    self.data_listener.close()
                except OSError:
                    pass
                self.data_listener = None
            self.send("200 PORT command successful")
        except ValueError:
            self.send("501 Bad PORT syntax")
        return True


# ---------- convenience for the UI ----------
