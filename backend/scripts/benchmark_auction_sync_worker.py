from __future__ import annotations

import argparse
import asyncio
import json
import os
import resource
import sys
import time
from dataclasses import dataclass

from sqlalchemy import event


@dataclass
class SqlMetrics:
    statements: int = 0
    selects: int = 0
    inserts: int = 0
    updates: int = 0
    deletes: int = 0

    def observe(self, statement: str) -> None:
        self.statements += 1
        verb = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
        if verb == "SELECT":
            self.selects += 1
        elif verb == "INSERT":
            self.inserts += 1
        elif verb == "UPDATE":
            self.updates += 1
        elif verb == "DELETE":
            self.deletes += 1


def _rss_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return usage / 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure one auction sync pass against the configured database.")
    parser.add_argument("--source", default="tbankrot", help="Auction source code to sync.")
    parser.add_argument("--limit", type=int, default=50, help="Lot list limit for this benchmark run.")
    parser.add_argument("--pages", type=int, default=None, help="TBankrot page window size for this run.")
    parser.add_argument(
        "--publication-backfill-limit",
        type=int,
        default=0,
        help="Publication backfill limit. 0 disables it.",
    )
    parser.add_argument(
        "--detail-sync",
        action="store_true",
        help="Enable detail sync during the benchmark. Keep disabled for baseline sizing.",
    )
    parser.add_argument(
        "--page-rotation",
        action="store_true",
        help="Enable TBankrot page rotation for this benchmark run.",
    )
    parser.add_argument(
        "--page-rotation-max-page",
        type=int,
        default=None,
        help="Max TBankrot page used by rotation before wrapping to page 1.",
    )
    parser.add_argument(
        "--confirm-write",
        action="store_true",
        help="Required because the benchmark writes sync results to the configured database.",
    )
    parser.add_argument(
        "--heartbeat-seconds",
        type=float,
        default=10.0,
        help="Print a progress heartbeat while the sync is still running.",
    )
    return parser.parse_args()


async def run_benchmark(args: argparse.Namespace) -> dict[str, object]:
    if not args.confirm_write:
        raise SystemExit("Refusing to run without --confirm-write because sync writes to the configured database.")

    os.environ["AUCTION_SYNC_LIMIT"] = str(args.limit)
    os.environ["AUCTION_PUBLICATION_SYNC_LIMIT"] = str(args.publication_backfill_limit)
    os.environ["AUCTION_DETAIL_SYNC_ENABLED"] = "true" if args.detail_sync else "false"
    if args.pages is not None:
        os.environ["TBANKROT_PAGES"] = str(args.pages)
    os.environ["TBANKROT_PAGE_ROTATION_ENABLED"] = "true" if args.page_rotation else "false"
    if args.page_rotation_max_page is not None:
        os.environ["TBANKROT_PAGE_ROTATION_MAX_PAGE"] = str(args.page_rotation_max_page)

    from app.infrastructure.db.database import AsyncSessionLocal, engine
    from app.services.auction_sync import sync_source_lots

    sql_metrics = SqlMetrics()

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        sql_metrics.observe(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", before_cursor_execute)
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    last_progress: dict[str, object] = {}
    completed = False

    def print_line(message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    async def on_progress(payload: dict) -> None:
        nonlocal last_progress
        last_progress = payload
        print_line(
            "progress "
            f"processed={payload.get('processed')} "
            f"fetched={payload.get('fetched')} "
            f"created={payload.get('created')} "
            f"updated={payload.get('updated')} "
            f"unchanged={payload.get('unchanged')} "
            f"sql={sql_metrics.statements} "
            f"rss_mb={_rss_mb():.1f}"
        )

    async def heartbeat() -> None:
        if args.heartbeat_seconds <= 0:
            return
        while not completed:
            await asyncio.sleep(args.heartbeat_seconds)
            if completed:
                return
            elapsed = time.perf_counter() - started_wall
            processed = last_progress.get("processed", 0)
            print_line(
                "heartbeat "
                f"elapsed_seconds={elapsed:.1f} "
                f"processed={processed} "
                f"sql={sql_metrics.statements} "
                f"rss_mb={_rss_mb():.1f}"
            )

    print_line(
        "starting auction sync benchmark "
        f"source={args.source} "
        f"limit={args.limit} "
        f"pages={args.pages} "
        f"publication_backfill_limit={args.publication_backfill_limit} "
        f"detail_sync={args.detail_sync} "
        f"page_rotation={args.page_rotation} "
        f"page_rotation_max_page={args.page_rotation_max_page}"
    )
    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        async with AsyncSessionLocal() as session:
            result = await sync_source_lots(session, source=args.source, limit=args.limit, on_progress=on_progress)
    finally:
        completed = True
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        event.remove(engine.sync_engine, "before_cursor_execute", before_cursor_execute)

    elapsed_wall = time.perf_counter() - started_wall
    elapsed_cpu = time.process_time() - started_cpu
    result_payload = result.model_dump(mode="json")
    fetched = max(1, int(result_payload.get("fetched") or 0))

    return {
        "source": args.source,
        "limit": args.limit,
        "pages": args.pages,
        "publication_backfill_limit": args.publication_backfill_limit,
        "detail_sync": args.detail_sync,
        "page_rotation": args.page_rotation,
        "page_rotation_max_page": args.page_rotation_max_page,
        "result": result_payload,
        "wall_seconds": round(elapsed_wall, 3),
        "cpu_seconds": round(elapsed_cpu, 3),
        "max_rss_mb": round(_rss_mb(), 1),
        "sql": {
            "statements": sql_metrics.statements,
            "selects": sql_metrics.selects,
            "inserts": sql_metrics.inserts,
            "updates": sql_metrics.updates,
            "deletes": sql_metrics.deletes,
            "statements_per_fetched_lot": round(sql_metrics.statements / fetched, 2),
        },
    }


def main() -> None:
    args = parse_args()
    metrics = asyncio.run(run_benchmark(args))
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
