# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Initial project structure with GenericAgent classic executor
- OpenAI Agents routing and orchestration layer
- Runtime optimization modules (profiler, LLM cache, read shortcuts)
- Structured memory system with indexing and write gate
- Skill activation, discovery, and prompt injection system
- Answer quality context guard
- Tool schema selection system
- Streamlit frontend interface
- Architecture documentation and capability matrices
- Project infrastructure (pyproject.toml, ruff.toml, .env.template)
- Contributing guide (CONTRIBUTING.md)

### Fixed
- Thinking block preservation for DeepSeek v4 tool calls

### Security
- API key loading migrated to environment variables (see `.env.template`)

## [0.1.0] - 2026-05-01

### Added
- Initial commit: GenericAgent Workbench bootstrap
