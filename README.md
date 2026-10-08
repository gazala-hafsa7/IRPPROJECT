# ⌨️ KeyMacro — Custom Keyboard Macro & App Automation Suite

> A Windows desktop application that lets you record, build, and replay powerful custom keyboard/mouse macros, automate application workflows, and extend automation through a modular plug-in system.

---

## 📖 Overview

**KeyMacro** is an open-source Windows automation desktop app that bridges the gap between simple keyboard shortcuts and complex workflow automation. Whether you want to replay a recorded input sequence, build macros using a concise scripting syntax, trigger actions with global hotkeys, or automate repetitive tasks like writing timestamps into log spreadsheets — KeyMacro handles it through an intuitive dark-themed GUI.

Built as a personal productivity tool (**IRP Project**), it is designed around extensibility: every feature is a composable module, and the plug-in system lets you connect any installed application as an automation target.

---

## ✨ Core Features

### 🎹 Macro Recording & Replay
- **Live Recording**: Capture keyboard and mouse events (keypresses, mouse clicks, mouse path, scroll, drag) into replayable macros with a single click.
- **Replay Engine**: Replay recorded macros faithfully with all original delays, or strip delays for instant playback.
- **Global Hotkeys**: Assign system-wide hotkeys (e.g. `Ctrl+Shift+F5`) to any macro — triggers work even when the app is minimized.
- **Target App Filtering**: Optionally restrict a macro to only fire when a specific application (e.g. `chrome.exe`, `notepad.exe`) is in focus.

### 📝 Sequence Script Builder
- **Text-based Sequence Editor**: Write macros in a concise, human-readable scripting syntax — one action per line:
  ```
  combo: ctrl+c
  wait: 300ms
  type: Hello, World!
  click: 500, 300
  launch: notepad.exe
  plugin: browser.open_url url=https://example.com
  plugin: custom.sheet_login target="C:\Work\Log.xlsx"
  ```
- **Live Action Preview**: Real-time parse validation and structured action preview as you type.
- **Quick Insert Toolbar**: One-click helpers to insert shortcuts, text, clicks, app launches, plugin actions, URL pastes, custom tasks, and delays.
- **Dry Run**: Simulate macros with full output logging — no actual input is sent.

### 🔌 Modular Plug-in System
- **Built-in Plugins**:
  - 🌐 **Browser** — Open URLs, search Google/Bing/YouTube/DuckDuckGo, open new tabs
  - 🖥️ **System** — Volume control, lock screen, take screenshots, open Settings/Task Manager
  - 🎵 **Media** — Play/pause, next/previous track, mute
  - 📝 **Notepad** — Open, type text, save files
  - ✨ **Custom Tasks** — Open spreadsheets & type timestamps, append log files, run scripts
- **User Plugins**: Drop `.py` plugin files into `%APPDATA%\KeyMacro\plugins\` for automatic loading.
- **Plugin Hub**: Browse all installed plugins, inspect actions, test execution, connect apps, and reload.

### ✨ Custom Plug-in Action Builder *(New)*
- **Visual Task Builder GUI**: Point-and-click interface to create custom automation tasks without writing code.
- **Sheet Log-in Automation**: Open any Excel/CSV sheet or Google Sheet URL and auto-type the current timestamp (`{time}`, `{date}`, `{timestamp}`) into a log-in column.
- **Live Timestamp Preview**: See exactly what text will be typed before saving.
- **One-click Test**: Test the custom action immediately in the builder before adding it to a macro.
- **Persistent Custom Actions**: Saved actions appear system-wide across all macros and the plugin hub.

### 🚀 App Launcher & Plugin Hub
- **Instant App Search**: Fuzzy search and launch any installed Windows application.
- **Macro-to-App Linking**: Create and assign macros directly from the launcher with 1 click.
- **Plugin Management**: View all connected app plugins, test individual actions, connect new apps, and reload plugins.

### 🔗 URL Copy-Paste Support *(New)*
- **Right-click context menus** on every input field with Cut, Copy, Paste, Paste URL, Clear, and Select All.
- **📋 Paste / 📋 Paste URL buttons** next to URL parameters for immediate clipboard pasting.
- **Auto URL detection**: When a URL is on the clipboard and a URL-type field is focused, it is auto-filled and sanitized.
- **Quick toolbar action** (`🌐 + Paste URL`) instantly inserts a `plugin: browser.open_url` macro line.

### 🛡️ Safety Layer
- **Risk Level Classification**: Actions are classified as LOW / MEDIUM / HIGH risk.
- **Confirmation Prompts**: High-risk actions (file deletion, moves) require user confirmation before execution.
- **Path Blocklist**: Configurable blocklist of protected paths that macros are prevented from touching.

---

## 🏗️ Architecture & Project Structure

```
irpproject/
├── keymacro/
│   ├── main.py                    # Entry point — wires all modules & launches GUI
│   ├── gui/
│   │   ├── app.py                 # Main application window (dark-theme Tkinter)
│   │   ├── sequence_dialog.py     # Macro Sequence Script editor modal
│   │   ├── launcher_dialog.py     # App Launcher & Plugin Hub modal
│   │   ├── custom_action_dialog.py# ✨ Custom Plug-in Action Builder GUI
│   │   └── widget_helpers.py      # Clipboard, context menus, URL paste helpers
│   ├── recorder/
│   │   └── recorder.py            # Live keyboard & mouse event recorder (pynput)
│   ├── engine/
│   │   └── replay.py              # Macro replay engine (pyautogui)
│   ├── hotkey/
│   │   └── listener.py            # Global system-wide hotkey listener (pynput)
│   ├── models/
│   │   ├── action.py              # ActionType, Action, Macro, RiskLevel data models
│   │   └── sequence.py            # Sequence syntax parser & serializer
│   ├── plugins/
│   │   ├── base.py                # BasePlugin, AppPlugin, PluginActionSpec
│   │   ├── manager.py             # Plugin discovery, loading, and dispatch
│   │   └── builtin/
│   │       ├── browser.py         # Web Browser plugin
│   │       ├── system.py          # Windows System Controls plugin
│   │       ├── media.py           # Media Playback plugin
│   │       ├── notepad.py         # Notepad plugin
│   │       └── custom.py          # ✨ Custom Tasks & Automation plugin
│   ├── launcher/
│   │   └── app_scanner.py         # Installed app discovery (Start Menu, Registry)
│   ├── safety/
│   │   └── safety_layer.py        # Risk classification & confirmation prompts
│   └── storage/
│       └── macro_store.py         # JSON macro persistence (%APPDATA%\KeyMacro\)
├── tests/                         # Unit test suite (23 tests)
├── PLUGINS_GUIDE.md               # Plugin development guide
├── requirements.txt
└── README.md
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Language** | Python 3.11+ |
| **GUI Framework** | Tkinter (stdlib) — dark-themed, custom-styled |
| **Input Recording** | [pynput](https://pypi.org/project/pynput/) — keyboard & mouse listener |
| **Input Replay** | [pyautogui](https://pypi.org/project/pyautogui/) — cross-process keyboard/mouse automation |
| **Global Hotkeys** | pynput — background listener thread |
| **App Discovery** | Windows Registry (`winreg`) + Start Menu scanning |
| **Macro Storage** | JSON files in `%APPDATA%\KeyMacro\macros\` |
| **Plugin Storage** | JSON config + `.py` user plugin files in `%APPDATA%\KeyMacro\plugins\` |
| **Data Models** | Python `dataclasses` + `enum` (stdlib only, no external ORM) |
| **Concurrency** | Python `threading` — recorder & replay run in daemon threads |
| **OS** | Windows 10 / 11 |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- Windows 10 or 11

### Installation

```bash
# Clone the repository
git clone https://github.com/gazala-hafsa7/IRPPROJECT.git
cd IRPPROJECT

# Install dependencies
pip install -r requirements.txt

# Run the application
python -m keymacro.main
```

### Requirements

```
pynput>=1.7.6
pyautogui>=0.9.54
```

---

## 🎯 Usage Examples

### Record and Replay a Macro
1. Click **● Record** to begin capturing keyboard and mouse input.
2. Perform your actions.
3. Click **■ Stop** to end recording.
4. Click **▶ Run** to replay the macro.

### Build a Sequence Macro (e.g. Log-in Timestamp)
1. Click **➕ New Macro** → open the Sequence Builder.
2. Click **✨ + Custom Task** → build a sheet login task:
   - Set target: `C:\Work\Timesheet.xlsx`
   - Set text: `Log-in: {time}`
3. Save → assign a hotkey (e.g. `Ctrl+Shift+Q`).
4. Press the hotkey anytime — the sheet opens and your login timestamp is typed automatically.

### Write Sequence Script Directly
```
# Open browser and search
plugin: browser.open_url url=https://github.com
wait: 1s
combo: ctrl+t
plugin: browser.search query="python automation" engine=google

# Type timestamped login into active spreadsheet
plugin: custom.type_timestamp format="%H:%M:%S" prefix="Log-in: " suffix=enter

# System controls
plugin: system.volume_up steps=3
plugin: media.play_pause
```

### Create a Custom Plug-in Action
1. Open **🔌 App Plugins & Hub** → click **✨ + Custom Action**.
2. Fill in the Action Name, target file/URL, and text pattern.
3. Click **⚡ Test Action Now** to verify.
4. Click **💾 Save** — it's now available as `plugin: custom.<your_action_id>` across all macros.

---

## 🧪 Running Tests

```bash
python -m unittest discover -s tests
```

23 unit tests covering: sequence parsing, plugin loading, custom plugin actions, URL helpers, app context, and launcher.

---

## 📄 License

This project is developed as part of an Individual Research Project (IRP). See the repository for details.
