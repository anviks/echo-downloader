# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [1.0.2] - 2025-03-03

### Fixed
- Fixed "SyntaxError: f-string expression part cannot include a backslash" error on Python versions below 3.12.


## [1.0.1] - 2025-03-02

### Changed
- On windows, long path prefix is now added only if the path size exceeds 260 characters.

### Fixed
- Fixed f-string usage, that was incompatible with Python versions below 3.12.


## [1.0.0] - 2025-03-01

### Added
- Official release of the package.
