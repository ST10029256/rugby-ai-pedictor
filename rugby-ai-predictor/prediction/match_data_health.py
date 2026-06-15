"""Scan and optionally clean duplicate or inconsistent Firestore match documents."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _normalize_date_key(value: Any) -> Optional[str]:
    if value is None:
        return None

    if hasattr(value, "to_datetime"):
        try:
            value = value.to_datetime()
        except Exception:
            pass

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).date().isoformat()

    text = str(value).strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).date().isoformat()
    except Exception:
        pass

    if len(text) >= 10:
        return text[:10]
    return None


def _fixture_key(data: Dict[str, Any]) -> Optional[str]:
    league_id = data.get("league_id")
    home_team_id = data.get("home_team_id")
    away_team_id = data.get("away_team_id")
    date_key = _normalize_date_key(data.get("date_event"))

    if league_id is None or home_team_id is None or away_team_id is None or not date_key:
        return None

    return f"{int(league_id)}|{date_key}|{int(home_team_id)}|{int(away_team_id)}"


def _doc_quality_score(doc_id: str, data: Dict[str, Any]) -> int:
    score = 0
    record_id = data.get("id")
    if record_id is not None and str(record_id) == str(doc_id):
        score += 100

    if data.get("home_score") is not None and data.get("away_score") is not None:
        score += 20

    for field in ("season", "round", "home_team_name", "away_team_name", "synced_at", "migrated_at"):
        if data.get(field) not in (None, ""):
            score += 2

    return score


def _serialize_match_doc(doc_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    date_key = _normalize_date_key(data.get("date_event"))
    return {
        "doc_id": doc_id,
        "id": data.get("id"),
        "league_id": data.get("league_id"),
        "date_event": date_key,
        "home_team_id": data.get("home_team_id"),
        "away_team_id": data.get("away_team_id"),
        "home_score": data.get("home_score"),
        "away_score": data.get("away_score"),
        "season": data.get("season"),
        "round": data.get("round"),
        "quality_score": _doc_quality_score(doc_id, data),
        "id_matches_doc_id": data.get("id") is not None and str(data.get("id")) == str(doc_id),
    }


def _pick_keeper(docs: List[Tuple[str, Dict[str, Any]]]) -> Tuple[str, List[str]]:
    ranked = sorted(
        docs,
        key=lambda item: (
            _doc_quality_score(item[0], item[1]),
            str(item[0]),
        ),
        reverse=True,
    )
    keeper_id = ranked[0][0]
    delete_ids = [doc_id for doc_id, _ in ranked[1:]]
    return keeper_id, delete_ids


def scan_firestore_matches(
    firestore_db: Any,
    *,
    remove_duplicates: bool = False,
    sample_limit: int = 25,
) -> Dict[str, Any]:
    matches_ref = firestore_db.collection("matches")

    total_docs = 0
    fixture_groups: Dict[str, List[Tuple[str, Dict[str, Any]]]] = defaultdict(list)
    id_mismatches: List[Dict[str, Any]] = []
    missing_fields: List[Dict[str, Any]] = []
    duplicate_ids: List[Dict[str, Any]] = []

    for doc in matches_ref.stream():
        total_docs += 1
        data = doc.to_dict() or {}
        doc_id = doc.id

        record_id = data.get("id")
        if record_id is not None and str(record_id) != str(doc_id):
            id_mismatches.append(
                {
                    "doc_id": doc_id,
                    "id_field": record_id,
                    "league_id": data.get("league_id"),
                    "date_event": _normalize_date_key(data.get("date_event")),
                }
            )

        fixture_key = _fixture_key(data)
        if not fixture_key:
            missing_fields.append(
                {
                    "doc_id": doc_id,
                    "league_id": data.get("league_id"),
                    "date_event": data.get("date_event"),
                    "home_team_id": data.get("home_team_id"),
                    "away_team_id": data.get("away_team_id"),
                }
            )
            continue

        fixture_groups[fixture_key].append((doc_id, data))

    duplicate_groups: List[Dict[str, Any]] = []
    docs_marked_for_delete: List[str] = []

    for fixture_key, docs in fixture_groups.items():
        if len(docs) <= 1:
            continue

        keeper_id, delete_ids = _pick_keeper(docs)
        duplicate_groups.append(
            {
                "fixture_key": fixture_key,
                "count": len(docs),
                "keeper_doc_id": keeper_id,
                "delete_doc_ids": delete_ids,
                "matches": [_serialize_match_doc(doc_id, data) for doc_id, data in docs],
            }
        )
        docs_marked_for_delete.extend(delete_ids)

    duplicate_groups.sort(key=lambda group: (-group["count"], group["fixture_key"]))
    duplicate_doc_count = sum(max(0, group["count"] - 1) for group in duplicate_groups)

    seen_record_ids: Dict[str, str] = {}
    for doc_id, data in (
        (doc_id, data)
        for docs in fixture_groups.values()
        for doc_id, data in docs
    ):
        record_id = data.get("id")
        if record_id is None:
            continue
        record_key = str(record_id)
        if record_key in seen_record_ids and seen_record_ids[record_key] != doc_id:
            duplicate_ids.append(
                {
                    "id_field": record_id,
                    "doc_ids": sorted({seen_record_ids[record_key], doc_id}),
                }
            )
        else:
            seen_record_ids[record_key] = doc_id

    deleted_count = 0
    if remove_duplicates and docs_marked_for_delete:
        batch = firestore_db.batch()
        batch_count = 0
        for doc_id in docs_marked_for_delete:
            batch.delete(matches_ref.document(doc_id))
            batch_count += 1
            deleted_count += 1
            if batch_count >= 450:
                batch.commit()
                batch = firestore_db.batch()
                batch_count = 0
        if batch_count:
            batch.commit()

    return {
        "success": True,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "total_docs": total_docs,
        "duplicate_fixture_groups": len(duplicate_groups),
        "duplicate_docs": duplicate_doc_count,
        "id_mismatches": len(id_mismatches),
        "missing_fixture_key_docs": len(missing_fields),
        "duplicate_id_field_groups": len(duplicate_ids),
        "removed_docs": deleted_count if remove_duplicates else 0,
        "dry_run": not remove_duplicates,
        "sample_duplicate_groups": duplicate_groups[: max(0, sample_limit)],
        "sample_id_mismatches": id_mismatches[: max(0, sample_limit)],
        "sample_missing_fields": missing_fields[: max(0, sample_limit)],
        "sample_duplicate_id_fields": duplicate_ids[: max(0, sample_limit)],
    }
