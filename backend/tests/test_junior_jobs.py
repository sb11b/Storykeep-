from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.services.chat_docx import text_filename
from app.services.junior_jobs import (
    JOB_RUN_CAP,
    SEARCH_FAILED,
    _complete_job_turn,
    attach_unread_catalog,
    cron_matches,
    due_this_minute,
    enforce_daily_cap,
    format_unread_news_block,
    parse_cron,
    prompt_wants_my_news,
    require_cron_secret,
    tools_for_job,
    unread_feed_scope,
    unread_limit_from_prompt,
    unread_news_block,
)


class JuniorJobsTests(unittest.TestCase):
    def test_weekdays_cron_skips_saturday(self):
        saturday = datetime(2026, 9, 12, 8, 0, tzinfo=timezone.utc)
        monday = datetime(2026, 9, 14, 8, 0, tzinfo=timezone.utc)
        expr = "0 8 * * 1-5"
        self.assertFalse(cron_matches(expr, saturday))
        self.assertTrue(cron_matches(expr, monday))

    def test_parse_cron_rejects_junk(self):
        with self.assertRaises(HTTPException):
            parse_cron("every morning")

    def test_due_this_minute_skips_same_minute(self):
        now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
        job = SimpleNamespace(
            enabled=True,
            timezone="UTC",
            cron="0 12 * * *",
            last_run_at=now,
        )
        self.assertFalse(due_this_minute(job, now))
        job.last_run_at = None
        self.assertTrue(due_this_minute(job, now))

    def test_daily_cap(self):
        db = MagicMock()
        db.scalar.return_value = JOB_RUN_CAP
        with self.assertRaises(HTTPException) as raised:
            enforce_daily_cap(db, uuid4())
        self.assertEqual(raised.exception.status_code, 429)

    def test_cron_secret(self):
        request = SimpleNamespace(headers={"x-junior-cron-secret": "nope", "authorization": ""})
        with patch("app.services.junior_jobs.settings") as settings:
            settings.junior_cron_secret = "s3cret"
            with self.assertRaises(HTTPException) as raised:
                require_cron_secret(request)
            self.assertEqual(raised.exception.status_code, 401)
            request.headers = {"x-junior-cron-secret": "s3cret", "authorization": ""}
            require_cron_secret(request)

    def test_text_export_names(self):
        paper = "# Grammar-fixed DAT-200 paper\n\nBody."
        self.assertEqual(text_filename(paper, "md"), "Grammar-fixed DAT-200 paper.md")
        self.assertEqual(text_filename("Just a line\n\nMore.", "txt"), "junior-note.txt")

    def test_job_tools_default_off_no_code_interpreter(self):
        self.assertIsNone(tools_for_job(SimpleNamespace(web_search=False)))
        self.assertIsNone(tools_for_job(SimpleNamespace()))
        tools = tools_for_job(SimpleNamespace(web_search=True))
        self.assertEqual(tools, [{"type": "live_search"}])
        self.assertFalse(any(item.get("type") == "code_interpreter" for item in tools))

    def test_my_news_prefers_unread_titles(self):
        self.assertTrue(prompt_wants_my_news("Summarize my news"))
        self.assertTrue(prompt_wants_my_news("Use only my StoryKeep Unread from Fox News. Five newest by published time."))
        self.assertFalse(prompt_wants_my_news("what's on Reuters homepage"))
        self.assertEqual(unread_feed_scope("Unread from Fox News. Five newest."), "fox")
        self.assertEqual(unread_feed_scope("Unread Fox only"), "fox")
        self.assertEqual(unread_feed_scope("What is my news today?"), "fox_maybe_newsmax")
        self.assertEqual(unread_limit_from_prompt("Five newest by published time. Exact titles."), 5)
        self.assertEqual(unread_limit_from_prompt("Unread Fox only"), 5)
        article_id = uuid4()
        db = MagicMock()
        fox = MagicMock()
        fox.all.return_value = [(article_id, "DAT-200 quiz", "Fox News")]
        empty = MagicMock()
        empty.all.return_value = []
        excerpts = MagicMock()
        excerpts.all.return_value = [
            (article_id, "The quiz opens Monday. Bring a pencil. Class meets in room 4.", None)
        ]
        db.execute.side_effect = [fox, empty, excerpts]
        block = unread_news_block(db, uuid4(), "What is my news today?")
        self.assertIn("StoryKeep Unread", block)
        self.assertIn("DAT-200 quiz", block)
        self.assertIn(f"article_id: {article_id}", block)
        self.assertIn("Fox News", block)
        self.assertIn(f"[DAT-200 quiz](#article/{article_id})", block)
        self.assertIn("Bring a pencil", block)
        self.assertIn("summary", block.lower())
        self.assertNotIn("http://", block or "")
        self.assertIsNone(unread_news_block(db, uuid4(), "what's on Reuters homepage"))

    def test_unread_is_fox_unless_newsmax_has_items(self):
        from app.services.junior_jobs import unread_items

        fox_id, nm_id = uuid4(), uuid4()
        db = MagicMock()
        fox = MagicMock()
        fox.all.return_value = [(fox_id, "Fox A", "Fox News")]
        empty = MagicMock()
        empty.all.return_value = []
        db.execute.side_effect = [fox, empty]
        items = unread_items(db, uuid4(), "my Unread")
        self.assertEqual([item["title"] for item in items], ["Fox A"])

        db2 = MagicMock()
        fox2 = MagicMock()
        fox2.all.return_value = [(fox_id, "Fox A", "Fox News")]
        nm = MagicMock()
        nm.all.return_value = [(nm_id, "NM B", "Newsmax")]
        both = MagicMock()
        both.all.return_value = [(fox_id, "Fox A", "Fox News"), (nm_id, "NM B", "Newsmax")]
        db2.execute.side_effect = [fox2, nm, both]
        titles = [item["title"] for item in unread_items(db2, uuid4(), "Unread today")]
        self.assertEqual(titles, ["Fox A", "NM B"])

    def test_rewrite_publisher_urls_to_reader_hash(self):
        from app.services.junior_jobs import ensure_reader_links

        article_id = str(uuid4())
        items = [{"article_id": article_id, "title": "Senate vote", "feed": "Fox News"}]
        out = ensure_reader_links("[Senate vote](https://www.foxnews.com/politics/x)", items)
        self.assertIn(f"[Senate vote](#article/{article_id})", out)
        self.assertNotIn("foxnews.com", out)
        listed = ensure_reader_links("Here are five:", items)
        self.assertIn(f"- [Senate vote](#article/{article_id})", listed)

    def test_unread_catalog_is_reader_links(self):
        article_id = uuid4()
        block = format_unread_news_block(
            [{"article_id": str(article_id), "title": "Exact Fox title", "feed": "Fox News"}]
        )
        self.assertIn(f"[Exact Fox title](#article/{article_id})", block)
        self.assertIn("article_id:", block)
        self.assertNotIn("foxnews.com", block)
        attached = attach_unread_catalog([{"role": "user", "content": "Five newest Unread Fox"}], block)
        self.assertIn("#article/", attached[0]["content"])
        self.assertIn("Exact Fox title", attached[0]["content"])

    def test_top_five_news_summaries(self):
        from app.services.junior_jobs import format_news_summaries, summaries_look_thin, wants_news_summary

        self.assertTrue(wants_news_summary("summarize the top five most read news articles"))
        self.assertFalse(wants_news_summary("what's on today"))
        self.assertFalse(wants_news_summary("mark the email from Ada read"))
        items = [
            {
                "article_id": "abc",
                "title": "Senate vote",
                "feed": "Fox News",
                "excerpt": "The Senate voted Monday. The bill passed. Leaders spoke after the vote.",
            }
        ]
        self.assertTrue(summaries_look_thin("See the list", items))
        long = "The Senate voted Monday and the bill passed after a long debate. Leaders spoke. " * 3
        self.assertFalse(summaries_look_thin(long, items))
        text = format_news_summaries(items)
        self.assertIn("The Senate voted Monday.", text)
        self.assertIn("[Senate vote](#article/abc)", text)
        self.assertNotIn("foxnews.com", text)

    @patch("app.services.junior_jobs.chat_service.complete_once")
    def test_job_without_search_omits_tools(self, complete):
        complete.return_value = {"text": "ok", "model": "grok-4.6", "reasoning": "low"}
        _complete_job_turn(
            [{"role": "user", "content": "hello"}],
            model="grok-4.6",
            reasoning="low",
            tools=None,
        )
        kwargs = complete.call_args.kwargs
        self.assertNotIn("tools", kwargs)
        self.assertEqual(kwargs["reasoning_effort"], "low")

    @patch("app.services.junior_jobs.chat_service.complete_once")
    @patch("app.services.junior_jobs.chat_service.complete_with_web_search")
    def test_job_with_search_uses_responses_web_search(self, search, complete):
        search.return_value = {"text": "Reuters homepage: markets", "model": "grok-4.6", "reasoning": "low"}
        _complete_job_turn(
            [{"role": "user", "content": "what's on Reuters homepage"}],
            model="grok-4.6",
            reasoning="low",
            tools=tools_for_job(SimpleNamespace(web_search=True)),
        )
        complete.assert_not_called()
        kwargs = search.call_args.kwargs
        self.assertEqual(kwargs["model"], "grok-4.6")
        self.assertEqual(kwargs["reasoning_effort"], "low")

    @patch("app.services.junior_jobs.chat_service.complete_with_web_search")
    def test_search_failure_is_search_failed(self, search):
        search.side_effect = HTTPException(status_code=502, detail="xAI HTTP 422: unknown variant `web_search`")
        with self.assertRaises(HTTPException) as raised:
            _complete_job_turn(
                [],
                model="grok-4.6",
                reasoning="low",
                tools=[{"type": "web_search"}],
            )
        self.assertEqual(raised.exception.detail, SEARCH_FAILED)

    def test_parse_responses_text_from_reuters_shape(self):
        from app.services.chat import parse_responses_text, responses_used_search

        body = {
            "output": [
                {"type": "reasoning", "summary": [{"text": "q", "type": "summary_text"}]},
                {"type": "web_search_call", "status": "completed", "action": {"type": "open_page", "url": "https://www.reuters.com/"}},
                {
                    "content": [
                        {"type": "output_text", "text": "The Reuters homepage leads with markets."},
                    ]
                },
            ]
        }
        self.assertEqual(parse_responses_text(body), "The Reuters homepage leads with markets.")
        self.assertTrue(responses_used_search(body))

    def test_patch_job_updates_prompt_same_id(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.database import get_db
        from app.deps import get_current_user
        from app.routers import junior_jobs as jobs_router

        job_id = uuid4()
        user = SimpleNamespace(id=uuid4(), email="reader@example.com", is_demo_locked=False)
        now = datetime.now(timezone.utc)
        row = SimpleNamespace(
            id=job_id,
            user_id=user.id,
            title="Top Five",
            prompt="Top five news",
            cron="0 8 * * *",
            timezone="America/New_York",
            conversation_id=uuid4(),
            shelf=None,
            folder_id=None,
            include_article_id=None,
            model="grok-4.6",
            reasoning="low",
            xhigh=False,
            web_search=False,
            enabled=True,
            last_run_at=None,
            last_status="ok",
            created_at=now,
            updated_at=now,
        )
        db = MagicMock()

        def fake_db():
            yield db

        app = FastAPI()
        app.include_router(jobs_router.router, prefix="/api/v1")
        app.dependency_overrides[get_db] = fake_db
        app.dependency_overrides[get_current_user] = lambda: user
        with patch("app.services.junior_jobs.owned_job", return_value=row):
            client = TestClient(app)
            response = client.patch(
                f"/api/v1/junior/jobs/{job_id}",
                json={"prompt": "Unread Fox only"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], str(job_id))
        self.assertEqual(response.json()["prompt"], "Unread Fox only")
        self.assertEqual(row.prompt, "Unread Fox only")
        self.assertEqual(row.title, "Top Five")
        self.assertTrue(all(call.args[0] is row for call in db.add.call_args_list))
        self.assertEqual(db.add.call_count, 1)

    @patch("app.services.junior_jobs.logger")
    @patch("app.services.junior_jobs.chat_service.complete_once")
    def test_run_now_appends_assistant_and_logs_chars(self, complete, log):
        from app.services.junior_jobs import execute_job

        complete.return_value = {
            "text": "See https://www.foxnews.com/politics/example",
            "model": "grok-4.6",
            "reasoning": "low",
        }
        user = SimpleNamespace(id=uuid4(), email="reader@example.com", is_demo_locked=False)
        conversation = SimpleNamespace(id=uuid4(), last_model=None, last_reasoning=None, title=None, updated_at=None)
        job = SimpleNamespace(
            id=uuid4(),
            user_id=user.id,
            title="Top Five",
            prompt="Unread Fox only",
            conversation_id=conversation.id,
            include_article_id=None,
            model="grok-4.6",
            reasoning="low",
            xhigh=False,
            web_search=False,
            shelf=None,
            folder_id=None,
            last_run_at=None,
            last_status=None,
            updated_at=None,
        )
        article_ids = [uuid4() for _ in range(5)]
        assistant = SimpleNamespace(id=uuid4(), content="", conversation_id=conversation.id)
        db = MagicMock()
        db.get.return_value = user
        fox = MagicMock()
        fox.all.return_value = [(article_ids[i], f"Headline {i+1}", "Fox News") for i in range(5)]
        db.execute.return_value = fox

        def append(_db, _conv, *, role, content, **_kwargs):
            if role == "assistant":
                assistant.content = content
                return assistant
            return SimpleNamespace(id=uuid4(), content=content)

        with (
            patch("app.services.junior_jobs.is_locked", return_value=False),
            patch("app.services.junior_jobs.reject_locked"),
            patch("app.services.junior_jobs.enforce_daily_cap"),
            patch("app.services.junior_jobs.chat_service.enforce_rate_limit"),
            patch("app.services.junior_jobs.chat_service.rewrite_xai_model", return_value="grok-4.6"),
            patch("app.services.junior_jobs.grok_store.owned_conversation", return_value=conversation),
            patch("app.services.junior_jobs.grok_store.conversation_history", return_value=[]),
            patch("app.services.junior_jobs.grok_store.append_message", side_effect=append),
            patch("app.services.junior_jobs.junior_memory.system_section", return_value=None),
            patch(
                "app.services.junior_jobs.chat_service.build_xai_messages",
                return_value=[{"role": "system", "content": "s"}, {"role": "user", "content": "u"}],
            ),
        ):
            result = execute_job(db, job, trigger="manual")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["conversation_id"], conversation.id)
        self.assertEqual(result["assistant_message"], assistant)
        self.assertIn("#article/", assistant.content)
        self.assertNotIn("foxnews.com", assistant.content)
        self.assertEqual(assistant.content.count("#article/"), 5)
        args = log.info.call_args[0]
        self.assertIn("job_id=%s", args[0])
        self.assertEqual(args[1], job.id)
        self.assertEqual(args[2], "ok")
        self.assertEqual(args[3], len(assistant.content))

    @patch("app.services.junior_jobs.chat_service.complete_once")
    @patch("app.services.junior_jobs.chat_service.complete_with_code_execution")
    def test_run_snippet_uses_responses_not_completions(self, code_run, complete):
        from app.services.junior_jobs import run_snippet

        user = SimpleNamespace(id=uuid4(), email="reader@example.com", is_demo_locked=False)
        conversation = SimpleNamespace(id=uuid4(), last_model=None, last_reasoning=None)
        assistant = SimpleNamespace(id=uuid4(), conversation_id=conversation.id)
        db = MagicMock()
        code_run.return_value = {"text": "2", "model": "grok-4.6", "reasoning": "low"}
        with (
            patch("app.services.junior_jobs.reject_locked"),
            patch("app.services.junior_jobs.grok_store.owned_assistant_message", return_value=assistant),
            patch("app.services.junior_jobs.grok_store.owned_conversation", return_value=conversation),
            patch("app.services.junior_jobs.chat_service.enforce_rate_limit"),
            patch("app.services.junior_jobs.grok_store.conversation_history", return_value=[]),
            patch("app.services.junior_jobs.grok_store.append_message", side_effect=[SimpleNamespace(), SimpleNamespace()]),
        ):
            run_snippet(db, user, assistant.id, "print(1+1)")
        complete.assert_not_called()
        code_run.assert_called_once()
        kwargs = code_run.call_args.kwargs
        self.assertEqual(kwargs["reasoning_effort"], "low")
        self.assertNotIn("tools", kwargs)

    def test_complete_once_drops_code_interpreter_from_completions(self):
        from app.services.chat import build_chat_completions_payload, filter_completions_tools

        self.assertIsNone(filter_completions_tools([{"type": "code_interpreter"}]))
        self.assertIsNone(filter_completions_tools([{"type": "code_execution"}]))
        self.assertEqual(filter_completions_tools([{"type": "live_search"}]), [{"type": "live_search"}])
        payload = build_chat_completions_payload(
            messages=[{"role": "user", "content": "hello"}],
            model="grok-4.6",
            reasoning_effort="low",
            max_tokens=64,
            stream=True,
            temperature=0.6,
            tools=[{"type": "code_interpreter"}],
        )
        self.assertNotIn("tools", payload)
        self.assertNotIn("code_interpreter", str(payload))

    def test_patch_missing_job_is_404(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.database import get_db
        from app.deps import get_current_user
        from app.routers import junior_jobs as jobs_router

        user = SimpleNamespace(id=uuid4(), email="reader@example.com", is_demo_locked=False)
        db = MagicMock()

        def fake_db():
            yield db

        app = FastAPI()
        app.include_router(jobs_router.router, prefix="/api/v1")
        app.dependency_overrides[get_db] = fake_db
        app.dependency_overrides[get_current_user] = lambda: user
        with patch(
            "app.services.junior_jobs.owned_job",
            side_effect=HTTPException(status_code=404, detail="Job not found."),
        ):
            client = TestClient(app)
            response = client.patch(f"/api/v1/junior/jobs/{uuid4()}", json={"prompt": "Unread Fox only"})
        self.assertEqual(response.status_code, 404)
        db.add.assert_not_called()


if __name__ == "__main__":
    unittest.main()
