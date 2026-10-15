# -*- coding: utf-8 -*-
"""Shared helpers for the MyTools windows (Windows Forms, built in code)."""
import clr

for _name in ("System.Windows.Forms", "System.Drawing", "System.Drawing.Common", "System.Drawing.Primitives"):
    try:
        clr.AddReference(_name)
    except Exception:
        pass

from System.Drawing import Font, FontStyle, Size, SizeF, Point, Color  # noqa: E402
from System.Windows.Forms import (Form, FormBorderStyle, FormStartPosition, AutoScaleMode,  # noqa: E402
                                  NativeWindow, Keys, DialogResult, Screen)

import mytools_host  # noqa: E402

FONT_NAME = "Segoe UI"


def ui_font(size=9.0, bold=False):
    return Font(FONT_NAME, size, FontStyle.Bold if bold else FontStyle.Regular)


def revit_handle():
    uiapp = mytools_host.CTX.uiapp
    try:
        return uiapp.MainWindowHandle if uiapp is not None else None
    except Exception:
        return None


class _Owner(object):
    """Revit's main window as a Windows Forms owner (keeps our windows in front of Revit)."""

    def __enter__(self):
        self.win = None
        h = revit_handle()
        if h is not None:
            try:
                self.win = NativeWindow()
                self.win.AssignHandle(h)
            except Exception:
                self.win = None
        return self.win

    def __exit__(self, *exc):
        if self.win is not None:
            try:
                self.win.ReleaseHandle()
            except Exception:
                pass
        return False


def owner():
    return _Owner()


def new_form(title, width=420, height=300, resizable=True):
    """A dialog laid out at 96 dpi; Windows Forms scales it to the screen's dpi when shown."""
    f = Form()
    f.SuspendLayout()
    f.AutoScaleDimensions = SizeF(96.0, 96.0)
    f.AutoScaleMode = AutoScaleMode.Dpi
    f.Text = title or mytools_host.tool_name()
    f.Font = ui_font()
    f.ClientSize = Size(int(width), int(height))
    f.MinimizeBox = False
    f.MaximizeBox = False
    f.ShowInTaskbar = False
    f.ShowIcon = False
    f.KeyPreview = True
    f.FormBorderStyle = FormBorderStyle.Sizable if resizable else FormBorderStyle.FixedDialog
    f.StartPosition = FormStartPosition.CenterParent

    def on_key(sender, e):
        if e.KeyCode == Keys.Escape:
            sender.DialogResult = DialogResult.Cancel
            sender.Close()
    f.KeyDown += on_key
    return f


def show_dialog(form):
    """Show a modal dialog over Revit. The output window is brought up to date first."""
    mytools_host.flush_output()
    form.ResumeLayout(True)
    with owner() as win:
        if win is None:
            form.StartPosition = FormStartPosition.CenterScreen
            return form.ShowDialog()
        return form.ShowDialog(win)


def show_modeless(form):
    form.ResumeLayout(True)
    with owner() as win:
        if win is None:
            form.Show()
        else:
            form.Show(win)


def work_area():
    """Screen area of the monitor Revit is on."""
    h = revit_handle()
    try:
        if h is not None:
            return Screen.FromHandle(h).WorkingArea
    except Exception:
        pass
    return Screen.PrimaryScreen.WorkingArea
