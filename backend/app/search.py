from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


def apply_search_schema(engine: Engine) -> None:
    """Postgres-only full-text search setup for segments.text (D20: `russian` config, GIN index).

    Deliberately outside SQLAlchemy's Base.metadata — tsvector/GIN/triggers
    have no SQLite equivalent, and the unit test suite runs against SQLite.
    Only invoked from the real API startup lifespan, never from tests.
    """
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE segments ADD COLUMN IF NOT EXISTS tsv tsvector"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS segments_tsv_idx ON segments USING gin(tsv)"))
        conn.execute(
            text(
                """
                CREATE OR REPLACE FUNCTION segments_tsv_trigger() RETURNS trigger AS $$
                begin
                  new.tsv := to_tsvector('russian', coalesce(new.text, ''));
                  return new;
                end
                $$ LANGUAGE plpgsql
                """
            )
        )
        conn.execute(text("DROP TRIGGER IF EXISTS segments_tsv_update ON segments"))
        conn.execute(
            text(
                "CREATE TRIGGER segments_tsv_update BEFORE INSERT OR UPDATE OF text ON segments "
                "FOR EACH ROW EXECUTE FUNCTION segments_tsv_trigger()"
            )
        )
        conn.execute(text("UPDATE segments SET tsv = to_tsvector('russian', text) WHERE tsv IS NULL"))


@dataclass
class SearchMatch:
    segment_id: str
    start_ms: int
    end_ms: int
    text: str


def search_segments(db: Session, recording_id: str, query: str) -> list[SearchMatch]:
    rows = db.execute(
        text(
            "SELECT id, start_ms, end_ms, text FROM segments "
            "WHERE recording_id = :recording_id AND tsv @@ plainto_tsquery('russian', :query) "
            "ORDER BY start_ms"
        ),
        {"recording_id": recording_id, "query": query},
    ).all()
    return [SearchMatch(segment_id=r.id, start_ms=r.start_ms, end_ms=r.end_ms, text=r.text) for r in rows]
