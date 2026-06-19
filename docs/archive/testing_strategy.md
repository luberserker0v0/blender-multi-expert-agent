# Archived Reference

This document is historical. It may describe removed runtime paths and must not
be used as active implementation guidance.

# Testing Strategy

## Current Layers

The project currently uses three lightweight testing layers:

- unit tests
  for isolated logic, adapters, and client wrappers
- end-to-end MVP tests
  for the simulated loop
- live smoke tests
  for real Blender MCP validation

## Current Automated Test Focus

- MCP client behavior
- Blender MCP adapter mapping
- YOLO perception output parsing
- task object table generation
- session progress persistence
- CLI argument handling
- simulated MVP loop behavior

## Current Manual / Smoke Test Focus

- live Blender MCP connectivity
- live object creation and scaling
- live scene cleanup
- live screenshot capture
- future live capture plus YOLO inference validation

## Current Test Entry Points

- automated:
  `python -m unittest ...`
- live Blender smoke:
  `python scripts/smoke_test_blender_mcp_adapter.py`
- live MVP:
  `python scripts/run_pipeline.py --use-blender-mcp ...`
