"""
keymacro/plugins/builtin/browser.py
───────────────────────────────────
Web Browser plugin — launches URLs, searches web, and handles tabs.
Supports Chrome, Edge, Firefox, Brave, Opera, etc.
"""

from __future__ import annotations

import os
import urllib.parse
import webbrowser
from typing import Any

from keymacro.plugins.base import BasePlugin, PluginActionSpec


class BrowserPlugin(BasePlugin):
    plugin_id = "browser"
    name = "Web Browser"
    description = "Open URLs, search the web, and control browser tabs."
    target_apps = ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"]

    def get_actions(self) -> dict[str, PluginActionSpec]:
        return {
            "open_url": PluginActionSpec(
                action_id="open_url",
                name="Open URL",
                description="Open a webpage in the default browser.",
                params_schema={"url": "Web address (e.g. https://google.com)"},
                example="plugin: browser.open_url url=https://github.com",
            ),
            "search": PluginActionSpec(
                action_id="search",
                name="Web Search",
                description="Search using Google, Bing, YouTube, or DuckDuckGo.",
                params_schema={
                    "query": "Search keywords",
                    "engine": "Search engine: google, bing, youtube, duckduckgo (default: google)",
                },
                example='plugin: browser.search query="python macros" engine=google',
            ),
            "new_tab": PluginActionSpec(
                action_id="new_tab",
                name="New Tab",
                description="Open a new browser tab or URL.",
                params_schema={"url": "Optional URL to open"},
                example="plugin: browser.new_tab url=https://news.ycombinator.com",
            ),
        }

    def execute(self, action_id: str, params: dict[str, Any]) -> Any:
        if action_id == "open_url":
            url = params.get("url") or params.get("arg", "https://google.com")
            if not url.startswith(("http://", "https://")):
                url = f"https://{url}"
            webbrowser.open(url)
            return f"Opened URL: {url}"

        if action_id == "search":
            query = params.get("query") or params.get("arg", "")
            engine = str(params.get("engine", "google")).lower()
            q_enc = urllib.parse.quote_plus(query)

            engines = {
                "google": f"https://www.google.com/search?q={q_enc}",
                "bing": f"https://www.bing.com/search?q={q_enc}",
                "youtube": f"https://www.youtube.com/results?search_query={q_enc}",
                "duckduckgo": f"https://duckduckgo.com/?q={q_enc}",
            }
            url = engines.get(engine, engines["google"])
            webbrowser.open(url)
            return f"Searched {engine} for: {query}"

        if action_id == "new_tab":
            url = params.get("url", "")
            if url:
                if not url.startswith(("http://", "https://")):
                    url = f"https://{url}"
                webbrowser.open_new_tab(url)
            else:
                webbrowser.open_new_tab("about:blank")
            return "Opened new browser tab"

        raise ValueError(f"Unknown browser action: '{action_id}'")
