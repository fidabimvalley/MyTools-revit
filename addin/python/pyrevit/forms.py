# -*- coding: utf-8 -*-
"""pyrevit.forms stand-in: the dialogs the MyTools buttons use, in plain Windows Forms.

alert, CommandSwitchWindow.show, SelectFromList.show, ask_for_string, toast, show_balloon,
WarningBar, ProgressBar.
"""
import sys

import mytools_host
import mytools_ui
from mytools_ui import ui_font

from System import Array, Object  # noqa: F401
from System.Drawing import Size, Point, Color, ContentAlignment
from System.Windows.Forms import (Label, TextBox, Button, CheckBox, ListBox, CheckedListBox, Panel,
                                  FlowLayoutPanel, TableLayoutPanel, FlowDirection, DockStyle, AnchorStyles,
                                  DialogResult, SelectionMode, Keys, Timer, FormBorderStyle,
                                  FormStartPosition, ColumnStyle, RowStyle, SizeType, AutoSizeMode,
                                  ProgressBar as _WinProgressBar, Padding, BorderStyle, Form)

_KEEP = []   # windows that close themselves later (toasts) must not be garbage collected


def _title(title):
    return title or mytools_host.tool_name()


def _text(x, name_attr=None):
    if name_attr:
        try:
            return u"%s" % getattr(x, name_attr)
        except Exception:
            pass
    return u"%s" % (x,)


# ------------------------------------------------------------------ alert
def _taskdialog_alert(msg, title, sub_msg, expanded, footer, ok, cancel, yes, no, retry, warn_icon, options):
    from Autodesk.Revit.UI import (TaskDialog, TaskDialogCommonButtons, TaskDialogResult,
                                   TaskDialogIcon, TaskDialogCommandLinkId)
    td = TaskDialog(_title(title))
    msg = u"%s" % msg
    if sub_msg is None and (len(msg) > 110 or msg.count("\n") > 1):
        td.MainInstruction = u""
        td.MainContent = msg
    else:
        td.MainInstruction = msg
        if sub_msg:
            td.MainContent = u"%s" % sub_msg
    if expanded:
        td.ExpandedContent = u"%s" % expanded
    if footer:
        td.FooterText = u"%s" % footer
    if warn_icon:
        td.MainIcon = TaskDialogIcon.TaskDialogIconWarning
    td.TitleAutoPrefix = False
    links = [TaskDialogCommandLinkId.CommandLink1, TaskDialogCommandLinkId.CommandLink2,
             TaskDialogCommandLinkId.CommandLink3, TaskDialogCommandLinkId.CommandLink4]
    results = [TaskDialogResult.CommandLink1, TaskDialogResult.CommandLink2,
               TaskDialogResult.CommandLink3, TaskDialogResult.CommandLink4]
    no_buttons = getattr(TaskDialogCommonButtons, "None")
    if options:
        for link, text in zip(links, options):
            td.AddCommandLink(link, u"%s" % text)
        td.CommonButtons = no_buttons
        td.AllowCancellation = True
        res = td.Show()
        for r, text in zip(results, options):
            if res == r:
                return text
        return None
    buttons = no_buttons
    for flag, name in ((ok, "Ok"), (cancel, "Cancel"), (yes, "Yes"), (no, "No"), (retry, "Retry")):
        if flag:
            buttons = buttons | getattr(TaskDialogCommonButtons, name)
    if buttons == no_buttons:
        buttons = TaskDialogCommonButtons.Ok
    td.CommonButtons = buttons
    td.AllowCancellation = bool(cancel or no or not (yes or retry))
    res = td.Show()
    return res in (TaskDialogResult.Ok, TaskDialogResult.Yes, TaskDialogResult.Retry)


def alert(msg, title=None, sub_msg=None, expanded=None, footer="", ok=True, cancel=False, yes=False,
          no=False, retry=False, warn_icon=True, options=None, exitscript=False):
    """Message box. With options, returns the chosen option (None if closed); otherwise True for
    OK / Yes / Retry. exitscript=True stops the button after the message."""
    if yes or no or retry:
        ok = False
    mytools_host.flush_output()
    if options and len(options) > 4:
        res = CommandSwitchWindow.show(options, message=u"%s%s" % (msg, ("\n\n" + sub_msg) if sub_msg else ""),
                                       title=title)
    else:
        try:
            res = _taskdialog_alert(msg, title, sub_msg, expanded, footer, ok, cancel, yes, no, retry,
                                    warn_icon, options)
        except ImportError:  # outside Revit (tests)
            print(u"[%s] %s" % (_title(title), msg))
            res = options[0] if options else True
    if exitscript:
        sys.exit(0)
    return res


def check_selection(exitscript=False, message="At least one element must be selected."):
    from pyrevit import revit
    if revit.get_selection().is_empty:
        alert(message, exitscript=exitscript)
        return False
    return True


# ------------------------------------------------------------------ text input
def ask_for_string(default=None, prompt=None, title=None, **kwargs):
    f = mytools_ui.new_form(_title(title), 420, 10, resizable=False)
    layout = TableLayoutPanel()
    layout.Dock = DockStyle.Fill
    layout.Padding = Padding(12)
    layout.ColumnCount = 1
    layout.AutoSize = True
    layout.AutoSizeMode = AutoSizeMode.GrowAndShrink
    lbl = Label()
    lbl.Text = prompt or u"Enter a value:"
    lbl.AutoSize = True
    lbl.MaximumSize = Size(396, 0)
    lbl.Margin = Padding(0, 0, 0, 6)
    box = TextBox()
    box.Text = u"" if default is None else u"%s" % default
    box.Width = 396
    box.Margin = Padding(0, 0, 0, 10)
    buttons = _button_row([("OK", DialogResult.OK), ("Cancel", DialogResult.Cancel)], f)
    for c in (lbl, box, buttons):
        layout.Controls.Add(c)
    f.Controls.Add(layout)
    f.AutoSize = True
    f.AutoSizeMode = AutoSizeMode.GrowAndShrink
    box.SelectAll()
    f.Shown += lambda s, e: box.Focus()
    if mytools_ui.show_dialog(f) == DialogResult.OK:
        return box.Text
    return None


def _button_row(specs, form):
    row = FlowLayoutPanel()
    row.FlowDirection = FlowDirection.RightToLeft
    row.AutoSize = True
    row.AutoSizeMode = AutoSizeMode.GrowAndShrink
    row.Dock = DockStyle.Fill
    row.Margin = Padding(0)
    first = True
    for text, result in specs:
        b = Button()
        b.Text = text
        b.AutoSize = True
        b.MinimumSize = Size(84, 28)
        b.DialogResult = result
        row.Controls.Add(b)
        if first:
            form.AcceptButton = b
            first = False
        if result == DialogResult.Cancel:
            form.CancelButton = b
    return row


# ------------------------------------------------------------------ pick one option
class CommandSwitchWindow(object):
    @staticmethod
    def show(context, title=None, width=None, height=None, message=None, switches=None,
             multiselect=False, config=None, recognize_access_key=False, **kwargs):
        """One button per option; returns the clicked option (None if closed).
        With switches, returns (option, {switch: bool})."""
        options = list(context or [])
        f = mytools_ui.new_form(_title(title), 420, 10, resizable=True)
        outer = TableLayoutPanel()
        outer.Dock = DockStyle.Fill
        outer.Padding = Padding(12)
        outer.ColumnCount = 1
        outer.ColumnStyles.Add(ColumnStyle(SizeType.Percent, 100.0))
        state = {"choice": None}
        if message:
            lbl = Label()
            lbl.Text = u"%s" % message
            lbl.AutoSize = True
            lbl.MaximumSize = Size(396, 0)
            lbl.Margin = Padding(0, 0, 0, 8)
            outer.Controls.Add(lbl)
        search = None
        if len(options) > 8:
            search = TextBox()
            search.Dock = DockStyle.Fill
            search.Margin = Padding(0, 0, 0, 8)
            try:
                search.PlaceholderText = u"Type to filter"
            except Exception:
                pass
            outer.Controls.Add(search)
        flow = FlowLayoutPanel()
        flow.FlowDirection = FlowDirection.TopDown
        flow.WrapContents = False
        flow.AutoScroll = len(options) > 12
        flow.Dock = DockStyle.Fill
        flow.Margin = Padding(0)
        buttons = []

        def make_click(opt):
            def click(sender, e):
                state["choice"] = opt
                f.DialogResult = DialogResult.OK
                f.Close()
            return click
        for opt in options:
            b = Button()
            b.Text = u"%s" % opt
            b.UseMnemonic = bool(recognize_access_key)
            b.Width = 376 if len(options) > 12 else 396
            b.Height = 32
            b.TextAlign = ContentAlignment.MiddleLeft
            b.Margin = Padding(0, 0, 0, 4)
            b.Click += make_click(opt)
            flow.Controls.Add(b)
            buttons.append((opt, b))
        outer.Controls.Add(flow)
        checks = []
        for sw in (switches or []):
            cb = CheckBox()
            cb.Text = u"%s" % sw
            cb.AutoSize = True
            if config and sw in config:
                cb.Checked = bool(config[sw].get("state", False)) if isinstance(config[sw], dict) else bool(config[sw])
            outer.Controls.Add(cb)
            checks.append((sw, cb))
        if search is not None:
            def on_filter(sender, e):
                q = search.Text.strip().lower()
                flow.SuspendLayout()
                for opt, b in buttons:
                    b.Visible = (not q) or (q in (u"%s" % opt).lower())
                flow.ResumeLayout(True)

            def on_enter(sender, e):
                if e.KeyCode == Keys.Enter:
                    for opt, b in buttons:
                        if b.Visible:
                            make_click(opt)(None, None)
                            break
                    e.SuppressKeyPress = True
            search.TextChanged += on_filter
            search.KeyDown += on_enter
            f.Shown += lambda s, e: search.Focus()
        f.Controls.Add(outer)
        rows = min(len(options), 12)
        extra = (60 if message else 0) + (34 if search is not None else 0) + 26 * len(checks)
        f.ClientSize = Size(width or 420, height or (24 + 36 * rows + extra))
        res = mytools_ui.show_dialog(f)
        if res != DialogResult.OK:
            return (None, {}) if switches else None
        if switches:
            return state["choice"], dict((sw, cb.Checked) for sw, cb in checks)
        return state["choice"]


# ------------------------------------------------------------------ pick from a list
class SelectFromList(object):
    @staticmethod
    def show(context, title=None, button_name="Select", width=500, height=600, multiselect=False,
             name_attr=None, info_panel=False, checked_only=False, return_all=False, **kwargs):
        """List with a filter box. Returns the chosen item (single) or a list of ticked items
        (multiselect), or None if closed."""
        if isinstance(context, dict):
            items = []
            for group in context.values():
                for x in group:
                    if x not in items:
                        items.append(x)
        else:
            items = list(context or [])
        labels = [_text(x, name_attr) for x in items]
        f = mytools_ui.new_form(_title(title), width or 500, height or 600, resizable=True)
        f.MinimumSize = Size(320, 300)
        grid = TableLayoutPanel()
        grid.Dock = DockStyle.Fill
        grid.Padding = Padding(12)
        grid.ColumnCount = 1
        grid.RowCount = 4
        grid.ColumnStyles.Add(ColumnStyle(SizeType.Percent, 100.0))
        grid.RowStyles.Add(RowStyle(SizeType.AutoSize))
        grid.RowStyles.Add(RowStyle(SizeType.Percent, 100.0))
        grid.RowStyles.Add(RowStyle(SizeType.AutoSize))
        grid.RowStyles.Add(RowStyle(SizeType.AutoSize))

        search = TextBox()
        search.Dock = DockStyle.Fill
        search.Margin = Padding(0, 0, 0, 8)
        try:
            search.PlaceholderText = u"Type to filter"
        except Exception:
            pass
        grid.Controls.Add(search, 0, 0)

        checked = set()
        visible = []          # indexes into items, in list order
        busy = {"v": False}
        if multiselect:
            lst = CheckedListBox()
            lst.CheckOnClick = True
        else:
            lst = ListBox()
            lst.SelectionMode = SelectionMode.One
        lst.Dock = DockStyle.Fill
        lst.IntegralHeight = False
        lst.Margin = Padding(0, 0, 0, 8)
        grid.Controls.Add(lst, 0, 1)

        def refill():
            q = search.Text.strip().lower()
            busy["v"] = True
            lst.BeginUpdate()
            lst.Items.Clear()
            del visible[:]
            for i, text in enumerate(labels):
                if not q or q in text.lower():
                    visible.append(i)
                    if multiselect:
                        lst.Items.Add(text, i in checked)
                    else:
                        lst.Items.Add(text)
            lst.EndUpdate()
            if not multiselect and lst.Items.Count:
                lst.SelectedIndex = 0
            busy["v"] = False
            update_count()

        count = Label()
        count.AutoSize = True
        count.ForeColor = Color.DimGray

        def update_count():
            if multiselect:
                count.Text = u"%d of %d ticked" % (len(checked), len(items))
            else:
                count.Text = u"%d item%s" % (len(visible), "" if len(visible) == 1 else "s")

        if multiselect:
            def on_check(sender, e):
                if busy["v"]:
                    return
                idx = visible[e.Index]
                if str(e.NewValue) == "Checked":
                    checked.add(idx)
                else:
                    checked.discard(idx)
                update_count()
            lst.ItemCheck += on_check

            def set_all(state):
                for i in visible:
                    if state:
                        checked.add(i)
                    else:
                        checked.discard(i)
                refill()
            tools = FlowLayoutPanel()
            tools.AutoSize = True
            tools.Dock = DockStyle.Fill
            tools.Margin = Padding(0, 0, 0, 6)
            for text, state in ((u"Tick all", True), (u"Untick all", False)):
                b = Button()
                b.Text = text
                b.AutoSize = True
                b.Click += (lambda st: (lambda s, e: set_all(st)))(state)
                tools.Controls.Add(b)
            count.Margin = Padding(8, 7, 0, 0)
            tools.Controls.Add(count)
            grid.Controls.Add(tools, 0, 2)
        else:
            grid.Controls.Add(count, 0, 2)

            def on_double(sender, e):
                if lst.SelectedIndex >= 0:
                    f.DialogResult = DialogResult.OK
                    f.Close()
            lst.DoubleClick += on_double

        buttons = _button_row([(button_name or "Select", DialogResult.OK), ("Cancel", DialogResult.Cancel)], f)
        grid.Controls.Add(buttons, 0, 3)

        def on_search_key(sender, e):
            if e.KeyCode in (Keys.Down, Keys.Up) and lst.Items.Count:
                lst.Focus()
                e.Handled = True
        search.TextChanged += lambda s, e: refill()
        search.KeyDown += on_search_key
        f.Controls.Add(grid)
        f.Shown += lambda s, e: search.Focus()
        refill()

        if mytools_ui.show_dialog(f) != DialogResult.OK:
            return None
        if multiselect:
            return [items[i] for i in sorted(checked)]
        if lst.SelectedIndex < 0:
            return None
        return items[visible[lst.SelectedIndex]]


def _action(fn):
    from System import Action
    return Action(fn)


# ------------------------------------------------------------------ small notices
def _popup(title, message, seconds=4.0):
    """A small notice at the bottom right of Revit's window that closes by itself."""
    try:
        f = Form()
        f.FormBorderStyle = FormBorderStyle.FixedToolWindow
        f.Text = _title(title)
        f.ShowInTaskbar = False
        f.TopMost = True
        f.StartPosition = FormStartPosition.Manual
        f.Font = ui_font()
        lbl = Label()
        lbl.Text = u"%s" % message
        lbl.AutoSize = True
        lbl.MaximumSize = Size(320, 0)
        lbl.Padding = Padding(12)
        f.Controls.Add(lbl)
        f.AutoSize = True
        f.AutoSizeMode = AutoSizeMode.GrowAndShrink
        f.MinimumSize = Size(260, 0)
        f.PerformLayout()
        area = mytools_ui.work_area()
        pref = f.GetPreferredSize(Size(0, 0))
        f.Location = Point(area.Right - max(pref.Width, 260) - 16, area.Bottom - pref.Height - 16)
        timer = Timer()
        timer.Interval = int(seconds * 1000)

        def done(sender, e):
            timer.Stop()
            try:
                f.Close()
            finally:
                if (f, timer) in _KEEP:
                    _KEEP.remove((f, timer))
        timer.Tick += done
        _KEEP.append((f, timer))
        mytools_ui.show_modeless(f)
        timer.Start()
    except Exception:
        print(u"[%s] %s" % (_title(title), message))


def toast(message, title=None, appid=None, icon=None, click=None, actions=None):
    _popup(title, message)


def show_balloon(header, text, tooltip="", group="", is_favourite=False, is_new=False,
                 timestamp=None, click_result=None):
    _popup(header, text)


# ------------------------------------------------------------------ busy indicators
class WarningBar(object):
    """with WarningBar(title="Reading parameters..."): ... shows a bar over Revit while it works."""

    def __init__(self, height=32, title=u"", **kwargs):
        self.title = title
        self.form = None

    def __enter__(self):
        try:
            area = mytools_ui.work_area()
            f = Form()
            f.FormBorderStyle = getattr(FormBorderStyle, "None")
            f.ShowInTaskbar = False
            f.TopMost = True
            f.StartPosition = FormStartPosition.Manual
            f.BackColor = Color.FromArgb(255, 200, 70)
            f.Size = Size(area.Width, 34)
            f.Location = Point(area.Left, area.Top)
            lbl = Label()
            lbl.Text = u"%s" % self.title
            lbl.Dock = DockStyle.Fill
            lbl.TextAlign = ContentAlignment.MiddleCenter
            lbl.Font = ui_font(10.0, True)
            f.Controls.Add(lbl)
            mytools_ui.show_modeless(f)
            f.Refresh()
            self.form = f
        except Exception:
            self.form = None
        return self

    def __exit__(self, *exc):
        if self.form is not None:
            try:
                self.form.Close()
                self.form.Dispose()
            except Exception:
                pass
        return False


class ProgressBar(object):
    """with ProgressBar(title="Working ({value} of {max_value})") as pb: pb.update_progress(i, n)"""

    def __init__(self, height=32, cancellable=False, step=0, title=None, indeterminate=False, **kwargs):
        self.title = title or u"{value} of {max_value}"
        self.cancelled = False
        self.indeterminate = indeterminate
        self.form = None
        self._last = 0

    def __enter__(self):
        try:
            f = mytools_ui.new_form(mytools_host.tool_name(), 420, 74, resizable=False)
            f.ControlBox = False
            f.StartPosition = FormStartPosition.CenterScreen
            self.label = Label()
            self.label.AutoSize = False
            self.label.SetBounds(12, 10, 396, 22)
            self.bar = _WinProgressBar()
            self.bar.SetBounds(12, 38, 396, 22)
            self.bar.Minimum = 0
            self.bar.Maximum = 100
            f.Controls.Add(self.label)
            f.Controls.Add(self.bar)
            mytools_ui.show_modeless(f)
            self.form = f
            self._paint(0, 1, force=True)
        except Exception:
            self.form = None
        return self

    def update_progress(self, new_value, max_value=1):
        self._paint(new_value, max_value)

    def _paint(self, value, max_value, force=False):
        if self.form is None:
            return
        import time
        now = time.time()
        if not force and now - self._last < 0.08 and value < max_value:
            return
        self._last = now
        try:
            pct = int(100.0 * value / max_value) if max_value else 0
            self.bar.Value = max(0, min(100, pct))
            try:
                self.label.Text = self.title.format(value=value, max_value=max_value)
            except Exception:
                self.label.Text = u"%s" % self.title
            self.form.Refresh()
        except Exception:
            pass

    def __exit__(self, *exc):
        if self.form is not None:
            try:
                self.form.Close()
                self.form.Dispose()
            except Exception:
                pass
        return False
