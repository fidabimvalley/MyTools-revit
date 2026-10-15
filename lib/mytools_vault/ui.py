# -*- coding: utf-8 -*-
"""Messages and the Sign In / Account / start-up flows."""
import re
import time

from mytools_vault import compat, core, shell

# Tests replace these with fakes that record messages and return scripted answers.
BACKEND = None        # alert(msg, title, options, sub_msg) -> chosen option or None
TEXT_BACKEND = None   # ask(prompt, title, default) -> text or None

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def alert(msg, title, options=None, sub_msg=None):
    """Show a message. With options, returns the chosen option text (None if closed)."""
    if BACKEND is not None:
        return BACKEND(msg, title, options, sub_msg)
    try:
        from pyrevit import forms
        if options:
            return forms.alert(msg, title=title, sub_msg=sub_msg, options=options, warn_icon=False)
        forms.alert(msg, title=title, sub_msg=sub_msg, warn_icon=False)
        return None
    except ImportError:
        print("[%s] %s%s" % (title, msg, ("\n" + sub_msg) if sub_msg else ""))
        return options[0] if options else None


def ask(prompt, title, default=""):
    """Ask for a line of text. Returns None if cancelled."""
    if TEXT_BACKEND is not None:
        return TEXT_BACKEND(prompt, title, default)
    from pyrevit import forms
    value = forms.ask_for_string(default=default or "", prompt=prompt, title=title)
    return value if value is None else value.strip()


def _fmt_time(t):
    if not t:
        return "never"
    return time.strftime("%d %b %Y %H:%M", time.localtime(t))


def _contact(cfg):
    return cfg.get("contact") or "your %s administrator" % cfg["toolName"]


def _host():
    """The MyTools Revit add-in, when running inside it (None under pyRevit or in tests)."""
    try:
        import mytools_host
        return mytools_host.HOST
    except ImportError:
        return None


def reload_pyrevit(cfg, ask_first=True, reason=""):
    """Bring the ribbon in step with the buttons on this PC."""
    host = _host()
    if host is not None:
        try:
            host.RefreshRibbon()
        except Exception as e:
            alert("The toolbar couldn't be updated (%s). Restart Revit to see the changes." % e, cfg["toolName"])
            return False
        if reason:
            alert(reason + " Your toolbar has been updated.", cfg["toolName"])
        return True
    msg = (reason + "\n\n" if reason else "") + "Reload pyRevit now so the toolbar updates? (Takes a few seconds.)"
    if ask_first and alert(msg, cfg["toolName"], ["Reload now", "Later"]) != "Reload now":
        return False
    try:
        from pyrevit.loader import sessionmgr
        sessionmgr.reload_pyrevit()
        return True
    except Exception:
        alert("Click pyRevit → Reload (or restart Revit) to update the toolbar.", cfg["toolName"])
        return False


# ------------------------------------------------------------------ messages used by buttons
def need_sign_in(cfg):
    if alert("Sign in or sign up with your email to use %s." % cfg["toolName"], cfg["toolName"],
             ["Sign in / Sign up", "Cancel"]) == "Sign in / Sign up":
        sign_in(cfg)


def revoked(session, signed_out=False):
    """Access was removed: clean this PC up."""
    cfg = session.cfg
    session.revoke()
    shell.remove_all(cfg)
    if signed_out:
        msg = "Your %s sign-in is no longer valid, so you've been signed out and the tools were removed from this PC." % cfg["toolName"]
    else:
        msg = "Your access to %s has been removed, so the tools were taken off this PC." % cfg["toolName"]
    alert(msg, cfg["toolName"], sub_msg="If you think this is a mistake, contact %s." % _contact(cfg))
    reload_pyrevit(cfg, ask_first=False)


def offline_expired(session, reason):
    cfg = session.cfg
    if reason == "clock":
        msg = "Your PC's date and time look wrong, so %s can't run offline. Fix the clock or connect to the internet." % cfg["toolName"]
    elif reason == "never":
        msg = "%s needs to connect to the internet once before it can be used offline." % cfg["toolName"]
    else:
        msg = ("%s can't reach its server, and the %d-day offline period has ended (last check: %s). "
               "Connect to the internet and try again.") % (cfg["toolName"], cfg["offlineDays"],
                                                          _fmt_time(session.cache and session.cache.get("verifiedAt")))
    alert(msg, cfg["toolName"])


def _waiting(cfg, email):
    alert("Thanks! Your request to use %s is waiting for approval." % cfg["toolName"], cfg["toolName"],
          sub_msg="You're signed in as %s. Once %s approves you, click Account → Check again." % (email, _contact(cfg)))


def _blocked(session, email):
    cfg = session.cfg
    session.revoke()
    shell.remove_all(cfg)
    alert("%s doesn't have access to %s." % (email, cfg["toolName"]), cfg["toolName"],
          sub_msg="If you think this is a mistake, contact %s." % _contact(cfg))


def _unreachable(cfg, title, err):
    """The server couldn't be reached. Show why, so a firewall or proxy problem can be spotted."""
    alert("Can't reach the %s server. Check your internet connection and try again." % cfg["toolName"], title,
          sub_msg="If your internet works, a company firewall or proxy may be blocking %s.\n\nDetails: %s"
                  % (cfg.get("supabaseUrl", "the server"), err or "no response"))


# ------------------------------------------------------------------ Sign In button
def sign_in(cfg):
    if core.Session(cfg).token_info():
        return account(cfg)
    if not (cfg.get("supabaseUrl") and cfg.get("supabaseKey")):
        alert("This copy of %s isn't set up yet (no server in vault.json)." % cfg["toolName"], cfg["toolName"])
        return
    title = cfg["toolName"] + ": sign in or sign up"
    email = ""
    while True:
        email = ask("Your email address\n(new users are signed up automatically):", title, email)
        if email is None:
            return
        email = email.strip().lower()
        if EMAIL_RE.match(email):
            break
        alert("That doesn't look like an email address. Please try again.", title)
    try:
        core.send_code(cfg, email)
    except compat.NetworkError as e:
        return _unreachable(cfg, title, e)
    except Exception as e:
        return alert(str(e), title)

    tok = None
    attempts = 0
    while tok is None:
        code = ask("We emailed a sign-in code to %s.\nEnter it here (check spam if it doesn't arrive within a minute):" % email, title)
        if code is None:
            return
        code = re.sub(r"\s", "", code)
        try:
            tok = core.verify_code(cfg, email, code)
        except core.BadCode:
            attempts += 1
            choice = alert("That code is wrong or has expired.", title, ["Try again", "Send a new code", "Cancel"])
            if choice == "Send a new code":
                try:
                    core.send_code(cfg, email)
                except Exception as e:
                    return alert(str(e), title)
            elif choice != "Try again":
                return
        except compat.NetworkError as e:
            return _unreachable(cfg, title, e)
    return _after_sign_in(cfg, email)


def _after_sign_in(cfg, email):
    session = core.Session(cfg)
    try:
        session.connect_token()
        status = session.status()
    except compat.NetworkError:
        alert("Signed in as %s, but the server can't be reached right now. Click Account → Check again later." % email, cfg["toolName"])
        return False
    if status == "approved":
        session.connect(allow_offline=False)
        return _sync_and_report(session, "Signed in as %s." % email)
    if status == "blocked":
        _blocked(session, email)
        return False
    # New sign-up (or still waiting): collect a name so the administrator knows who it is.
    name = ask("Your name (so %s knows who's asking for access):" % _contact(cfg), cfg["toolName"])
    company = ask("Your company (optional):", cfg["toolName"]) if name is not None else None
    try:
        session.call("mytools_set_profile", {"p_full_name": name or "", "p_company": company or ""})
    except Exception:
        pass
    _waiting(cfg, email)
    return False


def _sync_and_report(session, headline):
    cfg = session.cfg
    session.prefetch_code()
    changed = shell.sync(session)
    session.save()
    n = shell.installed_count(cfg)
    reason = "%s %d %s button%s ready." % (headline, n, cfg["toolName"], "" if n == 1 else "s")
    if changed:
        reload_pyrevit(cfg, ask_first=True, reason=reason)
    else:
        alert(reason + " Your toolbar is up to date.", cfg["toolName"])
    return True


# ------------------------------------------------------------------ Account button
def account(cfg):
    session = core.Session(cfg)
    info = session.token_info()
    if not info:
        return need_sign_in(cfg)
    email = info.get("email", "?")
    try:
        session.connect(allow_offline=True)
        status = "Access: approved (checked just now)" if session.online else \
            "Access: offline. Tools work until %s." % _fmt_time(session.offline_until())
    except core.NoAccess:
        try:
            s = session.status()
        except Exception:
            s = None
        if s == "blocked":
            return revoked(session)
        status = "Access: waiting for approval by %s." % _contact(cfg)
    except core.SignInRequired:
        return revoked(session, signed_out=True)
    except core.OfflineExpired:
        status = "Access: unknown. The server can't be reached and the offline period has ended."
    session.save()
    n = shell.installed_count(cfg)
    msg = "Signed in as %s\n%s\nButtons on this PC: %d" % (email, status, n)
    choice = alert(msg, cfg["toolName"] + " account", ["Check again", "Sign out", "Close"])
    if choice == "Check again":
        return sync_now(cfg)
    if choice == "Sign out":
        return sign_out(cfg)


def sync_now(cfg):
    session = core.Session(cfg)
    try:
        session.connect(allow_offline=False)
    except core.NoAccess:
        try:
            s = session.status()
        except Exception:
            s = None
        if s == "blocked" or shell.installed_count(cfg):
            return revoked(session)
        return _waiting(cfg, session.login)
    except core.SignInRequired:
        if session.token_info():
            return revoked(session, signed_out=True)
        return need_sign_in(cfg)
    except compat.NetworkError as e:
        return _unreachable(cfg, cfg["toolName"], e)
    _sync_and_report(session, "Access approved.")


def sign_out(cfg):
    if alert("Sign out of %s? The tools are removed from this PC until you sign in again." % cfg["toolName"],
             cfg["toolName"], ["Sign out", "Cancel"]) != "Sign out":
        return
    core.Store(cfg).wipe()
    shell.remove_all(cfg)
    reload_pyrevit(cfg, ask_first=False)


# ------------------------------------------------------------------ Revit start-up
def startup(ext_root):
    """Runs quietly every time pyRevit loads: keep the toolbar in step with access, never block for long."""
    cfg = core.load_config(ext_root)
    session = core.Session(cfg, timeout_ms=6000)
    if not session.token_info():
        shell.remove_all(cfg)
        return "signed-out"
    try:
        session.connect(allow_offline=True)
    except core.NoAccess:
        # Waiting for approval keeps the sign-in; anything else (blocked) removes it.
        try:
            s = session.status()
        except Exception:
            s = None
        shell.remove_all(cfg)
        if s == "pending":
            return "pending"
        session.revoke()
        return "revoked"
    except core.SignInRequired:
        session.revoke()
        shell.remove_all(cfg)
        return "revoked"
    except core.OfflineExpired:
        return "offline-expired"
    if not session.online:
        session.save()
        return "offline"
    try:
        session.prefetch_code(budget_s=15)
        shell.sync(session)
    except (compat.NetworkError, core.NoAccess):
        pass
    session.save()
    return "ok"
