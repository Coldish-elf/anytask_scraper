# Конфигурация

## Источники параметров и приоритет

Для CLI параметры берутся из нескольких источников в таком порядке:

1. Явные аргументы командной строки.
2. Файл настроек (`--settings-file`, по умолчанию `.anytask_scraper_settings.json`).
3. Встроенные значения по умолчанию.

Если параметр передан в CLI, он перекрывает значение из файла.

## Файл настроек

Файл по умолчанию: `.anytask_scraper_settings.json`.

Пример:

```json
{
  "credentials_file": "./credentials.json",
  "session_file": "./.anytask_session.json",
  "status_mode": "errors",
  "default_output": "./output",
  "save_session": true,
  "refresh_session": false,
  "auto_login_session": true,
  "debug": false
}
```

Описание ключей:

| Ключ | Тип | Назначение |
| --- | --- | --- |
| `credentials_file` | `string` | Файл с `username`/`password`. |
| `session_file` | `string` | Файл cookie-сессии. |
| `status_mode` | `all` или `errors` | Показывать все статусные сообщения CLI или только ошибки. |
| `default_output` | `string` | Базовая папка экспорта для `course`/`queue`/`gradebook`. |
| `save_session` | `boolean` | Сохранять сессию после команды (если задан `session_file`). |
| `refresh_session` | `boolean` | Игнорировать сохранённую сессию и выполнять новый login. |
| `auto_login_session` | `boolean` | Автовход в TUI по сессионному файлу. |
| `debug` | `boolean` | Режим подробного логирования. |

## Команда `settings`

### `settings init`

```bash
anytask-scraper settings init
```

Создаёт/обновляет файл настроек рекомендуемыми значениями и создаёт шаблон `credentials.json`, если файла ещё нет.

### `settings show`

```bash
anytask-scraper settings show
```

Печатает сохранённый JSON настроек.

### `settings set`

```bash
anytask-scraper settings set --default-output ./output --status-mode all
anytask-scraper settings set --debug
anytask-scraper settings set --no-save-session
```

Поддерживаемые флаги:

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

С ключами очищает только перечисленные поля, без ключей очищает весь файл настроек.

## Файл credentials

Поддерживаются форматы.

Формат JSON:

```json
{
  "username": "ivanov",
  "password": "secret"
}
```

Формат `key=value` или `key:value`:

```text
username=ivanov
password=secret
```

Двухстрочный fallback:

```text
ivanov
secret
```

## Авторизация и сессия

CLI работает так:

1. Если указан `session_file` и не включён `refresh_session`, пробует загрузить cookie-сессию.
2. Если сессия не подошла, выполняет login по логину/паролю.
3. По завершении (если включено `save_session`) сохраняет сессию в файл.

Если сохранённая сессия протухла во время запроса, клиент делает повторную авторизацию автоматически (при наличии credentials).

## Логи

Глобальные флаги:

```bash
anytask-scraper --debug --log-file ./logs/anytask.log course -c 12345
```

- `--debug` включает уровень `DEBUG`.
- `--log-file` дублирует вывод в файл.
