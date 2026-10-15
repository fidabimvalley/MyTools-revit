using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using IronPython.Hosting;
using Microsoft.Scripting.Hosting;

/// <summary>SmokeTest.exe --path DIR [--path DIR ...] FILE.py [args...]  (exit code = the script's)</summary>
static class Program
{
    [STAThread]
    static int Main(string[] args)
    {
        var paths = new List<string>();
        int i = 0;
        while (i < args.Length && args[i] == "--path") { paths.Add(Path.GetFullPath(args[i + 1])); i += 2; }
        if (i >= args.Length) { Console.Error.WriteLine("usage: SmokeTest --path DIR FILE.py [args]"); return 2; }
        var file = Path.GetFullPath(args[i]);
        var rest = args.Skip(i + 1).ToArray();

        var engine = Python.CreateEngine(new Dictionary<string, object> { ["Frames"] = true, ["FullFrames"] = true });
        var search = engine.GetSearchPaths().ToList();
        search.Insert(0, Path.GetDirectoryName(file));
        foreach (var p in paths) search.Add(p);
        engine.SetSearchPaths(search);
        engine.Runtime.LoadAssembly(typeof(System.Windows.Forms.Form).Assembly);
        engine.Runtime.LoadAssembly(typeof(System.Drawing.Color).Assembly);
        engine.Runtime.LoadAssembly(typeof(System.Drawing.Font).Assembly);

        var sys = engine.GetSysModule();
        var argv = new IronPython.Runtime.PythonList();
        argv.append(file);
        foreach (var a in rest) argv.append(a);
        sys.SetVariable("argv", argv);
        Console.WriteLine("IronPython " + engine.LanguageVersion + " running " + file);
        try
        {
            // runpy runs the file as __main__, so `if __name__ == "__main__":` blocks run too.
            var scope = engine.CreateScope();
            scope.SetVariable("_target", file);
            engine.Execute("import runpy\nrunpy.run_path(_target, run_name='__main__')", scope);
            return 0;
        }
        catch (IronPython.Runtime.Exceptions.SystemExitException ex)
        {
            var code = ex.GetExitCode(out var other);
            if (other != null) Console.Error.WriteLine(other);
            return code;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(engine.GetService<ExceptionOperations>().FormatException(ex));
            return 1;
        }
    }
}
