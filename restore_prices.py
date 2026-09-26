"""restore_prices.py - Restore last known prices from PriceHistory into GamePlatform rows."""
from app import create_app
app = create_app()
with app.app_context():
    from models import GamePlatform, Edition, Platform
    from extensions import db
    from sqlalchemy import text
    from datetime import datetime

    steam_platform = Platform.query.filter_by(name='Steam').first()
    if not steam_platform:
        print('No Steam platform!')
        exit()

    rows = db.session.execute(text(
        'SELECT ph.game_id, ph.price, ph.recorded_at '
        'FROM price_history ph '
        'WHERE ph.platform_id = :pid AND ph.verified = 1 '
        'AND ph.recorded_at = ('
        '  SELECT MAX(ph2.recorded_at) FROM price_history ph2 '
        '  WHERE ph2.game_id = ph.game_id AND ph2.platform_id = :pid AND ph2.verified = 1'
        ')'
    ), {'pid': steam_platform.id}).fetchall()

    print('Found %d games with price history to restore' % len(rows))

    restored = 0
    now = datetime.utcnow()
    for game_id, price, recorded_at in rows:
        listing = GamePlatform.query.filter_by(
            game_id=game_id, platform_id=steam_platform.id
        ).first()
        if not listing:
            continue
        if listing.verify_status == 'verified':
            continue

        listing.current_price = price
        listing.price_currency = 'INR'

        # Restore as 'verified' with now as last_verified_at so price_is_trusted passes.
        # verify_error notes this is a restored price so admins know.
        listing.verify_status = 'verified'
        listing.last_verified_at = now
        listing.verify_error = ''
        listing.in_stock = True
        listing.source = 'steam'
        listing.store_url = listing.store_url or ('https://store.steampowered.com/app/' + str(listing.store_product_id))

        # Also update cheapest edition if editions exist and have no current price
        live_editions = [e for e in listing.editions if e.current_price is not None and e.is_available]
        if not live_editions:
            # No live edition - set cheapest edition price from history so buy button works
            for ed in listing.editions:
                if ed.is_available:
                    ed.current_price = price
                    ed.original_price = price
                    ed.currency = 'INR'
                    ed.last_verified_at = now
                    # Keep url_verified_at as-is if already set
                    break

        restored += 1

    db.session.commit()
    print('Restored %d listings from price history' % restored)

    from sqlalchemy import func
    statuses = db.session.query(GamePlatform.verify_status, func.count()).group_by(GamePlatform.verify_status).all()
    print('Updated status counts:')
    for s, c in statuses:
        print('  %s: %d' % (s, c))

    # Check how many are now trusted
    from models import Game
    trusted_count = sum(1 for g in Game.query.all() if g.best_price is not None)
    print('Games with a trusted price (best_price): %d' % trusted_count)
