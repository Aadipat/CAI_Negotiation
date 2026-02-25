# AGENTS.md

## Recent Releases

### v0.1.1 (2026-01-14)
**Fixed case sensitivity issues for Linux/CI compatibility**

- Fixed three directories with uppercase names causing import failures on case-sensitive filesystems:
  - `BIU_agent` → `biu_agent` (9 files)
  - `Pinar_Agent` → `pinar_agent` (4 files)
  - `CSE3210` → `cse3210` (57 files)
- All tests now pass on both Python 3.13 and 3.14
- Successfully published to PyPI: https://pypi.org/project/negmas-geniusweb-bridge/
- GitHub Release: https://github.com/autoneg/negmas-geniusweb-bridge/releases/tag/v0.1.1

## Build/Test Commands
- Install: `uv sync`
- Run all tests: `python -m pytest`
- Run single test: `python -m pytest tests/test_negmas_wrapper.py::TestConversions::test_convert_ufun_to_geniusweb -v`
- Run test file: `python -m pytest tests/test_negmas_wrapper.py -v`
- Do not use uv run for running. activate the venv and use its python instead.

## Release Process
**IMPORTANT**: Do NOT create a GitHub release until AFTER everything is verified working:
1. Bump version in `pyproject.toml`
2. Update `uv.lock` with `uv lock`
3. Commit and push changes to `main`
4. Wait for GitHub Actions to pass (Test + Deploy Docs)
5. Create and push tag: `git tag vX.Y.Z && git push origin vX.Y.Z`
6. Wait for tag-triggered workflows to complete:
   - Verify PyPI publish succeeds
   - Verify GitHub Pages deployment succeeds
7. ONLY THEN create GitHub Release

This workflow allows deleting the tag and retrying without unnecessary version bumps if issues occur.

## Code Style
- **Python**: 3.13+, type hints required for function signatures
- **Imports**: Group as stdlib, third-party (geniusweb, negmas, numpy), local; use `from __future__ import annotations`
- **Formatting**: Double quotes for strings, 4-space indent
- **Types**: Use `TYPE_CHECKING` block for type-only imports; prefer `dict[str, Any]` over `Dict`
- **Naming**: snake_case for functions/variables, PascalCase for classes, UPPER_CASE for constants
- **Error handling**: Use `ValueError` with descriptive messages; check types explicitly before conversion
- **Optional imports**: Wrap in try/except with availability flag (e.g., `GENIUS_WEB_AVAILABLE`)
- **Docstrings**: Google-style with Args/Returns/Raises sections for public APIs
- **GeniusWeb agents**: Inherit from `DefaultParty`, implement `notifyChange()`, use `send_action()` or connection
- **Tests**: Use pytest fixtures, class-based test organization (`TestClassName`), descriptive method names
