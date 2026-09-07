from __future__ import annotations

from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.sql import ColumnElement

from app.models import Annotation, Article, Correction, OverlayAddition, OverlayHighlight


def article_search_match(user_id: UUID, tsquery, q: str) -> ColumnElement[bool]:
    like = f"%{q}%"
    note_hit = exists(
        select(Annotation.id).where(
            Annotation.article_id == Article.id,
            Annotation.user_id == user_id,
            or_(
                func.to_tsvector("english", func.coalesce(Annotation.body, "")).bool_op("@@")(tsquery),
                Annotation.body.ilike(like),
            ),
        )
    )
    highlight_hit = exists(
        select(OverlayHighlight.id).where(
            OverlayHighlight.article_id == Article.id,
            OverlayHighlight.user_id == user_id,
            or_(
                func.to_tsvector(
                    "english",
                    func.concat(
                        func.coalesce(OverlayHighlight.quote, ""),
                        " ",
                        func.coalesce(OverlayHighlight.note, ""),
                    ),
                ).bool_op("@@")(tsquery),
                OverlayHighlight.quote.ilike(like),
                OverlayHighlight.note.ilike(like),
            ),
        )
    )
    addition_hit = exists(
        select(OverlayAddition.id).where(
            OverlayAddition.article_id == Article.id,
            OverlayAddition.user_id == user_id,
            or_(
                func.to_tsvector(
                    "english",
                    func.concat(
                        func.coalesce(OverlayAddition.title, ""),
                        " ",
                        func.coalesce(OverlayAddition.markdown, ""),
                    ),
                ).bool_op("@@")(tsquery),
                OverlayAddition.title.ilike(like),
                OverlayAddition.markdown.ilike(like),
            ),
        )
    )
    correction_hit = exists(
        select(Correction.id).where(
            Correction.article_id == Article.id,
            Correction.user_id == user_id,
            or_(
                func.to_tsvector("english", func.coalesce(Correction.markdown, "")).bool_op("@@")(tsquery),
                Correction.markdown.ilike(like),
            ),
        )
    )
    return or_(
        Article.search_vector.bool_op("@@")(tsquery),
        Article.title.ilike(like),
        note_hit,
        highlight_hit,
        addition_hit,
        correction_hit,
    )


def overlay_text_subquery(user_id: UUID):
    notes = (
        select(func.string_agg(Annotation.body, " "))
        .where(Annotation.article_id == Article.id, Annotation.user_id == user_id)
        .correlate(Article)
        .scalar_subquery()
    )
    highlights = (
        select(func.string_agg(func.concat(OverlayHighlight.quote, " ", func.coalesce(OverlayHighlight.note, "")), " "))
        .where(OverlayHighlight.article_id == Article.id, OverlayHighlight.user_id == user_id)
        .correlate(Article)
        .scalar_subquery()
    )
    additions = (
        select(func.string_agg(func.concat(OverlayAddition.title, " ", OverlayAddition.markdown), " "))
        .where(OverlayAddition.article_id == Article.id, OverlayAddition.user_id == user_id)
        .correlate(Article)
        .scalar_subquery()
    )
    corrections = (
        select(func.string_agg(Correction.markdown, " "))
        .where(Correction.article_id == Article.id, Correction.user_id == user_id)
        .correlate(Article)
        .scalar_subquery()
    )
    return notes, highlights, additions, corrections
