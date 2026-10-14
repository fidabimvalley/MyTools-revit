# -*- coding: utf-8 -*-
"""Email sign-in, access checks and the encrypted offline copy of the button code.

The MyTools server is a Supabase project. Users sign up and sign in with their email and a
one-time code. The administrator approves or blocks them; only approved users get any code.
"""
import json
import os
import time

from mytools_vault import compat
from mytools_vault.compat import NetworkError

CLOCK_SLACK = 300      # seconds the PC clock may go backwards before the offline copy is refused
REFRESH_MARGIN = 120   # refresh the sign-in this many seconds before it expires
BATCH = 100            # files per download request


class NoAccess(Exception):
    """Signed in, but not approved (waiting for approval, or blocked)."""


class SignInRequired(Exception):
    """No saved sign-in, or the server no longer accepts it (e.g. the user was deleted)."""


class OfflineExpired(Exception):
    """The server can't be reached and the offline period has run out."""


class BadCode(Exception):
    """The emailed code is wrong or has expired."""


class _TokenExpired(Exception):
    pass


# ------------------------------------------------------------------ paths & config
def find_extension_root(path):
    p = os.path.abspath(path)
    while True:
        if p.lower().endswith(".extension") and os.path.isdir(p):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            raise RuntimeError("MyTools: can't find the .extension folder for " + path)
        p = parent


def load_config(ext_root):
    cfg = json.loads(compat.read_file(os.path.join(ext_root, "vault.json")))
    cfg.setdefault("offlineDays", 3)
    cfg.setdefault("toolName", "MyTools")
    cfg.setdefault("shellFolder", "_shell")
    cfg.setdefault("sourceExtension", cfg["toolName"] + ".extension")
    if os.environ.get("MYTOOLS_VAULT_API"):
        cfg["supabaseUrl"] = os.environ["MYTOOLS_VAULT_API"]
    cfg["supabaseUrl"] = cfg.get("supabaseUrl", "").rstrip("/")
    cfg["extRoot"] = ext_root
    return cfg


def now():
    return time.time()


# ------------------------------------------------------------------ encrypted local store
class Store(object):
    """Holds the sign-in and the offline copy, both encrypted for the Windows user."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.dir = compat.data_dir(cfg["toolName"])
        self.token_path = os.path.join(self.dir, "signin.bin")
        self.cache_path = os.path.join(self.dir, "offline.bin")

    def _read(self, path):
        if not os.path.exists(path):
            return None
        try:
            return json.loads(compat.unprotect(compat.read_file(path)))
        except Exception:
            return None

    def _write(self, path, obj):
        compat.write_file(path, compat.protect(json.dumps(obj)))

    def load_token(self):
        t = self._read(self.token_path)
        return t if t and t.get("refresh") else None

    def save_token(self, data):
        self._write(self.token_path, data)

    def load_cache(self):
        c = self._read(self.cache_path)
        server = self.cfg["supabaseUrl"]
        if not c or c.get("server") != server:
            return {"server": server, "verifiedAt": 0, "maxSeen": 0, "tree": {}, "files": {}}
        return c

    def save_cache(self, cache):
        cache["maxSeen"] = max(cache.get("maxSeen", 0), now())
        self._write(self.cache_path, cache)

    def wipe(self):
        for p in (self.token_path, self.cache_path):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass


# ------------------------------------------------------------------ Supabase
def _message(data):
    if isinstance(data, dict):
        return str(data.get("msg") or data.get("message") or data.get("error_description") or data.get("error") or "")
    return str(data)


class Server(object):
    def __init__(self, cfg, timeout_ms=15000):
        self.cfg = cfg
        self.timeout_ms = timeout_ms

    def _headers(self, access=None):
        h = {"apikey": self.cfg["supabaseKey"], "Content-Type": "application/json", "Accept": "application/json"}
        if access:
            h["Authorization"] = "Bearer " + access
        return h

    def _post(self, path, body, access=None):
        return compat.http_json("POST", self.cfg["supabaseUrl"] + path, self._headers(access),
                                json.dumps(body), self.timeout_ms)

    # ---- email sign-in
    def send_code(self, email):
        status, data = self._post("/auth/v1/otp", {"email": email, "create_user": True})
        if status == 429:
            raise RuntimeError("Too many codes requested. Wait a minute, then try again.")
        if status >= 500:
            raise NetworkError("The %s server had a problem (%d)." % (self.cfg["toolName"], status))
        if status != 200:
            raise RuntimeError(_message(data) or "Couldn't send the code (%d)." % status)

    def verify_code(self, email, code):
        status, data = self._post("/auth/v1/verify", {"type": "email", "email": email, "token": code})
        if status == 200 and data.get("access_token"):
            return _token_record(data, email)
        if status >= 500:
            raise NetworkError("The %s server had a problem (%d)." % (self.cfg["toolName"], status))
        raise BadCode(_message(data) or "That code is wrong or has expired.")

    def refresh(self, token):
        status, data = self._post("/auth/v1/token?grant_type=refresh_token", {"refresh_token": token["refresh"]})
        if status == 200 and data.get("access_token"):
            return _token_record(data, token.get("email", ""))
        if status >= 500 or status == 429:
            raise NetworkError("The %s server had a problem (%d)." % (self.cfg["toolName"], status))
        raise SignInRequired(_message(data) or "Your sign-in is no longer valid.")

    # ---- database functions
    def rpc(self, name, args, access):
        status, data = self._post("/rest/v1/rpc/" + name, args or {}, access)
        if status == 200:
            return data
        msg = _message(data)
        if status == 401 or "JWT" in msg:
            raise _TokenExpired(msg)
        if status == 403 or "not_approved" in msg:
            raise NoAccess(msg)
        if status == 404:
            raise NetworkError("The %s server isn't set up yet (%s missing)." % (self.cfg["toolName"], name))
        raise NetworkError("Unexpected reply from the %s server (%d): %s" % (self.cfg["toolName"], status, msg[:120]))


def _token_record(data, email):
    user = data.get("user") or {}
    return {"access": data["access_token"], "refresh": data["refresh_token"],
            "expiresAt": now() + int(data.get("expires_in", 3600)),
            "email": user.get("email") or email, "userId": user.get("id", "")}


# ------------------------------------------------------------------ the session used by every button
class Session(object):
    def __init__(self, cfg, timeout_ms=15000):
        self.cfg = cfg
        self.store = Store(cfg)
        self.server = Server(cfg, timeout_ms)
        self.cache = None
        self.tree = None
        self.online = False
        self.login = ""
        self._token = None
        self._dirty = False

    @property
    def source_prefix(self):
        return self.cfg["sourceExtension"].rstrip("/") + "/"

    def token_info(self):
        t = self.store.load_token()
        if t:
            t["login"] = t.get("email", "")
        return t

    def offline_until(self):
        c = self.cache or self.store.load_cache()
        if not c.get("verifiedAt"):
            return 0
        return c["verifiedAt"] + self.cfg["offlineDays"] * 86400

    # ---- sign-in token
    def _fresh_token(self, force=False):
        tok = self._token
        if force or tok["expiresAt"] - now() < REFRESH_MARGIN:
            tok = self.server.refresh(tok)          # NetworkError / SignInRequired propagate
            self.store.save_token(tok)
            self._token = tok
        return tok["access"]

    def call(self, name, args=None):
        """Call a server function with automatic sign-in refresh."""
        try:
            return self.server.rpc(name, args, self._fresh_token())
        except _TokenExpired:
            try:
                return self.server.rpc(name, args, self._fresh_token(force=True))
            except _TokenExpired as e:
                raise SignInRequired(str(e))

    def status(self):
        """'approved', 'pending', 'blocked' or None. Needs connect_token() first."""
        return self.call("mytools_my_status")

    def connect_token(self):
        self._token = self.store.load_token()
        if not self._token:
            raise SignInRequired("Not signed in.")
        self.login = self._token.get("email", "")

    def connect(self, allow_offline=True):
        """Check access. Online: the server decides. Offline: the encrypted copy decides, for a few days.

        Raises SignInRequired, NoAccess or OfflineExpired. NoAccess / SignInRequired from the server
        mean access was removed: callers must call revoke()."""
        self.connect_token()
        self.cache = self.store.load_cache()
        try:
            rows = self.call("mytools_tree")
            self.tree = dict((r["path"], r["sha"]) for r in rows)
            self.online = True
            self.cache["verifiedAt"] = now()
            self.cache["login"] = self.login
            self.cache["tree"] = self.tree
            self._dirty = True
            return
        except NetworkError as e:
            if not allow_offline:
                raise
            self.offline_reason = str(e)
        t = now()
        if self.cache.get("login") != self.login or not self.cache.get("verifiedAt"):
            raise OfflineExpired("never")
        if t < self.cache.get("maxSeen", 0) - CLOCK_SLACK:
            raise OfflineExpired("clock")
        if t > self.offline_until():
            raise OfflineExpired("expired")
        self.tree = self.cache.get("tree", {})
        self.online = False
        self.cache["maxSeen"] = max(self.cache.get("maxSeen", 0), t)
        self._dirty = True

    def has(self, path):
        return path in (self.tree or {})

    def _download(self, paths):
        out = {}
        for i in range(0, len(paths), BATCH):
            for r in self.call("mytools_files", {"p_paths": paths[i:i + BATCH]}):
                out[r["path"]] = r
        return out

    def _remember(self, path, row):
        text = compat.b64decode_text(row["content"])
        if path.endswith(".py"):
            self.cache["files"][path] = {"sha": row["sha"], "text": text}
            self._dirty = True
        return text

    def read_text(self, path):
        """Text of a tool file: from the server if it changed, else from the encrypted copy."""
        sha = (self.tree or {}).get(path)
        if sha is None:
            raise KeyError(path)
        cached = self.cache["files"].get(path)
        if cached and (cached.get("sha") == sha or not self.online):
            return cached["text"]
        if not self.online:
            raise OfflineExpired("missing:" + path)
        row = self._download([path]).get(path)
        if row is None:
            raise KeyError(path)
        return self._remember(path, row)

    def read_many_bytes(self, paths):
        rows = self._download(list(paths))
        return dict((p, compat.b64decode_bytes(r["content"])) for p, r in rows.items())

    def prefetch_code(self, budget_s=25):
        """Keep an up-to-date encrypted copy of every Python file, so buttons also work offline."""
        if not self.online:
            return
        keep, need = {}, []
        for path, sha in self.tree.items():
            if not (path.startswith(self.source_prefix) and path.endswith(".py")):
                continue
            cached = self.cache["files"].get(path)
            if cached and cached.get("sha") == sha:
                keep[path] = cached
            else:
                need.append(path)
        self.cache["files"] = keep
        start = now()
        for i in range(0, len(need), BATCH):
            if now() - start > budget_s:
                break
            for path, row in self._download(need[i:i + BATCH]).items():
                self._remember(path, row)
        self._dirty = True

    def save(self):
        if self._dirty and self.cache is not None:
            self.store.save_cache(self.cache)
            self._dirty = False

    def revoke(self):
        """Access is gone: forget the sign-in and the offline copy."""
        self.store.wipe()
        self.cache = None
        self.tree = None


# ------------------------------------------------------------------ sign-up / sign-in helpers
def send_code(cfg, email):
    Server(cfg).send_code(email)


def verify_code(cfg, email, code):
    tok = Server(cfg).verify_code(email, code)
    Store(cfg).save_token(tok)
    return tok
