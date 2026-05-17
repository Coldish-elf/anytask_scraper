from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from anytask_scraper.client import AnytaskClient, DownloadResult
from anytask_scraper.models import (
    Comment,
    Course,
    Gradebook,
    GradebookEntry,
    GradebookGroup,
    QueueEntry,
    ReviewQueue,
    Submission,
    Task,
)
from anytask_scraper.storage import (
    clone_submission_repos,
    download_submission_files,
    save_course_markdown,
    save_gradebook_markdown,
    save_queue_csv,
    save_queue_markdown,
    save_submissions_csv,
    save_submissions_json,
    save_submissions_markdown,
)


def test_save_queue_csv_supports_custom_filename_without_extension(tmp_path: Path) -> None:
    queue = ReviewQueue(
        course_id=1250,
        entries=[
            QueueEntry(
                student_name="Alice",
                student_url="/u/alice",
                task_title="Task 1",
                update_time="01-01-2026",
                mark="10",
                status_color="success",
                status_name="Done",
                responsible_name="Bob",
                responsible_url="/u/bob",
                has_issue_access=True,
                issue_url="/issue/1",
            )
        ],
    )

    path = save_queue_csv(queue, tmp_path, filename="custom_queue")

    assert path.name == "custom_queue.csv"
    assert path.exists()


def test_save_submissions_csv_applies_columns_and_custom_filename(tmp_path: Path) -> None:
    subs = [
        Submission(
            issue_id=7,
            task_title="Task 1",
            student_name="Alice",
            reviewer_name="Bob",
            status="Done",
            grade="10",
            max_score="10",
            comments=[
                Comment(
                    author_name="Bob",
                    author_url="/u/bob",
                    timestamp=None,
                    content_html="",
                )
            ],
        )
    ]

    path = save_submissions_csv(
        subs,
        course_id=1250,
        output_dir=tmp_path,
        columns=["Issue ID", "Task", "Comments"],
        filename="subs_export.csv",
    )

    assert path.name == "subs_export.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "Issue ID,Task,Comments"
    assert lines[1].startswith("7,Task 1,1")


def test_save_submissions_json_applies_columns(tmp_path: Path) -> None:
    subs = [
        Submission(
            issue_id=7,
            task_title="Task 1",
            student_name="Alice",
            reviewer_name="Bob",
            status="Done",
            grade="10",
            max_score="10",
        )
    ]

    path = save_submissions_json(
        subs,
        course_id=1250,
        output_dir=tmp_path,
        columns=["Issue ID", "Task"],
        filename="submissions_custom",
    )

    assert path.name == "submissions_custom.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["course_id"] == 1250
    assert payload["submissions"][0] == {"issue_id": 7, "task": "Task 1"}


def test_markdown_exports_escape_table_cells(tmp_path: Path) -> None:
    course = Course(
        course_id=1250,
        title="Course",
        tasks=[
            Task(
                task_id=1,
                title="Task | 1\nPart 2",
                status="Ready",
            )
        ],
    )
    queue = ReviewQueue(
        course_id=1250,
        entries=[
            QueueEntry(
                student_name="Alice | Smith",
                student_url="/u/alice",
                task_title="Task | 1\nPart 2",
                update_time="01-01-2026",
                mark="10",
                status_color="success",
                status_name="Done",
                responsible_name="Bob\nReviewer",
                responsible_url="/u/bob",
                has_issue_access=True,
                issue_url="/issue/1",
            )
        ],
    )
    submissions = [
        Submission(
            issue_id=7,
            task_title="Task | 1\nPart 2",
            student_name="Alice | Smith",
            reviewer_name="Bob\nReviewer",
            status="Done",
            grade="10",
            max_score="10",
        )
    ]
    gradebook = Gradebook(
        course_id=1250,
        groups=[
            GradebookGroup(
                group_name="Group | A",
                group_id=1,
                task_titles=["Task | 1\nPart 2"],
                entries=[
                    GradebookEntry(
                        student_name="Alice | Smith",
                        student_url="/u/alice",
                        scores={"Task | 1\nPart 2": 10.0},
                        total_score=10.0,
                    )
                ],
            )
        ],
    )

    course_md = save_course_markdown(course, tmp_path).read_text(encoding="utf-8")
    queue_md = save_queue_markdown(queue, tmp_path).read_text(encoding="utf-8")
    subs_md = save_submissions_markdown(submissions, 1250, tmp_path).read_text(encoding="utf-8")
    gradebook_md = save_gradebook_markdown(gradebook, tmp_path).read_text(encoding="utf-8")

    assert r"Task \| 1<br>Part 2" in course_md
    assert r"Alice \| Smith" in queue_md
    assert r"Bob<br>Reviewer" in subs_md
    assert r"Task \| 1<br>Part 2" in gradebook_md


class TestMakeSubmissionFilename:
    def _sub(self, student: str = "Ivanov Ivan", task: str = "Pandas HW") -> Submission:
        return Submission(issue_id=42, task_title=task, student_name=student)

    def test_basic_naming(self) -> None:
        from anytask_scraper.storage import _make_submission_filename

        used: set[str] = set()
        result = _make_submission_filename(self._sub(), ".ipynb", used)
        assert result == "Ivanov_Ivan_Pandas_HW.ipynb"

    def test_populates_used_set(self) -> None:
        from anytask_scraper.storage import _make_submission_filename

        used: set[str] = set()
        _make_submission_filename(self._sub(), ".ipynb", used)
        assert "Ivanov_Ivan_Pandas_HW.ipynb" in used

    def test_conflict_increments_index(self) -> None:
        from anytask_scraper.storage import _make_submission_filename

        used: set[str] = {"Ivanov_Ivan_Pandas_HW.py"}
        result = _make_submission_filename(self._sub(), ".py", used)
        assert result == "Ivanov_Ivan_Pandas_HW_2.py"

    def test_no_conflict_across_extensions(self) -> None:
        from anytask_scraper.storage import _make_submission_filename

        used: set[str] = {"Ivanov_Ivan_Pandas_HW.ipynb"}
        result = _make_submission_filename(self._sub(), ".csv", used)
        assert result == "Ivanov_Ivan_Pandas_HW.csv"

    def test_fallback_when_no_student_name(self) -> None:
        from anytask_scraper.storage import _make_submission_filename

        sub = Submission(issue_id=99, task_title="Task", student_name="")
        used: set[str] = set()
        result = _make_submission_filename(sub, ".py", used)
        assert result == "99_Task.py"

    def test_fallback_when_no_task_title(self) -> None:
        from anytask_scraper.storage import _make_submission_filename

        sub = Submission(issue_id=99, task_title="", student_name="Petrov Petr")
        used: set[str] = set()
        result = _make_submission_filename(sub, ".py", used)
        assert result == "Petrov_Petr_task_99.py"


class TestDownloadSubmissionFilesNaming:
    def _make_file_submission(
        self, student: str = "Ivanov Ivan", task: str = "Task 1"
    ) -> Submission:
        from anytask_scraper.models import FileAttachment

        fa = FileAttachment(filename="solution.py", download_url="/dl/sol.py")
        comment = Comment(
            author_name="", author_url="", timestamp=None, content_html="", files=[fa]
        )
        return Submission(issue_id=1, task_title=task, student_name=student, comments=[comment])

    def test_regular_file_uses_student_task_name(self, tmp_path: Path) -> None:
        from anytask_scraper.storage import download_submission_files

        sub = self._make_file_submission()
        with AnytaskClient() as client:

            def fake_dl(url: str, output_path: str) -> DownloadResult:
                Path(output_path).write_text("x")
                return DownloadResult(success=True, path=output_path, reason="ok")

            client.download_file = fake_dl  # type: ignore[method-assign]
            result = download_submission_files(client, sub, tmp_path)
        names = [p.name for p in result.values()]
        assert names == ["Ivanov_Ivan_Task_1.py"]

    def test_flat_mode_no_subfolder(self, tmp_path: Path) -> None:
        from anytask_scraper.storage import download_submission_files

        sub = self._make_file_submission()
        with AnytaskClient() as client:

            def fake_dl(url: str, output_path: str) -> DownloadResult:
                Path(output_path).write_text("x")
                return DownloadResult(success=True, path=output_path, reason="ok")

            client.download_file = fake_dl  # type: ignore[method-assign]
            result = download_submission_files(client, sub, tmp_path, flat=True)
        for path in result.values():
            assert path.parent == tmp_path

    def test_folder_mode_creates_student_subfolder(self, tmp_path: Path) -> None:
        from anytask_scraper.storage import download_submission_files

        sub = self._make_file_submission()
        with AnytaskClient() as client:

            def fake_dl(url: str, output_path: str) -> DownloadResult:
                Path(output_path).write_text("x")
                return DownloadResult(success=True, path=output_path, reason="ok")

            client.download_file = fake_dl  # type: ignore[method-assign]
            result = download_submission_files(client, sub, tmp_path, flat=False)
        for path in result.values():
            assert path.parent.name == "Ivanov_Ivan"

    def test_conflict_resolution_multiple_same_ext(self, tmp_path: Path) -> None:
        from anytask_scraper.models import FileAttachment
        from anytask_scraper.storage import download_submission_files

        fa1 = FileAttachment(filename="a.py", download_url="/dl/a")
        fa2 = FileAttachment(filename="b.py", download_url="/dl/b")
        comment = Comment(
            author_name="", author_url="", timestamp=None, content_html="", files=[fa1, fa2]
        )
        sub = Submission(
            issue_id=1, task_title="Task 1", student_name="Ivanov Ivan", comments=[comment]
        )
        with AnytaskClient() as client:

            def fake_dl(url: str, output_path: str) -> DownloadResult:
                Path(output_path).write_text("x")
                return DownloadResult(success=True, path=output_path, reason="ok")

            client.download_file = fake_dl  # type: ignore[method-assign]
            result = download_submission_files(client, sub, tmp_path)
        names = {p.name for p in result.values()}
        assert "Ivanov_Ivan_Task_1.py" in names
        assert "Ivanov_Ivan_Task_1_2.py" in names


class TestCloneSubmissionReposFlat:
    def test_flat_mode_clones_directly_into_base_dir(self, tmp_path: Path) -> None:
        from anytask_scraper.github_clone import CloneResult, GitHubRepoInfo

        github_url = "https://github.com/user/myrepo"
        comment = Comment(
            author_name="", author_url="", timestamp=None, content_html="", links=[github_url]
        )
        sub = Submission(
            issue_id=1, task_title="Task", student_name="Ivanov Ivan", comments=[comment]
        )

        fake_info = GitHubRepoInfo(owner="user", repo="myrepo", url=github_url)
        fake_result = CloneResult(success=True, path=tmp_path / "myrepo")

        with (
            patch("anytask_scraper.github_clone.extract_github_links", return_value=[fake_info]),
            patch(
                "anytask_scraper.github_clone.clone_github_repo", return_value=fake_result
            ) as mock_clone,
        ):
            clone_submission_repos(sub, tmp_path, flat=True)

        mock_clone.assert_called_once_with(fake_info, tmp_path, timeout=120)

    def test_default_mode_uses_student_subfolder(self, tmp_path: Path) -> None:
        from anytask_scraper.github_clone import CloneResult, GitHubRepoInfo

        github_url = "https://github.com/user/myrepo"
        comment = Comment(
            author_name="", author_url="", timestamp=None, content_html="", links=[github_url]
        )
        sub = Submission(
            issue_id=1, task_title="Task", student_name="Ivanov Ivan", comments=[comment]
        )

        fake_info = GitHubRepoInfo(owner="user", repo="myrepo", url=github_url)
        fake_result = CloneResult(success=True, path=tmp_path / "Ivanov_Ivan" / "myrepo")

        with (
            patch("anytask_scraper.github_clone.extract_github_links", return_value=[fake_info]),
            patch(
                "anytask_scraper.github_clone.clone_github_repo", return_value=fake_result
            ) as mock_clone,
        ):
            clone_submission_repos(sub, tmp_path)

        mock_clone.assert_called_once_with(fake_info, tmp_path / "Ivanov_Ivan", timeout=120)


def _make_comment(links: list[str]) -> Comment:
    return Comment(
        author_name="Alice",
        author_url="/u/alice",
        timestamp=None,
        content_html="",
        links=links,
    )


def _make_submission(
    issue_id: int = 42,
    student_name: str = "Alice Smith",
    comments: list[Comment] | None = None,
) -> Submission:
    return Submission(
        issue_id=issue_id,
        task_title="Task 1",
        student_name=student_name,
        comments=comments or [],
    )


class TestCloneSubmissionRepos:
    def test_clones_github_links(self, tmp_path: Path) -> None:
        from anytask_scraper.github_clone import CloneResult, GitHubRepoInfo

        github_url = "https://github.com/octocat/hello-world"
        colab_url = "https://colab.research.google.com/drive/abc123"
        submission = _make_submission(comments=[_make_comment([github_url, colab_url])])

        fake_info = GitHubRepoInfo(owner="octocat", repo="hello-world", url=github_url)
        fake_path = tmp_path / "alice_smith" / "hello-world"
        fake_result = CloneResult(success=True, path=fake_path)

        with (
            patch(
                "anytask_scraper.github_clone.extract_github_links",
                return_value=[fake_info],
            ) as mock_extract,
            patch(
                "anytask_scraper.github_clone.clone_github_repo",
                return_value=fake_result,
            ) as mock_clone,
        ):
            result = clone_submission_repos(submission, tmp_path)

        mock_extract.assert_called_once_with([github_url, colab_url])
        mock_clone.assert_called_once_with(fake_info, tmp_path / "Alice_Smith", timeout=120)
        assert result == {github_url: fake_path}

    def test_no_github_links(self, tmp_path: Path) -> None:
        submission = _make_submission(
            comments=[
                _make_comment(["https://colab.research.google.com/drive/xyz"]),
                _make_comment(["https://example.com/report.pdf"]),
            ]
        )

        with (
            patch(
                "anytask_scraper.github_clone.extract_github_links",
                return_value=[],
            ),
            patch(
                "anytask_scraper.github_clone.clone_github_repo",
            ) as mock_clone,
        ):
            result = clone_submission_repos(submission, tmp_path)

        mock_clone.assert_not_called()
        assert result == {}

    def test_creates_student_folder(self, tmp_path: Path) -> None:
        submission = _make_submission(student_name="Jane Doe")

        with patch("anytask_scraper.github_clone.extract_github_links", return_value=[]):
            clone_submission_repos(submission, tmp_path)

        assert (tmp_path / "Jane_Doe").is_dir()

    def test_uses_issue_id_when_no_name(self, tmp_path: Path) -> None:
        submission = _make_submission(issue_id=99, student_name="")

        with patch("anytask_scraper.github_clone.extract_github_links", return_value=[]):
            clone_submission_repos(submission, tmp_path)

        assert (tmp_path / "99").is_dir()

    def test_downloads_colab_notebooks_with_student_and_task_name(self, tmp_path: Path) -> None:
        colab_url = "https://colab.research.google.com/drive/abc123"
        submission = _make_submission(
            issue_id=42,
            student_name="Ivanov Ivan",
            comments=[_make_comment([colab_url])],
        )
        recorded_paths: list[Path] = []

        with AnytaskClient() as client:

            def fake_download(url: str, output_path: str) -> DownloadResult:
                assert url == colab_url
                path = Path(output_path)
                recorded_paths.append(path)
                path.write_text("{}", encoding="utf-8")
                return DownloadResult(success=True, path=output_path, reason="ok")

            client.download_colab_notebook = fake_download  # type: ignore[method-assign]
            result = download_submission_files(client, submission, tmp_path)

        expected = tmp_path / "Ivanov_Ivan" / "Ivanov_Ivan_Task_1.ipynb"
        assert recorded_paths == [expected]
        assert result == {colab_url: expected}
        assert expected.read_text(encoding="utf-8") == "{}"

    def test_clone_failure_logged(self, tmp_path: Path) -> None:
        from anytask_scraper.github_clone import CloneResult, GitHubRepoInfo

        github_url = "https://github.com/badorg/broken-repo"
        submission = _make_submission(comments=[_make_comment([github_url])])

        fake_info = GitHubRepoInfo(owner="badorg", repo="broken-repo", url=github_url)
        fake_path = tmp_path / "alice_smith" / "broken-repo"
        fake_result = CloneResult(success=False, path=fake_path, reason="auth_failed")

        with (
            patch(
                "anytask_scraper.github_clone.extract_github_links",
                return_value=[fake_info],
            ),
            patch(
                "anytask_scraper.github_clone.clone_github_repo",
                return_value=fake_result,
            ),
        ):
            result = clone_submission_repos(submission, tmp_path)

        assert result == {}
