"""Build the protected ribbon "shell" from the real pyRevit extension.

    python tools/build_shell.py MyTools.extension _shell

For every button the shell gets a stub script.py (title, tooltip and other pyRevit settings copied
from the real script, but no code), plus every non-Python file: icons, bundle.yaml, data files.
Signed-in users download the shell onto their ribbon; each stub loads the real code when clicked.

Runs automatically on GitHub (see .github/workflows/build-shell.yml) whenever the extension changes.
"""
import ast
import os
import shutil
import sys

ACCOUNT_PANEL = "Account"
SCRIPT_NAMES = ("script.py", "config.py")
# pyRevit reads these module-level settings from a button's script without running it.
COPY_DUNDERS = ("__title__", "__doc__", "__author__", "__context__", "__highlight__", "__helpurl__",
                "__min_revit_ver__", "__max_revit_ver__", "__beta__", "__cleanengine__",
                "__fullframeengine__", "__persistentengine__", "__selfinit__", "__authors__")
SKIP_DIRS = {"__pycache__", ".git", "bak", "backup", "old"}
SKIP_FILES = {".ds_store", "thumbs.db", "desktop.ini"}

STUB = '''{shebang}# -*- coding: utf-8 -*-
# Protected {tool} button. The code is loaded from GitHub when you click it,
# and only for signed-in users who have access.
{settings}
from mytools_vault import runner
runner.run(__file__, globals())
'''


def read_settings(path):
    """Literal module-level pyRevit settings (and the docstring) from a script, without running it."""
    with open(path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8-sig", errors="replace")
    shebang = text.splitlines()[0] + "\n" if text.startswith("#!") else ""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        # Python 2-only syntax: fall back to the title from the folder name.
        return shebang, {}
    settings = {}
    doc = ast.get_docstring(tree, clean=False)
    if doc:
        settings["__doc__"] = doc
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in COPY_DUNDERS:
                try:
                    settings[name] = ast.literal_eval(node.value)
                except ValueError:
                    pass
    return shebang, settings


def make_stub(src_path, tool):
    shebang, settings = read_settings(src_path)
    lines = ["%s = %r" % (k, settings[k]) for k in COPY_DUNDERS if k in settings]
    return STUB.format(shebang=shebang, tool=tool, settings="\n".join(lines))


def add_account_to_layout(path):
    """If the tab orders its panels with a layout list, keep the public Account panel on it."""
    try:
        import yaml
    except ImportError:
        return
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    layout = data.get("layout")
    if isinstance(layout, list) and ACCOUNT_PANEL not in [str(x) for x in layout]:
        layout.append(ACCOUNT_PANEL)
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def build(ext_dir, out_dir):
    tool = os.path.basename(os.path.normpath(ext_dir)).replace(".extension", "")
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)
    stubs = files = 0
    for tab in sorted(os.listdir(ext_dir)):
        tab_dir = os.path.join(ext_dir, tab)
        if not (tab.endswith(".tab") and os.path.isdir(tab_dir)):
            continue
        for dirpath, dirnames, filenames in os.walk(tab_dir):
            dirnames[:] = sorted(d for d in dirnames if d.lower() not in SKIP_DIRS and not d.startswith("."))
            rel_dir = os.path.relpath(dirpath, ext_dir)
            if os.path.basename(dirpath) == ACCOUNT_PANEL + ".panel":
                print("Skipping %s: the Account panel is part of the public installer." % rel_dir)
                dirnames[:] = []
                continue
            for name in sorted(filenames):
                if name.lower() in SKIP_FILES or name.startswith("."):
                    continue
                src = os.path.join(dirpath, name)
                dst = os.path.join(out_dir, rel_dir, name)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if name.endswith(".py"):
                    if name in SCRIPT_NAMES:
                        with open(dst, "w", encoding="utf-8", newline="\n") as f:
                            f.write(make_stub(src, tool))
                        stubs += 1
                    # Other .py files are helper modules: served from GitHub at run time, never copied.
                    continue
                shutil.copyfile(src, dst)
                files += 1
                if name == "bundle.yaml" and dirpath == tab_dir:
                    add_account_to_layout(dst)
    print("Shell built in %s: %d button scripts, %d other files." % (out_dir, stubs, files))
    return stubs, files


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2])
