# Archived Reference

This document is historical. It may describe removed runtime paths and must not
be used as active implementation guidance.

# Product Overview

## Summary

This project is an AI-driven 3D modeling agent for Blender.

The current implementation focus is a closed loop:

1. read current Blender state
2. observe scene state through perception
3. build a structured gap report
4. choose the next action
5. execute the action
6. repeat until the target state is reached or the run stops

## Current Status

The project currently has:

- a simulated MVP loop that runs end to end
- an endpoint-backed LLM decision experiment
- a Blender MCP-backed live execution path
- session progress persistence
- streaming console output
- scene cleanup based on a task-scoped object table

## Current MVP Scope

The MVP is intentionally narrow:

- single task flow: `build an apple`
- one primary target object: `apple_body`
- rule-based decision is still the default
- perception is still mock-driven for the main loop
- live Blender execution is available through MCP

## Key Terms

- `Gap Report`
  Structured state describing the current modeling mismatch.
- `Decision Engine`
  Module that decides the next action. It may be rule-based, LLM-based, or hybrid.
- `BlenderMcpAdapter`
  Agent-side adapter that translates Agent operations into Blender MCP tool calls.
- `Task Object Table`
  Structured list of objects required by the current task, including role and cleanup policy.
