# CLI

Основная команда:

```bash
anytask-scraper
```

## Общий синтаксис

```bash
anytask-scraper [GLOBAL_OPTIONS] COMMAND [COMMAND_OPTIONS]
```

## Глобальные опции

Эти опции можно использовать с любой подкомандой.

| Опция | Назначение |
| --- | --- |
| `-u`, `--username` | Логин Anytask. |
| `-p`, `--password` | Пароль Anytask. |
| `--credentials-file` | Путь к файлу credentials (`json`, `key=value`, `key:value`, либо 2 строки). |
| `--session-file` | Путь к файлу cookie-сессии. |
| `--status-mode all\|errors` | Показывать все статусные сообщения или только ошибки. |
| `--default-output` | Базовая папка для экспорта (`course`, `queue`, `gradebook`). |
| `--save-session`, `--no-save-session` | Включить/выключить сохранение сессии после выполнения команды. |
| `--refresh-session`, `--no-refresh-session` | Игнорировать сохранённую сессию и выполнять login заново. |
| `--settings-file` | Путь к JSON-файлу пользовательских настроек. |
| `-d`, `--debug` | Включить debug-логирование. |
| `--log-file` | Путь к файлу логов. |

## Команда `tui`

Запускает текстовый интерфейс:

```bash
anytask-scraper tui
anytask-tui
```

## Команда `discover`

Читает профиль пользователя и выводит доступные курсы с ролями.

```bash
anytask-scraper discover [--role all|student|teacher] [--student-only]
```

Опции:

| Опция | Назначение |
| --- | --- |
| `--role all\|student\|teacher` | Фильтр по роли (по умолчанию `all`). |
| `--student-only` | Оставляет только курсы, где пользователь студент и не преподаватель того же курса. |

## Команда `course`

Загружает задачи курса (или нескольких курсов).

```bash
anytask-scraper course -c COURSE_ID [COURSE_ID ...] [OPTIONS]
```

Опции:

| Опция | Назначение |
| --- | --- |
| `-c`, `--course` | Один или несколько ID курсов. |
| `-o`, `--output` | Папка вывода. |
| `--filename` | Имя файла экспорта (с расширением или без). Для нескольких `--course` недоступно. |
| `-f`, `--format json\|markdown\|csv\|table` | Формат вывода. `table` только печатает таблицу, файл не создаётся. |
| `--show` | После экспорта показать таблицу в терминале. |
| `--fetch-descriptions` | Для teacher-view догружает полные описания задач через `/task/edit/{id}`. |
| `--include-columns` | Экспортировать только перечисленные колонки. |
| `--exclude-columns` | Исключить перечисленные колонки. |

Поддерживаемые колонки зависят от представления курса:

- student-view: `#`, `Title`, `Score`, `Status`, `Deadline`
- teacher-view: `#`, `Title`, `Section`, `Max Score`, `Deadline`.

## Команда `queue`

Загружает очередь проверки курса.

```bash
anytask-scraper queue -c COURSE_ID [OPTIONS]
```

Опции:

| Опция | Назначение |
| --- | --- |
| `-c`, `--course` | ID курса. |
| `-o`, `--output` | Папка вывода. |
| `--filename` | Имя файла экспорта. |
| `-f`, `--format json\|markdown\|csv\|table` | Формат вывода (`table` без записи файла). |
| `--show` | После экспорта показать таблицу в терминале. |
| `--deep` | Для каждой доступной записи загружает страницу issue и собирает `Submission`. |
| `--download-files` | Скачивает файлы из комментариев и Colab-ссылки автоматически включает `--deep`. |
| `--filter-task` | Фильтр по подстроке названия задачи. |
| `--filter-reviewer` | Фильтр по подстроке имени проверяющего. |
| `--filter-status` | Фильтр по подстроке статуса. |
| `--last-name-from` | Фильтр нижней границы фамилии (без учёта регистра). |
| `--last-name-to` | Фильтр верхней границы фамилии (prefix-inclusive). |
| `--include-columns` | Экспортировать только перечисленные колонки. |
| `--exclude-columns` | Исключить перечисленные колонки. |

Колонки очереди: `#`, `Student`, `Task`, `Status`, `Reviewer`, `Updated`, `Grade`.

Дополнительно при `-f csv` и `--deep` создаётся файл `submissions_{course_id}.csv`.

## Команда `gradebook`

Загружает ведомость курса.

```bash
anytask-scraper gradebook -c COURSE_ID [OPTIONS]
```

Опции:

| Опция | Назначение |
| --- | --- |
| `-c`, `--course` | ID курса. |
| `-o`, `--output` | Папка вывода. |
| `--filename` | Имя файла экспорта. |
| `-f`, `--format json\|markdown\|csv\|table` | Формат вывода (`table` без записи файла). |
| `--show` | После экспорта показать таблицу в терминале. |
| `--filter-group` | Фильтр по подстроке названия группы (регистронезависимо). |
| `--filter-student` | Фильтр по подстроке имени студента (регистронезависимо). |
| `--filter-teacher` | Фильтр по точному имени преподавателя группы. |
| `--min-score` | Оставить студентов с суммой баллов `>=` значения. |
| `--last-name-from` | Нижняя граница диапазона фамилий. |
| `--last-name-to` | Верхняя граница диапазона фамилий. |
| `--include-columns` | Экспортировать только перечисленные колонки. |
| `--exclude-columns` | Исключить перечисленные колонки. |

Колонки: `Group`, `Student`, динамический набор задач, `Total`.

## Команда `settings`

Управляет локальным файлом настроек.

```bash
anytask-scraper settings init
anytask-scraper settings show
anytask-scraper settings set [OPTIONS]
anytask-scraper settings clear [KEY ...]
```

Опции `settings set`:

- `--credentials-file`
- `--session-file`
- `--status-mode all|errors`
- `--default-output`
- `--save-session / --no-save-session`
- `--refresh-session / --no-refresh-session`
- `--auto-login-session / --no-auto-login-session`
- `--debug / --no-debug`

Ключи для `settings clear`: `credentials_file`, `session_file`, `status_mode`, `default_output`, `save_session`, `refresh_session`, `auto_login_session`, `debug`.

## Ошибки и коды завершения

CLI завершает процесс с кодом `1` при ошибках авторизации, чтения настроек, валидации аргументов и сетевых ошибках.

## Примеры

```bash
# Показать все курсы из профиля
anytask-scraper discover

# Экспорт задач сразу по двум курсам
anytask-scraper course -c 11111 22222 -f csv -o ./output

# Очередь с догрузкой submissions и скачиванием файлов
anytask-scraper queue -c 11111 --download-files -o ./output

# Ведомость только для одной группы и студентов с total >= 50
anytask-scraper gradebook -c 11111 --filter-group IDK --min-score 50 -f markdown
```
