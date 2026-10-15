# -*- coding: utf-8 -*-
"""rpw.ui.forms stand-in: FlexForm with Label, TextBox, CheckBox, ComboBox, Separator and Button.

    form = FlexForm("Title", [Label("Size"), TextBox("size", Text="10"), Button("Run")])
    if form.show():
        form.values["size"]
"""
import mytools_ui
from System.Drawing import Size, Color
from System.Windows.Forms import (Label as _Label, TextBox as _TextBox, CheckBox as _CheckBox,
                                  ComboBox as _ComboBox, ComboBoxStyle, Button as _Button, Panel,
                                  FlowLayoutPanel, FlowDirection, DockStyle, DialogResult, Padding,
                                  BorderStyle, AutoSizeMode)

WIDTH = 360


class _Component(object):
    name = None

    def control(self):
        raise NotImplementedError

    def value(self):
        return None


class Label(_Component):
    def __init__(self, label_text, **kwargs):
        self.text = label_text

    def control(self):
        c = _Label()
        c.Text = u"%s" % self.text
        c.AutoSize = True
        c.MaximumSize = Size(WIDTH, 0)
        c.Margin = Padding(0, 6, 0, 2)
        return c


class TextBox(_Component):
    def __init__(self, name, default="", **kwargs):
        self.name = name
        self.default = kwargs.get("Text", default)
        self.ctrl = None

    def control(self):
        c = _TextBox()
        c.Text = u"" if self.default is None else u"%s" % self.default
        c.Width = WIDTH
        c.Margin = Padding(0, 0, 0, 4)
        self.ctrl = c
        return c

    def value(self):
        return self.ctrl.Text


class CheckBox(_Component):
    def __init__(self, name, checkbox_text, default=False, **kwargs):
        self.name = name
        self.text = checkbox_text
        self.default = default
        self.ctrl = None

    def control(self):
        c = _CheckBox()
        c.Text = u"%s" % self.text
        c.Checked = bool(self.default)
        c.AutoSize = True
        c.MaximumSize = Size(WIDTH, 0)
        c.Margin = Padding(0, 4, 0, 2)
        self.ctrl = c
        return c

    def value(self):
        return bool(self.ctrl.Checked)


class ComboBox(_Component):
    def __init__(self, name, options, default=None, sort=False, **kwargs):
        self.name = name
        if isinstance(options, dict):
            keys = list(options.keys())
            self.pairs = [(u"%s" % k, options[k]) for k in (sorted(keys) if sort else keys)]
        else:
            opts = list(options)
            self.pairs = [(u"%s" % o, o) for o in (sorted(opts) if sort else opts)]
        self.default = default
        self.ctrl = None

    def control(self):
        c = _ComboBox()
        c.DropDownStyle = ComboBoxStyle.DropDownList
        c.Width = WIDTH
        c.Margin = Padding(0, 0, 0, 4)
        for text, _ in self.pairs:
            c.Items.Add(text)
        idx = 0
        for i, (text, _) in enumerate(self.pairs):
            if self.default is not None and text == u"%s" % self.default:
                idx = i
        if self.pairs:
            c.SelectedIndex = idx
        self.ctrl = c
        return c

    def value(self):
        i = self.ctrl.SelectedIndex
        return self.pairs[i][1] if 0 <= i < len(self.pairs) else None


class Separator(_Component):
    def __init__(self, **kwargs):
        pass

    def control(self):
        c = Panel()
        c.Height = 1
        c.Width = WIDTH
        c.BackColor = Color.Silver
        c.Margin = Padding(0, 8, 0, 6)
        return c


class Button(_Component):
    def __init__(self, button_text, on_click=None, **kwargs):
        self.text = button_text
        self.on_click = on_click
        self.form = None

    def control(self):
        c = _Button()
        c.Text = u"%s" % self.text
        c.AutoSize = True
        c.MinimumSize = Size(96, 30)
        c.Margin = Padding(0, 8, 0, 0)
        c.Click += self._click
        return c

    def _click(self, sender, e):
        if self.on_click is not None:
            self.on_click(sender, e)
            return
        self.form.submit()


class FlexForm(object):
    def __init__(self, title, components, **kwargs):
        self.title = title
        self.components = list(components)
        self.values = {}
        self._form = None

    def submit(self):
        self.values = dict((c.name, c.value()) for c in self.components if c.name)
        self._form.DialogResult = DialogResult.OK
        self._form.Close()

    # rpw calls this from a button's on_click
    def get_values(self, sender=None, e=None):
        self.submit()

    def close(self):
        if self._form is not None:
            self._form.Close()

    def show(self):
        f = mytools_ui.new_form(self.title, WIDTH + 24, 10, resizable=False)
        self._form = f
        flow = FlowLayoutPanel()
        flow.FlowDirection = FlowDirection.TopDown
        flow.WrapContents = False
        flow.AutoSize = True
        flow.Padding = Padding(12)
        flow.Dock = DockStyle.Fill
        for comp in self.components:
            if isinstance(comp, Button):
                comp.form = self
            flow.Controls.Add(comp.control())
        f.Controls.Add(flow)
        f.AutoSize = True
        f.AutoSizeMode = AutoSizeMode.GrowAndShrink
        return mytools_ui.show_dialog(f) == DialogResult.OK
