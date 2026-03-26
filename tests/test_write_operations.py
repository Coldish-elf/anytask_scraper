from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from anytask_scraper.client import AnytaskClient, WriteError
from anytask_scraper.models import SubmissionForms
from anytask_scraper.parser import (
    extract_csrf_from_submission_page,
    extract_submission_forms,
)

from .html_builders import SubmissionForms as BuilderForms
from .html_builders import build_submission_page

LONG_CSRF = "a" * 64


def _submission_with_forms(
    *,
    has_grade: bool = False,
    has_status: bool = False,
    has_comment: bool = False,
    max_score: str = "",
    status_options: list[tuple[int, str, bool]] | None = None,
    issue_id: int = 500003,
) -> str:
    return build_submission_page(
        issue_id=issue_id,
        task_title="Телеграм-бот. Второй проект",
        csrf_token=LONG_CSRF,
        forms=BuilderForms(
            has_grade_form=has_grade,
            has_status_form=has_status,
            has_comment_form=has_comment,
            max_score=max_score,
            status_options=status_options or [],
            issue_id=issue_id,
        ),
    )


class TestExtractCsrfFromSubmissionPage:
    def test_extracts_from_hard(self) -> None:
        html = _submission_with_forms(has_grade=True, has_status=True, has_comment=True)
        csrf = extract_csrf_from_submission_page(html)
        assert len(csrf) > 20

    def test_extracts_from_file(self) -> None:
        html = build_submission_page(
            issue_id=500001,
            csrf_token=LONG_CSRF,
            forms=BuilderForms(has_comment_form=True, issue_id=500001),
        )
        csrf = extract_csrf_from_submission_page(html)
        assert len(csrf) > 20

    def test_extracts_from_link(self) -> None:
        html = build_submission_page(issue_id=500002, csrf_token=LONG_CSRF)
        csrf = extract_csrf_from_submission_page(html)
        assert len(csrf) > 20

    def test_extracts_from_harder(self) -> None:
        html = build_submission_page(issue_id=500004, csrf_token=LONG_CSRF)
        csrf = extract_csrf_from_submission_page(html)
        assert len(csrf) > 20

    def test_extracts_from_system_events(self) -> None:
        html = build_submission_page(issue_id=500003, csrf_token=LONG_CSRF)
        csrf = extract_csrf_from_submission_page(html)
        assert len(csrf) > 20

    def test_returns_empty_for_no_match(self) -> None:
        assert extract_csrf_from_submission_page("<html></html>") == ""


class TestExtractSubmissionFormsHard:
    def setup_method(self) -> None:
        html = _submission_with_forms(
            has_grade=True,
            has_status=True,
            has_comment=True,
            max_score="14",
            status_options=[
                (3, "На проверке", False),
                (4, "На доработке", False),
                (5, "Зачтено", True),
            ],
            issue_id=500003,
        )
        self.forms = extract_submission_forms(html)

    def test_csrf_token(self) -> None:
        assert len(self.forms.csrf_token) > 20

    def test_has_grade_form(self) -> None:
        assert self.forms.has_grade_form is True

    def test_has_status_form(self) -> None:
        assert self.forms.has_status_form is True

    def test_has_comment_form(self) -> None:
        assert self.forms.has_comment_form is True

    def test_max_score(self) -> None:
        assert self.forms.max_score is not None
        assert self.forms.max_score > 0

    def test_status_options(self) -> None:
        assert len(self.forms.status_options) >= 3
        codes = {code for code, _ in self.forms.status_options}
        assert {3, 4, 5} <= codes

    def test_current_status(self) -> None:
        assert self.forms.current_status == 5

    def test_issue_id(self) -> None:
        assert self.forms.issue_id == 500003

    def test_ignores_non_numeric_status_options(self) -> None:
        html = _submission_with_forms(
            has_status=True,
            status_options=[
                (3, "На проверке", False),
                (5, "Зачтено", True),
            ],
            issue_id=500003,
        ).replace(
            '<select name="status">',
            '<select name="status"><option value="">Выберите статус</option>',
            1,
        )

        forms = extract_submission_forms(html)

        assert forms.status_options == [(3, "На проверке"), (5, "Зачтено")]
        assert forms.current_status == 5


class TestExtractSubmissionFormsFile:
    def setup_method(self) -> None:
        html = build_submission_page(
            issue_id=500001,
            csrf_token=LONG_CSRF,
            forms=BuilderForms(has_comment_form=True, issue_id=500001),
        )
        self.forms = extract_submission_forms(html)

    def test_has_comment_form(self) -> None:
        assert self.forms.has_comment_form is True

    def test_csrf_present(self) -> None:
        assert len(self.forms.csrf_token) > 20


class TestExtractSubmissionFormsEmpty:
    def test_empty_html(self) -> None:
        forms = extract_submission_forms("<html><body></body></html>")
        assert forms.csrf_token == ""
        assert forms.has_grade_form is False
        assert forms.has_status_form is False
        assert forms.has_comment_form is False
        assert forms.issue_id == 0


class TestSetGrade:
    def _make_client(self) -> AnytaskClient:
        client = AnytaskClient("user", "pass")
        client._authenticated = True
        return client

    def _mock_forms(
        self,
        has_grade: bool = True,
        max_score: float | None = 14.0,
    ) -> SubmissionForms:
        return SubmissionForms(
            csrf_token="test-csrf-token",
            max_score=max_score,
            current_status=5,
            status_options=[(3, "На проверке"), (4, "На доработке"), (5, "Зачтено")],
            issue_id=500003,
            has_grade_form=has_grade,
            has_status_form=True,
            has_comment_form=True,
        )

    def test_successful_grade(self) -> None:
        client = self._make_client()
        with (
            patch.object(client, "_fetch_submission_forms", return_value=self._mock_forms()),
            patch.object(client, "_request") as mock_req,
        ):
            result = client.set_grade(500003, 10.0)

        assert result.success is True
        assert result.action == "grade"
        assert result.issue_id == 500003
        mock_req.assert_called_once()
        call_kwargs = mock_req.call_args
        assert call_kwargs[0][0] == "POST"
        assert "mark_form" in str(call_kwargs)

    def test_grade_with_comment(self) -> None:
        client = self._make_client()
        with (
            patch.object(client, "_fetch_submission_forms", return_value=self._mock_forms()),
            patch.object(client, "_request") as mock_req,
        ):
            result = client.set_grade(500003, 10.0, comment="Good work")

        assert result.success is True
        call_data = mock_req.call_args[1]["data"]
        assert call_data["comment_verdict"] == "Good work"

    def test_rejects_negative_grade(self) -> None:
        client = self._make_client()
        with patch.object(client, "_fetch_submission_forms", return_value=self._mock_forms()):
            result = client.set_grade(500003, -1.0)

        assert result.success is False
        assert "must be >= 0" in result.message

    def test_rejects_grade_above_max(self) -> None:
        client = self._make_client()
        with patch.object(
            client, "_fetch_submission_forms", return_value=self._mock_forms(max_score=14.0)
        ):
            result = client.set_grade(500003, 15.0)

        assert result.success is False
        assert "exceeds max" in result.message

    def test_no_grade_form(self) -> None:
        client = self._make_client()
        with patch.object(
            client, "_fetch_submission_forms", return_value=self._mock_forms(has_grade=False)
        ):
            result = client.set_grade(500003, 10.0)

        assert result.success is False
        assert "not available" in result.message

    def test_allows_grade_when_no_max_score(self) -> None:
        client = self._make_client()
        with (
            patch.object(
                client,
                "_fetch_submission_forms",
                return_value=self._mock_forms(max_score=None),
            ),
            patch.object(client, "_request"),
        ):
            result = client.set_grade(500003, 999.0)

        assert result.success is True


class TestSetStatus:
    def _make_client(self) -> AnytaskClient:
        client = AnytaskClient("user", "pass")
        client._authenticated = True
        return client

    def _mock_forms(self, has_status: bool = True) -> SubmissionForms:
        return SubmissionForms(
            csrf_token="test-csrf-token",
            max_score=14.0,
            current_status=5,
            status_options=[(3, "На проверке"), (4, "На доработке"), (5, "Зачтено")],
            issue_id=500003,
            has_grade_form=True,
            has_status_form=has_status,
            has_comment_form=True,
        )

    def test_successful_status(self) -> None:
        client = self._make_client()
        with (
            patch.object(client, "_fetch_submission_forms", return_value=self._mock_forms()),
            patch.object(client, "_request") as mock_req,
        ):
            result = client.set_status(500003, 4)

        assert result.success is True
        assert result.action == "status"
        call_data = mock_req.call_args[1]["data"]
        assert call_data["status"] == "4"
        assert call_data["form_name"] == "status_form"

    def test_rejects_invalid_status(self) -> None:
        client = self._make_client()
        with patch.object(client, "_fetch_submission_forms", return_value=self._mock_forms()):
            result = client.set_status(500003, 99)

        assert result.success is False
        assert "Invalid status" in result.message

    def test_no_status_form(self) -> None:
        client = self._make_client()
        with patch.object(
            client, "_fetch_submission_forms", return_value=self._mock_forms(has_status=False)
        ):
            result = client.set_status(500003, 5)

        assert result.success is False
        assert "not available" in result.message

    def test_status_with_comment(self) -> None:
        client = self._make_client()
        with (
            patch.object(client, "_fetch_submission_forms", return_value=self._mock_forms()),
            patch.object(client, "_request") as mock_req,
        ):
            result = client.set_status(500003, 5, comment="Approved")

        assert result.success is True
        call_data = mock_req.call_args[1]["data"]
        assert call_data["comment_verdict"] == "Approved"


class TestAddComment:
    def _make_client(self) -> AnytaskClient:
        client = AnytaskClient("user", "pass")
        client._authenticated = True
        return client

    def _mock_forms(self, has_comment: bool = True) -> SubmissionForms:
        return SubmissionForms(
            csrf_token="test-csrf-token",
            issue_id=500003,
            has_grade_form=True,
            has_status_form=True,
            has_comment_form=has_comment,
        )

    def test_successful_comment(self) -> None:
        client = self._make_client()
        with (
            patch.object(client, "_fetch_submission_forms", return_value=self._mock_forms()),
            patch.object(client, "_request") as mock_req,
        ):
            result = client.add_comment(500003, "Looks good!")

        assert result.success is True
        assert result.action == "comment"
        call_data = mock_req.call_args[1]["data"]
        assert call_data["comment"] == "Looks good!"
        assert call_data["form_name"] == "comment_form"
        assert call_data["issue_id"] == "500003"

    def test_rejects_empty_comment(self) -> None:
        client = self._make_client()
        with patch.object(client, "_fetch_submission_forms", return_value=self._mock_forms()):
            result = client.add_comment(500003, "   ")

        assert result.success is False
        assert "empty" in result.message

    def test_no_comment_form(self) -> None:
        client = self._make_client()
        with patch.object(
            client, "_fetch_submission_forms", return_value=self._mock_forms(has_comment=False)
        ):
            result = client.add_comment(500003, "Hello")

        assert result.success is False
        assert "not available" in result.message


class TestFetchSubmissionForms:
    def test_raises_write_error_on_missing_csrf(self) -> None:
        client = AnytaskClient("user", "pass")
        client._authenticated = True
        mock_resp = MagicMock()
        mock_resp.text = "<html></html>"
        mock_resp.url = "https://anytask.org/issue/500003/"
        with (
            patch.object(client, "_request", return_value=mock_resp),
            pytest.raises(WriteError),
        ):
            client._fetch_submission_forms(500003)
