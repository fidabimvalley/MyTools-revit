# -*- coding: utf-8 -*-
"""Platform helpers that work in IronPython (2.7 and 3.4) and CPython 3.

Inside Revit everything goes through .NET (web requests, DPAPI encryption, clipboard),
which both engines can reach. Outside Revit (automated tests) plain Python is used.
"""
import base64
import json
import os
import sys

PY2 = sys.version_info[0] == 2
TEST_MODE = os.environ.get("MYTOOLS_VAULT_TEST") == "1"

try:
    import clr  # noqa: F401  (present in both pyRevit engines)
    HAS_CLR = not TEST_MODE
except ImportError:
    HAS_CLR = False

if PY2:
    text_type = unicode  # noqa: F821
else:
    text_type = str


class NetworkError(Exception):
    """GitHub could not be reached (offline, proxy, timeout, rate limit)."""


def to_text(data):
    if isinstance(data, text_type):
        return data
    return data.decode("utf-8")


def b64decode_text(s):
    raw = base64.b64decode(s)
    try:
        return to_text(raw)
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def b64decode_bytes(s):
    return base64.b64decode(s)


# ------------------------------------------------------------------ HTTP
def _net_request(method, url, headers, body, timeout_ms):
    clr.AddReference("System")
    from System import Convert
    from System.IO import StreamReader
    from System.Net import (WebRequest, WebException, ServicePointManager,
                            SecurityProtocolType, CredentialCache)
    from System.Text import Encoding

    try:
        ServicePointManager.SecurityProtocol = ServicePointManager.SecurityProtocol | SecurityProtocolType.Tls12
    except Exception:
        pass
    req = WebRequest.Create(url)
    req.Method = method
    req.Timeout = timeout_ms
    req.ReadWriteTimeout = timeout_ms
    try:
        if req.Proxy is not None:
            req.Proxy.Credentials = CredentialCache.DefaultCredentials
    except Exception:
        pass
    for k, v in headers.items():
        lk = k.lower()
        if lk == "accept":
            req.Accept = v
        elif lk == "content-type":
            req.ContentType = v
        elif lk == "user-agent":
            req.UserAgent = v
        else:
            req.Headers.Add(k, v)
    if body is not None:
        data = Encoding.UTF8.GetBytes(body)
        req.ContentLength = data.Length
        stream = req.GetRequestStream()
        stream.Write(data, 0, data.Length)
        stream.Close()
    try:
        resp = req.GetResponse()
    except WebException as e:
        resp = e.Response
        if resp is None:
            raise NetworkError(str(e.Message))
    except Exception as e:
        raise NetworkError(str(e))
    try:
        status = Convert.ToInt32(resp.StatusCode)
        reader = StreamReader(resp.GetResponseStream(), Encoding.UTF8)
        text = reader.ReadToEnd()
        reader.Close()
    finally:
        resp.Close()
    return status, text_type(text)


def _py_request(method, url, headers, body, timeout_ms):
    if PY2:
        import urllib2 as ur  # noqa
        HTTPError = ur.HTTPError
        URLError = ur.URLError
    else:
        import urllib.request as ur
        import urllib.error
        HTTPError = urllib.error.HTTPError
        URLError = urllib.error.URLError
    data = body.encode("utf-8") if body is not None else None
    req = ur.Request(url, data=data, headers=headers)
    req.get_method = lambda: method
    try:
        resp = ur.urlopen(req, timeout=timeout_ms / 1000.0)
        status = resp.getcode()
        text = resp.read()
    except HTTPError as e:
        status = e.code
        text = e.read()
    except (URLError, IOError, OSError) as e:
        raise NetworkError(str(e))
    return status, to_text(text)


def http(method, url, headers=None, body=None, timeout_ms=15000):
    """Returns (status_code, response_text). Raises NetworkError when the server can't be reached."""
    headers = dict(headers or {})
    headers.setdefault("User-Agent", "MyTools-Revit")
    if HAS_CLR:
        return _net_request(method, url, headers, body, timeout_ms)
    return _py_request(method, url, headers, body, timeout_ms)


def http_json(method, url, headers=None, body=None, timeout_ms=15000):
    status, text = http(method, url, headers, body, timeout_ms)
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        data = {"message": text[:200]}
    return status, data


# ------------------------------------------------------------------ secure storage (Windows DPAPI)
_ENTROPY = "mytools-vault-v1"


def _load_dpapi():
    """ProtectedData lives in its own assembly on .NET 8 (Revit 2025+), in System.Security before."""
    for name in ("System.Security.Cryptography.ProtectedData", "System.Security"):
        try:
            clr.AddReference(name)
            return
        except Exception:
            pass


def protect(text):
    """Encrypt for the current Windows user. Returns a base64 string."""
    if HAS_CLR:
        _load_dpapi()
        from System import Convert
        from System.Security.Cryptography import ProtectedData, DataProtectionScope
        from System.Text import Encoding
        enc = ProtectedData.Protect(Encoding.UTF8.GetBytes(text), Encoding.UTF8.GetBytes(_ENTROPY),
                                    DataProtectionScope.CurrentUser)
        return text_type(Convert.ToBase64String(enc))
    if TEST_MODE:
        return to_text(base64.b64encode(("TEST:" + text).encode("utf-8")))
    raise RuntimeError("Secure storage is only available on Windows.")


def unprotect(blob):
    if HAS_CLR:
        _load_dpapi()
        from System import Convert
        from System.Security.Cryptography import ProtectedData, DataProtectionScope
        from System.Text import Encoding
        dec = ProtectedData.Unprotect(Convert.FromBase64String(blob), Encoding.UTF8.GetBytes(_ENTROPY),
                                      DataProtectionScope.CurrentUser)
        return text_type(Encoding.UTF8.GetString(dec))
    if TEST_MODE:
        raw = to_text(base64.b64decode(blob))
        if not raw.startswith("TEST:"):
            raise ValueError("bad blob")
        return raw[5:]
    raise RuntimeError("Secure storage is only available on Windows.")


# ------------------------------------------------------------------ desktop helpers
def copy_to_clipboard(text):
    if not HAS_CLR:
        return False
    try:
        clr.AddReference("System.Windows.Forms")
        from System.Windows.Forms import Clipboard
        Clipboard.SetText(text)
        return True
    except Exception:
        return False


def open_url(url):
    if not HAS_CLR:
        return False
    try:
        from System.Diagnostics import Process, ProcessStartInfo
        psi = ProcessStartInfo(url)
        psi.UseShellExecute = True
        Process.Start(psi)
        return True
    except Exception:
        try:
            import webbrowser
            webbrowser.open(url)
            return True
        except Exception:
            return False


def data_dir(tool_name):
    base = os.environ.get("MYTOOLS_VAULT_HOME") or os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, "MyToolsVault", tool_name)
    if not os.path.isdir(d):
        os.makedirs(d)
    return d


def read_file(path):
    with open(path, "rb") as f:
        return to_text(f.read())


def write_file(path, text):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(text.encode("utf-8"))
    if os.path.exists(path):
        os.remove(path)
    os.rename(tmp, path)


def write_bytes(path, data):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, "wb") as f:
        f.write(data)
