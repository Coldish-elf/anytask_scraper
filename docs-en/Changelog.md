# Changelog

## [1.1.1] - 2026-03-26

### Changed

- Session storage now defaults to ~/.config/anytask-scraper/session.json, with legacy .anytask_session.json still accepted for migration and saved-session login fallback.
- Google Colab notebook exports now use last-name/first-name/task-based names for .ipynb downloads and .url.txt fallback files instead of the old colab_{issue_id} naming.

### Fixed

- TUI login by username/password did not save a reusable session, so “saved session” login and auto-login stopped working after a fresh manual login.
- Switching courses in TUI could leave the visible task and queue filters out of sync with the rows currently shown in the tables.
- Queue and submission write actions used hardcoded status codes instead of the real status options parsed from the submission page.
- Queue preview could render stale background results after the highlighted row had already changed.
- Queue preview and cached submission data were not refreshed immediately after successful grade/status/comment writes.
- Submission form parsing crashed on non-numeric placeholder values in status \<option> entries.
- Comment timestamps always assumed the current year, which produced incorrect dates around New Year rollovers.
- JSON DB comment deduplication depended on comment order, so inserting an older comment could duplicate later issue_chain events.
- Export preview treated empty queue and gradebook datasets as “not loaded” and showed misleading placeholder text.
- Markdown table exports wrote raw values without escaping | and line breaks, which could corrupt generated tables.
- db sync --pull, db pull, and /db/pull did not expose the same name_list filtering behavior.
- API submission responses did not expose issue_url.

## [1.1.0] - 2026-03-24

### Added

- GitHub repo cloning: Automatically clone GitHub repositories from student submissions.
- Name list filter: Filter exports by a list of student names from a text file or pasted text.
- Queue preview now displays comment links.

### Changed

- TUI export defaults: "Include files" and "Clone repos" are now ON by default instead of OFF.

### Fixed

- Failed fetches now report count and details in the status bar.
- "Files Only" export no longer blocked by disabled "Include files" toggle: Files Only mode now implies file inclusion, removing the redundant validation gate.
- "Files Only" button stayed disabled on first switch to Submissions export type until data preload completed.
- TUI MainScreen not pushed after auto-login due to Textual call_from_thread not dispatching bound methods from worker threads (closures required).
- CLI session never loaded when settings file lacks session_file key: _merge_runtime_settings now applies all INIT_DEFAULTS as fallbacks.
- TUI autologin now tries both new and old session paths, with one-time migration and proper login-screen fallback.
- format_student_folder() now sanitizes unsafe filesystem characters (/ \ < > : " | ? * and control chars), not just spaces.
- Session file moved from CWD-relative (.anytask_session.json) to ~/.config/anytask-scraper/session.json - autologin now works from any directory. One-time migration from old location is automatic.
- TUI settings file lookup now checks ~/.config/anytask-scraper/settings.json first, with CWD fallback.

## [1.0.0] - 2026-03-08

### Changed

- Main README is now in English; separate Russian README added as README.ru.md.
- pyproject.toml metadata expanded.
- GitHub Actions CI now caches pip, upgrades pip explicitly, runs checks against tests/, and validates builds with python -m build.
- PR template now includes formatting and packaging checks.
- MainScreen mixin handler registration now reuses inherited decorated handlers through a local fallback mapping.
- Minor structural cleanup in the API client, API server, TUI mixins, and filter bar widgets.
- Docker build context filtering tightened for local state files.

## [0.10.2] - 2026-03-07

### Fixed

- IndentationError in client.py.
- SyntaxError in filter_bar.py: three Reset(Message) dataclasses in TaskFilterBar, QueueFilterBar, and GradebookFilterBar had empty bodies, breaking TUI import.
- course selection not working: OptionList.highlighted stayed None when options were added dynamically via add_option(), making Enter do nothing.
- MRO shadowing: type stubs (def _show_status(...): ...) in TasksMixin, QueueMixin, and GradebookMixin shadowed real implementations in CoreMixin, silently breaking status messages, cursor tracking, and submission screen navigation.
- @on handlers not firing: Textual's metaclass only discovers @on decorators on classes it creates directly. Mixin classes (plain Python classes) were invisible. Added _register_mixin_handlers() to propagate all mixin @on handlers.

## [0.10.1] - 2026-03-06

### Added

- GitHub Actions CI: tests, lint, typecheck on each PR.
- py.typed marker (PEP 561) for typed package consumers.
- API bearer token authentication via ANYTASK_API_TOKEN environment variable.
- Docker image and .dockerignore for ready-to-run API server container.

### Changed

- Refactor MainScreen into 5 mixin modules: _core.py,_tasks.py, _queue.py,_gradebook.py, _export.py, plus shared_helpers.py.

## [0.10.0] - 2026-03-04

### Added

#### Possibility of pushing ratings, comments and statuses in anytask

- Write operations (client.py): methods set_grade, set_status, add_comment for rating, changing status and commenting.
- SubmissionForms and WriteResult models in models.py.
- Form parser. Retrieving CSRF token and form metadata from the submission page. Form parser. Retrieving CSRF token and form metadata from the submission page.
- CLI subcommand push: push grade, push status, push comment.
- API endpoints: POST /submissions/{id}/grade, POST /submissions/{id}/status, POST /submissions/{id}/comment.
- TUI: action buttons (Accept & Rate, Grade, Status, Comment) in the queue panel and on the submission screen in teacher mode.

#### Functionality expansion

- ActionMenu in TUI has been expanded.
- CLI commands db diff and db stats to view queue changes and statistics.
- API endpoints: GET /db/diff, GET /db/stats.
- Methods diff_assignment, get_changed_entries, statistics in json_db.py.

#### Improvements

- Tests.
- Documentation in English

### Changed

- Refactoring of code.

### Corrected

- Correct multipart/form-data encoding for all POST post requests.
- TUI protection from crashes due to network errors in background recording workers.

## [0.9.0] - 2026-03-01

### Added

- Module json_db.py: local JSON queue database (QueueJsonDB) with hierarchy courses -> students -> assignments -> files and event log issue_chain.
- CLI commands db sync, db pull, db process, db write to manage the queue database.
- HTTP API.
- Documentation docs/API.md.

### Changed

- Documentation.

### Corrected

- Path traversal protection for API file parameters (session_file, db_file).
- Streaming file download: fixed redirect check during login (the URL was used instead of the response body, which led to empty files).
- Session files are saved with permissions 0600 (previously available to all users).
- Sanitization of downloaded file names to prevent path traversal (../).
- Errors when loading solutions are now logged rather than silently ignored.
*.html - CSV preview in TUI uses correct escaping via csv.writer.
- Removed unused imports, streamlined imports in all affected modules.

## [0.8.0] - 2026-02-27

### Added

- Support for multi-select filters when exporting to TUI.
- Detailed documentation

### Changed

- Appearance of export buttons in TUI.

## [0.7.5] - 2026-02-27

### Added

- String filtering by range for export.
- Open your own course submission on the Tasks page in TUI.

### Changed

- Handle focus and navigation for new input fields in the export tab.
- Refactor the size and proportions of the export/preview panel, as well as individual elements of the TUI theme.

### Corrected

- Colors of disabled states in export to TUI: incorrect shades and unnecessary highlighting have been removed.

## [0.7.4] - 2026-02-25

### Added

- The discover method for obtaining a list of courses, with the ability to filter by role and automatically add to TUI.

### Changed

- Behavior of comment blocks to automatically increase height.
- Colors for status messages in TUI submissions.

### Corrected

- Bug where gradebook in TUI did not scroll down when navigating with arrows.
- A bug where status messages were not displayed in submissions, leaving empty blocks.
- A bug in which line breaks in messages did not work in submissions.

## [0.7.3] - 2026-02-24

### Added

- Filename parameter when exporting.
- ActionMenu when right-clicking in TUI.
- Copying TUI content via shortcut and right-click.
- Option to download/skip solution files in submissions.

### Corrected

- Error where filtering parameters were not applied.

## [0.7.2] - 2026-02-18

### Added

- First version of documentation.

### Changed

- Updated README.md.
- Updated roadmap.md.

## [0.7.1] - 2026-02-15

### Added

- Logging.
- Support for debug mode in the CLI (--debug / -d) and writing logs to a file (--log-file).
- debug parameter in user settings.
- Support for launching TUI in debug mode.

### Changed

- Logging has been added to the key modules CLI, TUI, client/parser/storage/display.
- Improved handling of Export preload errors in TUI: errors are logged in more detail and shown in a cleaner form.

### Corrected

- Fixed an error in downloading attached files, when a directory was created, but the file itself was not downloaded.

## [0.7.0] - 2026-02-13

### Added

- settings init now automatically creates credentials.json with a template if the file is missing.
- Added auto_login_session: true to the default settings for settings init.

### Changed

- The logic of export filters and data preloading for Tasks, Queue, Submissions, Gradebook has been reworked.
- Added dynamic captions and filtering options to the Export page in TUI.

### Corrected

- Navigation through filter fields on the Export page: inactive (disabled) fields are skipped when navigating with arrows and with cyclic focus.
- Stabilized updating of filters and previews after data loading.
- Added protection against race-condition during asynchronous preload.
- Improved visual highlighting of focus in the Export Type and Format groups: the current element under the cursor is highlighted in color without resizing.

## [0.6.0] - 2026-02-13

### Added

- Gradebook support.
- Filters and parameters for export.
- Sorting by different parameters in TUI.
- Preview when exporting to TUI.
- Autologin using a session file in TUI.
- Hotkey for quickly logging out of your TUI account.
- Automatic loading of the required data when exporting to TUI.
- License.

### Changed

- Code refactoring.
- Updated appearance of TUI.

### Corrected

- Fixed errors when loading Google Colab notebooks.
- Fixed hotkeys in TUI.
- Improved focus and window changing behavior in TUI.

## [0.5.0] - 2026-02-09

### Changed

- Code refactoring.

### Corrected

- Minor bugs fixed.

## [0.4.0] - 2026-02-09

### Added

- Export to CSV.
- Filter by reviewers.

### Changed

- Improved queue filter panel.
- Redesigned home page.

## [0.3.0] - 2026-02-08

### Added

- Primary TUI and extended documentation.
- Support submissions.

### Changed

- Improved README.

## [0.2.0] - 2026-02-07

### Added

- Saving workflow authorization and settings (settings init, credentials and session files).

### Changed

- Updated README.

## [0.1.0] - 2026-02-06

### Added

- Basic MVP (main flow: course/queue).
