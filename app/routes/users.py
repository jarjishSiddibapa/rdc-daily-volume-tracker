"""User management routes — admin only."""

from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user

from app import db
from app.models import User, UserPlantAccess
from app.decorators import admin_required
from app.services.audit import log_action

users_bp = Blueprint("users", __name__)


@users_bp.route("/users")
@admin_required
def users_page():
    """User management page."""
    return render_template("users.html")


@users_bp.route("/api/users")
@admin_required
def api_list_users():
    """List all users."""
    users = User.query.order_by(User.username).all()
    return jsonify({"users": [u.to_dict() for u in users]})


@users_bp.route("/api/users", methods=["POST"])
@admin_required
def api_create_user():
    """Create a new user."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    username = (data.get("username") or "").strip().lower()
    email = (data.get("email") or "").strip().lower() or None
    password = data.get("password") or ""
    display_name = (data.get("display_name") or "").strip()
    role = data.get("role", "viewer")

    if not username:
        return jsonify({"error": "Username is required"}), 400
    if not email:
        return jsonify({"error": "Email is required"}), 400
    if not password or len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400
    if role not in ("admin", "manual_entry", "viewer"):
        return jsonify({"error": "Invalid role"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": f"Username '{username}' already exists"}), 409
    if User.query.filter_by(email=email).first():
        return jsonify({"error": f"Email '{email}' is already in use"}), 409

    user = User(
        username=username,
        email=email,
        display_name=display_name or username,
        role=role,
        is_active_user=True,
    )
    user.set_password(password)

    db.session.add(user)
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Database error — please try again."}), 500

    log_action("user_create", {
        "username": username,
        "email": email,
        "role": role,
        "display_name": display_name or username,
        "created_by": current_user.username,
    })
    db.session.commit()

    return jsonify({"status": "success", "user": user.to_dict()}), 201


@users_bp.route("/api/users/<int:user_id>", methods=["PUT"])
@admin_required
def api_update_user(user_id):
    """Update user details. Admin can change role, name, active status, password."""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Capture originals for specific audit events
    original_role = user.role
    original_active = user.is_active_user

    if "display_name" in data:
        user.display_name = (data["display_name"] or "").strip()
    if "email" in data:
        new_email = (data["email"] or "").strip().lower() or None
        if not new_email:
            return jsonify({"error": "Email cannot be empty"}), 400
        conflict = User.query.filter(User.email == new_email, User.id != user_id).first()
        if conflict:
            return jsonify({"error": f"Email '{new_email}' is already in use"}), 409
        user.email = new_email
    if "role" in data:
        new_role = data["role"]
        if new_role not in ("admin", "manual_entry", "viewer"):
            return jsonify({"error": "Invalid role"}), 400
        # Prevent removing the last admin
        if user.role == "admin" and new_role != "admin":
            admin_count = User.query.filter_by(role="admin", is_active_user=True).count()
            if admin_count <= 1:
                return jsonify({"error": "Cannot remove the last admin"}), 400
        user.role = new_role
        # Targets permission is only valid for manual_entry — clear it on role change
        if new_role != "manual_entry":
            user.can_update_targets = False
    if "is_active" in data:
        # Prevent deactivating self
        if user.id == current_user.id and not data["is_active"]:
            return jsonify({"error": "Cannot deactivate yourself"}), 400
        user.is_active_user = bool(data["is_active"])
    if "can_edit_employee_details" in data:
        user.can_edit_employee_details = bool(data["can_edit_employee_details"])
    if "can_update_targets" in data:
        # Only manual_entry users may hold this permission
        if user.role == "manual_entry":
            user.can_update_targets = bool(data["can_update_targets"])
        else:
            user.can_update_targets = False
    password_changed = bool(data.get("password"))
    if password_changed:
        if len(data["password"]) < 8:
            return jsonify({"error": "Password must be at least 8 characters"}), 400
        user.set_password(data["password"])

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Database error — please try again."}), 500

    # Generic update log
    log_action("user_update", {
        "user_id": user_id,
        "username": user.username,
        "changed_by": current_user.username,
    })

    # Specific events for significant changes
    if user.role != original_role:
        log_action("user_role_change", {
            "username": user.username,
            "from": original_role,
            "to": user.role,
            "changed_by": current_user.username,
        })
    if not user.is_active_user and original_active:
        log_action("user_deactivated", {
            "username": user.username,
            "deactivated_by": current_user.username,
        })
    elif user.is_active_user and not original_active:
        log_action("user_reactivated", {
            "username": user.username,
            "reactivated_by": current_user.username,
        })
    if password_changed:
        log_action("user_password_changed", {
            "username": user.username,
            "changed_by": current_user.username,
        })

    db.session.commit()

    return jsonify({"status": "success", "user": user.to_dict()})


@users_bp.route("/api/users/<int:user_id>/plant-access")
@admin_required
def api_get_plant_access(user_id):
    """Get plant access settings for a user."""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    accesses = UserPlantAccess.query.filter_by(user_id=user_id).all()
    return jsonify({
        "user_id": user_id,
        "manual_entry_all_plants": user.manual_entry_all_plants,
        "plant_codes": [a.plant_code for a in accesses],
    })


@users_bp.route("/api/users/<int:user_id>/plant-access", methods=["PUT"])
@admin_required
def api_set_plant_access(user_id):
    """Set plant access for a user."""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    data = request.get_json()
    if data is None:
        return jsonify({"error": "No data provided"}), 400

    user.manual_entry_all_plants = bool(data.get("manual_entry_all_plants", False))
    plant_codes = data.get("plant_codes", [])

    UserPlantAccess.query.filter_by(user_id=user_id).delete()
    for code in plant_codes:
        db.session.add(UserPlantAccess(user_id=user_id, plant_code=code))

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"error": "Database error — please try again."}), 500

    log_action("user_plant_access_update", {
        "user_id": user_id, "username": user.username,
        "all_plants": user.manual_entry_all_plants, "plant_count": len(plant_codes),
    })
    db.session.commit()

    return jsonify({"status": "success"})


@users_bp.route("/api/users/<int:user_id>", methods=["DELETE"])
@admin_required
def api_delete_user(user_id):
    """Delete a user. Cannot delete yourself."""
    if user_id == current_user.id:
        return jsonify({"error": "Cannot delete your own account"}), 400

    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Prevent deleting the last admin
    if user.role == "admin":
        admin_count = User.query.filter_by(role="admin", is_active_user=True).count()
        if admin_count <= 1:
            return jsonify({"error": "Cannot delete the last admin"}), 400

    deleted_username = user.username
    deleted_role = user.role
    deleted_email = user.email
    try:
        db.session.delete(user)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": "Database error — please try again."}), 500

    log_action("user_delete", {
        "user_id": user_id,
        "username": deleted_username,
        "role": deleted_role,
        "email": deleted_email,
        "deleted_by": current_user.username,
    })
    db.session.commit()

    return jsonify({"status": "success", "message": f"User {deleted_username} deleted"})
