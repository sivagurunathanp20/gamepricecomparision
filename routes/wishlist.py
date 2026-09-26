from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from extensions import db
from models import Wishlist, Game

wishlist_bp = Blueprint("wishlist", __name__, url_prefix="/wishlist")


@wishlist_bp.route("/")
@login_required
def index():
    items = Wishlist.query.filter_by(user_id=current_user.id).order_by(Wishlist.added_at.desc()).all()
    return render_template("wishlist.html", items=items)


@wishlist_bp.route("/add/<int:game_id>", methods=["POST"])
@login_required
def add(game_id):
    game = Game.query.get_or_404(game_id)
    existing = Wishlist.query.filter_by(user_id=current_user.id, game_id=game.id).first()
    if existing:
        return jsonify({"status": "exists", "message": f"{game.title} is already on your wishlist."})

    target_price = request.form.get("target_price", type=float)
    item = Wishlist(user_id=current_user.id, game_id=game.id, target_price=target_price)
    db.session.add(item)
    db.session.commit()
    return jsonify({"status": "added", "message": f"{game.title} added to your wishlist."})


@wishlist_bp.route("/remove/<int:item_id>", methods=["POST"])
@login_required
def remove(item_id):
    item = Wishlist.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        flash("You cannot modify this item.", "danger")
        return redirect(url_for("wishlist.index"))

    db.session.delete(item)
    db.session.commit()
    flash("Removed from wishlist.", "info")
    return redirect(url_for("wishlist.index"))


@wishlist_bp.route("/update-target/<int:item_id>", methods=["POST"])
@login_required
def update_target(item_id):
    item = Wishlist.query.get_or_404(item_id)
    if item.user_id != current_user.id:
        flash("You cannot modify this item.", "danger")
        return redirect(url_for("wishlist.index"))

    item.target_price = request.form.get("target_price", type=float)
    item.alert_sent = False
    db.session.commit()
    flash("Price alert updated.", "success")
    return redirect(url_for("wishlist.index"))
