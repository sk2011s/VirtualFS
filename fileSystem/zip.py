"""
vfs_zip.py — Export a VFS tree as a ZIP archive.

Uses only the stdlib `zipfile` module. No external dependencies.
"""

import io
import zipfile

from fileSystem import fs


# FAT-style forbidden characters, mapped to safe replacements.
_BAD_CHARS = ':*?"<>|'


def _safe_name(name: str) -> str:
    """Replace characters that are invalid on Windows filesystems."""
    out = "".join("_" if c in _BAD_CHARS else c for c in name)
    return out.strip() or "_"


def collect_paths(root):
    """
    Walk the VFS tree and return a list of (arcname, content) tuples.

    Directories get an entry with content=b"" and a trailing slash,
    so empty folders survive the round-trip.
    """
    entries = []

    def walk(node, prefix):
        for name, child in node.files.items():
            safe = _safe_name(name)
            path = f"{prefix}/{safe}" if prefix else safe
            if isinstance(child, fs.Directory):
                entries.append((path + "/", b""))
                walk(child, path)
            elif isinstance(child, fs.File):
                entries.append((path, child.content))

    walk(root, "")
    return entries


def build_zip_in_memory(entries) -> bytes:
    """Build a ZIP archive in memory from (arcname, content) tuples."""
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, "w", zipfile.ZIP_STORED) as zf:
        for arcname, content in entries:
            # Directories: a trailing "/" entry with no data
            if arcname.endswith("/"):
                info = zipfile.ZipInfo(arcname)
                info.external_attr = 0o40755 << 16   # drwxr-xr-x
                zf.writestr(info, b"")
            else:
                zf.writestr(arcname, content)
    return bio.getvalue()


def export_root_to_zip(root, out_path: str) -> int:
    """
    Walk the VFS root, build a ZIP, and write it to disk.
    Returns the size of the written file in bytes.
    """
    entries = collect_paths(root)
    data = build_zip_in_memory(entries)
    with open(out_path, "wb") as fh:
        fh.write(data)
    return len(data)


def export_selection_to_zip(nodes, out_path: str) -> int:
    """
    Export only the given nodes (a folder or a file).
    A folder keeps its own name as the top-level entry in the archive.
    """
    entries = []
    for n in nodes:
        if isinstance(n, fs.Directory):
            entries.append((_safe_name(n.name) + "/", b""))
            sub = collect_paths(n)
            for arc, data in sub:
                entries.append((_safe_name(n.name) + "/" + arc, data))
        else:
            entries.append((_safe_name(n.name), n.content))

    data = build_zip_in_memory(entries)
    with open(out_path, "wb") as fh:
        fh.write(data)
    return len(data)