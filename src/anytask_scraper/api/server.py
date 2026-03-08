from __future__ import annotations

import dataclasses
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from anytask_scraper._queue_helpers import filter_queue_entries, parse_ajax_entry
from anytask_scraper.client import LoginError, WriteError
from anytask_scraper.json_db import QueueJsonDB
from anytask_scraper.parser import (
    extract_csrf_from_queue_page,
    extract_issue_id_from_breadcrumb,
    parse_course_page,
    parse_gradebook_page,
    parse_profile_page,
    parse_submission_page,
)

from .schemas import (
    AddCommentRequest,
    AuthStatusResponse,
    CourseSchema,
    DBEntry,
    DBMarkProcessedRequest,
    DBMarkPulledRequest,
    DBPullRequest,
    DBSyncRequest,
    DBSyncResponse,
    DBWriteRequest,
    GradebookSchema,
    HealthResponse,
    LoadSessionRequest,
    LoginRequest,
    OkResponse,
    ProfileCourseEntrySchema,
    ReviewQueueSchema,
    SaveSessionRequest,
    SetGradeRequest,
    SetStatusRequest,
    SubmissionSchema,
    WriteResultSchema,
)
from .state import AppState

logger = logging.getLogger(__name__)

VERSION = "1.0.0"

_bearer_scheme = HTTPBearer(auto_error=False)
_bearer_dependency = Depends(_bearer_scheme)


def _verify_token(
    credentials: HTTPAuthorizationCredentials | None = _bearer_dependency,  # noqa: B008
) -> None:
    expected = os.environ.get("ANYTASK_API_TOKEN", "")
    if not expected:
        return
    if credentials is None or credentials.credentials != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


def _validate_file_path(raw_path: str) -> Path:
    p = Path(raw_path)
    if p.is_absolute():
        raise HTTPException(status_code=400, detail="Absolute file paths are not allowed")
    try:
        resolved = (Path.cwd() / p).resolve()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid file path: {exc}") from exc
    if not str(resolved).startswith(str(Path.cwd().resolve())):
        raise HTTPException(status_code=400, detail="File path escapes the working directory")
    return resolved


def _handle_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LoginError):
        return HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, httpx.HTTPError):
        return HTTPException(status_code=502, detail=f"Upstream HTTP error: {exc}")
    if isinstance(exc, (ValueError, KeyError)):
        return HTTPException(status_code=422, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def create_app(startup_session_file: str | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        state = AppState(startup_session_file)
        app.state.anytask = state
        yield
        state.logout()

    app = FastAPI(
        title="anytask-scraper API",
        version=VERSION,
        lifespan=lifespan,
        dependencies=[Depends(_verify_token)],
    )

    _register_routes(app)
    return app


def _register_routes(app: FastAPI) -> None:
    @app.get("/", response_model=HealthResponse, tags=["root"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": VERSION}

    @app.post("/auth/login", response_model=OkResponse, tags=["auth"])
    def route_auth_login(req: LoginRequest, request: Request) -> dict[str, Any]:
        state: AppState = request.app.state.anytask
        try:
            state.login(req.username, req.password)
            return {"ok": True}
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc

    @app.post("/auth/load-session", response_model=OkResponse, tags=["auth"])
    def route_auth_load_session(req: LoadSessionRequest, request: Request) -> dict[str, Any]:
        state: AppState = request.app.state.anytask
        try:
            safe_path = _validate_file_path(req.session_file)
            loaded = state.load_session(str(safe_path))
            if not loaded:
                raise HTTPException(status_code=404, detail="Session file not found or empty")
            return {"ok": True}
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc

    @app.post("/auth/save-session", response_model=OkResponse, tags=["auth"])
    def route_auth_save_session(req: SaveSessionRequest, request: Request) -> dict[str, Any]:
        state: AppState = request.app.state.anytask
        try:
            safe_path = _validate_file_path(req.session_file)
            state.save_session(str(safe_path))
            return {"ok": True}
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc

    @app.get("/auth/status", response_model=AuthStatusResponse, tags=["auth"])
    def route_auth_status(request: Request) -> dict[str, Any]:
        state: AppState = request.app.state.anytask
        return {
            "authenticated": state.is_authenticated(),
            "username": state.get_username(),
        }

    @app.post("/auth/logout", response_model=OkResponse, tags=["auth"])
    def route_auth_logout(request: Request) -> dict[str, Any]:
        state: AppState = request.app.state.anytask
        state.logout()
        return {"ok": True}

    @app.get("/profile/courses", response_model=list[ProfileCourseEntrySchema], tags=["profile"])
    def route_profile_courses(request: Request) -> list[dict[str, Any]]:
        state: AppState = request.app.state.anytask
        try:

            def _fetch(client: Any) -> list[dict[str, Any]]:
                html = client.fetch_profile_page()
                entries = parse_profile_page(html)
                return [dataclasses.asdict(e) for e in entries]

            return state.with_client(_fetch)
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc

    @app.get("/courses/{course_id}", response_model=CourseSchema, tags=["courses"])
    def route_get_course(
        course_id: int,
        request: Request,
        fetch_descriptions: bool = Query(default=False),
    ) -> dict[str, Any]:
        state: AppState = request.app.state.anytask
        try:

            def _fetch(client: Any) -> dict[str, Any]:
                html = client.fetch_course_page(course_id)
                course = parse_course_page(html, course_id)
                if fetch_descriptions:
                    for task in course.tasks:
                        if task.task_id:
                            task.description = client.fetch_task_description(task.task_id)
                return dataclasses.asdict(course)

            return state.with_client(_fetch)
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc

    @app.get("/courses/{course_id}/queue", response_model=ReviewQueueSchema, tags=["courses"])
    def route_get_queue(
        course_id: int,
        request: Request,
        filter_task: str = Query(default=""),
        filter_reviewer: str = Query(default=""),
        filter_status: str = Query(default=""),
        last_name_from: str = Query(default=""),
        last_name_to: str = Query(default=""),
        deep: bool = Query(default=False),
    ) -> dict[str, Any]:
        state: AppState = request.app.state.anytask
        try:

            def _fetch(client: Any) -> dict[str, Any]:
                from anytask_scraper.models import ReviewQueue

                queue_html = client.fetch_queue_page(course_id)
                csrf = extract_csrf_from_queue_page(queue_html)
                if not csrf:
                    raise ValueError("Could not extract CSRF token from queue page")

                raw_entries = client.fetch_all_queue_entries(course_id, csrf)
                entries = [parse_ajax_entry(row) for row in raw_entries]
                entries = filter_queue_entries(
                    entries,
                    filter_task=filter_task,
                    filter_reviewer=filter_reviewer,
                    filter_status=filter_status,
                    last_name_from=last_name_from,
                    last_name_to=last_name_to,
                )

                queue = ReviewQueue(course_id=course_id, entries=entries)

                if deep:
                    for entry in entries:
                        if not (entry.has_issue_access and entry.issue_url):
                            continue
                        try:
                            sub_html = client.fetch_submission_page(entry.issue_url)
                            iid = extract_issue_id_from_breadcrumb(sub_html)
                            if iid == 0:
                                continue
                            sub = parse_submission_page(sub_html, iid, issue_url=entry.issue_url)
                            queue.submissions[entry.issue_url] = sub
                        except Exception:
                            logger.debug(
                                "Failed to fetch submission %s",
                                entry.issue_url,
                                exc_info=True,
                            )

                return {
                    "course_id": queue.course_id,
                    "entries": [dataclasses.asdict(e) for e in queue.entries],
                    "submissions": {k: dataclasses.asdict(v) for k, v in queue.submissions.items()},
                }

            return state.with_client(_fetch)
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc

    @app.get("/courses/{course_id}/gradebook", response_model=GradebookSchema, tags=["courses"])
    def route_get_gradebook(course_id: int, request: Request) -> dict[str, Any]:
        state: AppState = request.app.state.anytask
        try:

            def _fetch(client: Any) -> dict[str, Any]:
                html = client.fetch_gradebook_page(course_id)
                gradebook = parse_gradebook_page(html, course_id)
                return dataclasses.asdict(gradebook)

            return state.with_client(_fetch)
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc

    @app.get("/submissions/{issue_id}", response_model=SubmissionSchema, tags=["submissions"])
    def route_get_submission(issue_id: int, request: Request) -> dict[str, Any]:
        state: AppState = request.app.state.anytask
        try:

            def _fetch(client: Any) -> dict[str, Any]:
                url = f"https://anytask.org/issue/{issue_id}"
                html = client.fetch_submission_page(url)
                sub = parse_submission_page(html, issue_id, issue_url=url)
                return dataclasses.asdict(sub)

            return state.with_client(_fetch)
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc

    @app.post("/db/sync", response_model=DBSyncResponse, tags=["db"])
    def route_db_sync(req: DBSyncRequest, request: Request) -> dict[str, Any]:
        state: AppState = request.app.state.anytask
        try:

            def _fetch(client: Any) -> dict[str, Any]:
                from anytask_scraper.models import ReviewQueue

                queue_html = client.fetch_queue_page(req.course_id)
                csrf = extract_csrf_from_queue_page(queue_html)
                if not csrf:
                    raise ValueError("Could not extract CSRF token from queue page")

                raw_entries = client.fetch_all_queue_entries(req.course_id, csrf)
                entries = [parse_ajax_entry(row) for row in raw_entries]
                entries = filter_queue_entries(
                    entries,
                    filter_task=req.filter_task,
                    filter_reviewer=req.filter_reviewer,
                    filter_status=req.filter_status,
                    last_name_from=req.last_name_from,
                    last_name_to=req.last_name_to,
                )

                queue = ReviewQueue(course_id=req.course_id, entries=entries)

                if req.deep:
                    for entry in entries:
                        if not (entry.has_issue_access and entry.issue_url):
                            continue
                        try:
                            sub_html = client.fetch_submission_page(entry.issue_url)
                            iid = extract_issue_id_from_breadcrumb(sub_html)
                            if iid == 0:
                                continue
                            sub = parse_submission_page(sub_html, iid, issue_url=entry.issue_url)
                            queue.submissions[entry.issue_url] = sub
                        except Exception:
                            logger.debug(
                                "Failed to fetch submission %s",
                                entry.issue_url,
                                exc_info=True,
                            )

                safe_db = _validate_file_path(req.db_file)
                db = QueueJsonDB(safe_db)
                newly_flagged = db.sync_queue(queue, course_title=req.course_title)
                total = len(db.get_all_entries(course_id=req.course_id))
                return {"newly_flagged": newly_flagged, "total_entries": total}

            return state.with_client(_fetch)
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc

    @app.get("/db/entries", response_model=list[DBEntry], tags=["db"])
    def route_db_entries(
        request: Request,
        db_file: str = Query(default="./queue_db.json"),
        course_id: int | None = Query(default=None),
        state_filter: str = Query(default="all", alias="state"),
    ) -> list[dict[str, Any]]:
        try:
            safe_db = _validate_file_path(db_file)
            db = QueueJsonDB(safe_db)
            entries = db.get_all_entries(course_id=course_id)
            if state_filter != "all":
                entries = [e for e in entries if e.get("queue_state") == state_filter]
            return entries
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc

    @app.post("/db/pull", response_model=list[DBEntry], tags=["db"])
    def route_db_pull(req: DBPullRequest, request: Request) -> list[dict[str, Any]]:
        try:
            safe_db = _validate_file_path(req.db_file)
            db = QueueJsonDB(safe_db)
            pulled = db.pull_new_entries(
                course_id=req.course_id,
                limit=req.limit,
                student_contains=req.student_contains,
                task_contains=req.task_contains,
                status_contains=req.status_contains,
                reviewer_contains=req.reviewer_contains,
                last_name_from=req.last_name_from,
                last_name_to=req.last_name_to,
                issue_id=req.issue_id,
            )
            return pulled
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc

    @app.post("/db/entries/pulled", response_model=OkResponse, tags=["db"])
    def route_db_mark_pulled(req: DBMarkPulledRequest, request: Request) -> dict[str, Any]:
        try:
            safe_db = _validate_file_path(req.db_file)
            db = QueueJsonDB(safe_db)
            ok = db.mark_entry_pulled(
                course_id=req.course_id,
                student_key=req.student_key,
                assignment_key=req.assignment_key,
            )
            if not ok:
                raise HTTPException(status_code=404, detail="Entry not found in DB")
            return {"ok": True}
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc

    @app.post("/db/entries/processed", response_model=OkResponse, tags=["db"])
    def route_db_mark_processed(req: DBMarkProcessedRequest, request: Request) -> dict[str, Any]:
        try:
            safe_db = _validate_file_path(req.db_file)
            db = QueueJsonDB(safe_db)
            ok = db.mark_entry_processed(
                course_id=req.course_id,
                student_key=req.student_key,
                assignment_key=req.assignment_key,
            )
            if not ok:
                raise HTTPException(status_code=404, detail="Entry not found in DB")
            return {"ok": True}
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc

    @app.post("/db/write", response_model=OkResponse, tags=["db"])
    def route_db_write(req: DBWriteRequest, request: Request) -> dict[str, Any]:
        try:
            safe_db = _validate_file_path(req.db_file)
            db = QueueJsonDB(safe_db)
            ok = db.record_issue_write(
                course_id=req.course_id,
                issue_id=req.issue_id,
                action=req.action,
                value=req.value,
                author=req.author,
                note=req.note,
            )
            if not ok:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"Assignment not found for course={req.course_id}, issue_id={req.issue_id}"
                    ),
                )
            return {"ok": True}
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc

    @app.get("/db/diff", tags=["db"])
    def route_db_diff(
        request: Request,
        db_file: str = Query("./queue_db.json"),
        course_id: int | None = Query(None),
    ) -> list[dict[str, Any]]:
        try:
            safe_db = _validate_file_path(db_file)
            db = QueueJsonDB(safe_db)
            return db.get_changed_entries(course_id=course_id)
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc

    @app.get("/db/stats", tags=["db"])
    def route_db_stats(
        request: Request,
        db_file: str = Query("./queue_db.json"),
        course_id: int | None = Query(None),
    ) -> dict[str, Any]:
        try:
            safe_db = _validate_file_path(db_file)
            db = QueueJsonDB(safe_db)
            return db.statistics(course_id=course_id)
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc

    _status_name_map: dict[str, int] = {
        "review": 3,
        "rework": 4,
        "accepted": 5,
    }

    @app.post(
        "/submissions/{issue_id}/grade",
        response_model=WriteResultSchema,
        tags=["submissions"],
    )
    def route_set_grade(
        issue_id: int,
        req: SetGradeRequest,
        request: Request,
    ) -> dict[str, Any]:
        state: AppState = request.app.state.anytask
        try:

            def _write(client: Any) -> dict[str, Any]:
                result = client.set_grade(issue_id, req.grade, comment=req.comment)
                return dataclasses.asdict(result)

            return state.with_client(_write)
        except WriteError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc

    @app.post(
        "/submissions/{issue_id}/status",
        response_model=WriteResultSchema,
        tags=["submissions"],
    )
    def route_set_status(
        issue_id: int,
        req: SetStatusRequest,
        request: Request,
    ) -> dict[str, Any]:
        state: AppState = request.app.state.anytask
        try:
            raw = req.status.strip().lower()
            if raw in _status_name_map:
                status_code = _status_name_map[raw]
            else:
                try:
                    status_code = int(raw)
                except ValueError:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"Invalid status {req.status!r}. "
                            "Use 'review', 'rework', 'accepted', or integers 3/4/5."
                        ),
                    ) from None

            def _write(client: Any) -> dict[str, Any]:
                result = client.set_status(issue_id, status_code, comment=req.comment)
                return dataclasses.asdict(result)

            return state.with_client(_write)
        except WriteError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc

    @app.post(
        "/submissions/{issue_id}/comment",
        response_model=WriteResultSchema,
        tags=["submissions"],
    )
    def route_add_comment(
        issue_id: int,
        req: AddCommentRequest,
        request: Request,
    ) -> dict[str, Any]:
        state: AppState = request.app.state.anytask
        try:

            def _write(client: Any) -> dict[str, Any]:
                result = client.add_comment(issue_id, req.comment)
                return dataclasses.asdict(result)

            return state.with_client(_write)
        except WriteError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise _handle_error(exc) from exc
