class Directory:
    def __init__(self, name: str):
        self.name = name
        self.files = {}
        self.parent = None

    def rm(self, path: str = None):
        if not path:
            self.parent.files.pop(self.name)
        else:
            self.files[path].rm()

    def mkdir(self, name):
        d = Directory(name)
        d.parent = self
        self.files[name] = d
        return d

    def touch(self, name, content: bytes):
        f = File(name)
        f.content = content
        f.parent = self
        self.files[name] = f
        return f

    def ls(self):
        return {k: self.files[k] for k in sorted(self.files)}

    def make_tree(self, indent=""):
        files = {k: v for k, v in
                 sorted(self.files.items(),
                        key=lambda item: (isinstance(item[1], File),
                                          item[0].lower()))}
        tree = f"{indent}{self.name}\n"
        for key, child in files.items():
            if isinstance(child, File):
                tree += f"{indent}\t{child.name}\n"
            else:
                tree += child.make_tree(indent + "\t")
        return tree

    def tree(self):
        print(self.make_tree())

    def __str__(self):
        return self.name

    def __repr__(self):
        return str(self)

class File:
    def __init__(self, name: str):
        self.parent = None
        self.name = name
        self.format = self.name.split(".")[-1] if "." in self.name else ""
        self.content = b""

    def rm(self):
        # NOTE: original had self.parent.file -> typo. Fixed to .files
        self.parent.files.pop(self.name)

    def __str__(self):
        return self.name

    def __repr__(self):
        return str(f"{self.name} {len(self.content)}B" +
                   (f" -- {self.format.upper()} file"
                    if self.format else ""))

class Root(Directory):
    def __init__(self):
        Directory.__init__(self, "root")

    def rm(self, path: str = None):
        if not path:
            print("You Cant Remove ROOT!")
        else:
            self.files[path].rm()
