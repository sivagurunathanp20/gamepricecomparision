"""
Scans every wishlist entry with a target_price set and, if any platform's
current price has dropped to or below that target, sends an email alert
(and logs an in-app Notification either way).

Run manually with:   flask --app app check-price-alerts
In production this would typically run on a schedule (cron / Celery beat)
right after your price-scraping job updates GamePlatform rows.
"""
from flask import current_app
from flask_mail import Message

from extensions import db, mail
from models import Wishlist, Notification


def check_and_send_alerts():
    sent = 0
    items = Wishlist.query.filter(
        Wishlist.target_price.isnot(None), Wishlist.alert_sent.is_(False)
    ).all()

    for item in items:
        best = item.game.best_price
        if not best or best.current_price > item.target_price:
            continue

        message = (
            f"{item.game.title} just dropped to ${best.current_price:.2f} "
            f"on {best.platform.name} — that's at or below your target of "
            f"${item.target_price:.2f}!"
        )

        db.session.add(Notification(user_id=item.user_id, message=message))

        try:
            msg = Message(
                subject=f"Price Alert: {item.game.title} is now ${best.current_price:.2f}",
                recipients=[item.user.email],
                body=message,
            )
            mail.send(msg)
        except Exception as exc:  # SMTP not configured in dev — safe to ignore
            current_app.logger.warning(f"Could not send alert email: {exc}")

        item.alert_sent = True
        sent += 1

    db.session.commit()
    return sent
