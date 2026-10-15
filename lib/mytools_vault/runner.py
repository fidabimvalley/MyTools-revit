# -*- coding: utf-8 -*-
"""Runs a protected button: checks access, loads its code from GitHub and runs it in memory.

Every button stub on the ribbon contains only:
    from mytools_vault import runner
    runner.run(__file__, globals())
"""
import os
import re
import sys

from mytools_vault import core, ui

_CODING = re.compile(r"^[ \t\f]*#.*?coding[:=][ \t]*[-\w.]+")


def _clean_source(text):
    """Remove a UTF-8 BOM and the coding line (compile() of text rejects it on some engines).
    Line numbers stay the same, so error messages still point at the right line."""
    if text.startswith(u"﻿"):
        text = text[1:]
    lines = text.split("\n")
    for i in range(min(2, len(lines))):
        if _CODING.match(lines[i]):
            lines[i] = "#"
    return "\n".join(lines)


def _repo_to_local(session, repo_path):
    rel = repo_path[len(session.source_prefix):]
    return os.path.join(session.cfg["extRoot"], *rel.split("/"))


class _Loader(object):
    def __init__(self, finder, fullname, repo_path, is_pkg):
        self.finder = finder
        self.fullname = fullname
        self.repo_path = repo_path
        self.is_pkg = is_pkg

    # Python 3
    def create_module(self, spec):
        return None

    def exec_module(self, module):
        self._fill(module)

    # Python 2 / IronPython
    def load_module(self, fullname):
        if fullname in sys.modules:
            return sys.modules[fullname]
        import imp
        module = imp.new_module(fullname)
        sys.modules[fullname] = module
        try:
            self._fill(module)
        except Exception:
            del sys.modules[fullname]
            raise
        return module

    def _fill(self, module):
        session = self.finder.session
        local = _repo_to_local(session, self.repo_path)
        module.__file__ = local
        module.__loader__ = self
        if self.is_pkg:
            module.__path__ = [os.path.dirname(local)]
            module.__package__ = self.fullname
        else:
            module.__package__ = self.fullname.rpartition(".")[0]
        self.finder.loaded.append(self.fullname)
        code = compile(_clean_source(session.read_text(self.repo_path)), local, "exec")
        exec(code, module.__dict__)


class ProtectedImporter(object):
    """Serves the button's helper modules and the extension's lib/ modules from GitHub."""

    def __init__(self, session, bundle_repo_dir):
        self.session = session
        self.roots = [bundle_repo_dir.rstrip("/"), session.source_prefix + "lib"]
        self.loaded = []

    def _locate(self, fullname):
        rel = fullname.replace(".", "/")
        for root in self.roots:
            for cand, is_pkg in ((root + "/" + rel + ".py", False), (root + "/" + rel + "/__init__.py", True)):
                if self.session.has(cand):
                    return cand, is_pkg
        return None, False

    # Python 3
    def find_spec(self, fullname, path=None, target=None):
        repo_path, is_pkg = self._locate(fullname)
        if not repo_path:
            return None
        import importlib.util
        loader = _Loader(self, fullname, repo_path, is_pkg)
        return importlib.util.spec_from_loader(fullname, loader, is_package=is_pkg,
                                               origin=_repo_to_local(self.session, repo_path))

    # Python 2 / IronPython
    def find_module(self, fullname, path=None):
        repo_path, is_pkg = self._locate(fullname)
        if not repo_path:
            return None
        return _Loader(self, fullname, repo_path, is_pkg)


def run(stub_file, globs):
    ext_root = core.find_extension_root(stub_file)
    cfg = core.load_config(ext_root)
    rel = os.path.relpath(os.path.abspath(stub_file), ext_root).replace(os.sep, "/")
    session = core.Session(cfg)
    try:
        session.connect(allow_offline=True)
    except core.SignInRequired:
        if session.token_info():
            ui.revoked(session, signed_out=True)
        else:
            ui.need_sign_in(cfg)
        return
    except core.NoAccess:
        ui.revoked(session)
        return
    except core.OfflineExpired as e:
        ui.offline_expired(session, str(e))
        return

    repo_path = session.source_prefix + rel
    if not session.has(repo_path):
        ui.alert("This button isn't available any more. Click Account → Check again to update your toolbar.",
                 cfg["toolName"])
        session.save()
        return
    try:
        source = session.read_text(repo_path)
    except core.OfflineExpired:
        ui.alert("This button hasn't been downloaded yet, and GitHub can't be reached. "
                 "Connect to the internet and try again.", cfg["toolName"])
        return
    except core.NoAccess:
        ui.revoked(session)
        return

    importer = ProtectedImporter(session, repo_path.rsplit("/", 1)[0])
    sys.meta_path.insert(0, importer)
    local_file = os.path.join(ext_root, *rel.split("/"))

    def read_protected_file(path):
        """Text of a file in this extension. Protected .py files come from GitHub; others from disk."""
        full = os.path.abspath(path)
        rel_path = os.path.relpath(full, ext_root).replace(os.sep, "/")
        candidate = session.source_prefix + rel_path
        if not rel_path.startswith("..") and session.has(candidate):
            return _clean_source(session.read_text(candidate))
        import io
        with io.open(full, "r", encoding="utf-8-sig") as f:
            return f.read()

    globs["read_protected_file"] = read_protected_file
    try:
        code = compile(_clean_source(source), local_file, "exec")
        exec(code, globs)
    finally:
        try:
            sys.meta_path.remove(importer)
        except ValueError:
            pass
        for name in importer.loaded:
            sys.modules.pop(name, None)
        try:
            session.save()
        except Exception:
            pass
