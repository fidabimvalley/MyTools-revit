using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Windows.Media.Imaging;
using Autodesk.Revit.UI;

namespace MyTools.Revit
{
    /// <summary>
    /// Builds the MyTools tab. Revit can't delete ribbon items, so buttons that go away (access removed,
    /// button deleted) are hidden and shown again if they come back.
    /// </summary>
    internal class RibbonManager
    {
        internal const int MaxButtons = 200;

        readonly string _tab;
        readonly string _appDir;
        readonly string _assembly;
        Func<string, string, RibbonPanel> _createPanel;
        Func<string, IList<RibbonPanel>> _getPanels;

        readonly Dictionary<string, RibbonPanel> _panels = new Dictionary<string, RibbonPanel>();
        readonly Dictionary<string, PushButton> _buttons = new Dictionary<string, PushButton>();
        readonly Dictionary<string, int> _slotOf = new Dictionary<string, int>();
        internal static readonly string[] SlotScripts = new string[MaxButtons];

        public RibbonManager(string tab, string appDir,
                             Func<string, string, RibbonPanel> createPanel,
                             Func<string, IList<RibbonPanel>> getPanels,
                             Action<string> createTab)
        {
            _tab = tab;
            _appDir = appDir;
            _assembly = Assembly.GetExecutingAssembly().Location;
            _createPanel = createPanel;
            _getPanels = getPanels;
            try { createTab(tab); } catch (Autodesk.Revit.Exceptions.ArgumentException) { /* tab exists */ }
        }

        public void Rebind(Func<string, string, RibbonPanel> createPanel, Func<string, IList<RibbonPanel>> getPanels)
        {
            _createPanel = createPanel;
            _getPanels = getPanels;
        }

        public void CreateAccountPanel()
        {
            var panel = Panel("Account", "Account");
            AddButton(panel, "SignIn", "Sign\nIn", typeof(SignInCommand).FullName,
                      "Sign in, or sign up with your email address, to use the " + _tab + " buttons.",
                      Icon("signin"), null);
            AddButton(panel, "Account", "Account", typeof(AccountCommand).FullName,
                      "Your " + _tab + " account: access status, check for approval and updates, or sign out.",
                      Icon("account"), null);
        }

        /// <summary>Show exactly the panels and buttons listed in the JSON from the engine.</summary>
        public void Sync(string json)
        {
            var wanted = new HashSet<string>();
            var wantedPanels = new HashSet<string>();
            using (var doc = JsonDocument.Parse(string.IsNullOrEmpty(json) ? "[]" : json))
            {
                foreach (var p in doc.RootElement.EnumerateArray())
                {
                    var name = p.GetProperty("panel").GetString();
                    var panel = Panel(name, Str(p, "title") ?? name);
                    wantedPanels.Add(name);
                    foreach (var b in p.GetProperty("buttons").EnumerateArray())
                    {
                        var key = b.GetProperty("key").GetString();
                        var script = b.GetProperty("script").GetString();
                        if (!_slotOf.TryGetValue(key, out var slot))
                        {
                            slot = _slotOf.Count;
                            if (slot >= MaxButtons) continue;
                            _slotOf[key] = slot;
                        }
                        SlotScripts[slot] = script;
                        var title = Str(b, "title") ?? key;
                        var tooltip = Str(b, "tooltip") ?? "";
                        var icon = Str(b, "icon");
                        if (_buttons.TryGetValue(key, out var existing))
                        {
                            existing.ItemText = title;
                            existing.ToolTip = tooltip;
                            SetImages(existing, icon);
                            existing.Visible = true;
                            existing.Enabled = true;
                        }
                        else
                        {
                            var btn = AddButton(panel, "b" + slot, title, "MyTools.Revit.Slot" + slot.ToString("000"), tooltip, icon, key);
                            if (btn != null) _buttons[key] = btn;
                        }
                        wanted.Add(key);
                    }
                }
            }
            foreach (var kv in _buttons)
                if (!wanted.Contains(kv.Key)) { kv.Value.Visible = false; kv.Value.Enabled = false; }
            foreach (var kv in _panels)
                if (kv.Key != "Account") kv.Value.Visible = wantedPanels.Contains(kv.Key);
            foreach (var kv in _slotOf)
                if (!wanted.Contains(kv.Key)) SlotScripts[kv.Value] = null;
        }

        RibbonPanel Panel(string name, string title)
        {
            if (_panels.TryGetValue(name, out var p)) { p.Title = title; p.Visible = true; return p; }
            p = _getPanels(_tab).FirstOrDefault(x => x.Name == name) ?? _createPanel(_tab, name);
            p.Title = title;
            p.Visible = true;
            _panels[name] = p;
            return p;
        }

        PushButton AddButton(RibbonPanel panel, string name, string text, string className, string tooltip, string icon, string key)
        {
            var data = new PushButtonData(name, text, _assembly, className) { ToolTip = tooltip };
            var btn = panel.AddItem(data) as PushButton;
            if (btn != null) SetImages(btn, icon);
            return btn;
        }

        static void SetImages(PushButton btn, string icon)
        {
            if (string.IsNullOrEmpty(icon)) return;
            var path = DarkVariant(icon);
            if (!File.Exists(path)) return;
            btn.LargeImage = Load(path, 32);
            btn.Image = Load(path, 16);
        }

        static string DarkVariant(string icon)
        {
            try
            {
                if (UIThemeManager.CurrentTheme == UITheme.Dark)
                {
                    var dark = Path.Combine(Path.GetDirectoryName(icon), Path.GetFileNameWithoutExtension(icon) + ".dark.png");
                    if (File.Exists(dark)) return dark;
                }
            }
            catch { }
            return icon;
        }

        static BitmapImage Load(string path, int size)
        {
            var img = new BitmapImage();
            img.BeginInit();
            img.CacheOption = BitmapCacheOption.OnLoad;   // don't lock the file: toolbar files can be removed
            img.DecodePixelWidth = size;
            img.UriSource = new Uri(path);
            img.EndInit();
            img.Freeze();
            return img;
        }

        string Icon(string name) => Path.Combine(_appDir, "icons", name + ".png");

        static string Str(JsonElement e, string prop) =>
            e.TryGetProperty(prop, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
    }
}
