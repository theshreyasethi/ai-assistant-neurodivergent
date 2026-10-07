"""Teacher-curated sign-language glossary (roadmap P4-04).

Deliberately licence-safe: this never stores or embeds third-party sign
videos. A teacher records or sources a school-owned clip, uploads it to
Firebase Storage client-side (the same pattern this app already uses for
other media), and this endpoint only ever stores the resulting URL plus
captions — the clip's bytes never pass through this backend at all.

sign_glossary/{term}_{lang} — one doc per (term, language) pair, so the
same word can have different clips/captions per sign language.
"""

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from firebase_admin import firestore as admin_firestore
from pydantic import BaseModel, Field, field_validator

from auth import require_active_user, verify_role
from firebase_config import db

router = APIRouter(prefix="/glossary")

_TERM_RE = re.compile(r"^[a-z0-9][a-z0-9 '-]{0,63}$")


def _doc_id(term: str, lang: str) -> str:
    return f"{term.strip().lower()}_{lang.strip().lower()}"


def _require_db():
    if db is None:
        raise HTTPException(status_code=503, detail="Persistence unavailable")


class GlossaryEntry(BaseModel):
    term: str = Field(min_length=1, max_length=64)
    lang: str = Field(default="asl", min_length=2, max_length=16)
    videoUrl: str = Field(min_length=1, max_length=2048)
    captions: str = Field(default="", max_length=1000)

    @field_validator("term")
    @classmethod
    def _valid_term(cls, value: str) -> str:
        normalised = value.strip().lower()
        if not _TERM_RE.match(normalised):
            raise ValueError("term must be plain letters/numbers/spaces/hyphens")
        return normalised

    @field_validator("videoUrl")
    @classmethod
    def _valid_url(cls, value: str) -> str:
        # Firebase Storage download URLs are always https — never accept a
        # data: URI or a third-party embed, which is exactly the "don't
        # embed sign videos until licences are verified" rule from a
        # different angle (anything NOT our own Storage bucket is suspect).
        if not value.startswith("https://"):
            raise ValueError("videoUrl must be an https URL (Firebase Storage)")
        return value


@router.get("/{term}")
async def get_entry(term: str, lang: str = "asl", _user: dict = Depends(require_active_user)):
    """Any signed-in user may look a term up — this is read access for
    students, not a teacher-only action."""
    _require_db()
    doc = db.collection("sign_glossary").document(_doc_id(term, lang)).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="No glossary entry for this term")
    return doc.to_dict()


@router.get("")
async def list_entries(lang: Optional[str] = None, _user: dict = Depends(require_active_user)):
    """Every curated term, optionally filtered by language — backs a
    management view or a "browse the glossary" page."""
    _require_db()
    docs = db.collection("sign_glossary").stream()
    entries = [d.to_dict() for d in docs]
    if lang:
        entries = [e for e in entries if e.get("lang") == lang.strip().lower()]
    entries.sort(key=lambda e: e.get("term", ""))
    return {"count": len(entries), "entries": entries}


@router.post("")
async def upsert_entry(body: GlossaryEntry, user: dict = Depends(verify_role("teacher"))):
    """Teachers only — an admin can promote a teacher account to manage this
    if that's ever needed, but students must never be able to write here."""
    _require_db()
    doc_ref = db.collection("sign_glossary").document(_doc_id(body.term, body.lang))
    doc_ref.set(
        {
            "term": body.term,
            "lang": body.lang.strip().lower(),
            "videoUrl": body.videoUrl,
            "captions": body.captions,
            "addedBy": user.get("uid"),
            "updatedAt": admin_firestore.SERVER_TIMESTAMP,
        }
    )
    return {"status": "ok", "term": body.term, "lang": body.lang.strip().lower()}


@router.delete("/{term}")
async def delete_entry(term: str, lang: str = "asl", user: dict = Depends(verify_role("teacher"))):
    _require_db()
    doc_ref = db.collection("sign_glossary").document(_doc_id(term, lang))
    if not doc_ref.get().exists:
        raise HTTPException(status_code=404, detail="No glossary entry for this term")
    doc_ref.delete()
    return {"status": "ok"}
