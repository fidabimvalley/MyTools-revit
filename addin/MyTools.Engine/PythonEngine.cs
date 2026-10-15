using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Runtime.Loader;
using IronPython.Hosting;
using Microsoft.Scripting.Hosting;
using MyTools.Revit;

namespace MyTools.Engine
{
    /// <summary>Hosts IronPython 3.4 and forwards add-in calls to python/mytools_host.py.</summary>
    public class PythonEngine : IEngine
    {
        ScriptEngine _engine;
        ScriptScope _host;

        /// <summary>Assemblies a button asks for by name (clr.AddReference) come from the engine folder first.</summary>
        static IDisposable EngineScope() =>
            AssemblyLoadContext.GetLoadContext(typeof(PythonEngine).Assembly)?.EnterContextualReflection()
            ?? new NoScope();

        sealed class NoScope : IDisposable { public void Dispose() { } }

        public void Initialize(string appDir, string extRoot, IHost host)
        {
            using var scope = EngineScope();
            var options = new Dictionary<string, object> { ["Frames"] = true, ["FullFrames"] = true };
            _engine = Python.CreateEngine(options);

            var engineDir = Path.GetDirectoryName(typeof(PythonEngine).Assembly.Location);
            var paths = _engine.GetSearchPaths().ToList();
            paths.Add(Path.Combine(appDir, "python"));
            foreach (var lib in new[] { "lib", "Lib" })
            {
                var p = Path.Combine(engineDir, lib);
                if (Directory.Exists(p) && !paths.Contains(p)) paths.Add(p);
            }
            _engine.SetSearchPaths(paths);

            _engine.Runtime.LoadAssembly(typeof(PythonEngine).Assembly);
            _engine.Runtime.LoadAssembly(typeof(System.Windows.Forms.Form).Assembly);
            _engine.Runtime.LoadAssembly(typeof(System.Drawing.Color).Assembly);
            _engine.Runtime.LoadAssembly(typeof(System.Drawing.Font).Assembly);
            try { LoadRevit(); } catch (Exception) { /* outside Revit (tests) */ }

            _host = _engine.ImportModule("mytools_host");
            _host.SetVariable("HOST", host);
            Call("init", appDir, extRoot);
        }

        [MethodImpl(MethodImplOptions.NoInlining)]
        void LoadRevit()
        {
            _engine.Runtime.LoadAssembly(typeof(Autodesk.Revit.DB.Document).Assembly);
            _engine.Runtime.LoadAssembly(typeof(Autodesk.Revit.UI.UIApplication).Assembly);
        }

        object Call(string name, params object[] args)
        {
            var fn = _host.GetVariable(name);
            using var scope = EngineScope();
            try { return _engine.Operations.Invoke(fn, args); }
            catch (Exception ex) when (!(ex is OperationCanceledException))
            {
                var detail = _engine.GetService<ExceptionOperations>().FormatException(ex);
                throw new InvalidOperationException(detail, ex);
            }
        }

        public string Startup() => Call("startup") as string;
        public string RibbonJson() => Call("ribbon_json") as string;
        public void RunButton(string scriptPath, bool shiftClick, Autodesk.Revit.UI.UIApplication uiapp) => Call("run_button", scriptPath, shiftClick, uiapp);
        public void RunAccount(string action, Autodesk.Revit.UI.UIApplication uiapp) => Call("run_account", action, uiapp);

        /// <summary>For automated tests: run a Python file with the add-in's search paths. Returns the exit code.</summary>
        public int RunFile(string path, string[] argv)
        {
            var sys = _engine.GetSysModule();
            var list = new IronPython.Runtime.PythonList();
            list.append(path);
            foreach (var a in argv) list.append(a);
            sys.SetVariable("argv", list);
            try
            {
                var scope = _engine.CreateScope();
                scope.SetVariable("__name__", "__main__");
                scope.SetVariable("__file__", path);
                _engine.CreateScriptSourceFromFile(path).Execute(scope);
                return 0;
            }
            catch (IronPython.Runtime.Exceptions.SystemExitException ex)
            {
                return ex.GetExitCode(out _);
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine(_engine.GetService<ExceptionOperations>().FormatException(ex));
                return 1;
            }
        }
    }
}
