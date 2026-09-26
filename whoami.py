"""
Maps the still-failing Steam app ids back to game titles/slugs in your
database, so you know exactly which rows to correct.
"""
from app import app
from models import Game

IDS = [1080600, 2519060, 1599340, 1798650, 1843600, 1738090]

with app.app_context():
    for app_id in IDS:
        g = Game.query.filter_by(steam_app_id=app_id).first()
        if g:
            print(f"{app_id} -> {g.title} (slug: {g.slug}, id: {g.id})")
        else:
            print(f"{app_id} -> no game found with this steam_app_id")
