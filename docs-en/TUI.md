# TUI

TUI is launched with the commands:

```bash
anytask-tui
anytask-scraper tui
```

## Login screen

Two options are supported:

1. Login using `username/password`.
2. Login using the saved session (`~/.config/anytask-scraper/session.json`), if the file exists. The legacy `.anytask_session.json` file is still checked as a fallback during migration.

If the settings are `auto_login_session=true` and the session file is found, the application logs in automatically.

## Interface structure

The main screen is divided into two panels:

1. On the left is a list of courses and a field to add Course ID.
2. On the right are the tabs: `Tasks`, `Queue`, `Gradebook`, `Export`.

### `Tasks` tab

Shows the objectives of the selected course.

The mode is automatically determined based on course data:

- student-view (score, status, deadline)
- teacher-view (section, maximum points, deadline).

Available:

- filters by text, status, section
- detailed panel with a description of the selected task
- opening your own submission for the selected issue (if available in the issue data)
- copying the selected entry to the buffer (`Ctrl+Y` or context menu).

### `Queue` tab

Available for courses with instructor rights.

Functions:

- queue table (`student`, `task`, `status`, `reviewer`, `updated`, `grade`)
- filters by text, student, task, status, reviewer
- sorting and navigation through the table
- detailed comment panel for the selected issue
- full screen submission screen with copying (`Ctrl+Y`) and scrolling `j/k`.

### `Gradebook` tab

Shows a table by group:

- dynamic task columns
- total score
- color indication of rating statuses.

There are filters by student, group and teacher.

### `Export` tab

Allows you to build exports without a CLI command.

Selected:

- data type: `Tasks`, `Queue`, `Submissions`, `Gradebook`, `DB`
- format: `JSON`, `Markdown`, `CSV`, `Files Only`
- columns via `ParameterSelector`
- string filters (including last name range `From/To`)
- the need to download submissions files
- output folder and custom file name.

There is a dynamic preview.

### DB export mode

`DB` is available in the data type selector in the `Export` tab.

Behavior:

- JSON format only
- uses current queue data and selected filters
- writes a snapshot of the database via `QueueJsonDB.sync_queue(...)`
- default file name: `queue_db_{course_id}.json`

DB mode supports row filters:

- task
- status
- inspector
- last name range (`From/To`)

For workflow states (`new` / `pulled` / `processed`) and record history (`issue_chain`)
use the CLI commands `db sync`, `db pull`, `db process`, `db write`.

## Hotkeys

Global:

| Key | Action |
| --- | --- |
| `Ctrl+Q` | Exit the application. |
| `Ctrl+C` twice | Quick exit. |
| `Ctrl+L` | Logout. |
| `?` | Show/hide built-in help. |
| `Esc` | Close overlay/go back. |
| `Ctrl+Y` | Copy the current selection to the clipboard. |

Navigation:

| Key | Action |
| --- | --- |
| `Tab` / `Shift+Tab` | Cycle focus. |
| `1` `2` `3` `4` | Switching tabs (`Tasks`, `Queue`, `Gradebook`, `Export`). |
| `Up` / `Down` | Navigation with up/down arrows through tables, lists and menu items. |
| `Left` / `Right` | Toggle arrow controls where the widget supports it. |
| `h` / `l` | Focus to left/right panel. |
| `j` / `k` | Navigation down/up through tables and lists. |

Filters:

| Key | Action |
| --- | --- |
| `/` | Focus on active tab filters. |
| `Ctrl+Up` | Go to filters. |
| `Ctrl+Down` | Return to table/content. |
| `Ctrl+Left` / `Ctrl+Right` | Switching filter fields. |
| `r` | Reset filters. |
| `u` | Cancels the last filter reset. |

Courses:

| Key | Action |
| --- | --- |
| `a` | Add a course by ID. |
| `d` | Auto-detection of courses from profile. |
| `x` | Remove the selected course from the list and caches. |

## Clipboard

Copying works using platform backends:

- macOS: `pbcopy`
- Windows: `powershell` / `pwsh` / `clip`
- Linux: `wl-copy` / `xclip` / `xsel` / `termux-clipboard-set`
- fallback via OSC52 (if supported by the terminal).

## Where TUI stores data

- Settings: `.anytask_scraper_settings.json` in the current directory
- Default session file: `~/.config/anytask-scraper/session.json`
- Legacy session fallback: `.anytask_session.json`
