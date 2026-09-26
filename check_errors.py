from app import app
from models import GamePlatform
from collections import Counter

with app.app_context():
    rows = GamePlatform.query.filter_by(verify_status="failed").all()
    c = Counter(r.verify_error for r in rows)
    for err, n in c.most_common():
        print(n, "-", err)
