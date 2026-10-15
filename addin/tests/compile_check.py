# -*- coding: utf-8 -*-
"""Checks that every Python file in a folder compiles in IronPython 3.4 (the add-in's engine).

    SmokeTest.exe --path lib compile_check.py <folder>
"""
import io
import os
import re
import sys

_CODING = re.compile(r"^[ \t\f]*#.*?coding[:=][ \t]*[-\w.]+")
SKIP = {"bak", "backup", "old", "__pycache__", ".git", "extracted"}


def clean(text):
    lines = text.split("\n")
    for i in range(min(2, len(lines))):
        if _CODING.match(lines[i]):
            lines[i] = "#"
    return "\n".join(lines)


root = os.path.abspath(sys.argv[1])
ok, bad = 0, []
for folder, dirs, files in os.walk(root):
    dirs[:] = [d for d in dirs if d.lower() not in SKIP]
    for name in sorted(files):
        if not name.endswith(".py"):
            continue
        path = os.path.join(folder, name)
        with io.open(path, "r", encoding="utf-8-sig") as f:
            src = f.read()
        try:
            compile(clean(src), path, "exec")
            ok += 1
        except SyntaxError as e:
            rel = os.path.relpath(path, root).replace("\\", "/")
            bad.append((rel, e.lineno or 1, e.msg))

for rel, line, msg in bad:
    print("%s:%d %s" % (rel, line, msg))
    if os.environ.get("GITHUB_ACTIONS"):
        print("::error file=%s,line=%d::Doesn't compile in the MyTools Python engine (IronPython 3.4): %s" % (rel, line, msg))
print("%d file(s) compile, %d don't." % (ok, len(bad)))
if os.environ.get("GITHUB_ACTIONS") and not bad:
    print("::notice title=IronPython check::%d Python files compile in IronPython 3.4" % ok)
sys.exit(1 if bad else 0)
