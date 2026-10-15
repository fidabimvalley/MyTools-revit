# -*- coding: utf-8 -*-
"""pyrevit.script stand-in: output window, per-button settings, exit."""
import io
import json
import os
import sys

import mytools_host


def exit():  # noqa: A001 - same name as pyRevit
    sys.exit(0)


def get_output():
    ctx = mytools_host.CTX
    if ctx.output is None:
        from pyrevit.output import OutputWindow
        name = ctx.title or ctx.bundle_name
        ctx.output = OutputWindow("%s - %s" % (mytools_host.tool_name(), name))
    return ctx.output


def get_script_path():
    return mytools_host.CTX.bundle_dir


def get_bundle_file(file_name):
    d = mytools_host.CTX.bundle_dir
    return os.path.join(d, file_name) if d else None


def get_bundle_name():
    return mytools_host.CTX.bundle_name


# ------------------------------------------------------------------ settings
def _settings_path():
    return os.path.join(mytools_host.data_dir(), "settings.json")


_STORE = {"data": None}


def _load():
    if _STORE["data"] is None:
        try:
            with io.open(_settings_path(), "r", encoding="utf-8") as f:
                _STORE["data"] = json.load(f)
        except Exception:
            _STORE["data"] = {}
    return _STORE["data"]


class ConfigSection(object):
    """Settings of one button. Values are read and set as attributes, like pyRevit's."""

    def __init__(self, name, values):
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_values", values)

    def __getattr__(self, key):
        if key.startswith("_"):
            raise AttributeError(key)
        values = object.__getattribute__(self, "_values")
        if key in values:
            return values[key]
        raise AttributeError("Setting '%s' not found." % key)

    def __setattr__(self, key, value):
        self._values[key] = value

    def __delattr__(self, key):
        self._values.pop(key, None)

    def has_option(self, key):
        return key in self._values

    def get_option(self, key, default_value=None):
        return self._values.get(key, default_value)

    def set_option(self, key, value):
        self._values[key] = value

    def remove_option(self, key):
        self._values.pop(key, None)

    def get_options(self):
        return list(self._values.keys())

    @property
    def subheader(self):
        return self._name


def get_config(section=None):
    data = _load()
    name = section or mytools_host.CTX.bundle_name
    return ConfigSection(name, data.setdefault(name, {}))


def _jsonable(v):
    if isinstance(v, (bool, int, float, str)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return dict((str(k), _jsonable(x)) for k, x in v.items())
    return str(v)


def save_config():
    data = _jsonable(_load())
    path = _settings_path()
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False))
    if os.path.exists(path):
        os.remove(path)
    os.rename(tmp, path)


def reset_config(section=None):
    data = _load()
    data.pop(section or mytools_host.CTX.bundle_name, None)
    save_config()


class _Logger(object):
    def _out(self, level, msg, *args):
        if args:
            try:
                msg = msg % args
            except Exception:
                pass
        if level in ("error", "critical"):
            get_output().print_error(u"%s" % msg)
        elif level in ("warning", "info", "success"):
            get_output().print_md(u"%s" % msg)

    def debug(self, msg, *a):
        pass

    def info(self, msg, *a):
        self._out("info", msg, *a)

    def success(self, msg, *a):
        self._out("success", msg, *a)

    def warning(self, msg, *a):
        self._out("warning", msg, *a)

    warn = warning

    def error(self, msg, *a):
        self._out("error", msg, *a)

    def critical(self, msg, *a):
        self._out("critical", msg, *a)

    def exception(self, msg, *a):
        self._out("error", msg, *a)


def get_logger():
    return _Logger()
