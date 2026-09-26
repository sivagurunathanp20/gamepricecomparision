"""
Corrects five Steam app ids that were wrong in the seed data (confirmed
against Steam's own store pages). Run once, then re-run verify-prices.
"""
from app import app
from extensions import db
from models import Game

FIXES = {
    "ea-sports-wrc": 1849250,                        # was pointing at a DLC pack
    "call-of-duty-modern-warfare-iii": 3595270,      # Valve remapped this app id
    "ghostrunner-2": 2144740,
    "like-a-dragon-ishin": 1805480,
    "death-stranding-directors-cut": 1850570,
}

with app.app_context():
    for slug, correct_id in FIXES.items():
        g = Game.query.filter_by(slug=slug).first()
        if not g:
            print(f"!! no game found with slug={slug}")
            continue
        print(f"{g.title}: {g.steam_app_id} -> {correct_id}")
        g.steam_app_id = correct_id
        # Also fix the linked GamePlatform's store_product_id so the old
        # wrong id isn't reused on the next verify.
        for listing in g.platform_listings:
            if listing.platform.name == "Steam":
                listing.store_product_id = str(correct_id)
    db.session.commit()
    print("Done.")
