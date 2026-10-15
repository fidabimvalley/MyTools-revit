"""End-to-end tests for MyTools email sign-up and access control, against a fake Supabase server.

    python tests/test_vault.py

Covers: sign-up with an emailed code, waiting for approval, approval, toolbar download, running
protected buttons (helper / lib / package imports, read_protected_file), sign-in refresh, blocking
(on click and at start-up), deleted users, offline use, offline expiry and clock tampering.
"""
import base64
import json
import os
import shutil
import sys
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.dirname(HERE)
TMP = tempfile.mkdtemp(prefix="vault-test-")
os.environ["MYTOOLS_VAULT_TEST"] = "1"
os.environ["MYTOOLS_VAULT_HOME"] = os.path.join(TMP, "appdata")
sys.path.insert(0, os.path.join(PUBLIC, "tools"))
import build_shell  # noqa: E402
import publish_supabase  # noqa: E402

KEY = "sb_publishable_test"


# ------------------------------------------------------------------ fake Supabase
class FakeSupabase(object):
    def __init__(self, ext_dir):
        self.ext_dir = ext_dir
        self.users = {}       # email -> {"id", "status", "name", "company"}
        self.codes = {}       # email -> code
        self.access = {}      # access token -> (email, expired?)
        self.refresh = {}     # refresh token -> email
        self.files = {}
        self.calls = []
        self.publish()

    def publish(self):
        """Exactly what the GitHub workflow uploads."""
        self.files = dict((f["path"], f) for f in publish_supabase.payload(publish_supabase.collect(self.ext_dir)))

    def expire_all_access_tokens(self):
        for t in self.access:
            self.access[t] = (self.access[t][0], True)

    def issue(self, email):
        a, r = "acc-" + uuid.uuid4().hex, "ref-" + uuid.uuid4().hex
        self.access[a] = (email, False)
        self.refresh[r] = email
        return {"access_token": a, "refresh_token": r, "expires_in": 3600,
                "user": {"id": self.users[email]["id"], "email": email}}


def make_handler(sb):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, status, obj):
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            url = urlparse(self.path)
            sb.calls.append(url.path)
            if self.headers.get("apikey") != KEY:
                return self._send(401, {"message": "Invalid API key"})
            if url.path == "/auth/v1/otp":
                email = body["email"]
                if email not in sb.users:
                    sb.users[email] = {"id": str(uuid.uuid4()), "status": "pending", "name": None, "company": None}
                sb.codes[email] = "123456"
                return self._send(200, {})
            if url.path == "/auth/v1/verify":
                email = body["email"]
                if email in sb.users and sb.codes.get(email) == body["token"]:
                    del sb.codes[email]
                    return self._send(200, sb.issue(email))
                return self._send(403, {"code": 403, "error_code": "otp_expired", "msg": "Token has expired or is invalid"})
            if url.path == "/auth/v1/token" and parse_qs(url.query).get("grant_type") == ["refresh_token"]:
                email = sb.refresh.pop(body.get("refresh_token"), None)
                if not email or email not in sb.users:
                    return self._send(400, {"error": "invalid_grant", "error_description": "Invalid Refresh Token: Refresh Token Not Found"})
                return self._send(200, sb.issue(email))
            if url.path.startswith("/rest/v1/rpc/"):
                auth = self.headers.get("Authorization", "").replace("Bearer ", "")
                if auth not in sb.access:
                    return self._send(401, {"code": "PGRST301", "message": "JWT invalid"})
                email, expired = sb.access[auth]
                if expired:
                    return self._send(401, {"code": "PGRST303", "message": "JWT expired"})
                user = sb.users.get(email)
                name = url.path.rsplit("/", 1)[1]
                if name == "mytools_my_status":
                    return self._send(200, user["status"] if user else None)
                if name == "mytools_set_profile":
                    user["name"], user["company"] = body.get("p_full_name"), body.get("p_company")
                    return self._send(200, None)
                if not user or user["status"] != "approved":
                    return self._send(403, {"code": "42501", "message": "not_approved"})
                if name == "mytools_tree":
                    return self._send(200, [{"path": f["path"], "sha": f["sha"]} for f in sb.files.values()])
                if name == "mytools_files":
                    return self._send(200, [sb.files[p] for p in body["p_paths"] if p in sb.files])
            self._send(404, {"message": "Not Found"})
    return H


# ------------------------------------------------------------------ fixtures
def write(root, rel, text, binary=False):
    p = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(text if binary else text.encode("utf-8"))


def make_source(ext):
    write(ext, "MyTools.tab/Demo.panel/bundle.yaml", "title: Demo\n")
    hello = "MyTools.tab/Demo.panel/Hello.pushbutton/"
    write(ext, hello + "script.py",
          '# -*- coding: utf-8 -*-\n"""Say hello – with a non-ASCII tooltip."""\n__title__ = "Hello"\n'
          "import helper\nimport shared\n"
          "RESULT = (helper.greet(), shared.lookup(), __file__)\n")
    write(ext, hello + "helper.py", "def greet():\n    return u'héllo'\n")
    write(ext, hello + "lookup.csv", "zone,activity\nZ1,A100\n")
    write(ext, hello + "icon.png", b"\x89PNG fake", binary=True)
    write(ext, "lib/shared.py",
          "import os\n_HERE = os.path.dirname(os.path.abspath(__file__))\n"
          "PATH = os.path.join(_HERE, '..', 'MyTools.tab', 'Demo.panel', 'Hello.pushbutton', 'lookup.csv')\n"
          "def lookup():\n    return open(PATH).read().splitlines()[1]\n")
    pkg = "MyTools.tab/Demo.panel/Pkg.pushbutton/"
    write(ext, pkg + "script.py", "from toolpkg import sub\nRESULT = sub.VALUE\n")
    write(ext, "lib/toolpkg/__init__.py", "NAME = 'pkg'\n")
    write(ext, "lib/toolpkg/sub.py", "from toolpkg import NAME\nVALUE = NAME + '.sub'\n")
    core = "MyTools.tab/Demo.panel/Core.pushbutton/"
    write(ext, core + "script.py",
          "import os\npath = os.path.join(os.path.dirname(__file__), 'panels_core.py')\n"
          "try:\n    src = read_protected_file(path)\nexcept NameError:\n    src = open(path).read()\n"
          "g = {'IN': 21}\nexec(compile(src, path, 'exec'), g)\nRESULT = g['OUT']\n")
    write(ext, core + "panels_core.py", "# -*- coding: utf-8 -*-\nOUT = IN * 2\n")
    write(ext, "MyTools.tab/Demo.panel/Boom.pushbutton/script.py", "import helper2\nraise ValueError('boom')\n")
    write(ext, "MyTools.tab/Demo.panel/Boom.pushbutton/helper2.py", "X = 1\n")
    write(ext, "MyTools.tab/Demo.panel/Boom.pushbutton/BAK/script.py", "OLD = 1\n")


ACCOUNT_STUB = (u"from mytools_vault import core, ui\n"
                u"ui.%s(core.load_config(core.find_extension_root(__file__)))\n")


def install_public_extension(dest, port):
    """What a user's PC has after installing: vault.json and the access library, plus the Sign In and
    Account buttons (in the add-in these are built in; here they are small scripts doing the same)."""
    os.makedirs(dest)
    shutil.copy(os.path.join(PUBLIC, "vault.json"), dest)
    shutil.copytree(os.path.join(PUBLIC, "lib"), os.path.join(dest, "lib"),
                    ignore=shutil.ignore_patterns("__pycache__"))
    for name, fn in (("SignIn", "sign_in"), ("Account", "account")):
        d = os.path.join(dest, "MyTools.tab", "Account.panel", name + ".pushbutton")
        os.makedirs(d)
        with open(os.path.join(d, "script.py"), "w") as f:
            f.write(ACCOUNT_STUB % fn)
    with open(os.path.join(dest, "vault.json")) as f:
        cfg = json.load(f)
    cfg.update(supabaseKey=KEY, contact="the BIM team")
    with open(os.path.join(dest, "vault.json"), "w") as f:
        json.dump(cfg, f)
    os.environ["MYTOOLS_VAULT_API"] = "http://127.0.0.1:%d" % port


class FakeUI(object):
    def __init__(self):
        self.answers, self.texts, self.log = [], [], []

    def __call__(self, msg, title, options, sub_msg):
        self.log.append((title, msg, sub_msg))
        if options:
            return self.answers.pop(0) if self.answers else options[-1]
        return None

    def text(self, prompt, title, default):
        self.log.append((title, prompt, None))
        return self.texts.pop(0) if self.texts else None

    def all(self):
        return " ".join(" ".join(x for x in e if x) for e in self.log)


def click(ext, rel):
    """Run a stub exactly like pyRevit does: exec the file with __file__ set."""
    path = os.path.join(ext, *rel.split("/"))
    globs = {"__name__": "__main__", "__file__": path}
    with open(path, encoding="utf-8") as f:
        src = f.read()
    exec(compile(src, path, "exec"), globs)
    return globs


# ------------------------------------------------------------------ tests
def main():
    src_ext = os.path.join(TMP, "source", "MyTools.extension")
    make_source(src_ext)
    sb = FakeSupabase(src_ext)
    srv = HTTPServer(("127.0.0.1", 0), make_handler(sb))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    ext = os.path.join(TMP, "Extensions", "MyTools.extension")
    install_public_extension(ext, port)
    sys.path.insert(0, os.path.join(ext, "lib"))
    from mytools_vault import core, ui, shell
    fake = FakeUI()
    ui.BACKEND, ui.TEXT_BACKEND = fake, fake.text
    tab = os.path.join(ext, "MyTools.tab")
    store_dir = os.path.join(os.environ["MYTOOLS_VAULT_HOME"], "MyToolsVault", "MyTools")
    hello = "MyTools.tab/Demo.panel/Hello.pushbutton/script.py"
    SIGN_IN = "MyTools.tab/Account.panel/SignIn.pushbutton/script.py"
    ACCOUNT = "MyTools.tab/Account.panel/Account.pushbutton/script.py"
    passed = [0]

    def ok(name):
        passed[0] += 1
        print("  ok  " + name)

    def restart_server():
        s = HTTPServer(("127.0.0.1", port), make_handler(sb))
        threading.Thread(target=s.serve_forever, daemon=True).start()
        return s

    # 1. Fresh install.
    assert sorted(os.listdir(tab)) == ["Account.panel"]
    assert ui.startup(ext) == "signed-out"
    assert "MyTools.extension/MyTools.tab/Demo.panel/Boom.pushbutton/BAK/script.py" not in sb.files
    ok("fresh install shows only the Account panel; backup folders aren't published")

    # 2. Sign up: bad email, wrong code, then right code; name collected; waiting for approval.
    fake.texts = ["not-an-email", "Alice@Example.com", "000000", "123 456", "Alice A", "ACME"]
    fake.answers = ["Try again"]
    click(ext, SIGN_IN)
    u = sb.users["alice@example.com"]
    assert u["status"] == "pending" and u["name"] == "Alice A" and u["company"] == "ACME", u
    assert "doesn't look like an email" in fake.all() and "wrong or has expired" in fake.all()
    assert "waiting for approval" in fake.all() and "the BIM team" in fake.all()
    assert sorted(os.listdir(tab)) == ["Account.panel"]
    assert ui.startup(ext) == "pending" and os.path.exists(os.path.join(store_dir, "signin.bin"))
    ok("sign up by email code; name and company sent; waits for approval, stays signed in")

    # 3. Approved: Account → Check again installs the toolbar.
    u["status"] = "approved"
    fake.log[:] = []
    fake.answers = ["Check again", "Later"]
    click(ext, ACCOUNT)
    assert os.path.isfile(os.path.join(ext, *hello.split("/")))
    assert os.path.isfile(os.path.join(tab, "Demo.panel", "Hello.pushbutton", "lookup.csv"))
    assert not os.path.exists(os.path.join(tab, "Demo.panel", "Hello.pushbutton", "helper.py")), "helper code on disk"
    assert not os.path.exists(os.path.join(ext, "lib", "shared.py")), "lib code on disk"
    with open(os.path.join(ext, *hello.split("/")), encoding="utf-8") as f:
        stub = f.read()
    assert "greet" not in stub and "__title__ = 'Hello'" in stub
    assert "4 MyTools buttons ready" in fake.all(), fake.log
    ok("approval: toolbar downloaded, no Python code written to disk")

    # 4. Buttons run.
    g = click(ext, hello)
    assert g["RESULT"][0] == u"héllo" and g["RESULT"][1] == "Z1,A100"
    assert g["RESULT"][2] == os.path.join(ext, *hello.split("/"))
    assert "helper" not in sys.modules and "shared" not in sys.modules
    assert click(ext, "MyTools.tab/Demo.panel/Pkg.pushbutton/script.py")["RESULT"] == "pkg.sub"
    assert click(ext, "MyTools.tab/Demo.panel/Core.pushbutton/script.py")["RESULT"] == 42
    try:
        click(ext, "MyTools.tab/Demo.panel/Boom.pushbutton/script.py")
        raise AssertionError("expected the button's own error")
    except ValueError:
        pass
    assert not any(type(f).__name__ == "ProtectedImporter" for f in sys.meta_path) and "helper2" not in sys.modules
    ok("buttons run with helper, lib, package imports and read_protected_file; cleaned up after errors")

    # 5. Expired sign-in is refreshed silently.
    sb.expire_all_access_tokens()
    assert click(ext, hello)["RESULT"][0] == u"héllo"
    assert "/auth/v1/token" in sb.calls
    ok("expired sign-in refreshed automatically")

    # 6. Code updates reach the next click; only changed files are downloaded.
    write(src_ext, "MyTools.tab/Demo.panel/Hello.pushbutton/helper.py", "def greet():\n    return 'v2'\n")
    sb.publish()
    before = sb.calls.count("/rest/v1/rpc/mytools_files")
    assert click(ext, hello)["RESULT"][0] == "v2"
    assert sb.calls.count("/rest/v1/rpc/mytools_files") - before == 1
    ok("updated code arrives on the next click; only changed files are fetched")

    # 7. Offline: works from the encrypted copy.
    srv.shutdown(); srv.server_close()
    assert click(ext, hello)["RESULT"][0] == "v2"
    assert ui.startup(ext) == "offline"
    with open(os.path.join(store_dir, "offline.bin")) as f:
        blob = f.read()
    assert "greet" not in blob and "v2" not in blob
    ok("offline: buttons keep working from the encrypted copy")

    # 8. Offline past 3 days, and clock turned back: refused.
    real_now = core.now
    core.now = lambda: real_now() + 3 * 86400 + 60
    fake.log[:] = []
    assert "RESULT" not in click(ext, hello) and "offline period has ended" in fake.all()
    core.now = lambda: real_now() - 2 * 86400
    fake.log[:] = []
    assert "RESULT" not in click(ext, hello) and "date and time look wrong" in fake.all()
    core.now = real_now
    ok("offline for more than 3 days, or with the clock turned back: refused")
    srv = restart_server()

    # 9. Buttons added / removed on GitHub follow at the next Revit start.
    write(src_ext, "MyTools.tab/Demo.panel/New.pushbutton/script.py", "RESULT = 'new'\n")
    shutil.rmtree(os.path.join(src_ext, "MyTools.tab", "Demo.panel", "Pkg.pushbutton"))
    sb.publish()
    assert ui.startup(ext) == "ok"
    assert click(ext, "MyTools.tab/Demo.panel/New.pushbutton/script.py")["RESULT"] == "new"
    assert not os.path.exists(os.path.join(tab, "Demo.panel", "Pkg.pushbutton"))
    ok("buttons added or removed on GitHub follow at the next Revit start")

    # 10. Blocked: next click removes everything and signs out.
    u["status"] = "blocked"
    fake.log[:] = []
    assert "RESULT" not in click(ext, hello)
    assert "access to MyTools has been removed" in fake.all(), fake.log
    assert sorted(os.listdir(tab)) == ["Account.panel"]
    assert not os.path.exists(os.path.join(store_dir, "signin.bin")) and not os.path.exists(os.path.join(store_dir, "offline.bin"))
    ok("blocked: next click takes the tools off the PC and signs out")

    # 11. Blocked user signs in again: refused, nothing installed.
    fake.texts = ["alice@example.com", "123456"]
    fake.log[:] = []
    click(ext, SIGN_IN)
    assert "doesn't have access" in fake.all() and sorted(os.listdir(tab)) == ["Account.panel"]
    assert not os.path.exists(os.path.join(store_dir, "signin.bin"))
    ok("a blocked user signing in again gets nothing")

    # 12. Blocked while Revit was closed: removed at start-up.
    u["status"] = "approved"
    fake.texts, fake.answers = ["alice@example.com", "123456"], ["Later"]
    click(ext, SIGN_IN)
    assert os.path.isfile(os.path.join(ext, *hello.split("/")))
    u["status"] = "blocked"
    assert ui.startup(ext) == "revoked" and sorted(os.listdir(tab)) == ["Account.panel"]
    ok("blocked while Revit was closed: tools gone at the next start")

    # 13. User deleted in Supabase: sign-in no longer valid → removed.
    u["status"] = "approved"
    fake.texts, fake.answers = ["alice@example.com", "123456"], ["Later"]
    click(ext, SIGN_IN)
    del sb.users["alice@example.com"]
    sb.expire_all_access_tokens()
    fake.log[:] = []
    assert "RESULT" not in click(ext, hello)
    assert "no longer valid" in fake.all() and sorted(os.listdir(tab)) == ["Account.panel"]
    ok("user deleted on the server: signed out and tools removed")

    # 14. Sign out.
    fake.texts, fake.answers = ["bob@example.com", "123456", "Bob", ""], []
    click(ext, SIGN_IN)
    sb.users["bob@example.com"]["status"] = "approved"
    fake.answers = ["Check again", "Later"]
    click(ext, ACCOUNT)
    assert os.path.isfile(os.path.join(ext, *hello.split("/")))
    fake.answers = ["Sign out", "Sign out"]
    click(ext, ACCOUNT)
    assert sorted(os.listdir(tab)) == ["Account.panel"] and not os.path.exists(os.path.join(store_dir, "signin.bin"))
    ok("sign out removes the tools")

    # 15. Downloads are confined to the tab folder.
    for bad in ("../evil.py", "MyTools.tab/Account.panel/SignIn.pushbutton/script.py", "lib/x.py", "MyTools.tab/../../x"):
        assert not shell._safe_rel(bad), bad
    assert shell._safe_rel("MyTools.tab/Demo.panel/Hello.pushbutton/icon.png")
    ok("toolbar downloads are confined to the tab folder")

    srv.shutdown()
    shutil.rmtree(TMP, ignore_errors=True)
    print("\n%d checks passed" % passed[0])
    if os.environ.get("GITHUB_ACTIONS"):
        print("::notice title=Access tests::%d checks passed (Python %s)" % (passed[0], sys.version.split()[0]))


if __name__ == "__main__":
    main()
