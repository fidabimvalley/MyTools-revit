# MyTools for Revit

A toolbar for **Revit 2025 and 2026**. Sign up with your email, and the MyTools administrator approves your access. You don't need pyRevit.

## Install

1. Close Revit.
2. **[Download Install-MyTools.bat](https://github.com/fidabimvalley/MyTools-revit/releases/download/installer/Install-MyTools.bat)** and double-click it. If Windows warns *"Windows protected your PC"*, click **More info → Run anyway**.
3. Start Revit. The first time, Revit asks whether to load MyTools: click **Always Load**.

A **MyTools** tab appears with **Sign In** and **Account** buttons. No admin rights are needed. To update MyTools later, run the installer again.

To remove MyTools, run **[Uninstall-MyTools.bat](https://github.com/fidabimvalley/MyTools-revit/releases/download/installer/Uninstall-MyTools.bat)**.

## Sign up / sign in

1. Click **MyTools → Sign In** and type your email address.
2. We email you a code. Type it into Revit. If it hasn't arrived within a minute, check your spam folder.
3. **First time:** enter your name and company. Your request goes to the administrator. Once you're approved, click **Account → Check again**.

The MyTools panels and buttons then appear.

## Good to know

- Each time you click a button, it loads its code from the MyTools server, so updates reach you straight away.
- **Working offline:** buttons keep working for **3 days** after your last connection. After that, connect to the internet once.
- **Account** shows your access status. Use it to check again or to sign out.
- New buttons appear when Revit starts, or after **Account → Check again**.
- If your access ends, the MyTools buttons are removed the next time you click one or start Revit.
- Your sign-in is stored encrypted, for your Windows user only. Button settings are kept in `%APPDATA%\MyTools\settings.json`.
- **Shift+Click** on a button opens its settings, where it has any.

---

### For maintainers

| Folder | What it is |
|---|---|
| `addin/MyTools.Revit` | The Revit add-in (C#, .NET 8). It builds the MyTools tab, with one ribbon slot per button. |
| `addin/MyTools.Engine` | The Python engine (IronPython 3.4). It's loaded in its own context, so it can't clash with Dynamo or pyRevit. |
| `addin/python` | Runs the buttons. Small stand-ins for the parts of `pyrevit` and `rpw` the buttons use: dialogs, the report window, settings, `revit.Transaction`. |
| `lib/mytools_vault` | Sign-in, access checks, offline cache and protected button loading. |
| `tools/` | The ribbon builder and publisher used by the source repository. |

Pushing to `main` triggers **Build add-in** (`.github/workflows/addin.yml`) on Windows. It:
1. builds the add-in;
2. runs `addin/tests/smoke.py` and `tests/test_vault.py` in IronPython;
3. publishes `MyTools-Revit.zip` to the `installer` release, which is where the installer downloads it from.
