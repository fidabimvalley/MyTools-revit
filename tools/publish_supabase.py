"""Upload the MyTools button code and ribbon files to the MyTools server (Supabase).

    SUPABASE_URL=https://xxxx.supabase.co SUPABASE_SECRET_KEY=... \
        python tools/publish_supabase.py path/to/MyTools.extension

Uploads:
  MyTools.extension/**.py   the button code (served only to approved users, run in memory)
  _shell/**                 ribbon stubs, icons, bundle.yaml and data files (built by build_shell.py)

Runs on GitHub after every change to the extension. Files removed from the extension are removed
from the server too. Add --dry-run to only list what would be uploaded.
"""
import base64
import hashlib
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_shell  # noqa: E402

SKIP_DIRS = {"__pycache__", ".git"}


def git_sha(data):
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _read(path):
    with open(path, "rb") as f:   # closed straight away: IronPython doesn't close files on its own
        return f.read()


def collect(ext_dir):
    """All files to publish, as {path: bytes}."""
    ext_dir = os.path.normpath(ext_dir)
    ext_name = os.path.basename(ext_dir)
    files = {}
    for dirpath, dirnames, filenames in os.walk(ext_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and d.lower() not in build_shell.SKIP_DIRS
                       and not d.startswith(".")]
        for name in filenames:
            if name.endswith(".py"):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, ext_dir).replace(os.sep, "/")
                files[ext_name + "/" + rel] = _read(full)
    with tempfile.TemporaryDirectory() as tmp:
        shell_dir = os.path.join(tmp, "_shell")
        build_shell.build(ext_dir, shell_dir)
        for dirpath, _, filenames in os.walk(shell_dir):
            for name in filenames:
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, shell_dir).replace(os.sep, "/")
                files["_shell/" + rel] = _read(full)
    return files


def payload(files):
    return [{"path": p, "sha": git_sha(d), "content": base64.b64encode(d).decode("ascii")}
            for p, d in sorted(files.items())]


def publish(url, key, files):
    headers = {"apikey": key, "Content-Type": "application/json"}
    if key.startswith("eyJ"):  # legacy service_role JWT
        headers["Authorization"] = "Bearer " + key
    body = json.dumps({"p_files": payload(files)}).encode("utf-8")
    req = urllib.request.Request(url.rstrip("/") + "/rest/v1/rpc/mytools_publish", data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        hint = ""
        if e.code in (401, 403):
            hint = "\nCheck the SUPABASE_SECRET_KEY secret: it must be the project's secret (service_role) key."
        elif e.code == 404:
            hint = "\nRun supabase/setup.sql in the Supabase SQL Editor first."
        sys.exit("Publishing failed (%d): %s%s" % (e.code, detail[:500], hint))


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    files = collect(args[0])
    code = len([p for p in files if not p.startswith("_shell/")])
    print("%d code files, %d ribbon files (%.0f KB)" % (code, len(files) - code, sum(len(d) for d in files.values()) / 1024.0))
    if "--dry-run" in argv:
        for p in sorted(files):
            print("  " + p)
        return
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SECRET_KEY")
    if not url or not key:
        sys.exit("Set SUPABASE_URL and SUPABASE_SECRET_KEY.")
    print("Published:", publish(url, key, files))


if __name__ == "__main__":
    main(sys.argv[1:])
