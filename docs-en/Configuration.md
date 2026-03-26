# Configuration

## Parameter sources and priority

For the CLI, parameters are taken from several sources in this order:

1. Explicit command line arguments.
2. Settings file (`--settings-file`, default `.anytask_scraper_settings.json`).
3. Built-in defaults.

If a parameter is passed to the CLI, it overrides the value from the file.

## Settings file

Default file: `.anytask_scraper_settings.json`.

Example:

```json
{
  "credentials_file": "./credentials.json",
  "session_file": "~/.config/anytask-scraper/session.json",
  "status_mode": "errors",
  "default_output": "./output",
  "save_session": true,
  "refresh_session": false,
  "auto_login_session": true,
  "debug": false
}
```

The TUI still checks the legacy `.anytask_session.json` file as a migration fallback when auto-login is enabled.

Description of keys:

| Key | Type | Destination |
| --- | --- | --- |
| `credentials_file` | `string` | File with `username`/`password`. |
| `session_file` | `string` | Session cookie. Default: `~/.config/anytask-scraper/session.json`. |
| `status_mode` | `all` or `errors` | Show all CLI status messages or only errors. |
| `default_output` | `string` | Base export folder for `course`/`queue`/`gradebook`. |
| `save_session` | `boolean` | Save the session after the command (if `session_file` is specified). |
| `refresh_session` | `boolean` | Ignore the saved session and perform a new login. |
| `auto_login_session` | `boolean` | Automatic login to TUI using a session file. |
| `debug` | `boolean` | Detailed logging mode. |

## `settings` command

### `settings init`

```bash
anytask-scraper settings init
```

Creates/updates a credentials file with recommended values ​​and creates a `credentials.json` template if the file does not already exist.

### `settings show`

```bash
anytask-scraper settings show
```

Prints the saved JSON settings.

### `settings set`

```bash
anytask-scraper settings set --default-output ./output --status-mode all
anytask-scraper settings set --debug
anytask-scraper settings set --no-save-session
```

Supported flags:

- `--credentials-file`
- `--session-file`
- `--status-mode all|errors`
- `--default-output`
- `--save-session / --no-save-session`
- `--refresh-session / --no-refresh-session`
- `--auto-login-session / --no-auto-login-session`
- `--debug / --no-debug`

### `settings clear`

```bash
anytask-scraper settings clear session_file debug
anytask-scraper settings clear
```

With keys, clears only the listed fields; without keys, clears the entire settings file.

## Credentials file

Formats supported.

JSON format:

```json
{
  "username": "ivanov",
  "password": "secret"
}
```

`key=value` or `key:value` format:

```text
username=ivanov
password=secret
```

Two-line fallback:

```text
ivanov
secret
```

## Authorization and session

The CLI works like this:

1. If `session_file` is specified and `refresh_session` is not enabled, tries to load a session cookie.
2. If the session does not work, log in using your login/password.
3. Upon completion (if `save_session` is enabled) saves the session to a file.

If the saved session expires during the request, the client re-authorizes automatically (if credentials are available).

## Logs

Global flags:

```bash
anytask-scraper --debug --log-file ./logs/anytask.log course -c 12345
```

- `--debug` enables the `DEBUG` level.
- `--log-file` duplicates the output to a file.
