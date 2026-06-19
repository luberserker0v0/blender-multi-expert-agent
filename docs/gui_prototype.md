# GUI Prototype

## Purpose

This document explains how to start and use the older local `tkinter` GUI prototype for the multi-stage modeling workflow.

This document is kept for reference and fallback use. The primary UI direction is now the React workspace described in [react_ui.md](</D:/program/Projects/Blender 3DModel Agent/repo/docs/react_ui.md>).

The current `tkinter` GUI is intended for:

- local workflow validation
- progress-schema inspection
- capture-history browsing
- early UX iteration before a fuller GUI architecture is chosen

It is not intended to be the long-term production UI.

The current layout direction is intentionally closer to a desktop chat-style tool:

- a large central activity pane
- a compact prompt area
- a collapsible settings sidebar
- secondary tabs for progress, history, and captures

## Entry Point

Start the GUI from `repo/`:

```powershell
python scripts/run_gui.py
```

The current GUI script is:

- `scripts/run_gui.py`

The helper logic used by that GUI is:

- `src/ai_3d_modeling_agent/gui/prototype.py`

## Required Setup

Before launching the GUI:

1. activate the project environment
2. make sure the LLM endpoint you want to use is already running
3. if you want live Blender execution, make sure Blender MCP is available
4. if you want final YOLO validation, prepare a local YOLO model path

Example environment setup:

```powershell
conda activate ai3d
```

Example LLM endpoint:

```powershell
llama-server -m D:\models\your-model.gguf --host 127.0.0.1 --port 8080
```

## Startup Flow

After the GUI window opens, the intended flow is:

1. enter the task text
2. use `New Session` when you want a fresh session id
3. enter the LLM endpoint URL
4. optionally adjust the LLM model name
5. optionally add one or more reference text lines
6. optionally add one or more reference images
7. optionally enable Blender MCP
8. optionally enable YOLO validation and choose a YOLO model file with `Browse...`
9. click `Start`

The GUI then:

1. builds a `multi-stage` CLI command
2. launches the multi-expert pipeline command helper
3. watches the session progress JSON under `data/runtime/sessions/`
4. updates the visible status, stage, captures, and history panes

## Current UI Areas

### Run Settings

The current settings are split between a compact prompt area and a collapsible settings sidebar.

The prompt area lets you configure:

- task
- reference text
- reference images

The settings sidebar lets you configure:

- auto-generated session id
- `New Session` button
- LLM endpoint URL
- LLM model
- max part refinement rounds
- max assembly rounds
- Blender MCP toggle
- YOLO validation toggle
- YOLO model path with file picker
- YOLO viewpoints
- reference text
- reference images

The sidebar also includes:

- `Save Settings`

The current saved settings are:

- LLM endpoint URL
- LLM model
- max part refinement rounds
- max assembly rounds
- Blender MCP toggle
- YOLO validation toggle
- YOLO model path
- YOLO viewpoints

The current GUI intentionally does not treat these as per-task chat content. Task text, references, and session id remain run-specific.

The sidebar can be toggled with:

- `Show Settings`
- `Hide Settings`

## Saved Settings Behavior

When you click `Save Settings`, the GUI writes the current saved settings to:

- `data/runtime/gui/saved_settings.json`

When the GUI starts, it automatically loads that file if it exists.

This allows you to keep stable environment settings without having to re-enter them every time.

## Desktop-Style Layout

The current GUI layout is divided into:

### Toolbar

- application title
- current session id
- `New Session`
- `Start`
- `Stop`
- settings toggle
- current status

### Prompt Area

- a single large task input
- reference image attach button
- reference image summary
- reference text box

### Activity Pane

- large central scrolling pane
- records the submitted task
- records stage/status changes
- records LLM feedback updates
- gives the UI a chat-like working surface

### Lower Tabs

- `Progress`
- `History`
- `Captures`

### Progress

This area shows:

- overall status
- current stage
- active task
- completed task ids
- detected parts from final validation
- latest capture path
- final capture path
- stop reason
- latest feedback

### History And Captures

This area shows:

- the full `part_tasks` list
- the full round history for the selected part task
- the full assembly round history
- an inspector-style history detail pane
- capture previews when supported by Tk image loading

## Inspector Detail Behavior

When you select a part round or assembly round, the detail pane is updated with grouped sections such as:

- round summary
- Blender context
- requested action
- requested action parameters

This is driven by the multi-stage progress schema rather than by ad hoc UI state.

## Data Source

The GUI does not talk directly to Blender or the LLM endpoint.

Instead, it relies on:

- command construction for `scripts/run_pipeline.py`
- the session progress file written under `data/runtime/sessions/`

This keeps the GUI decoupled from the orchestration core.

## Current Limitations

- the GUI currently targets the `multi-stage` workflow only
- `Stop` terminates the spawned CLI process only
- image preview currently depends on Tk-compatible image formats such as PNG
- the GUI currently polls the progress file rather than subscribing to events
- there is not yet a resume-single-task or replay-single-round action

## Related Documents

- `README.md`
- `docs/session_and_progress.md`
- `docs/runtime_loop.md`
- `docs/react_ui.md`
