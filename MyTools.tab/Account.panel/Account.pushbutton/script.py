# -*- coding: utf-8 -*-
"""Your MyTools account: access status, check for approval and updates, or sign out."""
__title__ = "Account"
__author__ = "MyTools"
from mytools_vault import core, ui
ui.account(core.load_config(core.find_extension_root(__file__)))
