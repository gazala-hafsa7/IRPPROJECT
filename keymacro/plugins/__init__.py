"""
keymacro/plugins/__init__.py
"""
from keymacro.plugins.base import BasePlugin, PluginActionSpec
from keymacro.plugins.manager import PluginManager

__all__ = ["BasePlugin", "PluginActionSpec", "PluginManager"]
