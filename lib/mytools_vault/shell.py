# -*- coding: utf-8 -*-
"""Puts the protected panels and buttons on the ribbon for signed-in users, and takes them away again.

The ribbon "shell" (button stubs, icons, settings and data files) is kept on the MyTools server
under _shell/. Python code is never written here; buttons fetch it when clicked.
"""
import json
import os
import re

from mytools_vault import compat

STATE_FILE = ".vault_shell.json"
PROTECTED_NAMES = ("Account.panel",)


def _state_path(cfg):
    return os.path.join(cfg["extRoot"], STATE_FILE)


def _load_state(cfg):
    try:
        return json.loads(compat.read_file(_state_path(cfg)))
    except Exception:
        return {"files": {}}


def _save_state(cfg, state):
    compat.write_file(_state_path(cfg), json.dumps(state, indent=1, sort_keys=True))


def _safe_rel(rel):
    """Only plain paths inside a .tab folder, never the Account panel or anything outside."""
    if not rel or rel.startswith("/") or "\\" in rel or ":" in rel:
        return False
    parts = rel.split("/")
    if ".." in parts or "." in parts or "" in parts:
        return False
    if not re.match(r"^[^/]+\.tab$", parts[0]):
        return False
    return not any(p in PROTECTED_NAMES for p in parts)


def _local(cfg, rel):
    return os.path.join(cfg["extRoot"], *rel.split("/"))


def wanted_files(session):
    prefix = session.cfg["shellFolder"].rstrip("/") + "/"
    out = {}
    for path, sha in (session.tree or {}).items():
        if path.startswith(prefix):
            rel = path[len(prefix):]
            if _safe_rel(rel):
                out[rel] = sha
    return out


def sync(session):
    """Download new/changed ribbon files and remove ones that are gone. Needs an online session.
    Returns the number of added + removed files (0 = the ribbon layout didn't change)."""
    cfg = session.cfg
    state = _load_state(cfg)
    have = state.get("files", {})
    want = wanted_files(session)
    prefix = cfg["shellFolder"].rstrip("/") + "/"
    changed = 0
    todo = [rel for rel, sha in sorted(want.items())
            if not (have.get(rel) == sha and os.path.exists(_local(cfg, rel)))]
    if todo:
        data = session.read_many_bytes([prefix + rel for rel in todo])
        for rel in todo:
            if prefix + rel not in data:
                continue
            compat.write_bytes(_local(cfg, rel), data[prefix + rel])
            if rel not in have:
                changed += 1
            have[rel] = want[rel]
        state["files"] = have
        _save_state(cfg, state)
    for rel in sorted(set(have) - set(want)):
        _remove_file(cfg, rel)
        del have[rel]
        changed += 1
    state["files"] = have
    _save_state(cfg, state)
    _prune_empty_dirs(cfg)
    return changed


def remove_all(cfg):
    """Take every protected panel off this PC. Returns True if anything was removed."""
    state = _load_state(cfg)
    files = state.get("files", {})
    removed = bool(files)
    for rel in list(files):
        _remove_file(cfg, rel)
    _save_state(cfg, {"files": {}})
    _prune_empty_dirs(cfg)
    return removed


def installed_count(cfg):
    return len([r for r in _load_state(cfg).get("files", {}) if r.endswith("script.py")])


def _remove_file(cfg, rel):
    if not _safe_rel(rel):
        return
    p = _local(cfg, rel)
    try:
        if os.path.isfile(p):
            os.remove(p)
    except OSError:
        pass


def _prune_empty_dirs(cfg):
    """Remove folders the shell left empty (any depth), never the Account panel."""
    root = cfg["extRoot"]
    for name in os.listdir(root):
        tab = os.path.join(root, name)
        if not (name.endswith(".tab") and os.path.isdir(tab)):
            continue
        for dirpath, dirnames, filenames in os.walk(tab, topdown=False):
            if os.path.basename(dirpath) in PROTECTED_NAMES or any(p in dirpath for p in PROTECTED_NAMES):
                continue
            if dirpath == tab:
                continue
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
            except OSError:
                pass

