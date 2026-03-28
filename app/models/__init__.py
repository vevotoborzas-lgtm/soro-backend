"""
app/models/__init__.py – importálja az összes modellt
hogy az init_db megtalálja őket.
"""
from app.models.user import User        # noqa
from app.models.article import Article  # noqa
from app.models.api_key import APIKey   # noqa
