# -*- coding: utf-8 -*-
"""MyTools' stand-in for the parts of pyRevit the buttons use, so pyRevit isn't needed.

    from pyrevit import revit, DB, UI, forms, script, EXEC_PARAMS
"""
import mytools_host

try:
    import clr
    clr.AddReference("RevitAPI")
    clr.AddReference("RevitAPIUI")
    from Autodesk.Revit import DB, UI  # noqa: F401
except Exception:  # outside Revit (tests)
    DB = UI = None


class _ExecParams(object):
    @property
    def config_mode(self):
        return mytools_host.CTX.shift

    @property
    def command_path(self):
        return mytools_host.CTX.bundle_dir

    @property
    def command_name(self):
        return mytools_host.CTX.bundle_name

    script_file = property(lambda self: mytools_host.CTX.script_path)
    debug_mode = False
    executed_from_ui = True
    window_handle = None


EXEC_PARAMS = _ExecParams()


class _Selection(object):
    """revit.get_selection(): the elements selected in Revit."""

    def __init__(self, uidoc):
        self._uidoc = uidoc

    @property
    def element_ids(self):
        return list(self._uidoc.Selection.GetElementIds())

    @property
    def elements(self):
        doc = self._uidoc.Document
        return [e for e in (doc.GetElement(i) for i in self.element_ids) if e is not None]

    @property
    def first(self):
        els = self.elements
        return els[0] if els else None

    @property
    def is_empty(self):
        return not self.element_ids

    def __iter__(self):
        return iter(self.elements)

    def __len__(self):
        return len(self.element_ids)

    def set_to(self, items):
        from System.Collections.Generic import List
        ids = List[DB.ElementId]()
        for x in items or []:
            ids.Add(x if isinstance(x, DB.ElementId) else x.Id)
        self._uidoc.Selection.SetElementIds(ids)

    def append(self, items):
        self.set_to(self.element_ids + [x if isinstance(x, DB.ElementId) else x.Id for x in items])

    def clear(self):
        self.set_to([])


class _Transaction(object):
    """with revit.Transaction("name"): ...  commits, or rolls back if the block raises."""

    def __init__(self, name=None, doc=None, clear_after_rollback=False, show_error_dialog=False,
                 swallow_errors=False, log_errors=True, nested=False):
        self._doc = doc or revit.doc
        self._name = name or "MyTools"
        self._swallow = swallow_errors
        self._tx = None

    def __enter__(self):
        self._tx = DB.Transaction(self._doc, self._name)
        self._tx.Start()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            try:
                if self._tx.HasStarted() and not self._tx.HasEnded():
                    self._tx.RollBack()
            except Exception:
                pass
            return bool(self._swallow) and exc_type is not SystemExit
        self._tx.Commit()
        return False


class _TransactionGroup(_Transaction):
    def __enter__(self):
        self._tx = DB.TransactionGroup(self._doc, self._name)
        self._tx.Start()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not None:
            try:
                self._tx.RollBack()
            except Exception:
                pass
            return False
        self._tx.Assimilate()
        return False


class _Revit(object):
    """`from pyrevit import revit`: the active document, view and selection."""

    Transaction = _Transaction
    TransactionGroup = _TransactionGroup

    @property
    def uiapp(self):
        return mytools_host.CTX.uiapp

    @property
    def uidoc(self):
        app = self.uiapp
        return app.ActiveUIDocument if app is not None else None

    @property
    def doc(self):
        u = self.uidoc
        return u.Document if u is not None else None

    @property
    def active_view(self):
        d = self.doc
        return d.ActiveView if d is not None else None

    @property
    def docs(self):
        return list(self.uiapp.Application.Documents)

    def get_selection(self):
        return _Selection(self.uidoc)

    def pick_element(self, message=""):
        from Autodesk.Revit.UI.Selection import ObjectType
        try:
            ref = self.uidoc.Selection.PickObject(ObjectType.Element, message)
        except Exception:
            return None
        return self.doc.GetElement(ref)


revit = _Revit()


class _HostApp(object):
    uiapp = property(lambda self: revit.uiapp)
    uidoc = property(lambda self: revit.uidoc)
    doc = property(lambda self: revit.doc)
    app = property(lambda self: revit.uiapp.Application)
    active_view = property(lambda self: revit.active_view)

    @property
    def version(self):
        return revit.uiapp.Application.VersionNumber


HOST_APP = _HostApp()
