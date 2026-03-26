from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from html import unescape

from bs4 import BeautifulSoup, Tag

from anytask_scraper.models import (
    Comment,
    Course,
    FileAttachment,
    Gradebook,
    GradebookEntry,
    GradebookGroup,
    ProfileCourseEntry,
    QueueFilters,
    Submission,
    SubmissionForms,
    Task,
)

logger = logging.getLogger(__name__)

_DEADLINE_RE = re.compile(r"(\d{2}):(\d{2})\s+(\d{2})-(\d{2})-(\d{4})")
_TASK_ID_RE = re.compile(r"collapse_(\d+)")
_TASK_EDIT_RE = re.compile(r"/task/edit/(\d+)")
_COURSE_URL_RE = re.compile(r"/course/(\d+)")


def parse_course_page(html: str, course_id: int) -> Course:
    logger.debug("Parsing course page for course %d", course_id)
    soup = BeautifulSoup(html, "lxml")

    title = _extract_course_title(soup)
    teachers = _extract_teachers(soup)

    tasks_tab = soup.find("div", id="tasks-tab")
    if tasks_tab is None:
        logger.warning("No tasks-tab found for course %d", course_id)
        return Course(course_id=course_id, title=title, teachers=teachers)

    has_groups = tasks_tab.find("div", id=re.compile(r"^collapse_group_\d+$")) is not None

    tasks = _parse_teacher_tasks(tasks_tab) if has_groups else _parse_student_tasks(tasks_tab)
    logger.debug("Parsed %d tasks for course %d", len(tasks), course_id)

    return Course(course_id=course_id, title=title, teachers=teachers, tasks=tasks)


def parse_profile_page(html: str) -> list[ProfileCourseEntry]:
    soup = BeautifulSoup(html, "lxml")
    seen: dict[int, ProfileCourseEntry] = {}

    teacher_div = soup.find("div", id="teacher_course")
    if teacher_div:
        for a_tag in teacher_div.find_all("a", href=_COURSE_URL_RE):
            m = _COURSE_URL_RE.search(str(a_tag["href"]))
            if m:
                cid = int(m.group(1))
                title = a_tag.get_text(strip=True)
                seen[cid] = ProfileCourseEntry(course_id=cid, title=title, role="teacher")

    student_div = soup.find("div", id="course_list")
    if student_div:
        for a_tag in student_div.find_all("a", href=_COURSE_URL_RE):
            m = _COURSE_URL_RE.search(str(a_tag["href"]))
            if m:
                cid = int(m.group(1))
                if cid not in seen:
                    title = a_tag.get_text(strip=True)
                    seen[cid] = ProfileCourseEntry(course_id=cid, title=title, role="student")

    return list(seen.values())


def _extract_course_title(soup: BeautifulSoup) -> str:
    card_title = soup.find("h5", class_="card-title")
    if card_title is None:
        return ""
    for span in card_title.find_all("span"):
        span.decompose()
    return card_title.get_text(strip=True)


def _extract_teachers(soup: BeautifulSoup) -> list[str]:
    teachers_p = soup.find("p", class_="course_teachers")
    if teachers_p is None:
        return []
    return [a.get_text(strip=True) for a in teachers_p.find_all("a")]


def _parse_deadline(text: str) -> datetime | None:
    m = _DEADLINE_RE.search(text)
    if m is None:
        return None
    hour, minute, day, month, year = (int(x) for x in m.groups())
    return datetime(year, month, day, hour, minute)


def _parse_student_tasks(tasks_tab: Tag) -> list[Task]:
    tasks: list[Task] = []
    tasks_table = tasks_tab.find("div", id="tasks-table")
    if tasks_table is None:
        return tasks

    for task_div in tasks_table.find_all("div", class_="tasks-list"):
        columns = [c for c in task_div.children if isinstance(c, Tag) and c.name == "div"]
        if len(columns) < 4:
            continue

        title_link = columns[0].find("a", attrs={"data-toggle": "collapse"})
        if title_link:
            title = title_link.get_text(strip=True)
            task_id = _extract_task_id_from_collapse(title_link)
        else:
            title = columns[0].get_text(strip=True)
            task_id = 0

        score = _parse_float(columns[1].get_text(strip=True))

        status_span = columns[2].find("span", class_="label")
        status = status_span.get_text(strip=True) if status_span else ""

        deadline = _parse_deadline(columns[3].get_text())

        submit_url = ""
        if len(columns) > 4:
            submit_link = columns[4].find("a", href=True)
            if submit_link:
                submit_url = str(submit_link["href"])

        description = ""
        if task_id:
            collapse_div = tasks_table.find("div", id=f"collapse_{task_id}")
            if collapse_div:
                inner_div = collapse_div.find("div")
                if inner_div:
                    description = inner_div.decode_contents().strip()

        tasks.append(
            Task(
                task_id=task_id,
                title=title,
                description=description,
                deadline=deadline,
                score=score,
                status=status,
                submit_url=submit_url,
            )
        )

    return tasks


def _parse_teacher_tasks(tasks_tab: Tag) -> list[Task]:
    tasks: list[Task] = []
    tasks_table = tasks_tab.find("div", id="tasks-table")
    if tasks_table is None:
        return tasks

    for group_div in tasks_table.find_all("div", id=re.compile(r"^collapse_group_\d+")):
        group_header = _find_group_header(group_div)
        section_name = group_header if group_header else ""

        for task_div in group_div.find_all("div", class_="tasks-list"):
            columns = [c for c in task_div.children if isinstance(c, Tag) and c.name == "div"]
            if len(columns) < 4:
                continue

            title = columns[0].get_text(strip=True)

            edit_link = columns[1].find("a", href=_TASK_EDIT_RE)
            task_id = 0
            edit_url = ""
            if edit_link:
                edit_url = str(edit_link["href"])
                m = _TASK_EDIT_RE.search(edit_url)
                if m:
                    task_id = int(m.group(1))

            score_span = columns[2].find("span", class_="label")
            max_score = _parse_float(score_span.get_text(strip=True)) if score_span else None

            deadline = _parse_deadline(columns[3].get_text())

            tasks.append(
                Task(
                    task_id=task_id,
                    title=title,
                    deadline=deadline,
                    max_score=max_score,
                    section=unescape(section_name),
                    edit_url=edit_url,
                )
            )

    return tasks


def _find_group_header(collapse_div: Tag) -> str:
    prev = collapse_div.find_previous_sibling("div")
    if prev is None:
        return ""
    h6 = prev.find("h6")
    if h6 is None:
        return ""
    for a_tag in h6.find_all("a"):
        a_tag.decompose()
    return h6.get_text(strip=True)


def _extract_task_id_from_collapse(tag: Tag) -> int:
    href = tag.get("href", "")
    m = _TASK_ID_RE.search(str(href))
    return int(m.group(1)) if m else 0


def strip_html(text: str) -> str:
    soup = BeautifulSoup(text, "lxml")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tag in soup.find_all(["p", "li", "tr", "div"]):
        tag.insert_before("\n")
    raw = soup.get_text()
    lines = [line.strip() for line in raw.splitlines()]
    result = "\n".join(line for line in lines if line)
    return unescape(result)


def parse_task_edit_page(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    textarea = soup.find("textarea", id="id_task_text")
    if textarea:
        return textarea.decode_contents().strip()
    ck_div = soup.find("div", class_=re.compile(r"ck-editor"))
    if ck_div:
        return ck_div.decode_contents().strip()
    return ""


def _parse_float(text: str) -> float | None:
    try:
        return float(text)
    except (ValueError, TypeError):
        return None


_CSRF_JS_RE = re.compile(r'csrfmiddlewaretoken["\'\]]\s*[:=]\s*["\']([^"\']+)["\']')
_ISSUE_ID_RE = re.compile(r"Issue:\s*(\d+)")
_COLAB_RE = re.compile(r"https?://colab\.research\.google\.com/drive/([a-zA-Z0-9_-]+)")
_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_UNSAFE_FOLDER_RE = re.compile(r'[/\\<>:"|?*\x00-\x1f]')


def parse_queue_filters(html: str) -> QueueFilters:
    soup = BeautifulSoup(html, "lxml")
    modal = soup.find("div", id="modal_filter")
    if modal is None:
        return QueueFilters()

    def _extract_options(name: str) -> list[tuple[str, str]]:
        select = modal.find("select", attrs={"name": name})
        if select is None:
            return []
        return [
            (str(opt.get("value", "")), opt.get_text(strip=True))
            for opt in select.find_all("option")
            if opt.get("value")
        ]

    return QueueFilters(
        students=_extract_options("students"),
        tasks=_extract_options("task"),
        reviewers=_extract_options("responsible"),
        statuses=_extract_options("status_field"),
    )


def extract_csrf_from_queue_page(html: str) -> str:
    m = _CSRF_JS_RE.search(html)
    return m.group(1) if m else ""


def parse_submission_page(html: str, issue_id: int, issue_url: str = "") -> Submission:
    logger.debug("Parsing submission page for issue %d", issue_id)
    soup = BeautifulSoup(html, "lxml")
    meta = _parse_submission_metadata(soup)
    comments = _parse_comment_thread(soup)
    forms = extract_submission_forms(html)

    return Submission(
        issue_id=issue_id,
        task_title=meta.get("task_title", ""),
        student_name=meta.get("student_name", ""),
        student_url=meta.get("student_url", ""),
        reviewer_name=meta.get("reviewer_name", ""),
        reviewer_url=meta.get("reviewer_url", ""),
        status=meta.get("status", ""),
        grade=meta.get("grade", ""),
        max_score=meta.get("max_score", ""),
        deadline=meta.get("deadline", ""),
        issue_url=issue_url,
        current_status=forms.current_status,
        status_options=list(forms.status_options),
        has_grade_form=forms.has_grade_form,
        has_status_form=forms.has_status_form,
        has_comment_form=forms.has_comment_form,
        comments=comments,
    )


def _parse_submission_metadata(soup: BeautifulSoup) -> dict[str, str]:
    result: dict[str, str] = {}
    accordion = soup.find("div", id="accordion2")
    if accordion is None:
        return result

    cards = accordion.find_all("div", class_="card")
    for card in cards:
        label_div = card.find("div", class_="accordion2-label")
        result_div = card.find("div", class_="accordion2-result")
        if label_div is None or result_div is None:
            continue

        label_text = label_div.get_text(strip=True).rstrip(":")
        result_text = result_div.get_text(strip=True)

        if "Задача" in label_text:
            btn = result_div.find("a", id="modal_task_description_btn")
            result["task_title"] = btn.get_text(strip=True) if btn else result_text

        elif "Студент" in label_text:
            user_link = result_div.find("a", class_="user")
            if user_link:
                result["student_name"] = user_link.get_text(strip=True)
                result["student_url"] = str(user_link.get("href", ""))

        elif "Проверяющий" in label_text:
            user_link = result_div.find("a", class_="user")
            if user_link:
                result["reviewer_name"] = user_link.get_text(strip=True)
                result["reviewer_url"] = str(user_link.get("href", ""))

        elif "Статус" in label_text:
            result["status"] = result_text

        elif "Оценка" in label_text:
            parts = result_text.split("из")
            if len(parts) == 2:
                result["grade"] = parts[0].strip()
                result["max_score"] = parts[1].strip()
            else:
                result["grade"] = result_text

        elif "Дата сдачи" in label_text:
            result["deadline"] = result_text

    return result


def _parse_comment_thread(soup: BeautifulSoup) -> list[Comment]:
    comments: list[Comment] = []
    history = soup.find("ul", class_="history")
    if history is None:
        return comments

    for li in history.find_all("li"):
        row = li.find("div", class_="row")
        if row is None:
            continue
        comment = _parse_single_comment(li)
        if comment is not None:
            comments.append(comment)

    return comments


def _parse_single_comment(li: Tag) -> Comment | None:
    row = li.find("div", class_="row")
    if row is None:
        return None

    author_link = row.find("strong")
    author_name = ""
    author_url = ""
    if author_link:
        a_tag = author_link.find("a", class_="card-link")
        if a_tag:
            author_name = a_tag.get_text(strip=True)
            author_url = str(a_tag.get("href", ""))

    timestamp = None
    time_small = row.find("small", class_="text-muted")
    if time_small:
        time_text = time_small.get_text(strip=True)
        timestamp = _parse_comment_timestamp(time_text)

    history_body = row.find("div", class_="history-body")
    is_after_deadline = False
    if history_body:
        classes = list(history_body.get("class") or [])
        if isinstance(classes, list):
            is_after_deadline = "after_deadline" in classes

    content_div = row.find("div", class_="issue-page-comment")
    content_html = ""
    is_system_event = False
    if content_div:
        content_html = content_div.decode_contents().strip()
    elif history_body:
        p_tag = history_body.find("p", recursive=False)
        if p_tag:
            content_html = p_tag.decode_contents().strip()
            is_system_event = True

    files = _parse_comment_files(row)

    links = _extract_urls_from_html(content_html)

    return Comment(
        author_name=author_name,
        author_url=author_url,
        timestamp=timestamp,
        content_html=content_html,
        files=files,
        links=links,
        is_after_deadline=is_after_deadline,
        is_system_event=is_system_event,
    )


_RU_MONTHS = {
    "Янв": 1,
    "Фев": 2,
    "Мар": 3,
    "Апр": 4,
    "Май": 5,
    "Июн": 6,
    "Июл": 7,
    "Авг": 8,
    "Сен": 9,
    "Окт": 10,
    "Ноя": 11,
    "Дек": 12,
}
_COMMENT_TS_RE = re.compile(r"(\d{1,2})\s+(\S+)\s+(\d{2}):(\d{2})")


def _parse_comment_timestamp(text: str) -> datetime | None:
    m = _COMMENT_TS_RE.search(text)
    if m is None:
        return None
    day = int(m.group(1))
    month_name = m.group(2)
    hour = int(m.group(3))
    minute = int(m.group(4))
    month = _RU_MONTHS.get(month_name)
    if month is None:
        return None
    now = datetime.now()
    candidate = datetime(now.year, month, day, hour, minute)
    if candidate - now > timedelta(days=31):
        candidate = datetime(now.year - 1, month, day, hour, minute)
    return candidate


def _parse_comment_files(container: Tag) -> list[FileAttachment]:
    files: list[FileAttachment] = []
    files_div = container.find("div", class_="files")
    if files_div is None:
        return files

    for ipynb_div in files_div.find_all("div", class_="ipynb-file-link"):
        toggle = ipynb_div.find("a", class_="dropdown-toggle")
        if toggle is None:
            continue
        filename = toggle.get_text(strip=True)
        dropdown = ipynb_div.find("div", class_="dropdown-menu")
        download_url = ""
        if dropdown:
            items = dropdown.find_all("a", class_="dropdown-item")
            preferred_url = ""
            media_url = ""
            fallback_url = ""
            for item in items:
                href = str(item.get("href", ""))
                if not href:
                    continue
                text = item.get_text(strip=True).lower()
                if not fallback_url:
                    fallback_url = href
                if "скач" in text or "download" in text:
                    preferred_url = href
                if "/media/files/" in href or href.startswith("/media/"):
                    media_url = href
            if preferred_url:
                download_url = preferred_url
            elif media_url:
                download_url = media_url
            else:
                download_url = fallback_url
        files.append(FileAttachment(filename=filename, download_url=download_url, is_notebook=True))

    for a_tag in files_div.find_all("a", recursive=True):
        if a_tag.find_parent("div", class_="ipynb-file-link"):
            continue
        href = str(a_tag.get("href", ""))
        filename = a_tag.get_text(strip=True)
        if href and filename:
            is_nb = filename.endswith(".ipynb")
            files.append(FileAttachment(filename=filename, download_url=href, is_notebook=is_nb))

    return files


def _extract_urls_from_html(html: str) -> list[str]:
    if not html:
        return []
    urls: list[str] = []
    soup = BeautifulSoup(html, "lxml")
    for a_tag in soup.find_all("a", href=True):
        href = str(a_tag["href"])
        if href.startswith("http"):
            urls.append(href)
    text = soup.get_text()
    for url_match in _URL_RE.finditer(text):
        url = url_match.group(0)
        if url not in urls:
            urls.append(url)
    return urls


def extract_issue_id_from_breadcrumb(html: str) -> int:
    m = _ISSUE_ID_RE.search(html)
    return int(m.group(1)) if m else 0


def format_student_folder(name: str) -> str:
    safe = name.strip().replace(" ", "_")
    safe = _UNSAFE_FOLDER_RE.sub("_", safe)
    safe = re.sub(r"_+", "_", safe)
    safe = safe.strip("_.")
    return safe or "unknown"


_TABLE_ID_RE = re.compile(r"table_results_(\d+)")


def parse_gradebook_page(html: str, course_id: int) -> Gradebook:
    logger.debug("Parsing gradebook page for course %d", course_id)
    soup = BeautifulSoup(html, "lxml")
    gradebook = Gradebook(course_id=course_id)

    for table in soup.find_all("table", class_="table-results"):
        group = _parse_gradebook_table(table)
        if group is not None:
            gradebook.groups.append(group)

    logger.debug("Parsed %d gradebook groups for course %d", len(gradebook.groups), course_id)
    return gradebook


def _parse_gradebook_table(table: Tag) -> GradebookGroup | None:
    table_id = str(table.get("id", ""))
    m = _TABLE_ID_RE.search(table_id)
    group_id = int(m.group(1)) if m else 0

    card = table.find_parent("div", class_="card")
    group_name = ""
    teacher_name = ""
    if card is not None:
        title_link = card.find("h5", class_="card-title")
        if title_link:
            a_tag = title_link.find("a", class_="card-link")
            if a_tag:
                group_name = a_tag.get_text(strip=True)
            teacher_a = title_link.find_all("a", class_="card-link")
            if len(teacher_a) > 1:
                teacher_name = teacher_a[-1].get_text(strip=True)

    thead = table.find("thead")
    if thead is None:
        return None

    task_titles: list[str] = []
    max_scores: dict[str, float] = {}
    header_row = thead.find("tr")
    if header_row is None:
        return None

    ths = header_row.find_all("th")
    for th in ths:
        if "dom-number" not in (th.get("class") or []) or "word-wrap" not in (
            th.get("class") or []
        ):
            continue
        a_tag = th.find("a")
        title = a_tag.get_text(strip=True) if a_tag else th.get_text(strip=True)
        task_titles.append(title)
        score_span = th.find("span", class_="label-inverse")
        if score_span:
            val = _parse_float(score_span.get_text(strip=True))
            if val is not None:
                max_scores[title] = val

    tbody = table.find("tbody")
    entries: list[GradebookEntry] = []
    if tbody is not None:
        for tr in tbody.find_all("tr", recursive=False):
            entry = _parse_gradebook_row(tr, task_titles)
            if entry is not None:
                entries.append(entry)

    return GradebookGroup(
        group_name=group_name,
        group_id=group_id,
        teacher_name=teacher_name,
        task_titles=task_titles,
        max_scores=max_scores,
        entries=entries,
    )


def _parse_gradebook_row(tr: Tag, task_titles: list[str]) -> GradebookEntry | None:
    tds = tr.find_all("td", recursive=False)
    if len(tds) < 3:
        return None

    student_td = tds[1]
    student_link = student_td.find("a", class_="card-link")
    if student_link is None:
        return None
    student_name = student_link.get_text(strip=True).replace("\xa0", " ")
    student_url = str(student_link.get("href", ""))

    scores: dict[str, float] = {}
    statuses: dict[str, str] = {}
    issue_urls: dict[str, str] = {}

    score_tds = tds[2:]
    for i, title in enumerate(task_titles):
        if i >= len(score_tds):
            break
        td = score_tds[i]
        span = td.find("span", class_="label")
        if span:
            val = _parse_float(span.get_text(strip=True))
            scores[title] = val if val is not None else 0.0
            style = str(span.get("style", ""))
            color_m = re.search(r"background-color:\s*(#[0-9a-fA-F]+)", style)
            if color_m:
                statuses[title] = color_m.group(1)
        a_tag = td.find("a", href=True)
        if a_tag:
            issue_urls[title] = str(a_tag["href"])

    total_score = 0.0
    sum_td = tr.find("td", class_="sum-score")
    if sum_td:
        sum_span = sum_td.find("span", class_="label")
        if sum_span:
            val = _parse_float(sum_span.get_text(strip=True))
            if val is not None:
                total_score = val

    return GradebookEntry(
        student_name=student_name,
        student_url=student_url,
        scores=scores,
        statuses=statuses,
        issue_urls=issue_urls,
        total_score=total_score,
    )


_CSRF_INPUT_RE = re.compile(
    r"""<input\s+type=['"]hidden['"]\s+name=['"]csrfmiddlewaretoken['"]\s+value=['"]([^'"]+)['"]""",
)


def extract_csrf_from_submission_page(html: str) -> str:
    m = _CSRF_INPUT_RE.search(html)
    return m.group(1) if m else ""


def extract_submission_forms(html: str) -> SubmissionForms:
    soup = BeautifulSoup(html, "lxml")

    csrf = extract_csrf_from_submission_page(html)

    issue_input = soup.find("input", attrs={"name": "issue_id", "type": "hidden"})
    issue_id = int(str(issue_input["value"])) if issue_input else 0

    mark_form = soup.find("form", id="mark_form")
    has_grade_form = mark_form is not None
    max_score: float | None = None
    if has_grade_form:
        max_input = soup.find("input", id="max_mark")
        if max_input:
            max_score = _parse_float(str(max_input.get("value", "")))

    status_form = soup.find("form", id="status_form")
    has_status_form = status_form is not None
    current_status = 0
    status_options: list[tuple[int, str]] = []
    if has_status_form and status_form is not None:
        select = status_form.find("select", attrs={"name": "status"})
        if select:
            for opt in select.find_all("option"):
                val = opt.get("value", "")
                if val:
                    try:
                        code = int(str(val))
                    except ValueError:
                        continue
                    label = opt.get_text(strip=True)
                    status_options.append((code, label))
                    if opt.get("selected") is not None:
                        current_status = code

    upload_form = soup.find("form", id="fileupload")
    has_comment_form = upload_form is not None

    return SubmissionForms(
        csrf_token=csrf,
        max_score=max_score,
        current_status=current_status,
        status_options=status_options,
        issue_id=issue_id,
        has_grade_form=has_grade_form,
        has_status_form=has_status_form,
        has_comment_form=has_comment_form,
    )
