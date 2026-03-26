# HTTP API

## Установка

API - опциональная зависимость. Установите с флагом `[api]`:

```bash
pip install "anytask-scraper[api] @ git+https://github.com/Coldish-elf/anytask_scraper.git"
```

Или при локальной разработке:

```bash
pip install -e ".[api]"
```

## Запуск сервера

### Через CLI

```bash
anytask-scraper serve --host 127.0.0.1 --port 8000
```

### Через entry point

```bash
anytask-api --host 127.0.0.1 --port 8000
```

### С reload

```bash
anytask-scraper serve --reload
```

### С загрузкой существующей сессии

```bash
anytask-scraper serve --session-file ~/.anytask_session.json
```

## Опции запуска

| Опция | Значение по умолчанию | Описание |
| --- | --- | --- |
| `--host` | `127.0.0.1` | IP адрес для bind. |
| `--port` | `8000` | Порт сервера. |
| `--session-file` | None | Путь к сохранённой сессии cookie для auto-login. |
| `--reload` | False | Автоперезагрузка на изменение кода (development). |

## Основные концепции

### Состояние приложения

Сервер управляет одним экземпляром `AnytaskClient` в памяти. Состояние хранится в `AppState` с thread-safe блокировкой (`threading.RLock`).

### Аутентификация

Все операции требуют аутентификации:

- либо через `POST /auth/login` с логином/паролем
- либо через `POST /auth/load-session` с существующим файлом сессии

После успешной аутентификации клиент остаётся в памяти и переиспользуется для всех последующих запросов.

### Сессия

При завершении работы сервер закрывает HTTP-сессию. Можно сохранить состояние с `POST /auth/save-session`.

## Endpoints

### Health Check

#### `GET /`

Проверка статуса сервера.

### Аутентификация

#### `POST /auth/login`

Аутентификация по username/password.

**Тело запроса:**

```json
{
  "username": "student@example.com",
  "password": "secret"
}
```

**Ответ (200):**

```json
{
  "ok": true,
  "message": "Logged in successfully"
}
```

**Ошибки:**

- `401` - неверные credentials
- `500` - ошибка сети

#### `POST /auth/load-session`

Восстановление сессии из файла cookie.

**Тело запроса:**

```json
{
  "session_file": "/path/to/.anytask_session.json"
}
```

**Ответ (200):**

```json
{
  "ok": true,
  "message": "Session loaded successfully"
}
```

**Ошибки:**

- `404` - файл сессии не найден

#### `GET /auth/status`

Получить текущий статус аутентификации.

**Ответ (200):**

```json
{
  "authenticated": true,
  "username": "student@example.com"
}
```

или при не аутентифицированном состоянии:

```json
{
  "authenticated": false,
  "username": null
}
```

#### `POST /auth/save-session`

Сохранить текущую сессию в файл.

**Тело запроса:**

```json
{
  "session_file": "/path/to/.anytask_session.json"
}
```

**Ответ (200):**

```json
{
  "ok": true,
  "message": "Session saved to /path/to/.anytask_session.json"
}
```

#### `POST /auth/logout`

Закрыть текущую сессию.

**Ответ (200):**

```json
{
  "ok": true,
  "message": "Logged out"
}
```

### Профиль

#### `GET /profile/courses`

Загрузить список доступных курсов из профиля пользователя.

**Query параметры:**

- нет

**Ответ (200):**

```json
{
  "courses": [
    {
      "id": 12345,
      "title": "Алгоритмы",
      "role": "student"
    },
    {
      "id": 12346,
      "title": "Базы данных",
      "role": "teacher"
    }
  ]
}
```

### Курсы

#### `GET /courses/{course_id}`

Загрузить задачи курса.

**Path параметры:**

- `course_id` (int) - ID курса

**Query параметры:**

- `fetch_descriptions` (bool, default=false) - для teacher-view загружать полные описания задач

**Ответ (200):**

```json
{
  "course": {
    "id": 12345,
    "title": "Алгоритмы",
    "is_student": true,
    "tasks": [
      {
        "id": 1,
        "title": "Сортировка",
        "score": 10,
        "status": "ok",
        "deadline": "2025-03-15"
      }
    ]
  }
}
```

#### `GET /courses/{course_id}/queue`

Загрузить очередь проверки курса.

**Path параметры:**

- `course_id` (int) - ID курса

**Query параметры:**

- `filter_task` - фильтр по названию задачи (подстрока, case-insensitive)
- `filter_reviewer` - фильтр по имени проверяющего
- `filter_status` - фильтр по статусу
- `last_name_from` - нижняя граница диапазона фамилий
- `last_name_to` - верхняя граница диапазона фамилий

**Ответ (200):**

```json
{
  "entries": [
    {
      "id": 421525,
      "student": "Alice Smith",
      "task": "HW 1",
      "status": "on review",
      "reviewer": "Bob Johnson",
      "updated": "2025-03-10T14:30:00",
      "grade": "8/10"
    }
  ]
}
```

#### `GET /courses/{course_id}/gradebook`

Загрузить ведомость курса.

**Path параметры:**

- `course_id` (int) - ID курса

**Ответ (200):**

```json
{
  "gradebook": {
    "groups": [
      {
        "group": "Group A",
        "students": [
          {
            "student": "Alice Smith",
            "scores": {
              "HW 1": 10,
              "HW 2": 8
            },
            "total": 18
          }
        ]
      }
    ]
  }
}
```

### Submissions

#### `GET /submissions/{issue_id}`

Загрузить детали submission по issue ID.

**Path параметры:**

- `issue_id` (int) - ID issue/submission

**Ответ (200):**

```json
{
  "submission": {
    "id": 421525,
    "title": "Student submission for HW 1",
    "status": "on review",
    "grade": "8/10",
    "attachments": [
      {
        "name": "solution.py",
        "url": "https://anytask.org/attachments/..."
      }
    ],
    "comments": [
      {
        "author": "Bob Johnson",
        "text": "Good work!",
        "date": "2025-03-10T14:30:00"
      }
    ]
  }
}
```

### JSON Database

#### `POST /db/sync`

Синхронизировать очередь курса с локальной JSON DB.

**Тело запроса:**

```json
{
  "course_id": 12345,
  "db_file": "/path/to/queue_db.json",
  "course_title": "Алгоритмы",
  "deep": false,
  "pull": false,
  "limit": null,
  "filter_task": null,
  "filter_reviewer": null,
  "filter_status": null,
  "last_name_from": null,
  "last_name_to": null
}
```

**Ответ (200):**

```json
{
  "ok": true,
  "message": "Synced 5 new entries",
  "synced_count": 5
}
```

#### `GET /db/entries`

Получить список всех записей в DB.

**Query параметры:**

- `course_id` (int, optional) - фильтр по курсу
- `state` (string, optional) - фильтр по состоянию (new, pulled, processed)

**Ответ (200):**

```json
{
  "entries": [
    {
      "course_id": 12345,
      "student_key": "/users/alice/",
      "assignment_key": "issue:421525",
      "state": "new",
      "data": {
        "student": "Alice Smith",
        "task": "HW 1",
        "status": "on review"
      }
    }
  ]
}
```

#### `POST /db/pull`

Вытянуть новые (state=new) записи из DB и пометить их pulled.

**Тело запроса:**

```json
{
  "db_file": "/path/to/queue_db.json",
  "course_id": null,
  "limit": null,
  "student_contains": null,
  "task_contains": null,
  "status_contains": null,
  "reviewer_contains": null,
  "last_name_from": null,
  "last_name_to": null,
  "issue_id": null
}
```

**Ответ (200):**

```json
{
  "pulled": [
    {
      "course_id": 12345,
      "student_key": "/users/alice/",
      "assignment_key": "issue:421525",
      "state": "pulled",
      "data": { ... }
    }
  ],
  "pulled_count": 1
}
```

#### `POST /db/entries/pulled`

Пометить одну запись как pulled.

**Тело запроса:**

```json
{
  "db_file": "/path/to/queue_db.json",
  "course_id": 12345,
  "student_key": "/users/alice/",
  "assignment_key": "issue:421525"
}
```

**Ответ (200):**

```json
{
  "ok": true,
  "message": "Entry marked as pulled"
}
```

#### `POST /db/entries/processed`

Пометить запись как processed.

**Тело запроса:**

```json
{
  "db_file": "/path/to/queue_db.json",
  "course_id": 12345,
  "student_key": "/users/alice/",
  "assignment_key": "issue:421525"
}
```

**Ответ (200):**

```json
{
  "ok": true,
  "message": "Entry marked as processed"
}
```

#### `POST /db/write`

Добавить write-событие в issue_chain (например grading/status update).

**Тело запроса:**

```json
{
  "db_file": "/path/to/queue_db.json",
  "course_id": 12345,
  "issue_id": 421525,
  "action": "grade",
  "value": "10/10",
  "author": "Bob Johnson",
  "note": "Perfect solution!"
}
```

**Ответ (200):**

```json
{
  "ok": true,
  "message": "Write event recorded"
}
```

## HTTP статус коды

| Код | Значение |
| --- | --- |
| `200` | Успешный запрос |
| `400` | Bad Request (невалидные параметры) |
| `401` | Unauthorized (требуется аутентификация или неверные credentials) |
| `404` | Not Found (курс/issue не найден или файл не существует) |
| `422` | Unprocessable Entity (ошибка валидации данных) |
| `500` | Internal Server Error (ошибка сервера) |
| `502` | Bad Gateway (сетевая ошибка при обращении к anytask.org) |

## Примеры использования

### curl

```bash
# Логин
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"student@example.com","password":"secret"}'

# Получить доступные курсы
curl http://localhost:8000/profile/courses

# Загрузить задачи курса
curl http://localhost:8000/courses/12345

# Загрузить очередь с фильтром
curl 'http://localhost:8000/courses/12345/queue?filter_task=hw'

# Синхронизировать DB
curl -X POST http://localhost:8000/db/sync \
  -H "Content-Type: application/json" \
  -d '{
    "course_id": 12345,
    "db_file": "./queue_db.json",
    "pull": true,
    "limit": 10
  }'
```

### Python (requests)

```python
import requests

BASE_URL = "http://localhost:8000"

# Логин
resp = requests.post(f"{BASE_URL}/auth/login", json={
    "username": "student@example.com",
    "password": "secret"
})
assert resp.status_code == 200

# Получить курсы
resp = requests.get(f"{BASE_URL}/profile/courses")
courses = resp.json()["courses"]
print(courses)

# Загрузить очередь
course_id = 12345
resp = requests.get(f"{BASE_URL}/courses/{course_id}/queue")
entries = resp.json()["entries"]

# Синхронизировать DB и вытянуть новые
resp = requests.post(f"{BASE_URL}/db/sync", json={
    "course_id": course_id,
    "db_file": "./queue_db.json",
    "pull": True,
    "limit": 10
})
print(resp.json())

# Пометить запись как pulled
resp = requests.post(f"{BASE_URL}/db/entries/pulled", json={
    "db_file": "./queue_db.json",
    "course_id": course_id,
    "student_key": "/users/alice/",
    "assignment_key": "issue:421525"
})

# Выход
requests.post(f"{BASE_URL}/auth/logout")
```

## Thread-safety

Сервер использует `threading.RLock` для всех операций с `AnytaskClient`. Все запросы к endpoints безопасны для параллельного выполнения.

## Ограничения

- Сервер хранит только одну аутентифицированную сессию в памяти (один пользователь за раз)
- JSON DB операции требуют явного указания пути к файлу для каждого запроса
- Большие очереди загружаются синхронно (блокируют обработку других запросов на время загрузки)
