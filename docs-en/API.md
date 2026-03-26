# HTTP API

## Installation

API is an optional dependency. Install with the `[api]` flag:

```bash
pip install "anytask-scraper[api] @ git+https://github.com/Coldish-elf/anytask_scraper.git"
```

Or when developing locally:

```bash
pip install -e ".[api]"
```

## Starting the server

### Via CLI

```bash
anytask-scraper serve --host 127.0.0.1 --port 8000
```

### Via entry point

```bash
anytask-api --host 127.0.0.1 --port 8000
```

### With reload

```bash
anytask-scraper serve --reload
```

### With loading of an existing session

```bash
anytask-scraper serve --session-file ~/.anytask_session.json
```

## Launch options

| Option | Default | Description |
| --- | --- | --- |
| `--host` | `127.0.0.1` | IP address for bind. |
| `--port` | `8000` | Server port. |
| `--session-file` | None | Path to the saved session cookie for auto-login. |
| `--reload` | False | Auto-reboot for code changes (development). |

## Basic Concepts

### Application state

The server manages one instance of `AnytaskClient` in memory. The state is stored in `AppState` with a thread-safe lock (`threading.RLock`).

### Authentication

All operations require authentication:

- or via `POST /auth/login` with login/password
- either via `POST /auth/load-session` with an existing session file

After successful authentication, the client remains in memory and is reused for all subsequent requests.

### Session

When shutting down, the server closes the HTTP session. You can save the state with `POST /auth/save-session`.

## Endpoints

### Health Check

#### `GET /`

Checking the server status.

### Authentication

#### `POST /auth/login`

Authentication by username/password.

**Request body:**

```json
{
  "username": "student@example.com",
  "password": "secret"
}
```

**Answer (200):**

```json
{
  "ok": true,
  "message": "Logged in successfully"
}
```

**Errors:**

- `401` - invalid credentials
- `500` - network error

#### `POST /auth/load-session`

Recovering a session from a cookie.

**Request body:**

```json
{
  "session_file": "/path/to/.anytask_session.json"
}
```

**Answer (200):**

```json
{
  "ok": true,
  "message": "Session loaded successfully"
}
```

**Errors:**

- `404` - session file not found

#### `GET /auth/status`

Get the current authentication status.

**Answer (200):**

```json
{
  "authenticated": true,
  "username": "student@example.com"
}
```

or in an unauthenticated state:

```json
{
  "authenticated": false,
  "username": null
}
```

#### `POST /auth/save-session`

Save the current session to a file.

**Request body:**

```json
{
  "session_file": "/path/to/.anytask_session.json"
}
```

**Answer (200):**

```json
{
  "ok": true,
  "message": "Session saved to /path/to/.anytask_session.json"
}
```

#### `POST /auth/logout`

Close the current session.

**Answer (200):**

```json
{
  "ok": true,
  "message": "Logged out"
}
```

### Profile

#### `GET /profile/courses`

Load a list of available courses from the user profile.

**Query parameters:**

- No

**Answer (200):**

```json
{
  "courses": [
    {
      "id": 12345,
      "title": "Algorithms",
      "role": "student"
    },
    {
      "id": 12346,
      "title": "Databases",
      "role": "teacher"
    }
  ]
}
```

### Courses

#### `GET /courses/{course_id}`

Download course objectives.

**Path parameters:**

- `course_id` (int) - course ID

**Query parameters:**

- `fetch_descriptions` (bool, default=false) - for teacher-view load full task descriptions

**Answer (200):**

```json
{
  "course": {
    "id": 12345,
    "title": "Algorithms",
    "is_student": true,
    "tasks": [
      {
        "id": 1,
        "title": "Sorting",
        "score": 10,
        "status": "ok",
        "deadline": "2025-03-15"
      }
    ]
  }
}
```

#### `GET /courses/{course_id}/queue`

Load the course verification queue.

**Path parameters:**

- `course_id` (int) - course ID

**Query parameters:**

- `filter_task` - filter by task name (substring, case-insensitive)
- `filter_reviewer` - filter by reviewer name
- `filter_status` - filter by status
- `last_name_from` - lower limit of the last name range
- `last_name_to` - the upper limit of the last name range

**Answer (200):**

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

Download the course transcript.

**Path parameters:**

- `course_id` (int) - course ID

**Answer (200):**

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

Upload submission details by issue ID.

**Path parameters:**

- `issue_id` (int) - ID issue/submission

**Answer (200):**

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

Synchronize the course queue with the local JSON DB.

**Request body:**

```json
{
  "course_id": 12345,
  "db_file": "/path/to/queue_db.json",
  "course_title": "Algorithms",
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

**Answer (200):**

```json
{
  "ok": true,
  "message": "Synced 5 new entries",
  "synced_count": 5
}
```

#### `GET /db/entries`

Get a list of all records in the DB.

**Query parameters:**

- `course_id` (int, optional) - filter by course
- `state` (string, optional) - filter by state (new, pulled, processed)

**Answer (200):**

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

Pull new (state=new) records from the DB and mark them pulled.

**Request body:**

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

**Answer (200):**

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

Mark one entry as pulled.

**Request body:**

```json
{
  "db_file": "/path/to/queue_db.json",
  "course_id": 12345,
  "student_key": "/users/alice/",
  "assignment_key": "issue:421525"
}
```

**Answer (200):**

```json
{
  "ok": true,
  "message": "Entry marked as pulled"
}
```

#### `POST /db/entries/processed`

Mark the entry as processed.

**Request body:**

```json
{
  "db_file": "/path/to/queue_db.json",
  "course_id": 12345,
  "student_key": "/users/alice/",
  "assignment_key": "issue:421525"
}
```

**Answer (200):**

```json
{
  "ok": true,
  "message": "Entry marked as processed"
}
```

#### `POST /db/write`

Add a write event to issue_chain (for example grading/status update).

**Request body:**

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

**Answer (200):**

```json
{
  "ok": true,
  "message": "Write event recorded"
}
```

## HTTP status codes

| Code | Meaning |
| --- | --- |
| `200` | Successful request |
| `400` | Bad Request (invalid parameters) |
| `401` | Unauthorized (authentication required or invalid credentials) |
| `404` | Not Found (course/issue not found or file does not exist) |
| `422` | Unprocessable Entity (data validation error) |
| `500` | Internal Server Error |
| `502` | Bad Gateway (network error when accessing anytask.org) |

## Examples of use

### curl

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"student@example.com","password":"secret"}'

curl http://localhost:8000/profile/courses

curl http://localhost:8000/courses/12345

curl 'http://localhost:8000/courses/12345/queue?filter_task=hw'

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

resp = requests.post(f"{BASE_URL}/auth/login", json={
    "username": "student@example.com",
    "password": "secret"
})
assert resp.status_code == 200

resp = requests.get(f"{BASE_URL}/profile/courses")
courses = resp.json()["courses"]
print(courses)

course_id = 12345
resp = requests.get(f"{BASE_URL}/courses/{course_id}/queue")
entries = resp.json()["entries"]

resp = requests.post(f"{BASE_URL}/db/sync", json={
    "course_id": course_id,
    "db_file": "./queue_db.json",
    "pull": True,
    "limit": 10
})
print(resp.json())

resp = requests.post(f"{BASE_URL}/db/entries/pulled", json={
    "db_file": "./queue_db.json",
    "course_id": course_id,
    "student_key": "/users/alice/",
    "assignment_key": "issue:421525"
})

requests.post(f"{BASE_URL}/auth/logout")
```

## Thread-safety

The server uses `threading.RLock` for all operations with `AnytaskClient`. All requests to endpoints are safe for parallel execution.

## Restrictions

- The server stores only one authenticated session in memory (one user at a time)
- JSON DB operations require an explicit file path for each request
- Large queues load synchronously (block processing of other requests while loading)
