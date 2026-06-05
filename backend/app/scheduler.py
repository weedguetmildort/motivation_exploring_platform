# backend/app/scheduler.py
import os
import threading

_scheduler = None
_scheduler_lock = threading.Lock()


def run_jobs_now(app) -> None:
    """Run health check then discovery immediately. Safe to call from any thread."""
    from .services.link_health import run_health_check, run_discovery
    from .services.allowlist import get_allowlist_collection, load_allowlist_cache
    from .services.knowledge_links import get_knowledge_links_collection, reload_knowledge_links_cache
    from openai import OpenAI

    db = app.state.db
    settings = app.state.settings

    openai_client = OpenAI(
        api_key=os.getenv("UF_OPENAI_API_KEY"),
        base_url=os.getenv("UF_OPENAI_BASE_URL", "https://api.ai.it.ufl.edu"),
    )

    allowlist_col = get_allowlist_collection(db)
    allowlist_cache = load_allowlist_cache(allowlist_col)

    summary_health = run_health_check(db, settings, openai_client, allowlist_cache)
    print(f"[scheduler] health_check: {summary_health}")

    summary_discovery = run_discovery(db, settings, openai_client, allowlist_cache)
    print(f"[scheduler] discovery: {summary_discovery}")

    # Reload chatbot cache to reflect any status changes
    links_col = get_knowledge_links_collection(db)
    app.state.knowledge_links = reload_knowledge_links_cache(links_col)
    print(f"[scheduler] cache reloaded: {len(app.state.knowledge_links)} READY links")


def start_scheduler(app) -> None:
    global _scheduler

    with _scheduler_lock:
        if _scheduler is not None and _scheduler.running:
            return

        from apscheduler.schedulers.background import BackgroundScheduler

        interval_hours = app.state.settings.LINK_CHECK_INTERVAL_HOURS

        sched = BackgroundScheduler(daemon=True)
        sched.add_job(
            func=run_jobs_now,
            args=[app],
            trigger="interval",
            hours=interval_hours,
            id="link_health_and_discovery",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        sched.start()
        _scheduler = sched
        print(f"[scheduler] started — interval={interval_hours}h")


def stop_scheduler() -> None:
    global _scheduler
    with _scheduler_lock:
        if _scheduler and _scheduler.running:
            _scheduler.shutdown(wait=False)
            _scheduler = None
            print("[scheduler] stopped")
