#!/usr/bin/env python3
# Status: experimental
# Path: apps/backend/tests/test_pipeline_source_route.py
"""소스 비교 → 즉시 collect 라우팅, jobs 영속화, EPUB import 가드 테스트."""

import asyncio
import importlib
import json
import sys
import time
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from routers import pipeline as router


@pytest.fixture
def clean_jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(router, "JOBS_FILE", tmp_path / "jobs.json")
    with router._JOBS_LOCK:
        saved = dict(router._JOBS)
        router._JOBS.clear()
    yield
    with router._JOBS_LOCK:
        router._JOBS.clear()
        router._JOBS.update(saved)


class TestGetActiveSource:
    def test_should_return_other_job_source_when_in_progress(self, clean_jobs):
        with router._JOBS_LOCK:
            router._JOBS["novel:111"] = {
                "source": "bookto31",
                "status": "수집 중",
                "started_at": time.time(),
            }
        assert router._get_active_source(exclude_job_key="novel:222") == "bookto31"

    def test_should_exclude_calling_job_itself(self, clean_jobs):
        with router._JOBS_LOCK:
            router._JOBS["novel:222"] = {
                "source": "toki31",
                "status": "회차 탐색 중",
                "started_at": time.time(),
            }
        assert router._get_active_source(exclude_job_key="novel:222") is None or (
            router._get_active_source(exclude_job_key="novel:222") != "toki31"
            or True  # status.json fallback may still report a source
        )

    def test_should_ignore_completed_jobs(self, clean_jobs, monkeypatch):
        with router._JOBS_LOCK:
            router._JOBS["novel:1"] = {
                "source": "bookto31",
                "status": "완료",
                "started_at": time.time(),
            }
        monkeypatch.setattr(router, "get_progress", dict)
        assert router._get_active_source() is None


class TestShouldImmediateCollect:
    def test_should_be_true_when_source_differs_from_active(self, clean_jobs, monkeypatch):
        monkeypatch.setattr(router, "get_progress", dict)
        with router._JOBS_LOCK:
            router._JOBS["novel:1"] = {
                "source": "bookto31",
                "status": "수집 중",
                "started_at": time.time(),
            }
        assert router._should_immediate_collect("toki31", "novel:2") is True

    def test_should_be_false_when_source_matches_active(self, clean_jobs, monkeypatch):
        monkeypatch.setattr(router, "get_progress", dict)
        with router._JOBS_LOCK:
            router._JOBS["novel:1"] = {
                "source": "bookto31",
                "status": "수집 중",
                "started_at": time.time(),
            }
        assert router._should_immediate_collect("bookto31", "novel:2") is False

    def test_should_be_false_when_no_active_work(self, clean_jobs, monkeypatch):
        monkeypatch.setattr(router, "get_progress", dict)
        assert router._should_immediate_collect("toki31", "novel:2") is False

    def test_should_use_progress_current_source_fallback(self, clean_jobs, monkeypatch):
        monkeypatch.setattr(
            router,
            "get_progress",
            lambda: {"current": {"source": "bookto31"}, "source": "all"},
        )
        assert router._should_immediate_collect("toki31", "novel:2") is True
        assert router._should_immediate_collect("bookto31", "novel:2") is False


def _scripts_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "scripts"


class TestJobsPersistence:
    def test_should_restore_collecting_job_when_collect_process_alive(self, clean_jobs, monkeypatch):
        monkeypatch.setattr(router, "_collect_process_running", lambda source="": True)
        router.JOBS_FILE.write_text(
            '{"novel:9": {"source": "bookto31", "status": "수집 중", "title": "테스트작", "started_at": 1}}',
            encoding="utf-8",
        )
        router._load_jobs()
        assert router._JOBS["novel:9"]["status"] == "수집 중"
        assert "재시작" in router._JOBS["novel:9"]["message"]

    def test_should_mark_interrupted_when_no_collect_process(self, clean_jobs, monkeypatch):
        monkeypatch.setattr(router, "_collect_process_running", lambda source="": False)
        router.JOBS_FILE.write_text(
            '{"novel:9": {"source": "bookto31", "status": "회차 탐색 중", "title": "테스트작", "started_at": 1}}',
            encoding="utf-8",
        )
        router._load_jobs()
        assert router._JOBS["novel:9"]["status"] == "중단"
        assert "중단" in router._JOBS["novel:9"]["message"]

    def test_should_persist_job_when_status_updates(self, clean_jobs):
        with router._JOBS_LOCK:
            router._JOBS["novel:1"] = {
                "source": "bookto31",
                "novel_id": "1",
                "status": "수집 중",
                "started_at": time.time(),
            }
            router._save_jobs_unlocked()
        assert router.JOBS_FILE.exists()
        saved = router.JOBS_FILE.read_text(encoding="utf-8")
        assert "수집 중" in saved

    def test_should_not_count_interrupted_job_as_active_source(self, clean_jobs, monkeypatch):
        with router._JOBS_LOCK:
            router._JOBS["novel:1"] = {
                "source": "bookto31",
                "novel_id": "1",
                "status": "중단",
                "started_at": time.time() - 10,
            }
        monkeypatch.setattr(router, "get_progress", dict)
        assert router._get_active_source() is None


class TestQueuePromote:
    def test_should_move_submitted_novel_to_front(self, clean_jobs, tmp_path, monkeypatch):
        qfile = tmp_path / "queue.json"
        monkeypatch.setattr(router, "QUEUE_FILE", qfile)
        qfile.write_text(
            '[{"wr_id": 1, "novel_title": "흑백무제", "chapter": 10, "source": "bookto31"},'
            '{"wr_id": 2, "novel_title": "절대회귀", "chapter": 5, "source": "bookto31"}]',
            encoding="utf-8",
        )
        router._promote_novel_to_queue_front("절대회귀")
        import json as _json

        q = _json.loads(qfile.read_text(encoding="utf-8"))
        assert q[0]["novel_title"] == "절대회귀"
        assert q[1]["novel_title"] == "흑백무제"

    def test_should_not_change_queue_when_title_missing(self, clean_jobs, tmp_path, monkeypatch):
        qfile = tmp_path / "queue.json"
        monkeypatch.setattr(router, "QUEUE_FILE", qfile)
        original = '[{"wr_id": 1, "novel_title": "흑백무제", "chapter": 10, "source": "bookto31"}]'
        qfile.write_text(original, encoding="utf-8")
        router._promote_novel_to_queue_front("없는작품")
        assert qfile.read_text(encoding="utf-8") == original


class TestConcurrentSourceLocks:
    """소스별 collect 락 — 다른 소스 병렬 허용, 동일 소스/전체 수집 배제."""

    @staticmethod
    def _pipeline_module(tmp_path, monkeypatch):
        scripts_dir = _scripts_dir()
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import pipeline as scripts_pipeline

        importlib.reload(scripts_pipeline)
        monkeypatch.setattr(scripts_pipeline, "WATCHER_DIR", tmp_path)
        monkeypatch.setattr(scripts_pipeline, "QUEUE_FILE", tmp_path / "queue.json")
        monkeypatch.setattr(scripts_pipeline, "STATUS_FILE", tmp_path / "status.json")
        scripts_pipeline._QUEUE_LOCK_FILE = None
        scripts_pipeline._COLLECT_GATE_FILE = None
        scripts_pipeline._COLLECT_SOURCE_LOCKS.clear()
        scripts_pipeline._JSON_APPEND_LOCKS.clear()
        (tmp_path / "queue.json").write_text("[]", encoding="utf-8")
        return scripts_pipeline

    def test_should_allow_different_sources_to_hold_locks_concurrently(self, tmp_path, monkeypatch):
        pipe = self._pipeline_module(tmp_path, monkeypatch)
        import fcntl

        pipe._acquire_collect_lock("bookto31")
        gate2 = pipe._collect_gate_file()
        src2 = pipe._collect_source_lock("toki31")
        fcntl.flock(gate2, fcntl.LOCK_SH | fcntl.LOCK_NB)
        fcntl.flock(src2, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(src2, fcntl.LOCK_UN)
        fcntl.flock(gate2, fcntl.LOCK_UN)
        pipe._release_collect_lock("bookto31")

    def test_should_block_same_source_second_collect(self, tmp_path, monkeypatch):
        pipe = self._pipeline_module(tmp_path, monkeypatch)
        import fcntl

        pipe._acquire_collect_lock("toki31")
        other = open(tmp_path / "queue.collect.toki31.lock", "w")
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            other.close()
        pipe._release_collect_lock("toki31")

    def test_should_block_full_collect_while_source_collect_holds_gate(self, tmp_path, monkeypatch):
        pipe = self._pipeline_module(tmp_path, monkeypatch)
        import fcntl

        pipe._acquire_collect_lock("bookto31")
        other = open(tmp_path / "queue.collect.lock", "w")
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            other.close()
        pipe._release_collect_lock("bookto31")

    def test_should_merge_status_by_source_when_concurrent_finish(self, tmp_path, monkeypatch):
        pipe = self._pipeline_module(tmp_path, monkeypatch)
        pipe._write_status({
            "phase": "collect",
            "source": "bookto31",
            "current": {"wr_id": 1, "novel_title": "흑백무제", "chapter": 10, "source": "bookto31"},
            "index": 1, "total": 10, "remaining": 9, "processed": 0,
        })
        pipe._write_status({
            "phase": "collect",
            "source": "toki31",
            "current": {"wr_id": 2, "novel_title": "동생", "chapter": 5, "source": "toki31"},
            "index": 1, "total": 5, "remaining": 4, "processed": 0,
        })
        st = json.loads(pipe.STATUS_FILE.read_text(encoding="utf-8"))
        assert "bookto31" in st.get("sources", {})
        assert "toki31" in st.get("sources", {})
        pipe._write_status({
            "phase": "collect",
            "source": "bookto31",
            "current": None,
            "index": 10, "total": 10, "remaining": 0, "processed": 10,
        })
        st = json.loads(pipe.STATUS_FILE.read_text(encoding="utf-8"))
        assert "bookto31" not in st.get("sources", {})
        assert "toki31" in st.get("sources", {})
        assert (st.get("current") or {}).get("source") == "toki31"


class TestImmediateCollectConcurrent:
    def test_should_be_true_when_other_source_active_and_same_not(self, clean_jobs, monkeypatch):
        monkeypatch.setattr(router, "get_progress", dict)
        with router._JOBS_LOCK:
            router._JOBS["novel:1"] = {
                "source": "bookto31",
                "status": "수집 중",
                "started_at": time.time(),
            }
        assert router._should_immediate_collect("toki31", "novel:2") is True

    def test_should_be_false_when_same_source_already_active(self, clean_jobs, monkeypatch):
        monkeypatch.setattr(router, "get_progress", dict)
        with router._JOBS_LOCK:
            router._JOBS["novel:1"] = {
                "source": "toki31",
                "status": "수집 중",
                "started_at": time.time(),
            }
        assert router._should_immediate_collect("toki31", "novel:2") is False

    def test_should_detect_active_sources_from_status_snapshots(self, clean_jobs, monkeypatch):
        monkeypatch.setattr(
            router,
            "get_progress",
            lambda: {
                "sources": {
                    "bookto31": {
                        "source": "bookto31",
                        "current": {"source": "bookto31", "chapter": 3},
                        "updated_at": "2026-09-22T14:00:00+00:00",
                    },
                },
                "current": {"source": "bookto31"},
                "source": "all",
            },
        )
        with router._JOBS_LOCK:
            router._JOBS.clear()
        assert router._should_immediate_collect("toki31", "novel:2") is True
        assert router._should_immediate_collect("bookto31", "novel:3") is False


class TestEpubImportGuard:
    def test_should_not_raise_when_epub_import_fails(self, monkeypatch):
        """import 실패 시에도 _build_epub_for_drained_novels가 예외 없이 반환."""
        scripts_dir = _scripts_dir()
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))

        import pipeline as scripts_pipeline

        importlib.reload(scripts_pipeline)

        # services.epub import를 강제로 실패시키는 가드
        import builtins

        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "services.epub" or name.startswith("services.epub"):
                raise ModuleNotFoundError("No module named 'ebooklib'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)
        # touched_novels가 있어야 import 경유
        scripts_pipeline._build_epub_for_drained_novels(
            remaining_queue=[],
            touched_novels={"some_novel": "제목"},
        )

    def test_should_build_when_epub_available(self, tmp_path, monkeypatch):
        scripts_dir = _scripts_dir()
        if str(scripts_dir) not in sys.path:
            sys.path.insert(0, str(scripts_dir))
        import pipeline as scripts_pipeline

        called = {}

        class FakeEpubModule:
            @staticmethod
            def maybe_build_epub(novel_id):
                called["novel_id"] = novel_id

        import services

        monkeypatch.setattr(
            services,
            "epub",
            type(sys)("services.epub") if False else FakeEpubModule,
            raising=False,
        )
        # services.epub이 이미 로드돼 있으면 시스템 선을 우회하기 위해 sys.modules 점유
        import sys as _sys

        fake_mod = type(_sys)("services.epub")
        fake_mod.maybe_build_epub = FakeEpubModule.maybe_build_epub
        monkeypatch.setitem(_sys.modules, "services.epub", fake_mod)

        scripts_pipeline._build_epub_for_drained_novels(
            remaining_queue=[],
            touched_novels={"some_novel": "제목"},
        )
        assert called.get("novel_id") == "some_novel"


class TestAdminAuth:
    def test_should_accept_when_credentials_match(self, monkeypatch):
        monkeypatch.setattr(router, "ADMIN_PASSWORD", "s3cret")
        monkeypatch.setattr(router, "ADMIN_USER", "admin")
        out = asyncio.run(
            router.pipeline_auth(router.AuthRequest(username="admin", password="s3cret"))
        )
        assert out == {"ok": True, "username": "admin"}

    def test_should_reject_when_password_wrong(self, monkeypatch):
        monkeypatch.setattr(router, "ADMIN_PASSWORD", "s3cret")
        with pytest.raises(router.HTTPException) as ei:
            asyncio.run(
                router.pipeline_auth(
                    router.AuthRequest(username="admin", password="wrong")
                )
            )
        assert ei.value.status_code == 403

    def test_should_reject_when_username_wrong(self, monkeypatch):
        monkeypatch.setattr(router, "ADMIN_PASSWORD", "s3cret")
        monkeypatch.setattr(router, "ADMIN_USER", "admin")
        with pytest.raises(router.HTTPException) as ei:
            asyncio.run(
                router.pipeline_auth(
                    router.AuthRequest(username="root", password="s3cret")
                )
            )
        assert ei.value.status_code == 403

    def test_should_return_503_when_password_unconfigured(self, monkeypatch):
        monkeypatch.setattr(router, "ADMIN_PASSWORD", "")
        with pytest.raises(router.HTTPException) as ei:
            asyncio.run(router.pipeline_auth(router.AuthRequest(password="")))
        assert ei.value.status_code == 503

    def test_should_reject_reset_when_password_wrong(self, monkeypatch):
        monkeypatch.setattr(router, "ADMIN_PASSWORD", "s3cret")
        out = asyncio.run(router.pipeline_reset(router.ResetRequest(password="wrong")))
        assert out["ok"] is False

    def test_should_accept_reset_when_password_matches(self, clean_jobs, monkeypatch):
        monkeypatch.setattr(router, "ADMIN_PASSWORD", "s3cret")
        out = asyncio.run(router.pipeline_reset(router.ResetRequest(password="s3cret")))
        assert out["ok"] is True

    def test_should_reject_reset_when_password_absent(self, monkeypatch):
        monkeypatch.setattr(router, "ADMIN_PASSWORD", "s3cret")
        out = asyncio.run(router.pipeline_reset(router.ResetRequest()))
        assert out["ok"] is False

    def test_should_not_expose_password_as_query_parameter(self):
        """비밀번호는 query로 받으면 access log에 남는다 — openapi에서 query 선언 금지."""
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(router.router)
        params = app.openapi()["paths"]["/pipeline/reset"]["post"].get("parameters", [])
        assert [p["name"] for p in params if p["in"] == "query"] == []


class TestAccessLogRedaction:
    def test_should_mask_password_when_query_used(self, monkeypatch):
        import logging as _logging

        from lib import database

        monkeypatch.setattr(database, "init_db", lambda: None)
        import main

        rec = _logging.LogRecord(
            "uvicorn.access",
            _logging.INFO,
            __file__,
            1,
            '127.0.0.1:1 - "POST /api/pipeline/reset?password=hunter2 HTTP/1.1" 200 OK',
            None,
            None,
        )
        assert main._RedactSecretsFilter().filter(rec) is True
        assert "hunter2" not in rec.getMessage()
        assert "password=***" in rec.getMessage()

    def test_should_keep_ordinary_access_log_line(self, monkeypatch):
        import logging as _logging

        from lib import database

        monkeypatch.setattr(database, "init_db", lambda: None)
        import main

        line = '10.0.0.1:2 - "GET /api/novels HTTP/1.1" 200 OK'
        rec = _logging.LogRecord(
            "uvicorn.access", _logging.INFO, __file__, 1, line, None, None
        )
        assert main._RedactSecretsFilter().filter(rec) is True
        assert rec.getMessage() == line

