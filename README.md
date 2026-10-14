# MyTools for Revit

A pyRevit toolbar for Revit. Sign up with your email; the MyTools administrator approves access.

## Install

You need [pyRevit](https://github.com/pyrevitlabs/pyRevit/releases) installed first.

**Option A: one command (recommended).** Open **Command Prompt** and run:

```
pyrevit extend ui MyTools https://github.com/fidabimvalley/mytools-revit.git
```

Then start Revit, or click **pyRevit → Reload** if Revit is already open.

**Option B: by hand.**
1. Click the green **Code** button on this page → **Download ZIP**, and unzip it.
2. Rename the unzipped folder to exactly `MyTools.extension`.
3. Move it into `%APPDATA%\pyRevit\Extensions\` (paste that into the File Explorer address bar).
4. Start Revit, or click **pyRevit → Reload**.

A **MyTools** tab appears with **Sign In** and **Account** buttons.

## Sign up / sign in

1. Click **MyTools → Sign In** and type your email address.
2. We email you a code. Type it into Revit. Check your spam folder if it hasn't arrived within a minute.
3. **First time:** enter your name and company. Your request goes to the administrator. Once you're approved, click **Account → Check again**, then **Reload now**.

The MyTools panels and buttons appear.

## Good to know

- Buttons load their code from the MyTools server each time you click them, so updates reach you straight away.
- **Working offline:** buttons keep working for **3 days** after your last connection. After that, connect to the internet once.
- **Account** shows your access status. Use it to check again or to sign out.
- New buttons appear the next time Revit starts, or after **Account → Check again**.
- If your access ends, the MyTools buttons are removed from your PC the next time you click one or start Revit.
- Your sign-in is stored encrypted for your Windows user only.

---

*For maintainers:* `tests/test_vault.py` runs the full sign-up and access flow against a fake server (`python tests/test_vault.py`). `tools/` holds the ribbon builder and publisher used by the source repository.
