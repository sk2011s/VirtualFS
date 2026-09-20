# VirtualFS

VirtualFS is a temporary virtual file system that runs entirely in memory (RAM).

It provides a GUI for managing the file system and can also expose the same file system through an FTP server.

## Features

* In-memory virtual file system
* GUI for managing files and directories
* FTP server support
* Manage the same file system through the GUI or FTP
* Export the entire file system as a `.zip` archive
* No permanent storage required
* All files are removed from memory when the application closes

## How It Works

VirtualFS stores files and directories in RAM instead of directly storing them on disk.

While the application is running, the virtual file system can be accessed and modified through the GUI or, when enabled, through an FTP server.

You can export the entire file system to a ZIP archive at any time.

If the application is closed without exporting the file system, all files and directories are lost.

