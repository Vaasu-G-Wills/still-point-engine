"""
api/routes/trends.py — Trending Topics Endpoint
"""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class TrendsRequest(BaseModel):
    region_code:   str = "IN"
    n_suggestions: int = 8


@router.post("/trends")
def get_trends(req: TrendsRequest):
    from yt_trends import get_trending_topic_suggestions
    return get_trending_topic_suggestions(
        region_code=req.region_code,
        n_suggestions=req.n_suggestions,
    )
