# -*- coding: utf-8 -*-
"""Sign in, or sign up with your email address, to use the MyTools buttons."""
__title__ = "Sign\nIn"
__author__ = "MyTools"
from mytools_vault import core, ui
ui.sign_in(core.load_config(core.find_extension_root(__file__)))
