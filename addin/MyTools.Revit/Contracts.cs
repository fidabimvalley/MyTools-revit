using System;
using Autodesk.Revit.UI;

namespace MyTools.Revit
{
    /// <summary>What the Python engine (in its own load context) offers the add-in.</summary>
    public interface IEngine
    {
        void Initialize(string appDir, string extRoot, IHost host);
        /// <summary>Quiet access check and toolbar sync at Revit start. Returns a short status word.</summary>
        string Startup();
        /// <summary>The protected panels and buttons on this PC, as JSON.</summary>
        string RibbonJson();
        void RunButton(string scriptPath, bool shiftClick, UIApplication uiapp);
        void RunAccount(string action, UIApplication uiapp);
    }

    /// <summary>What the add-in offers Python.</summary>
    public interface IHost
    {
        /// <summary>Rebuild the protected panels from what is on disk (after sign-in, sync or removal).</summary>
        void RefreshRibbon();
        /// <summary>Run an action later inside a valid Revit API context (e.g. from a modeless window).</summary>
        void Post(Action action);
        string ToolName { get; }
    }
}
