# -*- coding: utf-8 -*-
# Runs when pyRevit loads: checks MyTools access and keeps the protected panels in step with it.
import os
try:
    from mytools_vault import ui
    ui.startup(os.path.dirname(os.path.abspath(__file__)))
except Exception as _err:  # never stop Revit or pyRevit from starting
    print("MyTools start-up check skipped: %s" % _err)
