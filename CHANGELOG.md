# Changelog

All notable changes to this project are documented in this file.

This project follows a Keep a Changelog-style format and Semantic Versioning principles where practical.

## [Unreleased]

### Added

- Multi-target discovery support via `BLOG_INDEX_PATHS` and `BLOG_SCRAPER_TARGETS_JSON`
- ACI dispatcher routes for run and status from Function App
- Downloader utility for recent bilingual post artifacts
- Published-date extraction and storage metadata support
- Architecture and lessons-learned documentation

### Changed

- ACI runner option parsing to avoid JSON env comma-splitting issues
- Pipeline to persist artifacts even when translation fails
- Translator call behavior with retry/backoff for `429`/`5xx`

### Fixed

- Bash compatibility issues in scripts for macOS default shell tooling
- Post-publish setting script parsing edge cases
- Publish-date reliability in downloaded filenames and metadata

## [0.1.0] - 2026-05-07

### Added

- Initial BlogScraper implementation
- Azure Function trigger entrypoints
- Core pipeline for discover -> fetch -> extract -> translate -> store
- Test suite for discovery, extraction, pipeline, ACI invocation, and downloader utilities
