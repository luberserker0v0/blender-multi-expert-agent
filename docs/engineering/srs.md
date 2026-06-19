# Software Requirements Specification

## 1. Purpose

This document defines the current functional scope and engineering direction for the AI 3D Modeling Agent.

## 2. Product Goal

The system should help an Agent build and iteratively refine 3D models inside Blender through a closed modeling loop.

## 3. Current Users

- developers building the Agent
- developers integrating Blender and MCP workflows
- future end users interacting with the Agent through a session-oriented interface

## 4. Current Scope

The current project scope includes:

- a runnable MVP loop
- session-oriented execution
- structured gap report generation
- rule-based decision
- optional endpoint-backed LLM decision
- live Blender execution through MCP
- task object cleanup before modeling iterations

## 5. Functional Requirements

### FR-1 Task Loading

The system shall load a target checklist for the current task.

### FR-2 Task Object Table

The system shall derive a task-scoped object table from the task definition.

### FR-3 Scene Cleanup

The system shall remove scene objects that are not part of the current task object table before modeling iterations.

### FR-4 Blender Context Read

The system shall read current Blender context before each decision step.

### FR-5 Perception Interface

The system shall provide a perception abstraction that can be backed by mock or future YOLO implementations.

### FR-6 Gap Report

The system shall build a structured gap report from Blender context and perception output.

### FR-7 Decision Engine

The system shall choose the next modeling action using a decision engine.

### FR-8 Action Execution

The system shall execute selected actions against either a simulated Blender backend or a live Blender MCP backend.

### FR-9 Session Progress

The system shall persist per-session progress and runtime metadata.

### FR-10 Streaming Output

The system shall stream progress messages to the user during execution.

## 6. Non-Functional Requirements

### NFR-1 Modularity

The system should keep Blender execution, perception, decision, and persistence loosely coupled.

### NFR-2 Replaceability

The system should allow backends to be swapped without rewriting the main loop.

### NFR-3 Debuggability

The system should persist enough state to inspect failures after a run.

### NFR-4 Incremental Growth

The system should evolve from MVP to fuller capability without large structural rewrites.

## 7. Current Constraints

- current MVP task is limited to `build an apple`
- live Blender control currently depends on the installed Blender MCP server
- perception is not yet driven by a real YOLO runtime inside the main loop
- recovery logic is not yet complete

## 8. Out Of Scope For Current MVP

- full topology editing automation
- automatic task recovery after process interruption
- multi-object complex modeling plans
- production-grade GUI
- full server-side state recovery across MCP reconnects
