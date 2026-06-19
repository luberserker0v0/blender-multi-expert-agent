# ADR 0005: Conda And Pip Python Environment

## Status

Accepted for now.

## Context

The project currently uses a standard Python package layout with:

- `pyproject.toml` and `setuptools` for package metadata
- `environment.yml` for local conda environment creation
- `requirements.txt` for pip-installed Python dependencies
- GitHub Actions using `setup-python` and `pip install -r requirements.txt`

The repository also references `uv` in Blender MCP command examples, but that is
for launching an external Blender MCP server. It is not the dependency manager
for this repository.

## Decision

Keep the project on conda + pip for Python environment management.

Developers should use:

```powershell
conda env create -f environment.yml
conda activate ai3d-stage2
make install
```

CI should continue to use standard Python + pip unless the project deliberately
migrates to another environment manager later.

## Rationale

- The local development workflow already assumes a conda environment named
  `ai3d-stage2`.
- Blender, MCP, YOLO, and native-tooling dependencies can require practical
  control over Python version and native build tools.
- The current CI path is simple and portable with pip.
- Avoiding a second Python dependency manager keeps local setup and docs easier
  to reason about.
- `uv` remains valid as an external command for Blender MCP, but that use does
  not imply repo-level dependency management.

## Consequences

- Do not add `uv.lock` or make `uv sync` part of the active setup flow without a
  deliberate migration decision.
- README, Makefile, CI, local scripts, and developer docs should continue to
  describe conda + pip as the active setup path.
- If the project later migrates to uv, this ADR should be superseded with a new
  decision that updates all setup, CI, and release commands together.
