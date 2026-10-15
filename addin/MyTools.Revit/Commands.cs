using System;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace MyTools.Revit
{
    /// <summary>Base for every MyTools button. Revit needs a class per button, so buttons use numbered slots.</summary>
    [Transaction(TransactionMode.Manual)]
    [Regeneration(RegenerationOption.Manual)]
    public abstract class MyToolsCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData data, ref string message, ElementSet elements)
        {
            var app = App.Instance;
            CommandContext.Current = data.Application;
            try
            {
                if (app?.Engine == null)
                {
                    TaskDialog.Show(app?.ToolName ?? "MyTools",
                        "MyTools couldn't start its Python engine.\n\n" + (app?.StartupError ?? "Unknown error."));
                    return Result.Failed;
                }
                Run(app, data.Application);
                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                var td = new TaskDialog(app?.ToolName ?? "MyTools")
                {
                    MainInstruction = "Something went wrong.",
                    MainContent = ex.Message,
                    ExpandedContent = ex.ToString()
                };
                td.Show();
                return Result.Failed;
            }
            finally { CommandContext.Current = null; }
        }

        protected abstract void Run(App app, UIApplication uiapp);

        protected static bool ShiftDown()
        {
            return (System.Windows.Forms.Control.ModifierKeys & System.Windows.Forms.Keys.Shift) != 0;
        }
    }

    public class SignInCommand : MyToolsCommand
    {
        protected override void Run(App app, UIApplication uiapp) => app.Engine.RunAccount("signin", uiapp);
    }

    public class AccountCommand : MyToolsCommand
    {
        protected override void Run(App app, UIApplication uiapp) => app.Engine.RunAccount("account", uiapp);
    }

    /// <summary>A protected button: runs whatever script is currently mapped to its slot.</summary>
    public abstract class SlotCommand : MyToolsCommand
    {
        protected abstract int Slot { get; }

        protected override void Run(App app, UIApplication uiapp)
        {
            var script = RibbonManager.SlotScripts[Slot];
            if (string.IsNullOrEmpty(script))
            {
                TaskDialog.Show(app.ToolName, "This button isn't available any more. Click Account → Check again.");
                return;
            }
            app.Engine.RunButton(script, ShiftDown(), uiapp);
        }
    }
}
