"""
Announcement endpoints for the High School Management System API
"""

from datetime import date
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"],
)


class AnnouncementPayload(BaseModel):
    """Payload for creating and updating announcements."""

    message: str = Field(min_length=1, max_length=500)
    expiration_date: date
    start_date: Optional[date] = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("Message is required")
        return trimmed

    @field_validator("start_date")
    @classmethod
    def validate_dates(
        cls, start_date: Optional[date], info
    ) -> Optional[date]:
        expiration_date = info.data.get("expiration_date")
        if start_date and expiration_date and start_date > expiration_date:
            raise ValueError("Start date cannot be after expiration date")
        return start_date


def _verify_teacher_access(teacher_username: Optional[str]) -> Dict[str, Any]:
    """Verify teacher session from username passed by frontend."""
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def _serialize_announcement(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "message": doc["message"],
        "start_date": doc.get("start_date"),
        "expiration_date": doc["expiration_date"],
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at"),
    }


@router.get("/active", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get active announcements for public display banner."""
    today_iso = date.today().isoformat()

    query = {
        "expiration_date": {"$gte": today_iso},
        "$or": [
            {"start_date": {"$exists": False}},
            {"start_date": None},
            {"start_date": {"$lte": today_iso}},
        ],
    }

    announcements: List[Dict[str, Any]] = []
    for item in announcements_collection.find(query).sort(
        [("expiration_date", 1), ("created_at", -1)]
    ):
        announcements.append(_serialize_announcement(item))

    return announcements


@router.get("", response_model=List[Dict[str, Any]])
def get_all_announcements(
    teacher_username: Optional[str] = Query(None),
) -> List[Dict[str, Any]]:
    """Get all announcements for announcement management."""
    _verify_teacher_access(teacher_username)

    announcements: List[Dict[str, Any]] = []
    for item in announcements_collection.find().sort(
        [("expiration_date", 1), ("created_at", -1)]
    ):
        announcements.append(_serialize_announcement(item))

    return announcements


@router.post("", response_model=Dict[str, Any])
def create_announcement(
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Create a new announcement."""
    _verify_teacher_access(teacher_username)

    today_iso = date.today().isoformat()
    announcement_doc = {
        "message": payload.message,
        "start_date": payload.start_date.isoformat() if payload.start_date else None,
        "expiration_date": payload.expiration_date.isoformat(),
        "created_at": today_iso,
        "updated_at": today_iso,
    }

    insert_result = announcements_collection.insert_one(announcement_doc)
    created = announcements_collection.find_one({"_id": insert_result.inserted_id})
    if not created:
        raise HTTPException(status_code=500, detail="Failed to create announcement")

    return _serialize_announcement(created)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None),
) -> Dict[str, Any]:
    """Update an existing announcement."""
    _verify_teacher_access(teacher_username)

    try:
        object_id = ObjectId(announcement_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid announcement id") from exc

    existing = announcements_collection.find_one({"_id": object_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    update_result = announcements_collection.update_one(
        {"_id": object_id},
        {
            "$set": {
                "message": payload.message,
                "start_date": payload.start_date.isoformat() if payload.start_date else None,
                "expiration_date": payload.expiration_date.isoformat(),
                "updated_at": date.today().isoformat(),
            }
        },
    )

    if update_result.matched_count == 0:
        raise HTTPException(status_code=500, detail="Failed to update announcement")

    updated = announcements_collection.find_one({"_id": object_id})
    if not updated:
        raise HTTPException(status_code=500, detail="Failed to load updated announcement")

    return _serialize_announcement(updated)


@router.delete("/{announcement_id}", response_model=Dict[str, str])
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None),
) -> Dict[str, str]:
    """Delete an announcement."""
    _verify_teacher_access(teacher_username)

    try:
        object_id = ObjectId(announcement_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid announcement id") from exc

    delete_result = announcements_collection.delete_one({"_id": object_id})
    if delete_result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
