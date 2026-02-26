"""
item_request_routes.py

Member → Host item-addition approval workflow.

Endpoints:
  POST /api/kitchen/request_add_items       — member submits items for approval
  GET  /api/kitchen/item_requests           — list requests (host sees all, member sees own)
  POST /api/kitchen/respond_to_item_request — host/co-host approves or rejects a request
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from datetime import datetime, timezone
import threading
import uuid

from db_connection import get_session
from models import Kitchen, KitchenMember, KitchenItemsHistory, User, ItemAddRequest
from utils.kitchen_item_helpers import _insert_item_into_kitchen
from utils.gpt_vision import generate_thumbnails_background

item_request_blueprint = Blueprint('item_request_blueprint', __name__)


# ── Shared helper ────────────────────────────────────────────────────────────

def _add_items_to_kitchen_history(kitchen_id: int, item_names: list, session):
    """Add unique item names to kitchen_items_history."""
    clean_names = list({name.strip().lower() for name in item_names if name.strip()})
    if not clean_names:
        return

    history = session.query(KitchenItemsHistory).filter(
        KitchenItemsHistory.kitchen_id == kitchen_id
    ).first()

    if history:
        existing = set(history.item_names or [])
        existing.update(clean_names)
        history.item_names = list(existing)
    else:
        history = KitchenItemsHistory(kitchen_id=kitchen_id, item_names=clean_names)
        session.add(history)


# ── Endpoints ────────────────────────────────────────────────────────────────

@item_request_blueprint.route('/api/kitchen/request_add_items', methods=['POST'])
@jwt_required()
def request_add_items():
    """
    Any kitchen member submits one or more items for the host/co-host to review.

    Request body:
    {
        "kitchen_id": 1,
        "items": [
            {
                "name": "tomato",           (required)
                "quantity": 5,              (optional, default 1)
                "unit": "kg",               (optional, default "count")
                "group": "vegetables",      (optional, default "pantry")
                "expiry_date": "7 days",    (optional)
                "thumbnail": "base64..."    (optional)
            }
        ]
    }
    """
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()

        kitchen_id = data.get('kitchen_id')
        items = data.get('items', [])

        if not items:
            return jsonify({'error': 'items list cannot be empty'}), 400

        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400

        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404

        # Must be a member of this kitchen (any role)
        is_member = (
            kitchen.host_id == user_id or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == kitchen_id,
                KitchenMember.user_id == user_id
            ).first() is not None
        )
        if not is_member:
            return jsonify({'error': 'You are not a member of this kitchen'}), 403

        # Validate item names upfront
        for item in items:
            if not item.get('name', '').strip():
                return jsonify({'error': 'Each item must have a name'}), 400

        created_request_ids = []

        for item in items:
            unit_value = item.get('unit')
            unit = (
                unit_value.strip().lower()
                if (unit_value and isinstance(unit_value, str) and unit_value.strip())
                else 'count'
            )

            group = item.get('group', '').strip().lower() or 'pantry'

            quantity_value = item.get('quantity')
            if quantity_value is not None:
                try:
                    quantity = float(quantity_value)
                except (ValueError, TypeError):
                    return jsonify({'error': f"Invalid quantity for '{item['name']}'"}), 400
            else:
                quantity = 1.0

            request_id = uuid.uuid4().hex

            item_request = ItemAddRequest(
                request_id=request_id,
                kitchen_id=kitchen_id,
                requested_by=user_id,
                name=item['name'].strip(),
                quantity=quantity,
                unit=unit,
                group=group,
                thumbnail=item.get('thumbnail') or None,
                expiry_date=item.get('expiry_date') or None,
                status='pending',
                created_at=datetime.now(timezone.utc)
            )
            session.add(item_request)
            created_request_ids.append(request_id)

        session.commit()

        return jsonify({
            'message': (
                f'{len(created_request_ids)} item request(s) submitted successfully. '
                'Awaiting host approval.'
            ),
            'request_ids': created_request_ids
        }), 201

    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@item_request_blueprint.route('/api/kitchen/item_requests', methods=['GET'])
@jwt_required()
def get_item_requests():
    """
    Get item add requests for a kitchen.

    Host/co-host: all requests, filterable by status (default: pending).
    Member:       their own requests only.

    Query params:
        kitchen_id  (required)
        status      'pending' | 'approved' | 'rejected' | 'all'  (default: pending)
    """
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])

        kitchen_id = request.args.get('kitchen_id')
        status_filter = request.args.get('status', 'pending').lower()

        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Valid kitchen_id is required'}), 400

        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404

        is_host = kitchen.host_id == user_id
        is_co_host = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == user_id,
            KitchenMember.member_type == 'co-host'
        ).first() is not None
        is_member = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == user_id
        ).first() is not None

        if not (is_host or is_co_host or is_member):
            return jsonify({'error': 'You are not a member of this kitchen'}), 403

        query = session.query(ItemAddRequest).filter(
            ItemAddRequest.kitchen_id == kitchen_id
        )

        valid_statuses = {'pending', 'approved', 'rejected', 'all'}

        if is_host or is_co_host:
            if status_filter not in valid_statuses:
                status_filter = 'pending'
            if status_filter != 'all':
                query = query.filter(ItemAddRequest.status == status_filter)
        else:
            # Regular member sees only their own requests
            query = query.filter(ItemAddRequest.requested_by == user_id)
            if status_filter in valid_statuses and status_filter != 'all':
                query = query.filter(ItemAddRequest.status == status_filter)

        requests_list = query.order_by(ItemAddRequest.created_at.desc()).all()

        # Enrich with requester name
        result = []
        for req in requests_list:
            requester = session.query(User).filter(User.id == req.requested_by).first()
            requester_name = (
                f"{requester.first_name} {requester.last_name}"
                if requester else 'Unknown'
            )
            result.append({
                'request_id':     req.request_id,
                'kitchen_id':     str(req.kitchen_id),
                'requested_by':   str(req.requested_by),
                'requester_name': requester_name,
                'name':           req.name,
                'quantity':       req.quantity,
                'unit':           req.unit,
                'group':          req.group,
                'expiry_date':    req.expiry_date,
                'thumbnail':      req.thumbnail,
                'status':         req.status,
                'reject_reason':  req.reject_reason,
                'created_at':     req.created_at.isoformat() if req.created_at else None,
                'reviewed_at':    req.reviewed_at.isoformat() if req.reviewed_at else None,
            })

        return jsonify({
            'kitchen_id': str(kitchen_id),
            'total':      len(result),
            'requests':   result
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@item_request_blueprint.route('/api/kitchen/respond_to_item_request', methods=['POST'])
@jwt_required()
def respond_to_item_request():
    """
    Host or co-host approves or rejects a pending item add request.

    On approval  → item immediately inserted into kitchen inventory
                   (merges quantity if item already exists).
    On rejection → request closed, inventory unchanged.

    Request body:
    {
        "request_id": "abc123...",
        "action": "approved",           "approved" | "rejected"
        "reject_reason": "..."          (optional, only meaningful on rejection)
    }
    """
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()

        request_id = data.get('request_id')
        action = data.get('action', '').lower()
        reject_reason = data.get('reject_reason', '').strip() or None

        if not request_id:
            return jsonify({'error': 'request_id is required'}), 400

        if action not in ('approved', 'rejected'):
            return jsonify({'error': 'action must be "approved" or "rejected"'}), 400

        item_request = session.query(ItemAddRequest).filter(
            ItemAddRequest.request_id == request_id
        ).first()

        if not item_request:
            return jsonify({'error': 'Item request not found'}), 404

        if item_request.status != 'pending':
            return jsonify({
                'error': f'This request has already been {item_request.status}'
            }), 409

        # Verify the responding user is host or co-host of the request's kitchen
        kitchen = session.query(Kitchen).filter(
            Kitchen.id == item_request.kitchen_id
        ).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404

        is_host = kitchen.host_id == user_id
        is_co_host = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == item_request.kitchen_id,
            KitchenMember.user_id == user_id,
            KitchenMember.member_type == 'co-host'
        ).first() is not None

        if not (is_host or is_co_host):
            return jsonify({
                'error': 'Only the host or co-host can approve or reject item requests'
            }), 403

        now = datetime.now(timezone.utc)
        item_request.status = action
        item_request.reviewed_by = user_id
        item_request.reviewed_at = now

        new_item_ids = []

        if action == 'approved':
            item_dict = {
                'name':        item_request.name,
                'quantity':    item_request.quantity,
                'unit':        item_request.unit,
                'group':       item_request.group,
                'expiry_date': item_request.expiry_date,
                'thumbnail':   item_request.thumbnail,
            }

            item_id, needs_thumbnail = _insert_item_into_kitchen(
                session, item_request.kitchen_id, item_dict
            )

            if needs_thumbnail:
                new_item_ids.append(item_id)

            _add_items_to_kitchen_history(
                item_request.kitchen_id,
                [item_request.name.strip().lower()],
                session
            )
        else:
            item_request.reject_reason = reject_reason

        session.commit()

        # Fire background thumbnail generation after commit so item_id is persisted
        if new_item_ids:
            t = threading.Thread(
                target=generate_thumbnails_background,
                args=(new_item_ids,),
                daemon=True
            )
            t.start()

        if action == 'approved':
            message = (
                f"Item '{item_request.name}' has been approved and "
                "added to the kitchen inventory."
            )
        else:
            message = f"Item request for '{item_request.name}' has been rejected."
            if reject_reason:
                message += f" Reason: {reject_reason}"

        return jsonify({'message': message, 'status': action}), 200

    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()