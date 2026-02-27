# API библиотеки

`anytask-scraper` можно использовать как Python-пакет:

```python
from anytask_scraper import AnytaskClient, parse_course_page
```

## Быстрый пример

```python
from anytask_scraper import (
    AnytaskClient,
    extract_csrf_from_queue_page,
    parse_course_page,
    parse_submission_page,
    save_course_json,
)

with AnytaskClient(username="login", password="password") as client:
    course_html = client.fetch_course_page(12345)
    course = parse_course_page(course_html, 12345)
    save_course_json(course, "./output")

    queue_html = client.fetch_queue_page(12345)
    csrf = extract_csrf_from_queue_page(queue_html)
    rows = client.fetch_all_queue_entries(12345, csrf)

    if rows:
        issue_url = str(rows[0].get("issue_url", ""))
        if issue_url:
            sub_html = client.fetch_submission_page(issue_url)
            submission = parse_submission_page(sub_html, issue_id=1)
            print(submission.task_title)
```

## Клиент

### `AnytaskClient`

Создаёт HTTP-клиент с поддержкой login, cookie-сессии и автоматического пере-входа при протухшей сессии.

Конструктор:

```python
AnytaskClient(username: str = "", password: str = "")
```

Публичные методы:

| Метод | Назначение |
| --- | --- |
| `login()` | Выполняет login через Django-форму (`/accounts/login/`). |
| `load_session(session_path)` | Загружает cookies из JSON, возвращает `True/False`. |
| `save_session(session_path)` | Сохраняет текущие cookies в JSON-файл. |
| `fetch_course_page(course_id)` | Возвращает HTML страницы курса. |
| `fetch_profile_page()` | Возвращает HTML страницы профиля пользователя. |
| `fetch_task_description(task_id)` | Возвращает HTML-описание задачи из `/task/edit/{id}`. |
| `fetch_queue_page(course_id)` | Возвращает HTML страницы очереди курса. |
| `fetch_gradebook_page(course_id)` | Возвращает HTML страницы ведомости курса. |
| `fetch_queue_ajax(course_id, csrf_token, start=0, length=50, filter_query="")` | Читает одну страницу AJAX-очереди. |
| `fetch_all_queue_entries(course_id, csrf_token, filter_query="")` | Читает всю очередь с пагинацией. |
| `fetch_submission_page(issue_url)` | Возвращает HTML issue (полный URL или относительный путь). |
| `download_file(url, output_path)` | Скачивает файл и валидирует содержимое. |
| `download_colab_notebook(colab_url, output_path)` | Пытается скачать Colab notebook как `.ipynb`. |
| `close()` | Закрывает HTTP-клиент. |
| `__enter__()` / `__exit__()` | Поддержка контекстного менеджера. |

Исключения и результаты:

- `LoginError` - ошибка авторизации.
- `DownloadResult(success: bool, path: str, reason: str = "")` - результат скачивания.

Типичные `DownloadResult.reason`:
`ok`, `download_error`, `login_redirect`, `html_instead_of_file`, `invalid_notebook_format`, `google_drive_html_page`, `no_file_id_in_url`.

## Парсеры

### `parse_course_page(html, course_id) -> Course`

Разбирает страницу курса, автоматически поддерживает student-view и teacher-view.

### `parse_profile_page(html) -> list[ProfileCourseEntry]`

Читает профиль и возвращает курсы пользователя с ролью `teacher`/`student`.

### `parse_gradebook_page(html, course_id) -> Gradebook`

Разбирает таблицы ведомости по группам, задачам и студентам.

### `parse_submission_page(html, issue_id) -> Submission`

Разбирает issue-страницу: метаданные, комментарии, файлы, ссылки, дедлайновые флаги.

### `parse_queue_filters(html) -> QueueFilters`

Извлекает доступные опции фильтров из модального окна очереди.

### Вспомогательные функции

| Функция | Назначение |
| --- | --- |
| `parse_task_edit_page(html) -> str` | Извлечь описание задачи из страницы редактирования. |
| `strip_html(text) -> str` | Очистить HTML до plain text с переносами строк. |
| `extract_csrf_from_queue_page(html) -> str` | Достать CSRF-токен для AJAX очереди. |
| `extract_issue_id_from_breadcrumb(html) -> int` | Извлечь numeric issue ID из breadcrumb. |
| `format_student_folder(name) -> str` | Преобразовать имя студента в имя папки. |

## Модели данных

### Курс и задачи

`Task`:

- `task_id: int`
- `title: str`
- `description: str = ""`
- `deadline: datetime | None = None`
- `max_score: float | None = None`
- `score: float | None = None`
- `status: str = ""`
- `section: str = ""`
- `edit_url: str = ""`
- `submit_url: str = ""`

`Course`:

- `course_id: int`
- `title: str = ""`
- `teachers: list[str]`
- `tasks: list[Task]`

`ProfileCourseEntry`:

- `course_id: int`
- `title: str`
- `role: str`

### Очередь и решения

`QueueEntry`:

- `student_name`, `student_url`, `task_title`, `update_time`, `mark`
- `status_color`, `status_name`
- `responsible_name`, `responsible_url`
- `has_issue_access: bool`
- `issue_url`

`FileAttachment`:

- `filename: str`
- `download_url: str`
- `is_notebook: bool = False`

`Comment`:

- `author_name`, `author_url`
- `timestamp: datetime | None`
- `content_html: str`
- `files: list[FileAttachment]`
- `links: list[str]`
- `is_after_deadline: bool`
- `is_system_event: bool`

`Submission`:

- `issue_id: int`
- `task_title: str`
- `student_name`, `student_url`
- `reviewer_name`, `reviewer_url`
- `status`, `grade`, `max_score`, `deadline`
- `comments: list[Comment]`

`QueueFilters`:

- `students: list[tuple[value, label]]`
- `tasks: list[tuple[value, label]]`
- `reviewers: list[tuple[value, label]]`
- `statuses: list[tuple[value, label]]`

`ReviewQueue`:

- `course_id: int`
- `entries: list[QueueEntry]`
- `submissions: dict[str, Submission]` (ключ - `issue_url`)

### Ведомость

`GradebookEntry`:

- `student_name`, `student_url`
- `scores: dict[task_title, float]`
- `statuses: dict[task_title, str]`
- `issue_urls: dict[task_title, str]`
- `total_score: float`

`GradebookGroup`:

- `group_name: str`
- `group_id: int`
- `teacher_name: str`
- `task_titles: list[str]`
- `max_scores: dict[task_title, float]`
- `entries: list[GradebookEntry]`

`Gradebook`:

- `course_id: int`
- `groups: list[GradebookGroup]`

Модельные функции:

- `extract_last_name(name) -> str`
- `last_name_in_range(name, from_name="", to_name="") -> bool`
- `filter_gradebook(gradebook, group="", teacher="", student="", min_score=None, last_name_from="", last_name_to="") -> Gradebook`

## Экспорт и сохранение

### Функции курса

| Функция | Результат |
| --- | --- |
| `save_course_json(course, output_dir=".", columns=None, filename=None)` | Путь к `course_{id}.json`. |
| `save_course_markdown(course, output_dir=".", columns=None, filename=None)` | Путь к `course_{id}.md`. |
| `save_course_csv(course, output_dir=".", columns=None, filename=None)` | Путь к `course_{id}.csv`. |

### Функции очереди

| Функция | Результат |
| --- | --- |
| `save_queue_json(queue, output_dir=".", columns=None, filename=None)` | Путь к `queue_{id}.json`. |
| `save_queue_markdown(queue, output_dir=".", columns=None, filename=None)` | Путь к `queue_{id}.md`. |
| `save_queue_csv(queue, output_dir=".", columns=None, filename=None)` | Путь к `queue_{id}.csv`. |

### Функции submissions

| Функция | Результат |
| --- | --- |
| `save_submissions_json(submissions, course_id, output_dir=".", columns=None, filename=None)` | Путь к `submissions_{id}.json`. |
| `save_submissions_markdown(submissions, course_id, output_dir=".", columns=None, filename=None)` | Путь к `submissions_{id}.md`. |
| `save_submissions_csv(submissions, course_id, output_dir=".", columns=None, filename=None)` | Путь к `submissions_{id}.csv`. |
| `download_submission_files(client, submission, base_dir)` | `dict[source, saved_path]` по скачанным артефактам. |

### Функции ведомости

| Функция | Результат |
| --- | --- |
| `save_gradebook_json(gradebook, output_dir=".", columns=None, filename=None)` | Путь к `gradebook_{id}.json`. |
| `save_gradebook_markdown(gradebook, output_dir=".", columns=None, filename=None)` | Путь к `gradebook_{id}.md`. |
| `save_gradebook_csv(gradebook, output_dir=".", columns=None, filename=None)` | Путь к `gradebook_{id}.csv`. |

`columns` в функциях экспорта ограничивает набор полей выходного файла.

## Отрисовка в терминал (Rich)

| Функция | Назначение |
| --- | --- |
| `display_course(course, console=None)` | Таблица задач курса. |
| `display_task_detail(task, console=None)` | Подробности одной задачи. |
| `display_queue(queue, console=None)` | Таблица очереди. |
| `display_submission(submission, console=None)` | Тред комментариев issue. |
| `display_gradebook(gradebook, console=None)` | Таблицы ведомости по группам. |

## Логирование

`setup_logging(level=logging.WARNING, log_file=None, fmt=DEFAULT_FORMAT)` настраивает логгер пакета `anytask_scraper`.

## Минимальный рабочий сценарий: queue + submissions + файлы

```python
from anytask_scraper import (
    AnytaskClient,
    ReviewQueue,
    extract_csrf_from_queue_page,
    extract_issue_id_from_breadcrumb,
    parse_submission_page,
    save_queue_json,
    save_submissions_markdown,
    download_submission_files,
)

course_id = 12345

with AnytaskClient("login", "password") as client:
    queue_html = client.fetch_queue_page(course_id)
    csrf = extract_csrf_from_queue_page(queue_html)
    rows = client.fetch_all_queue_entries(course_id, csrf)

    queue = ReviewQueue(course_id=course_id)
    for row in rows:
        issue_url = str(row.get("issue_url", ""))
        if not issue_url:
            continue
        sub_html = client.fetch_submission_page(issue_url)
        issue_id = extract_issue_id_from_breadcrumb(sub_html)
        if issue_id == 0:
            continue
        submission = parse_submission_page(sub_html, issue_id)
        queue.submissions[issue_url] = submission
        download_submission_files(client, submission, "./downloads")

    save_queue_json(queue, "./output")
    save_submissions_markdown(queue.submissions, course_id, "./output")
```
