# Test Design Document

## 1. Purpose

This document describes how the current codebase is tested and what each test layer is intended to prove.

## 2. Test Levels

### Unit Tests

Unit tests validate isolated components such as:

- MCP client wrapper
- Blender MCP adapter
- task loader
- session progress store
- CLI parsing and object construction

### End-To-End Tests

End-to-end tests validate the simulated MVP loop, including:

- object creation
- scaling actions
- gap report persistence
- task cleanup behavior
- session progress persistence

### Live Smoke Tests

Live smoke tests validate the real Blender path, including:

- MCP tool discovery
- live object creation
- live scaling
- live screenshot capture
- live task cleanup

## 3. Current Test Objectives

- prove the MVP loop still runs after architecture changes
- prove simulated and live Blender backends share the same operational contract
- prove new task object table behavior does not regress progress tracking
- prove CLI entry points remain usable

## 4. Current Gaps

- no automated assertion yet for live Blender screenshot content quality
- no automated assertion yet for live Blender scene restoration behavior
- no automated full integration yet for endpoint-backed decision plus live Blender in one run

## 5. Current Test Commands

Typical automated command:

```powershell
python scripts/run_all_tests.py
```

Typical live smoke commands:

```powershell
python scripts/smoke_test_blender_mcp_adapter.py
python scripts/run_pipeline.py --use-blender-mcp --task "build an apple"
```
