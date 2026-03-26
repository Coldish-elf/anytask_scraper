from datetime import datetime

import anytask_scraper.parser as parser_mod
from anytask_scraper.parser import (
    extract_csrf_from_queue_page,
    extract_issue_id_from_breadcrumb,
    format_student_folder,
    parse_queue_filters,
    parse_submission_page,
)

from .html_builders import (
    SubmissionComment,
    SubmissionFile,
    build_queue_page,
    build_submission_page,
)
from .html_builders import (
    SubmissionForms as BuilderForms,
)


class TestQueueFilters:
    def setup_method(self) -> None:
        html = build_queue_page(
            students=[
                ("199942", "Broccoli McStuffins"),
                ("190814", "Noodle Waffleton"),
            ],
            tasks=[
                ("80012", "Numpy"),
                ("80013", "Pandas"),
                ("80015", "Join"),
            ],
            reviewers=[
                ("190516", "Зефирчик Пётр"),
            ],
            statuses=[
                ("1", "Новый"),
                ("700001", "На автоматической проверке"),
                ("6", "Требуется информация"),
                ("3", "На проверке"),
                ("4", "На доработке"),
                ("5", "Зачтено"),
            ],
        )
        self.filters = parse_queue_filters(html)

    def test_students_not_empty(self) -> None:
        assert len(self.filters.students) > 0

    def test_students_have_id_and_name(self) -> None:
        val, name = self.filters.students[0]
        assert val.isdigit()
        assert len(name) > 0

    def test_tasks_extracted(self) -> None:
        assert len(self.filters.tasks) >= 3
        task_names = [name for _, name in self.filters.tasks]
        assert "Numpy" in task_names

    def test_reviewers_extracted(self) -> None:
        assert len(self.filters.reviewers) >= 1

    def test_statuses_extracted(self) -> None:
        assert len(self.filters.statuses) >= 4
        status_names = [name for _, name in self.filters.statuses]
        assert "Зачтено" in status_names


class TestQueueCsrf:
    def test_csrf_extracted(self) -> None:
        html = build_queue_page(
            csrf_token="VNlNPlw3F4DPszbTK5njBSJF1iLR0HRHY9Se28KNORO99V4v69dY7czgdDq8jLVG",
        )
        csrf = extract_csrf_from_queue_page(html)
        assert len(csrf) > 20

    def test_csrf_empty_for_no_match(self) -> None:
        assert extract_csrf_from_queue_page("<html></html>") == ""


class TestSubmissionFile:
    def setup_method(self) -> None:
        html = build_submission_page(
            issue_id=500001,
            task_title="Join",
            student_name="Котлетов Борис",
            student_url="/users/kotletov/",
            reviewer_name="Кефиров Дмитрий",
            reviewer_url="/users/kefirov/",
            status="На проверке",
            grade="0",
            max_score="13",
            deadline="09-02-2026",
            comments=[
                SubmissionComment(
                    author_name="Котлетов Борис",
                    author_url="/users/kotletov/",
                    timestamp="06 Фев 12:00",
                    files=[
                        SubmissionFile(
                            filename="hw3.ipynb",
                            download_url="/media/files/7eb069d5/hw3.ipynb",
                            is_notebook=True,
                        ),
                    ],
                ),
            ],
            forms=None,
        )
        self.sub = parse_submission_page(html, 500001)

    def test_issue_id(self) -> None:
        assert self.sub.issue_id == 500001

    def test_task_title(self) -> None:
        assert self.sub.task_title == "Join"

    def test_student_name(self) -> None:
        assert "Котлетов" in self.sub.student_name

    def test_student_url(self) -> None:
        assert "/users/kotletov/" in self.sub.student_url

    def test_reviewer_name(self) -> None:
        assert "Кефиров" in self.sub.reviewer_name

    def test_status(self) -> None:
        assert self.sub.status != ""

    def test_grade(self) -> None:
        assert self.sub.grade != ""

    def test_max_score(self) -> None:
        assert self.sub.max_score != ""

    def test_deadline(self) -> None:
        assert "09-02-2026" in self.sub.deadline

    def test_has_comments(self) -> None:
        assert len(self.sub.comments) >= 1

    def test_first_comment_author(self) -> None:
        assert "Котлетов" in self.sub.comments[0].author_name

    def test_first_comment_has_file(self) -> None:
        assert len(self.sub.comments[0].files) >= 1
        assert self.sub.comments[0].files[0].filename == "hw3.ipynb"
        assert self.sub.comments[0].files[0].is_notebook

    def test_file_download_url(self) -> None:
        f = self.sub.comments[0].files[0]
        assert "/media/files/" in f.download_url


class TestSubmissionLink:
    def setup_method(self) -> None:
        html = build_submission_page(
            issue_id=500002,
            task_title="Join",
            comments=[
                SubmissionComment(
                    author_name="Блинчиков Игорь",
                    author_url="/users/blinchikov/",
                    timestamp="06 Фев 12:00",
                    content_html=("<p>https://colab.research.google.com/drive/1pwPQEXExY</p>"),
                ),
            ],
        )
        self.sub = parse_submission_page(html, 500002)

    def test_task_title(self) -> None:
        assert self.sub.task_title == "Join"

    def test_has_comments(self) -> None:
        assert len(self.sub.comments) >= 1

    def test_comment_has_colab_link(self) -> None:
        links = self.sub.comments[0].links
        colab_links = [u for u in links if "colab.research.google.com" in u]
        assert len(colab_links) >= 1

    def test_no_files(self) -> None:
        assert len(self.sub.comments[0].files) == 0


class TestSubmissionHard:
    def setup_method(self) -> None:
        html = build_submission_page(
            issue_id=500003,
            task_title="Телеграм-бот. Второй проект",
            comments=[
                SubmissionComment(
                    author_name="Шпротина Алина",
                    author_url="/users/shprotina/",
                    timestamp="05 Фев 10:00",
                    content_html="Первая версия",
                    files=[
                        SubmissionFile(filename="bot.py", download_url="/media/files/bot.py"),
                    ],
                ),
                SubmissionComment(
                    author_name="Сырникова Ольга",
                    author_url="/users/syrnikova/",
                    timestamp="06 Фев 14:00",
                    content_html=(
                        '<a href="https://github.com/muradpo/telegram_bot">'
                        "https://github.com/muradpo/telegram_bot</a>"
                    ),
                ),
            ],
        )
        self.sub = parse_submission_page(html, 500003)

    def test_task_title(self) -> None:
        assert "Телеграм-бот" in self.sub.task_title

    def test_multiple_comments(self) -> None:
        assert len(self.sub.comments) >= 2

    def test_comment_with_file(self) -> None:
        file_comments = [c for c in self.sub.comments if len(c.files) > 0]
        assert len(file_comments) >= 1

    def test_comment_with_github_link(self) -> None:
        link_comments = [c for c in self.sub.comments if any("github.com" in u for u in c.links)]
        assert len(link_comments) >= 1


class TestSubmissionHarder:
    def setup_method(self) -> None:
        many_files = [
            SubmissionFile(filename=f"file{i}.py", download_url=f"/media/files/file{i}.py")
            for i in range(6)
        ]
        html = build_submission_page(
            issue_id=500004,
            task_title="Телеграм-бот. Второй проект",
            student_name="Зефирчик Пётр",
            student_url="/users/zefirchik/",
            deadline="17-01-2026",
            comments=[
                SubmissionComment(
                    author_name="Зефирчик Пётр",
                    author_url="/users/zefirchik/",
                    timestamp="15 Янв 10:00",
                    is_after_deadline=True,
                    files=many_files,
                ),
                SubmissionComment(
                    author_name="Зефирчик Пётр",
                    author_url="/users/zefirchik/",
                    timestamp="16 Янв 08:00",
                    is_after_deadline=True,
                    content_html="Доработка",
                ),
            ],
        )
        self.sub = parse_submission_page(html, 500004)

    def test_task_title(self) -> None:
        assert "Телеграм-бот" in self.sub.task_title

    def test_student_name(self) -> None:
        assert "Зефирчик" in self.sub.student_name

    def test_reviewer_empty(self) -> None:
        assert self.sub.reviewer_name == ""

    def test_after_deadline_flag(self) -> None:
        after = [c for c in self.sub.comments if c.is_after_deadline]
        assert len(after) >= 1

    def test_many_files_in_comment(self) -> None:
        max_files = max(len(c.files) for c in self.sub.comments)
        assert max_files >= 5

    def test_deadline(self) -> None:
        assert "17-01-2026" in self.sub.deadline


def test_parse_submission_page_keeps_form_metadata() -> None:
    html = build_submission_page(
        issue_id=500005,
        task_title="Final Project",
        status="На проверке",
        max_score="20",
        forms=BuilderForms(
            has_grade_form=True,
            has_status_form=True,
            has_comment_form=True,
            max_score="20",
            status_options=[(3, "На проверке", False), (7, "Accepted", True)],
            issue_id=500005,
        ),
    )

    sub = parse_submission_page(html, 500005, issue_url="/issue/500005")

    assert sub.issue_url == "/issue/500005"
    assert sub.has_grade_form is True
    assert sub.has_status_form is True
    assert sub.has_comment_form is True
    assert sub.current_status == 7
    assert sub.status_options == [(3, "На проверке"), (7, "Accepted")]


def test_comment_timestamp_uses_previous_year_near_year_rollover(monkeypatch) -> None:
    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):  # type: ignore[override]
            return cls(2026, 1, 2, 12, 0, tzinfo=tz)

    monkeypatch.setattr(parser_mod, "datetime", _FrozenDateTime)
    html = build_submission_page(
        issue_id=500006,
        task_title="Join",
        comments=[
            SubmissionComment(
                author_name="Иван Иванов",
                author_url="/users/ivanov/",
                timestamp="31 Дек 23:50",
                content_html="<p>late upload</p>",
            )
        ],
    )

    sub = parse_submission_page(html, 500006)

    assert sub.comments[0].timestamp == datetime(2025, 12, 31, 23, 50)


class TestSubmissionAttachmentDownloadVariants:
    def test_prefers_download_link_for_absolute_media_url(self) -> None:
        html = build_submission_page(
            issue_id=500006,
            comments=[
                SubmissionComment(
                    author_name="Тапочкин Василий",
                    author_url="/users/tapochkin/",
                    files=[
                        SubmissionFile(
                            filename="hw2.ipynb",
                            download_url=(
                                "https://storage.yandexcloud.net/anytask-ng/S3/media/files/"
                                "c20de280-64e0-4bda-9781-0f9a87e98aa9/hw2.ipynb"
                            ),
                            is_notebook=True,
                        ),
                    ],
                ),
            ],
        )
        sub = parse_submission_page(html, 500006)
        file_att = sub.comments[0].files[0]
        assert file_att.filename == "hw2.ipynb"
        assert file_att.download_url == (
            "https://storage.yandexcloud.net/anytask-ng/S3/media/files/"
            "c20de280-64e0-4bda-9781-0f9a87e98aa9/hw2.ipynb"
        )


class TestSubmissionSystemEvents:
    def setup_method(self) -> None:
        html = build_submission_page(
            issue_id=500003,
            task_title="Телеграм-бот",
            comments=[
                SubmissionComment(
                    author_name="Кактусов Аркадий",
                    author_url="/users/kaktusov/",
                    timestamp="06 Фев 22:24",
                    content_html="code - github link",
                ),
                SubmissionComment(
                    author_name="Пончикова Марина",
                    author_url="/users/ponchikova/",
                    timestamp="24 Фев 22:58",
                    content_html="Добрый вечер! TG бот работает",
                ),
                SubmissionComment(
                    author_name="Пончикова Марина",
                    author_url="/users/ponchikova/",
                    timestamp="24 Фев 22:59",
                    content_html="Статус изменен: Зачтено",
                    is_system_event=True,
                ),
                SubmissionComment(
                    author_name="Пончикова Марина",
                    author_url="/users/ponchikova/",
                    timestamp="24 Фев 22:59",
                    content_html="Оценка изменена на 10.8",
                    is_system_event=True,
                ),
                SubmissionComment(
                    author_name="Пончикова Марина",
                    author_url="/users/ponchikova/",
                    timestamp="24 Фев 22:59",
                    content_html="Теперь задачу проверяет Пончикова Марина",
                    is_system_event=True,
                ),
            ],
        )
        self.sub = parse_submission_page(html, 500003)

    def test_has_system_events(self) -> None:
        system = [c for c in self.sub.comments if c.is_system_event]
        assert len(system) >= 3

    def test_status_change_parsed(self) -> None:
        system = [c for c in self.sub.comments if c.is_system_event]
        texts = [c.content_html for c in system]
        assert any("Статус изменен" in t for t in texts)

    def test_grade_change_parsed(self) -> None:
        system = [c for c in self.sub.comments if c.is_system_event]
        texts = [c.content_html for c in system]
        assert any("Оценка изменена" in t for t in texts)

    def test_reviewer_assignment_parsed(self) -> None:
        system = [c for c in self.sub.comments if c.is_system_event]
        texts = [c.content_html for c in system]
        assert any("проверяет" in t for t in texts)

    def test_regular_comments_not_system(self) -> None:
        regular = [c for c in self.sub.comments if not c.is_system_event]
        assert len(regular) >= 1

    def test_system_event_has_author(self) -> None:
        system = [c for c in self.sub.comments if c.is_system_event]
        for c in system:
            assert c.author_name != ""

    def test_system_event_has_timestamp(self) -> None:
        system = [c for c in self.sub.comments if c.is_system_event]
        for c in system:
            assert c.timestamp is not None


class TestFormatStudentFolder:
    def test_basic(self) -> None:
        assert format_student_folder("Фамилия Имя") == "Фамилия_Имя"

    def test_strips_whitespace(self) -> None:
        assert format_student_folder("  Фамилия Имя  ") == "Фамилия_Имя"

    def test_single_name(self) -> None:
        assert format_student_folder("Фамилия") == "Фамилия"


class TestIssueIdExtraction:
    def test_extract_from_inline_html(self) -> None:
        html = build_submission_page(issue_id=500001)
        assert extract_issue_id_from_breadcrumb(html) == 500001

    def test_no_match(self) -> None:
        assert extract_issue_id_from_breadcrumb("<html></html>") == 0
