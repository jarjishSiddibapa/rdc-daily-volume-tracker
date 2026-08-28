"""Region management routes — admin only."""

from flask import Blueprint, render_template, jsonify, request

from app import db
from app.models import Region
from app.decorators import admin_required
from app.services.audit import log_action
from app.services.report_generator import invalidate_region_cache

regions_bp = Blueprint("regions", __name__)


@regions_bp.route("/regions")
@admin_required
def regions_page():
    return render_template("regions.html")


@regions_bp.route("/api/regions")
@admin_required
def api_list_regions():
    """List all regions ordered by display_order."""
    regions = Region.query.order_by(Region.display_order, Region.name).all()
    return jsonify({"regions": [r.to_dict() for r in regions]})


@regions_bp.route("/api/regions", methods=["POST"])
@admin_required
def api_add_region():
    data = request.get_json()
    if not data or not data.get("name", "").strip():
        return jsonify({"error": "Region name is required"}), 400

    name = data["name"].strip()
    if Region.query.filter_by(name=name).first():
        return jsonify({"error": f"Region '{name}' already exists"}), 409

    # Auto display_order = max + 1
    max_order = db.session.query(db.func.max(Region.display_order)).scalar() or 0
    region = Region(name=name, display_order=max_order + 1)
    db.session.add(region)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Database error — please try again."}), 500

    invalidate_region_cache()
    log_action("region_create", {"name": name})
    db.session.commit()

    return jsonify({"status": "success", "region": region.to_dict()}), 201


@regions_bp.route("/api/regions/<int:region_id>", methods=["PUT"])
@admin_required
def api_update_region(region_id):
    region = db.session.get(Region, region_id)
    if not region:
        return jsonify({"error": "Region not found"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    old_name = region.name

    if "name" in data:
        new_name = data["name"].strip()
        if new_name and new_name != region.name:
            if Region.query.filter_by(name=new_name).first():
                return jsonify({"error": f"Region '{new_name}' already exists"}), 409
            region.name = new_name
    if "display_order" in data:
        region.display_order = int(data["display_order"])

    # Update plants in the same transaction — both or neither
    if region.name != old_name:
        from app.models import Plant
        Plant.query.filter_by(region=old_name).update({"region": region.name})

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Database error — please try again."}), 500

    invalidate_region_cache()
    log_action("region_update", {"id": region_id, "name": region.name})
    db.session.commit()

    return jsonify({"status": "success", "region": region.to_dict()})


@regions_bp.route("/api/regions/<int:region_id>", methods=["DELETE"])
@admin_required
def api_delete_region(region_id):
    region = db.session.get(Region, region_id)
    if not region:
        return jsonify({"error": "Region not found"}), 404

    # Clear region from plants that use it
    from app.models import Plant
    count = Plant.query.filter_by(region=region.name).update({"region": ""})

    db.session.delete(region)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Database error — please try again."}), 500

    invalidate_region_cache()
    log_action("region_delete", {"name": region.name, "plants_cleared": count})
    db.session.commit()

    return jsonify({"status": "success", "message": f"Region deleted, {count} plants unassigned"})


@regions_bp.route("/api/regions/reorder", methods=["PUT"])
@admin_required
def api_reorder_regions():
    """Update display_order for multiple regions at once."""
    data = request.get_json()
    if not data or "order" not in data:
        return jsonify({"error": "order array required"}), 400

    for i, region_id in enumerate(data["order"]):
        region = db.session.get(Region, region_id)
        if region:
            region.display_order = i + 1

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Database error — please try again."}), 500

    invalidate_region_cache()
    log_action("region_reorder", {"new_order": data["order"]})
    db.session.commit()
    return jsonify({"status": "success"})


@regions_bp.route("/api/regions/names")
@admin_required
def api_region_names():
    """Region names for dropdowns. Admin only (plants page is admin only)."""
    regions = Region.query.order_by(Region.display_order, Region.name).all()
    return jsonify({"regions": [r.name for r in regions]})
