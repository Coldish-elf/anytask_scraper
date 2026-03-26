from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from pydantic import ValidationError
from starlette.requests import Request

from anytask_scraper.api import create_app
from anytask_scraper.api.schemas import (
    AddCommentRequest,
    DBPullRequest,
    SetGradeRequest,
    SetStatusRequest,
)
from anytask_scraper.client import WriteError
from anytask_scraper.json_db import QueueJsonDB
from anytask_scraper.models import WriteResult

from .html_builders import build_submission_page


def _route_endpoint(app, path: str, method: str):
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            return route.endpoint
    raise AssertionError(f"Route not found: {method} {path}")


def _request(app, path: str, method: str = "POST") -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "app": app,
    }
    return Request(scope)


@pytest.fixture()
def _setup():
    application = create_app()
    mock_client = MagicMock()
    mock_client._authenticated = True
    application.state.anytask._client = mock_client
    return application, mock_client


@pytest.fixture()
def application(_setup):
    return _setup[0]


@pytest.fixture()
def mock_anytask_client(_setup):
    return _setup[1]


class TestSetGradeEndpoint:
    def test_successful_grade(self, application, mock_anytask_client) -> None:
        mock_anytask_client.set_grade.return_value = WriteResult(
            success=True,
            action="grade",
            issue_id=500003,
            value="10.0",
            message="Grade set to 10.0",
        )
        endpoint = _route_endpoint(application, "/submissions/{issue_id}/grade", "POST")

        data = endpoint(
            500003,
            SetGradeRequest(grade=10.0),
            _request(application, "/submissions/500003/grade"),
        )

        assert data["success"] is True
        assert data["action"] == "grade"
        assert data["issue_id"] == 500003
        assert data["value"] == "10.0"
        mock_anytask_client.set_grade.assert_called_once_with(500003, 10.0, comment="")

    def test_grade_with_comment(self, application, mock_anytask_client) -> None:
        mock_anytask_client.set_grade.return_value = WriteResult(
            success=True,
            action="grade",
            issue_id=500003,
            value="10.0",
        )
        endpoint = _route_endpoint(application, "/submissions/{issue_id}/grade", "POST")

        endpoint(
            500003,
            SetGradeRequest(grade=10.0, comment="Well done"),
            _request(application, "/submissions/500003/grade"),
        )

        mock_anytask_client.set_grade.assert_called_once_with(500003, 10.0, comment="Well done")

    def test_grade_write_error(self, application, mock_anytask_client) -> None:
        mock_anytask_client.set_grade.side_effect = WriteError("Missing CSRF token")
        endpoint = _route_endpoint(application, "/submissions/{issue_id}/grade", "POST")

        with pytest.raises(HTTPException) as exc_info:
            endpoint(
                500003,
                SetGradeRequest(grade=10.0),
                _request(application, "/submissions/500003/grade"),
            )

        assert exc_info.value.status_code == 500
        assert "Missing CSRF token" in exc_info.value.detail

    def test_grade_missing_body(self) -> None:
        with pytest.raises(ValidationError):
            SetGradeRequest()


class TestSetStatusEndpoint:
    def test_successful_status_by_name(self, application, mock_anytask_client) -> None:
        mock_anytask_client.set_status.return_value = WriteResult(
            success=True,
            action="status",
            issue_id=500003,
            value="5",
        )
        endpoint = _route_endpoint(application, "/submissions/{issue_id}/status", "POST")

        data = endpoint(
            500003,
            SetStatusRequest(status="accepted"),
            _request(application, "/submissions/500003/status"),
        )

        assert data["success"] is True
        assert data["action"] == "status"
        mock_anytask_client.set_status.assert_called_once_with(500003, 5, comment="")

    def test_status_by_number(self, application, mock_anytask_client) -> None:
        mock_anytask_client.set_status.return_value = WriteResult(
            success=True,
            action="status",
            issue_id=500003,
            value="3",
        )
        endpoint = _route_endpoint(application, "/submissions/{issue_id}/status", "POST")

        endpoint(
            500003,
            SetStatusRequest(status="3"),
            _request(application, "/submissions/500003/status"),
        )

        mock_anytask_client.set_status.assert_called_once_with(500003, 3, comment="")

    def test_status_review(self, application, mock_anytask_client) -> None:
        mock_anytask_client.set_status.return_value = WriteResult(
            success=True,
            action="status",
            issue_id=500003,
            value="3",
        )
        endpoint = _route_endpoint(application, "/submissions/{issue_id}/status", "POST")

        endpoint(
            500003,
            SetStatusRequest(status="review"),
            _request(application, "/submissions/500003/status"),
        )

        mock_anytask_client.set_status.assert_called_once_with(500003, 3, comment="")

    def test_status_rework(self, application, mock_anytask_client) -> None:
        mock_anytask_client.set_status.return_value = WriteResult(
            success=True,
            action="status",
            issue_id=500003,
            value="4",
        )
        endpoint = _route_endpoint(application, "/submissions/{issue_id}/status", "POST")

        endpoint(
            500003,
            SetStatusRequest(status="rework"),
            _request(application, "/submissions/500003/status"),
        )

        mock_anytask_client.set_status.assert_called_once_with(500003, 4, comment="")

    def test_invalid_status_name(self, application) -> None:
        endpoint = _route_endpoint(application, "/submissions/{issue_id}/status", "POST")

        with pytest.raises(HTTPException) as exc_info:
            endpoint(
                500003,
                SetStatusRequest(status="invalid"),
                _request(application, "/submissions/500003/status"),
            )

        assert exc_info.value.status_code == 422
        assert "Invalid status" in exc_info.value.detail

    def test_status_with_comment(self, application, mock_anytask_client) -> None:
        mock_anytask_client.set_status.return_value = WriteResult(
            success=True,
            action="status",
            issue_id=500003,
            value="4",
        )
        endpoint = _route_endpoint(application, "/submissions/{issue_id}/status", "POST")

        endpoint(
            500003,
            SetStatusRequest(status="rework", comment="Please fix section 2"),
            _request(application, "/submissions/500003/status"),
        )

        mock_anytask_client.set_status.assert_called_once_with(
            500003, 4, comment="Please fix section 2"
        )

    def test_status_write_error(self, application, mock_anytask_client) -> None:
        mock_anytask_client.set_status.side_effect = WriteError("CSRF expired")
        endpoint = _route_endpoint(application, "/submissions/{issue_id}/status", "POST")

        with pytest.raises(HTTPException) as exc_info:
            endpoint(
                500003,
                SetStatusRequest(status="accepted"),
                _request(application, "/submissions/500003/status"),
            )

        assert exc_info.value.status_code == 500


class TestAddCommentEndpoint:
    def test_successful_comment(self, application, mock_anytask_client) -> None:
        mock_anytask_client.add_comment.return_value = WriteResult(
            success=True,
            action="comment",
            issue_id=500003,
            value="Looks good!",
            message="Comment added",
        )
        endpoint = _route_endpoint(application, "/submissions/{issue_id}/comment", "POST")

        data = endpoint(
            500003,
            AddCommentRequest(comment="Looks good!"),
            _request(application, "/submissions/500003/comment"),
        )

        assert data["success"] is True
        assert data["action"] == "comment"
        mock_anytask_client.add_comment.assert_called_once_with(500003, "Looks good!")

    def test_comment_write_error(self, application, mock_anytask_client) -> None:
        mock_anytask_client.add_comment.side_effect = WriteError("No form")
        endpoint = _route_endpoint(application, "/submissions/{issue_id}/comment", "POST")

        with pytest.raises(HTTPException) as exc_info:
            endpoint(
                500003,
                AddCommentRequest(comment="Hello"),
                _request(application, "/submissions/500003/comment"),
            )

        assert exc_info.value.status_code == 500
        assert "No form" in exc_info.value.detail

    def test_comment_missing_body(self) -> None:
        with pytest.raises(ValidationError):
            AddCommentRequest()


class TestReadSubmissionEndpoint:
    def test_submission_response_includes_issue_url(self, application, mock_anytask_client) -> None:
        mock_anytask_client.fetch_submission_page.return_value = build_submission_page(
            issue_id=500003,
            task_title="Task 1",
            student_name="Alice",
        )
        endpoint = _route_endpoint(application, "/submissions/{issue_id}", "GET")

        data = endpoint(500003, _request(application, "/submissions/500003", method="GET"))

        assert data["issue_id"] == 500003
        assert data["issue_url"] == "https://anytask.org/issue/500003"


def test_db_pull_passes_name_list_to_db(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_pull(self, **kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return []

    monkeypatch.setattr(QueueJsonDB, "pull_new_entries", fake_pull)
    application = create_app()
    endpoint = _route_endpoint(application, "/db/pull", "POST")

    pulled = endpoint(
        DBPullRequest(
            db_file="queue_db.json",
            course_id=1250,
            name_list=["Alice Smith"],
        ),
        _request(application, "/db/pull"),
    )

    assert pulled == []
    assert captured["course_id"] == 1250
    assert captured["name_list"] == ["Alice Smith"]
