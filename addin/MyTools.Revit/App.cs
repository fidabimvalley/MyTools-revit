using System;
using System.Collections.Concurrent;
using System.IO;
using System.Reflection;
using System.Runtime.Loader;
using Autodesk.Revit.UI;

namespace MyTools.Revit
{
    /// <summary>
    /// Revit add-in entry point. Creates the MyTools tab with the Account panel, starts the Python engine,
    /// checks access quietly and shows the protected panels the signed-in user may use.
    /// </summary>
    public class App : IExternalApplication, IHost
    {
        internal static App Instance;
        internal IEngine Engine;
        internal RibbonManager Ribbon;
        internal string AppDir;
        internal string ExtRoot;
        internal string StartupError;

        readonly ConcurrentQueue<Action> _posted = new ConcurrentQueue<Action>();
        ExternalEvent _event;

        public string ToolName { get; private set; } = "MyTools";

        public Result OnStartup(UIControlledApplication app)
        {
            Instance = this;
            AppDir = Path.GetDirectoryName(Assembly.GetExecutingAssembly().Location);
            var dataDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "MyTools");
            ExtRoot = Path.Combine(dataDir, "MyTools.extension");
            ToolName = ReadToolName(Path.Combine(ExtRoot, "vault.json")) ?? "MyTools";

            Ribbon = new RibbonManager(ToolName, AppDir,
                (tab, panel) => app.CreateRibbonPanel(tab, panel),
                tab => app.GetRibbonPanels(tab),
                tab => app.CreateRibbonTab(tab));
            Ribbon.CreateAccountPanel();

            _event = ExternalEvent.Create(new PostedActionHandler(_posted));

            try
            {
                Engine = EngineLoader.Load(AppDir);
                Engine.Initialize(AppDir, ExtRoot, this);
                Engine.Startup();
                Ribbon.Sync(Engine.RibbonJson());
            }
            catch (Exception ex)
            {
                // Never stop Revit from starting. The Account button reports the problem.
                StartupError = ex.ToString();
            }
            return Result.Succeeded;
        }

        public Result OnShutdown(UIControlledApplication app) => Result.Succeeded;

        // ---- IHost (called from Python, always inside a command, so the API context is valid)
        public void RefreshRibbon()
        {
            var uiapp = CommandContext.Current;
            if (uiapp == null || Engine == null) return;
            Ribbon.Rebind((tab, panel) => uiapp.CreateRibbonPanel(tab, panel), tab => uiapp.GetRibbonPanels(tab));
            Ribbon.Sync(Engine.RibbonJson());
        }

        public void Post(Action action)
        {
            _posted.Enqueue(action);
            _event.Raise();
        }

        static string ReadToolName(string vaultJson)
        {
            try
            {
                if (!File.Exists(vaultJson)) return null;
                using var doc = System.Text.Json.JsonDocument.Parse(File.ReadAllText(vaultJson));
                return doc.RootElement.TryGetProperty("toolName", out var n) ? n.GetString() : null;
            }
            catch { return null; }
        }
    }

    /// <summary>The UIApplication of the command that is running right now (for ribbon updates from Python).</summary>
    internal static class CommandContext
    {
        [ThreadStatic] internal static UIApplication Current;
    }

    /// <summary>Runs actions queued by Python windows (e.g. "select these elements") in a valid API context.</summary>
    internal class PostedActionHandler : IExternalEventHandler
    {
        readonly ConcurrentQueue<Action> _queue;
        public PostedActionHandler(ConcurrentQueue<Action> queue) { _queue = queue; }

        public void Execute(UIApplication app)
        {
            CommandContext.Current = app;
            try
            {
                while (_queue.TryDequeue(out var action))
                {
                    try { action(); }
                    catch (Exception ex) { TaskDialog.Show("MyTools", ex.Message); }
                }
            }
            finally { CommandContext.Current = null; }
        }

        public string GetName() => "MyTools posted action";
    }

    /// <summary>
    /// Loads MyTools.Engine and its Python runtime into a private AssemblyLoadContext, so they can't clash
    /// with other add-ins (e.g. Dynamo's own Python). Revit and .NET assemblies still come from Revit.
    /// </summary>
    internal static class EngineLoader
    {
        class EngineContext : AssemblyLoadContext
        {
            readonly string _dir;
            public EngineContext(string dir) : base("MyTools.Engine", isCollectible: false) { _dir = dir; }

            protected override Assembly Load(AssemblyName name)
            {
                // Share the contracts with the add-in, whichever load context Revit put the add-in in.
                if (name.Name == "MyTools.Revit") return typeof(IEngine).Assembly;
                var path = Path.Combine(_dir, name.Name + ".dll");
                return File.Exists(path) ? LoadFromAssemblyPath(path) : null; // null = use Revit's copy
            }
        }

        public static IEngine Load(string appDir)
        {
            var engineDir = Path.Combine(appDir, "engine");
            var ctx = new EngineContext(engineDir);
            var asm = ctx.LoadFromAssemblyPath(Path.Combine(engineDir, "MyTools.Engine.dll"));
            var type = asm.GetType("MyTools.Engine.PythonEngine", throwOnError: true);
            return (IEngine)Activator.CreateInstance(type);
        }
    }
}
