# -*- coding: utf-8 -*-
"""Checks the packaged add-in's Python side in IronPython 3.4 on Windows, without Revit.

    SmokeTest.exe --path <app>/python smoke.py <app> [<vault.json>] [<folder of button sources>]
"""
import io
import json
import os
import shutil
import sys
import tempfile
import traceback

APP = os.path.abspath(sys.argv[1])
VAULT = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] != "-" else None
SOURCES = sys.argv[3] if len(sys.argv) > 3 else None
FAILED = []


def check(name):
    def wrap(fn):
        try:
            fn()
            print("  ok    " + name)
        except Exception:
            FAILED.append(name)
            print("  FAIL  " + name)
            tb = traceback.format_exc()
            print(tb)
            if os.environ.get("GITHUB_ACTIONS"):
                print("::error title=%s::%s" % (name.replace(":", " -"), tb[-3000:].replace("%", "%25").replace("\r", "").replace("\n", "%0A")))
        return fn
    return wrap


print("Python %s" % sys.version.split()[0])
WORK = tempfile.mkdtemp(prefix="mytools-smoke-")
os.environ["APPDATA"] = WORK
EXT = os.path.join(WORK, "MyTools", "MyTools.extension")


class FakeHost(object):
    ToolName = "MyTools"
    refreshed = 0
    posted = []

    def RefreshRibbon(self):
        FakeHost.refreshed += 1

    def Post(self, action):
        FakeHost.posted.append(action)


@check("app layout: engine, stdlib, python, icons")
def _():
    for rel in ("MyTools.Revit.dll", "engine/MyTools.Engine.dll", "engine/IronPython.dll",
                "engine/System.Security.Cryptography.ProtectedData.dll",
                "python/mytools_host.py", "python/pyrevit/forms.py", "python/rpw/ui/forms.py",
                "python/mytools_vault/core.py", "icons/signin.png", "icons/account.png"):
        assert os.path.exists(os.path.join(APP, rel)), "missing " + rel
    eng = os.path.join(APP, "engine")
    assert any(os.path.isfile(os.path.join(eng, d, "json", "__init__.py")) for d in ("lib", "Lib")), \
        "Python standard library not found in engine/lib"


import mytools_host  # noqa: E402
mytools_host.HOST = FakeHost()
mytools_host.init(APP, EXT)


@check("imports: pyrevit, rpw and the vault in IronPython")
def _():
    import mytools_ui  # noqa: F401
    import pyrevit
    from pyrevit import forms, script, revit, EXEC_PARAMS  # noqa: F401
    from rpw.ui.forms import FlexForm, Label, TextBox, CheckBox, Separator, Button, ComboBox  # noqa: F401
    from mytools_vault import compat, core, runner, shell, ui  # noqa: F401
    assert compat.HAS_CLR, "clr not available"
    assert EXEC_PARAMS.config_mode is False
    assert pyrevit.DB is None  # no Revit here


@check("Windows encryption (DPAPI) round trip")
def _():
    from mytools_vault import compat
    blob = compat.protect(u"secret ✓ token")
    assert compat.unprotect(blob) == u"secret ✓ token"


@check("settings: get_config / save_config")
def _():
    from pyrevit import script
    mytools_host.CTX.reset(None, os.path.join(EXT, "MyTools.tab", "A.panel", "Trim.pushbutton", "script.py"))
    cfg = script.get_config()
    try:
        cfg.gap_mm
        raise AssertionError("missing setting should raise AttributeError")
    except AttributeError:
        pass
    cfg.gap_mm = 12.5
    other = script.get_config("SectionBox")
    other.set_option("offset_mm", "500")
    script.save_config()
    script._STORE["data"] = None
    assert float(script.get_config().gap_mm) == 12.5
    assert script.get_config("SectionBox").get_option("offset_mm", "x") == "500"
    assert script.get_config("SectionBox").get_option("nope", "d") == "d"


import mytools_ui  # noqa: E402
from System.Windows.Forms import DialogResult  # noqa: E402

SEEN = []


def press(button):
    """Click a button of a window that isn't on screen (PerformClick needs a visible window)."""
    from System import EventArgs, Array, Object
    from System.Reflection import BindingFlags
    m = button.GetType().GetMethod("OnClick", BindingFlags.Instance | BindingFlags.NonPublic)
    m.Invoke(button, Array[Object]([EventArgs.Empty]))


def fake_dialog(result_fn):
    def show(form):
        form.ResumeLayout(True)
        form.CreateControl()
        form.PerformLayout()
        SEEN.append(form)
        res = result_fn(form)
        form.Dispose()
        return res
    return show


@check("dialogs: SelectFromList (single and multi), filter and tick all")
def _():
    from pyrevit import forms
    from System.Windows.Forms import TextBox, CheckedListBox, Button, ListBox

    def walk(c):
        yield c
        for ch in c.Controls:
            for x in walk(ch):
                yield x

    def pick_first(form):
        return DialogResult.OK
    mytools_ui.show_dialog = fake_dialog(pick_first)
    assert forms.SelectFromList.show(["b", "a", "c"], title="T", button_name="Next", width=420, height=520) == "b"

    def tick_all_after_filter(form):
        ctrls = list(walk(form))
        box = [c for c in ctrls if isinstance(c, TextBox)][0]
        box.Text = "apple"        # filter: the two apples stay
        press([c for c in ctrls if isinstance(c, Button) and c.Text == "Tick all"][0])
        box.Text = ""
        lst = [c for c in ctrls if isinstance(c, CheckedListBox)][0]
        assert lst.Items.Count == 3
        return DialogResult.OK
    mytools_ui.show_dialog = fake_dialog(tick_all_after_filter)
    got = forms.SelectFromList.show(["red apple", "banana", "green apple"], multiselect=True, button_name="OK")
    assert got == ["red apple", "green apple"], got

    mytools_ui.show_dialog = fake_dialog(lambda f: DialogResult.Cancel)
    assert forms.SelectFromList.show(["x"], multiselect=True) is None
    assert ListBox is not None


@check("dialogs: CommandSwitchWindow, ask_for_string, FlexForm")
def _():
    from pyrevit import forms
    from System.Windows.Forms import Button

    def walk(c):
        yield c
        for ch in c.Controls:
            for x in walk(ch):
                yield x

    def click(text):
        def go(form):
            b = [c for c in walk(form) if isinstance(c, Button) and c.Text == text][0]
            press(b)
            return form.DialogResult
        return go
    mytools_ui.show_dialog = fake_dialog(click("Slanted"))
    assert forms.CommandSwitchWindow.show(["Vertical", "Slanted"], message="Which?") == "Slanted"
    many = ["Option %d" % i for i in range(20)]
    mytools_ui.show_dialog = fake_dialog(click("Option 7"))
    assert forms.CommandSwitchWindow.show(many, message="Pick") == "Option 7"
    mytools_ui.show_dialog = fake_dialog(lambda f: DialogResult.OK)
    assert forms.ask_for_string(default="500", prompt="Offset (mm):", title="T") == "500"
    mytools_ui.show_dialog = fake_dialog(lambda f: DialogResult.Cancel)
    assert forms.ask_for_string(default="x") is None

    from rpw.ui.forms import FlexForm, Label, TextBox, CheckBox, Separator, Button as RButton, ComboBox
    form = FlexForm("Settings", [Label("Wall type"), ComboBox("wall_type", ["Vertical", "Slanted"]),
                                 Separator(), Label("Width"), TextBox("w", Text="3000"),
                                 CheckBox("eq", "Equalize", default=True), RButton("Run")])
    mytools_ui.show_dialog = fake_dialog(click("Run"))
    assert form.show() is True
    assert form.values == {"wall_type": "Vertical", "w": "3000", "eq": True}, form.values


@check("output window: markdown, tables, element links, print()")
def _():
    from pyrevit import script
    mytools_host.CTX.reset(None, os.path.join(EXT, "x.pushbutton", "script.py"))
    out = script.get_output()
    out.print_md("## Report\n- one\n    - nested <None>\n**bold** QIC_4D_X")
    out.print_table([[1, "a<b"]], columns=["n", "v"])
    old = sys.stdout
    sys.stdout = mytools_host._OutputStream(mytools_host.CTX)
    try:
        print("plain", "text")
    finally:
        sys.stdout = old
    html = out.html()
    assert "<h2>Report</h2>" in html and "&lt;None&gt;" in html and "a&lt;b" in html
    assert "<div class='txt'>plain text</div>" in html, html
    out.flush()   # creates the window with its web view
    assert out.form is not None and out.browser is not None
    out.browser.DocumentText = out.html()
    out.close()


@check("notices: toast, WarningBar, ProgressBar")
def _():
    from pyrevit import forms
    forms.toast("Done.", title="T")
    with forms.WarningBar(title="Working..."):
        pass
    with forms.ProgressBar(title="Checking ({value} of {max_value})") as pb:
        for i in range(5):
            pb.update_progress(i + 1, 5)
    for f, t in list(forms._KEEP):
        t.Stop()
        f.Close()


@check("ribbon layout from a downloaded toolbar")
def _():
    btn = os.path.join(EXT, "MyTools.tab", "Walls.panel", "TrimToWall.pushbutton")
    os.makedirs(btn)
    with io.open(os.path.join(btn, "script.py"), "w", encoding="utf-8") as f:
        f.write(u"# -*- coding: utf-8 -*-\n__title__ = 'Trim to\\nWall'\n__doc__ = 'Trim walls ✓'\n"
                u"from mytools_vault import runner\nrunner.run(__file__, globals())\n")
    with io.open(os.path.join(btn, "config.py"), "w", encoding="utf-8") as f:
        f.write(u"pass\n")
    with io.open(os.path.join(os.path.dirname(btn), "bundle.yaml"), "w", encoding="utf-8") as f:
        f.write(u"layout:\n  - TrimToWall\n")
    data = json.loads(mytools_host.ribbon_json())
    assert data[0]["panel"] == "Walls", data
    b = data[0]["buttons"][0]
    assert b["title"] == "Trim to\nWall" and b["tooltip"].startswith(u"Trim walls ✓"), b
    assert "Shift+Click" in b["tooltip"]


@check("account flow uses the add-in to refresh the toolbar")
def _():
    from mytools_vault import ui
    shown = []
    ui.BACKEND = lambda msg, title, options, sub: shown.append(msg)
    try:
        before = FakeHost.refreshed
        ui.reload_pyrevit({"toolName": "MyTools"}, ask_first=True, reason="Ready.")
        assert FakeHost.refreshed == before + 1 and "updated" in shown[-1]
    finally:
        ui.BACKEND = None


@check("server reachable from .NET (Supabase auth settings)")
def _():
    if not VAULT:
        print("        (skipped: no vault.json given)")
        return
    from mytools_vault import compat
    cfg = json.load(io.open(VAULT, encoding="utf-8"))
    status, data = compat.http_json("GET", cfg["supabaseUrl"].rstrip("/") + "/auth/v1/settings",
                                    {"apikey": cfg["supabaseKey"]})
    assert status == 200, (status, data)
    assert data.get("external", {}).get("email") is True, "email sign-in is not enabled"


@check("button sources compile in IronPython 3.4")
def _():
    if not SOURCES:
        print("        (skipped: no source folder given)")
        return
    from mytools_vault.runner import _clean_source
    n = 0
    bad = []
    for root, dirs, files in os.walk(SOURCES):
        dirs[:] = [d for d in dirs if d.lower() not in ("bak", "backup", "old", "__pycache__", ".git")]
        for name in files:
            if name.endswith(".py"):
                path = os.path.join(root, name)
                with io.open(path, "r", encoding="utf-8-sig") as f:
                    src = f.read()
                try:
                    compile(_clean_source(src), path, "exec")
                    n += 1
                except SyntaxError as e:
                    bad.append("%s:%s %s" % (path, e.lineno, e.msg))
    print("        %d files compiled" % n)
    assert not bad, "\n".join(bad)


shutil.rmtree(WORK, ignore_errors=True)
print("")
if FAILED:
    print("%d check(s) failed: %s" % (len(FAILED), ", ".join(FAILED)))
    sys.exit(1)
print("All checks passed.")
if os.environ.get("GITHUB_ACTIONS"):
    print("::notice title=Smoke test::All checks passed (Python %s)" % sys.version.split()[0])
