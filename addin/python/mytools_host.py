# -*- coding: utf-8 -*-
"""Bridge between the MyTools Revit add-in (C#) and the Python buttons.

The add-in calls: init(app_dir, ext_root), startup(), ribbon_json(), run_button(...), run_account(...).
HOST is set by the add-in: HOST.RefreshRibbon(), HOST.Post(System.Action), HOST.ToolName.
"""
import io
import json
import os
import re
import sys
import traceback

HOST = None
APP_DIR = None
EXT_ROOT = None


class _Context(object):
    """What the running button can see (used by the pyrevit replacement modules)."""

    def __init__(self):
        self.reset()

    def reset(self, uiapp=None, script_path=None, shift=False):
        self.uiapp = uiapp
        self.script_path = script_path
        self.bundle_dir = os.path.dirname(script_path) if script_path else None
        self.shift = bool(shift)
        self.output = None
        self.title = None

    @property
    def bundle_name(self):
        if not self.bundle_dir:
            return "MyTools"
        return os.path.basename(self.bundle_dir).rsplit(".", 1)[0]


CTX = _Context()


def tool_name():
    try:
        if HOST is not None:
            return HOST.ToolName
    except Exception:
        pass
    return "MyTools"


def data_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "MyTools")
    if not os.path.isdir(d):
        os.makedirs(d)
    return d


def flush_output():
    out = CTX.output
    if out is not None:
        try:
            out.flush()
        except Exception:
            pass


# ------------------------------------------------------------------ add-in entry points
def init(app_dir, ext_root):
    global APP_DIR, EXT_ROOT
    APP_DIR = app_dir
    EXT_ROOT = ext_root
    py = os.path.join(app_dir, "python")
    if py not in sys.path:
        sys.path.insert(0, py)
    if not os.path.isdir(ext_root):
        os.makedirs(ext_root)


def startup():
    """Quiet access check when Revit starts. Returns a short status word."""
    from mytools_vault import ui
    return ui.startup(EXT_ROOT)


def _config():
    from mytools_vault import core
    return core.load_config(EXT_ROOT)


def run_account(action, uiapp):
    CTX.reset(uiapp)
    from mytools_vault import ui
    cfg = _config()
    if action == "signin":
        ui.sign_in(cfg)
    else:
        ui.account(cfg)


class _OutputStream(object):
    """sys.stdout while a button runs: print() goes to the output window."""

    def __init__(self, ctx):
        self.ctx = ctx

    def write(self, text):
        if text:
            from pyrevit import script
            script.get_output().write_text(text)

    def flush(self):
        pass

    def isatty(self):
        return False


def _is_cancel(exc):
    name = type(exc).__name__
    if name == "OperationCanceledException":
        return True
    inner = getattr(exc, "clsException", None)
    return inner is not None and inner.GetType().Name == "OperationCanceledException"


def run_button(script_path, shift, uiapp):
    """Run a button. Shift+Click runs the button's config.py when it has one."""
    if shift:
        cfg_script = os.path.join(os.path.dirname(script_path), "config.py")
        if os.path.isfile(cfg_script):
            script_path = cfg_script
    CTX.reset(uiapp, script_path, shift)
    from mytools_vault import runner

    globs = {
        "__name__": "__main__",
        "__file__": script_path,
        "__revit__": uiapp,
        "__shiftclick__": bool(shift),
        "__forceddebugmode__": False,
        "__commandpath__": os.path.dirname(script_path),
        "__commandname__": CTX.bundle_name,
    }
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = sys.stderr = _OutputStream(CTX)
    try:
        runner.run(script_path, globs)
    except SystemExit:
        pass
    except BaseException as e:  # noqa: B902 - report every error, Revit's included
        if not _is_cancel(e):
            _report_error(traceback.format_exc())
    finally:
        sys.stdout, sys.stderr = old_out, old_err
        flush_output()
        CTX.output = None


def _report_error(text):
    from pyrevit import script
    out = script.get_output()
    out.print_error(text)


# ------------------------------------------------------------------ ribbon layout
_LITERAL = re.compile(r"""^(?:[ubrUBR]{0,2})(?:'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*")$""")
_DUNDER = re.compile(r"^(__[a-z]+__)\s*=\s*(.+?)\s*$")


def _stub_settings(path):
    """__title__ / __doc__ written by the shell builder (always one literal per line)."""
    out = {}
    try:
        with io.open(path, "r", encoding="utf-8-sig") as f:
            for line in f:
                m = _DUNDER.match(line.rstrip("\r\n"))
                if m and _LITERAL.match(m.group(2)):
                    try:
                        out[m.group(1)] = eval(m.group(2), {"__builtins__": {}}, {})
                    except Exception:
                        pass
    except (IOError, OSError):
        pass
    return out


def read_yaml(path):
    """The small part of YAML bundle files use: `key: value`, folded/literal blocks, and lists."""
    data = {}
    try:
        with io.open(path, "r", encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
    except (IOError, OSError):
        return data
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#") or line[0] in " \t-":
            continue
        if ":" not in line:
            continue
        key, _, rest = line.partition(":")
        key, rest = key.strip(), rest.strip()
        if rest in ("", ">", ">-", "|", "|-", ">+", "|+"):
            block = []
            while i < len(lines) and (not lines[i].strip() or lines[i][0] in " \t-"):
                block.append(lines[i])
                i += 1
            items = [b.strip()[1:].strip() for b in block if b.strip().startswith("- ") or b.strip() == "-"]
            if rest == "" and items:
                data[key] = [_unquote(x) for x in items]
            elif rest.startswith("|"):
                data[key] = "\n".join(b.strip() for b in block).strip()
            else:
                paras, cur = [], []
                for b in block:
                    if b.strip():
                        cur.append(b.strip())
                    elif cur:
                        paras.append(" ".join(cur))
                        cur = []
                if cur:
                    paras.append(" ".join(cur))
                data[key] = "\n\n".join(paras)
        else:
            data[key] = _unquote(rest)
    return data


def _unquote(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
        inner = s[1:-1]
        if s[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
        else:
            inner = inner.replace("''", "'")
        return inner
    return s


def _ordered(names, layout, suffix):
    """Folder names in the order of a bundle layout list, the rest alphabetically."""
    stems = dict((n[:-len(suffix)], n) for n in names)
    out = []
    for item in layout or []:
        key = str(item).strip()
        if key in stems and stems[key] not in out:
            out.append(stems[key])
    out += sorted((n for n in names if n not in out), key=lambda s: s.lower())
    return out


def _clean_title(s):
    return s.replace("\\n", "\n").strip()


def ribbon_layout(ext_root):
    panels = []
    if not os.path.isdir(ext_root):
        return panels
    for tab in sorted(os.listdir(ext_root)):
        tab_dir = os.path.join(ext_root, tab)
        if not (tab.endswith(".tab") and os.path.isdir(tab_dir)):
            continue
        tab_yaml = read_yaml(os.path.join(tab_dir, "bundle.yaml"))
        panel_dirs = [p for p in os.listdir(tab_dir)
                      if p.endswith(".panel") and p != "Account.panel" and os.path.isdir(os.path.join(tab_dir, p))]
        for pname in _ordered(panel_dirs, tab_yaml.get("layout"), ".panel"):
            pdir = os.path.join(tab_dir, pname)
            pyaml = read_yaml(os.path.join(pdir, "bundle.yaml"))
            bdirs = [b for b in os.listdir(pdir)
                     if b.endswith(".pushbutton") and os.path.isfile(os.path.join(pdir, b, "script.py"))]
            buttons = []
            for bname in _ordered(bdirs, pyaml.get("layout"), ".pushbutton"):
                bdir = os.path.join(pdir, bname)
                script_path = os.path.join(bdir, "script.py")
                byaml = read_yaml(os.path.join(bdir, "bundle.yaml"))
                stub = _stub_settings(script_path)
                stem = bname[:-len(".pushbutton")]
                title = byaml.get("title") or stub.get("__title__") or stem
                tooltip = byaml.get("tooltip") or stub.get("__doc__") or ""
                if os.path.isfile(os.path.join(bdir, "config.py")) and "shift" not in tooltip.lower():
                    tooltip = (tooltip + "\n\nShift+Click: settings.").strip()
                icon = os.path.join(bdir, "icon.png")
                buttons.append({
                    "key": pname[:-6] + "/" + stem,
                    "script": script_path,
                    "title": _clean_title(title),
                    "tooltip": tooltip.strip(),
                    "icon": icon if os.path.isfile(icon) else None,
                })
            if buttons:
                panels.append({"panel": pname[:-6], "title": pyaml.get("title") or pname[:-6], "buttons": buttons})
    return panels


def ribbon_json():
    return json.dumps(ribbon_layout(EXT_ROOT))
