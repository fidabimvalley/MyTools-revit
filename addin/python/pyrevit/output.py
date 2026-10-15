# -*- coding: utf-8 -*-
"""The report window buttons print to (replaces pyRevit's output window).

print(), print_md(), print_table() and linkify() collect HTML; the window shows it whenever a dialog
opens and when the button finishes. Clicking an element link selects and shows it in Revit.
"""
import re

import mytools_host

SELECT_HOST = "select.mytools.invalid"
_ANCHOR = re.compile(r'<a class="elid" href="https://select\.mytools\.invalid/\?ids=[0-9,\-]*">.*?</a>', re.S)
_ENTITY = re.compile(r"&(#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);")

CSS = u"""
body{font-family:'Segoe UI',Arial,sans-serif;font-size:13px;color:#222;margin:14px 18px;background:#fff}
h1,h2,h3,h4{font-weight:600;margin:16px 0 6px} h1{font-size:20px} h2{font-size:17px} h3{font-size:15px} h4{font-size:13px}
p{margin:4px 0} ul,ol{margin:4px 0 4px 22px;padding:0} li{margin:1px 0}
.txt{white-space:pre-wrap;margin:1px 0;font-family:'Segoe UI',Arial,sans-serif}
table{border-collapse:collapse;margin:8px 0} th,td{border:1px solid #ccc;padding:3px 8px;text-align:left;vertical-align:top}
th{background:#f1f3f5} caption{text-align:left;font-weight:600;padding:4px 0}
a.elid{color:#0b65c2;text-decoration:none;border-bottom:1px dotted #0b65c2;cursor:pointer}
code{background:#f3f3f3;padding:0 3px;font-family:Consolas,monospace}
pre{background:#f6f6f6;padding:8px;overflow:auto;font-family:Consolas,monospace;font-size:12px}
pre.err{background:#fff1f0;color:#a40000;border-left:3px solid #d00}
hr{border:0;border-top:1px solid #ddd;margin:10px 0}
"""


# ------------------------------------------------------------------ HTML helpers
def escape(text):
    return (u"%s" % text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _keep_links(text, convert):
    """Escape text but keep element links (and HTML entities such as &nbsp;) working."""
    keep = []

    def stash(m):
        keep.append(m.group(0))
        return u"\x00%d\x00" % (len(keep) - 1)
    text = _ANCHOR.sub(stash, u"%s" % text)
    text = _ENTITY.sub(stash, text)
    text = convert(text)
    return re.sub(u"\x00(\\d+)\x00", lambda m: keep[int(m.group(1))], text)


def _inline_md(text):
    t = escape(text)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', t)
    return t


_LIST = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")


def markdown(md):
    """Small Markdown converter: headings, lists (nested by indent), rules, paragraphs, inline styles."""
    lines = (u"%s" % md).replace("\r\n", "\n").split("\n")
    html, para, stack = [], [], []   # stack of (indent, tag)

    def close_lists(indent=-1):
        while stack and stack[-1][0] > indent:
            html.append(u"</li></%s>" % stack.pop()[1])

    def end_para():
        if para:
            html.append(u"<p>%s</p>" % u"<br>".join(para))
            del para[:]

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            end_para()
            close_lists()
            continue
        m = _LIST.match(line)
        h = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
        if m:
            end_para()
            indent = len(m.group(1).replace("\t", "    "))
            tag = "ol" if m.group(2)[0].isdigit() else "ul"
            if stack and indent < stack[-1][0]:
                close_lists(indent)
            if stack and stack[-1][0] == indent:
                html.append(u"</li><li>%s" % _keep_links(m.group(3), _inline_md))
            else:
                html.append(u"<%s><li>%s" % (tag, _keep_links(m.group(3), _inline_md)))
                stack.append((indent, tag))
        elif h:
            end_para()
            close_lists()
            n = len(h.group(1))
            html.append(u"<h%d>%s</h%d>" % (n, _keep_links(h.group(2), _inline_md), n))
        elif re.match(r"^\s*([-*_])(\s*\1){2,}\s*$", line):
            end_para()
            close_lists()
            html.append(u"<hr>")
        else:
            if stack:
                close_lists()
            para.append(_keep_links(line.strip() if not line.startswith("&") else line, _inline_md))
    end_para()
    close_lists()
    return u"".join(html)


def _cell(value):
    return _keep_links(u"%s" % value, escape)


def _id_value(x):
    eid = getattr(x, "Id", x)
    for attr in ("Value", "IntegerValue"):
        v = getattr(eid, attr, None)
        if v is not None:
            return int(v)
    return int(eid)


# ------------------------------------------------------------------ the window
class OutputWindow(object):
    def __init__(self, title=None):
        self.title = title or mytools_host.tool_name()
        self.parts = []
        self._version = 0
        self._shown = -1
        self.last_error = None
        self.form = None
        self.browser = None
        self.uiapp = mytools_host.CTX.uiapp

    # --- pyRevit-style API used by buttons
    def print_md(self, md):
        self._add(markdown(md))

    def print_html(self, html):
        self._add(u"%s" % html)

    def print_code(self, code):
        self._add(u"<pre>%s</pre>" % escape(code))

    def print_error(self, text):
        self._add(u"<pre class='err'>%s</pre>" % escape(text))

    def print_table(self, table_data, columns=None, formats=None, title="", last_line_style=""):
        rows = [list(r) for r in (table_data or [])]
        out = [u"<table>"]
        if title:
            out.append(u"<caption>%s</caption>" % _cell(title))
        if columns:
            out.append(u"<tr>%s</tr>" % u"".join(u"<th>%s</th>" % _cell(c) for c in columns))
        for i, row in enumerate(rows):
            cells = []
            for j, v in enumerate(row):
                if formats and j < len(formats) and formats[j]:
                    try:
                        v = formats[j].format(v)
                    except Exception:
                        pass
                cells.append(u"<td>%s</td>" % _cell(v))
            style = u" style='%s'" % escape(last_line_style) if (last_line_style and i == len(rows) - 1) else u""
            out.append(u"<tr%s>%s</tr>" % (style, u"".join(cells)))
        out.append(u"</table>")
        self._add(u"".join(out))

    def linkify(self, element_ids, title=None):
        ids = element_ids if isinstance(element_ids, (list, tuple, set)) else [element_ids]
        try:
            ids = list(ids)
        except TypeError:
            ids = [ids]
        nums = [str(_id_value(i)) for i in ids]
        text = title if title is not None else (nums[0] if len(nums) == 1 else u"%d elements" % len(nums))
        return u'<a class="elid" href="https://%s/?ids=%s">%s</a>' % (SELECT_HOST, u",".join(nums), escape(text))

    def insert_divider(self, level=""):
        self._add(u"<hr>")

    def set_title(self, title):
        self.title = title
        if self.form is not None:
            self.form.Text = title

    def write_text(self, text):
        text = u"%s" % text
        if self.parts and self.parts[-1].startswith(u"<div class='txt'>") and not self._closed_line:
            # continue the current line (print writes text and the newline separately)
            body = self.parts[-1][len(u"<div class='txt'>"):-len(u"</div>")]
            self.parts[-1] = u"<div class='txt'>%s%s</div>" % (body, self._txt(text))
        else:
            self.parts.append(u"<div class='txt'>%s</div>" % self._txt(text))
        self._version += 1
        self._closed_line = text.endswith("\n")
        if self._closed_line:
            self.parts[-1] = self.parts[-1].replace(u"\n</div>", u"</div>")

    _closed_line = True

    def _txt(self, text):
        return _keep_links(text, escape)

    def show(self):
        self.flush()

    def close(self):
        if self.form is not None:
            try:
                self.form.Close()
            except Exception:
                pass

    def freeze(self):
        pass

    def unfreeze(self):
        pass

    def resize(self, width, height):
        pass

    def center(self):
        pass

    def log_info(self, msg):
        self.print_md(msg)

    log_success = log_warning = log_debug = log_info

    def log_error(self, msg):
        self.print_error(msg)

    def __getattr__(self, name):
        # Anything else pyRevit's window could do is quietly ignored, so buttons don't break.
        if name.startswith("_"):
            raise AttributeError(name)
        return lambda *a, **k: None

    # --- internals
    def _add(self, html):
        self.parts.append(html)
        self._version += 1
        self._closed_line = True

    def html(self):
        return (u"<!DOCTYPE html><html><head><meta charset='utf-8'>"
                u"<meta http-equiv='X-UA-Compatible' content='IE=edge'><style>%s</style></head>"
                u"<body>%s<div id='end'></div></body></html>") % (CSS, u"\n".join(self.parts))

    def flush(self):
        """Show the window (first time) or refresh it with everything printed so far."""
        alive = self.form is not None and not self.form.IsDisposed
        if not self.parts or (self._version == self._shown and alive):
            return
        self._shown = self._version
        try:
            if self.form is None or self.form.IsDisposed:
                self._create()
            self.browser.DocumentText = self.html()
        except Exception as e:  # outside Windows (tests)
            if mytools_host.HOST is not None:
                raise
            self.last_error = e

    def _create(self):
        import mytools_ui
        from System.Drawing import Point
        from System.Windows.Forms import WebBrowser, DockStyle, FormStartPosition, FormBorderStyle
        f = mytools_ui.new_form(self.title, 820, 560)
        f.MinimizeBox = True
        f.MaximizeBox = True
        f.ShowInTaskbar = True
        f.FormBorderStyle = FormBorderStyle.Sizable
        f.KeyPreview = False
        area = mytools_ui.work_area()
        f.StartPosition = FormStartPosition.Manual
        f.Location = Point(area.Right - 860, area.Top + 80)
        b = WebBrowser()
        b.Dock = DockStyle.Fill
        b.ScriptErrorsSuppressed = True
        b.IsWebBrowserContextMenuEnabled = True
        b.AllowWebBrowserDrop = False
        b.Navigating += self._on_navigating
        b.DocumentCompleted += self._on_loaded
        f.Controls.Add(b)
        self.form, self.browser = f, b
        mytools_ui.show_modeless(f)

    def _on_loaded(self, sender, e):
        try:
            end = sender.Document.GetElementById("end")
            if end is not None:
                end.ScrollIntoView(False)
        except Exception:
            pass

    def _on_navigating(self, sender, e):
        url = e.Url
        if url is None or url.Scheme not in ("http", "https"):
            return
        e.Cancel = True
        if url.Host == SELECT_HOST:
            ids = [s for s in url.Query.lstrip("?").replace("ids=", "").split(",") if s.strip()]
            self._select(ids)
        else:
            try:
                from mytools_vault import compat
                compat.open_url(url.AbsoluteUri)
            except Exception:
                pass

    def _select(self, ids):
        uiapp = self.uiapp

        def do_select():
            from System import Int64
            from System.Collections.Generic import List
            from Autodesk.Revit.DB import ElementId
            uidoc = uiapp.ActiveUIDocument
            if uidoc is None:
                return
            doc = uidoc.Document
            eids = List[ElementId]()
            for s in ids:
                eid = ElementId(Int64(int(s)))
                if doc.GetElement(eid) is not None:
                    eids.Add(eid)
            uidoc.Selection.SetElementIds(eids)
            if eids.Count:
                try:
                    uidoc.ShowElements(eids)
                except Exception:
                    pass

        from System import Action
        mytools_host.HOST.Post(Action(do_select))
