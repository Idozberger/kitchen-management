"""
Kitchen Management Routes - COMPLETE POSTGRESQL VERSION
ALL 32 endpoints converted from MongoDB to PostgreSQL
Original: 2414 lines, 32 endpoints
"""

from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from flask import Blueprint, request, jsonify, url_for
from datetime import datetime, timezone, timedelta
import uuid
import threading
from random import randint
from utils.gpt_vision import generate_food_thumbnail, generate_thumbnails_background
from utils.kitchen_item_helpers import _insert_item_into_kitchen

# PostgreSQL imports
from db_connection import get_session
from models import (
    Kitchen, KitchenMember, KitchenItem, User, Invitation, MyList, Pantry,
    KitchenItemsHistory, GeneratedRecipe, ConsumptionEvent, ConsumptionUsageEvent
)
from sqlalchemy import and_, or_, func

kitchen_management_blueprint = Blueprint('kitchen_management_blueprint', __name__)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def add_items_to_kitchen_history(kitchen_id, item_names, session):
    """Add unique item names to kitchen_items_history (PostgreSQL)"""
    clean_names = list({name.strip().lower() for name in item_names if name.strip()})
    if not clean_names:
        return
    
    history = session.query(KitchenItemsHistory).filter(
        KitchenItemsHistory.kitchen_id == kitchen_id
    ).first()
    
    if history:
        existing_items = set(history.item_names or [])
        existing_items.update(clean_names)
        history.item_names = list(existing_items)
    else:
        history = KitchenItemsHistory(kitchen_id=kitchen_id, item_names=clean_names)
        session.add(history)


# ============================================================
# KITCHEN MANAGEMENT ENDPOINTS (1-13)
# ============================================================

@kitchen_management_blueprint.route('/api/kitchen/create', methods=['POST'])
@jwt_required()
def create_kitchen():
    """Create a new kitchen"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_name = data.get('kitchen_name', '').strip()
        
        if not kitchen_name:
            return jsonify({'error': 'Kitchen name is required'}), 400
        
        def generate_unique_code():
            while True:
                new_code = str(randint(100000, 999999))
                if not session.query(Kitchen).filter(Kitchen.invitation_code == new_code).first():
                    return new_code
        
        invitation_code = generate_unique_code()
        kitchen = Kitchen(
            kitchen_name=kitchen_name,
            host_id=user_id,
            invitation_code=invitation_code,
            created_at=datetime.now(timezone.utc)
        )
        session.add(kitchen)
        session.flush()
        
        host_member = KitchenMember(
            kitchen_id=kitchen.id,
            user_id=user_id,
            member_type='host',
            joined_at=datetime.now(timezone.utc)
        )
        session.add(host_member)
        session.commit()
        
        return jsonify({
            'message': 'Kitchen created successfully',
            'kitchen_id': str(kitchen.id),
            'invitation_code': invitation_code
        }), 201
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/join_with_code', methods=['POST'])
@jwt_required(optional=True)
def join_kitchen_with_code():
    """Join a kitchen using invitation code"""
    session = get_session()
    try:
        data = request.get_json()
        invitation_code = data.get('invitation_code', '').strip()
        provided_user_id = data.get('user_id', '').strip()
        
        if not invitation_code:
            return jsonify({'error': 'Invitation code is required'}), 400
        
        user_identity = get_jwt()
        if user_identity:
            user_id = int(user_identity['user_id'])
        elif provided_user_id:
            try:
                user_id = int(provided_user_id)
            except (ValueError, TypeError):
                return jsonify({'error': 'Invalid user ID'}), 400
        else:
            return jsonify({'error': 'User ID is required when not authenticated'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.invitation_code == invitation_code).first()
        if not kitchen:
            return jsonify({'error': 'Invalid invitation code'}), 404
        
        is_member = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen.id,
            KitchenMember.user_id == user_id
        ).first() is not None
        
        if is_member:
            return jsonify({'error': 'User is already a member of this kitchen'}), 400
        
        new_member = KitchenMember(
            kitchen_id=kitchen.id,
            user_id=user_id,
            member_type='member',
            joined_at=datetime.now(timezone.utc)
        )
        session.add(new_member)
        session.commit()
        
        if kitchen.host_id == user_id:
            role = 'host'
            invitation_code_to_return = kitchen.invitation_code
        else:
            member = session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == kitchen.id,
                KitchenMember.user_id == user_id
            ).first()
            role = member.member_type if member else 'member'
            invitation_code_to_return = kitchen.invitation_code if role == 'co-host' else None
        
        return jsonify({
            'message': 'User has successfully joined the kitchen',
            'kitchen': {
                'kitchen_id': str(kitchen.id),
                'kitchen_name': kitchen.kitchen_name,
                'role': role,
                'invitation_code': invitation_code_to_return
            }
        }), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/refresh_invitation_code', methods=['POST'])
@jwt_required()
def refresh_invitation_code():
    """Refresh kitchen invitation code (host only)"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        
        if not kitchen_id:
            return jsonify({'error': 'Kitchen ID is required'}), 400
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        if kitchen.host_id != user_id:
            return jsonify({'error': 'Only the host can refresh the invitation code'}), 403
        
        def generate_unique_code():
            while True:
                new_code = str(randint(100000, 999999))
                if not session.query(Kitchen).filter(Kitchen.invitation_code == new_code).first():
                    return new_code
        
        kitchen.invitation_code = generate_unique_code()
        session.commit()
        
        return jsonify({
            'message': 'Invitation code refreshed successfully',
            'new_invitation_code': kitchen.invitation_code
        }), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/remove', methods=['POST'])
@jwt_required()
def remove_kitchen():
    """Remove kitchen and all related data (host only)"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        if kitchen.host_id != user_id:
            return jsonify({'error': 'Only the host can remove the kitchen'}), 403
        
        # Delete all related data
        session.query(MyList).filter(MyList.kitchen_id == kitchen_id).delete()
        session.query(Invitation).filter(Invitation.kitchen_id == kitchen_id).delete()
        session.query(Pantry).filter(Pantry.kitchen_id == kitchen_id).delete()
        session.query(KitchenItemsHistory).filter(KitchenItemsHistory.kitchen_id == kitchen_id).delete()
        session.query(KitchenItem).filter(KitchenItem.kitchen_id == kitchen_id).delete()
        session.query(KitchenMember).filter(KitchenMember.kitchen_id == kitchen_id).delete()
        session.delete(kitchen)
        session.commit()
        
        return jsonify({'message': 'Kitchen and all related data removed successfully'}), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/invite', methods=['POST'])
@jwt_required()
def invite_member():
    """Send invitation to user by email (host only)"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        inviter_name = f"{user_identity['first_name']} {user_identity['last_name']}"
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        invitee_email = data.get('email')
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen or kitchen.host_id != user_id:
            return jsonify({'error': 'Only the host can send invitations'}), 403
        
        invitee = session.query(User).filter(User.email == invitee_email).first()
        if not invitee:
            return jsonify({'error': 'Invitee does not exist on the platform'}), 404
        
        is_member = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == invitee.id
        ).first() is not None
        
        if is_member:
            return jsonify({'error': 'Invitee is already a member of the kitchen'}), 409
        
        invitation_id = str(uuid.uuid4())
        invitation_url = url_for('kitchen_management_blueprint.respond_to_invitation', _external=True)
        
        invitation = Invitation(
            invitation_id=invitation_id,
            kitchen_id=kitchen_id,
            kitchen_name=kitchen.kitchen_name,
            inviter_name=inviter_name,
            invitee_id=invitee.id,
            status='pending',
            created_at=datetime.now(timezone.utc)
        )
        session.add(invitation)
        session.commit()
        
        return jsonify({
            'message': 'Invitation sent successfully',
            'invitation_url': invitation_url
        }), 201
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/respond_to_invitation', methods=['POST'])
@jwt_required()
def respond_to_invitation():
    """Accept or deny kitchen invitation"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        invitation_id = data.get('invitation_id')
        response = data.get('response')
        
        if not invitation_id:
            return jsonify({'error': 'Invitation ID is required'}), 400
        if response not in ['accepted', 'denied']:
            return jsonify({'error': 'Invalid response. Use "accepted" or "denied".'}), 400
        
        invitation = session.query(Invitation).filter(
            Invitation.invitation_id == invitation_id,
            Invitation.invitee_id == user_id,
            Invitation.status == 'pending'
        ).first()
        
        if not invitation:
            return jsonify({'error': 'Invalid or already processed invitation'}), 404
        
        current_time = datetime.now(timezone.utc)
        
        if response == 'accepted':
            new_member = KitchenMember(
                kitchen_id=invitation.kitchen_id,
                user_id=user_id,
                member_type='member',
                joined_at=current_time
            )
            session.add(new_member)
            invitation.status = 'accepted'
            invitation.accepted_at = current_time
            session.commit()
            message = 'You have joined the kitchen successfully'
        else:
            invitation.status = 'denied'
            invitation.denied_at = current_time
            session.commit()
            message = 'Invitation has been denied'
        
        return jsonify({'message': message}), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/invitations', methods=['GET'])
@jwt_required()
def view_invitations():
    """Get pending invitations for current user"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        
        pending_invitations = session.query(Invitation).filter(
            Invitation.invitee_id == user_id,
            Invitation.status == 'pending'
        ).all()
        
        invitations_list = [{
            '_id': str(inv.id),
            'invitation_id': inv.invitation_id,
            'kitchen_id': str(inv.kitchen_id),
            'kitchen_name': inv.kitchen_name,
            'inviter_name': inv.inviter_name,
            'invitee_id': str(inv.invitee_id),
            'status': inv.status,
            'created_at': inv.created_at.isoformat() if inv.created_at else None
        } for inv in pending_invitations]
        
        return jsonify({'invitations': invitations_list}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/leave', methods=['POST'])
@jwt_required()
def leave_kitchen():
    """Leave a kitchen (members only, not host)"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        if kitchen.host_id == user_id:
            return jsonify({
                'error': 'As the host, you cannot leave a kitchen you created. You can only remove it.'
            }), 403
        
        member = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == user_id
        ).first()
        
        if not member:
            return jsonify({'error': 'You are not a member of this kitchen'}), 403
        
        session.delete(member)
        session.commit()
        
        return jsonify({'message': 'You have left the kitchen successfully'}), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/list_user_kitchens', methods=['GET'])
@jwt_required()
def list_user_kitchens():
    """List all kitchens user is member of"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        
        kitchens = session.query(Kitchen).filter(
            or_(
                Kitchen.host_id == user_id,
                Kitchen.id.in_(
                    session.query(KitchenMember.kitchen_id).filter(KitchenMember.user_id == user_id)
                )
            )
        ).all()
        
        kitchens_with_roles = []
        for kitchen in kitchens:
            if kitchen.host_id == user_id:
                role = 'host'
                invitation_code = kitchen.invitation_code
            else:
                member = session.query(KitchenMember).filter(
                    KitchenMember.kitchen_id == kitchen.id,
                    KitchenMember.user_id == user_id
                ).first()
                role = member.member_type if member else 'unknown'
                invitation_code = kitchen.invitation_code if role == 'co-host' else None
            
            kitchens_with_roles.append({
                'kitchen_id': str(kitchen.id),
                'kitchen_name': kitchen.kitchen_name,
                'role': role,
                'invitation_code': invitation_code
            })
        
        return jsonify({'kitchens': kitchens_with_roles}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/view', methods=['GET'])
@jwt_required()
def view_kitchen_details():
    """View kitchen details with members list"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        kitchen_id = request.args.get('kitchen_id')
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_member = (
            kitchen.host_id == user_id or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == kitchen_id,
                KitchenMember.user_id == user_id
            ).first() is not None
        )
        
        if not is_member:
            return jsonify({'error': 'You are not a member of this kitchen'}), 403
        
        is_host_or_cohost = (
            kitchen.host_id == user_id or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == kitchen_id,
                KitchenMember.user_id == user_id,
                KitchenMember.member_type == 'co-host'
            ).first() is not None
        )
        
        members = session.query(KitchenMember, User).join(
            User, KitchenMember.user_id == User.id
        ).filter(KitchenMember.kitchen_id == kitchen_id).all()
        
        member_details = [{
            'user_id': str(member.user_id),
            'name': f"{user.first_name} {user.last_name}",
            'type': member.member_type
        } for member, user in members]
        
        kitchen_details = {
            'kitchen_id': str(kitchen.id),
            'kitchen_name': kitchen.kitchen_name,
            'host_id': str(kitchen.host_id),
            'created_at': kitchen.created_at.isoformat() if kitchen.created_at else None,
            'members': member_details,
            'invitation_code': kitchen.invitation_code if is_host_or_cohost else ''
        }
        
        return jsonify({'kitchen': kitchen_details}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/get_members', methods=['GET'])
@jwt_required()
def get_kitchen_members():
    """Get list of kitchen members"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        kitchen_id = request.args.get('kitchen_id')
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_member = (
            kitchen.host_id == user_id or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == kitchen_id,
                KitchenMember.user_id == user_id
            ).first() is not None
        )
        
        if not is_member:
            return jsonify({'error': 'You are not a member of this kitchen'}), 403
        
        is_host_or_cohost = (
            kitchen.host_id == user_id or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == kitchen_id,
                KitchenMember.user_id == user_id,
                KitchenMember.member_type == 'co-host'
            ).first() is not None
        )
        
        members = session.query(KitchenMember, User).join(
            User, KitchenMember.user_id == User.id
        ).filter(KitchenMember.kitchen_id == kitchen_id).all()
        
        member_details = [{
            'user_id': str(member.user_id),
            'name': f"{user.first_name} {user.last_name}",
            'type': member.member_type
        } for member, user in members]
        
        response = {
            'members': member_details,
            'invitation_code': kitchen.invitation_code if is_host_or_cohost else ''
        }
        
        return jsonify(response), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/kick_member', methods=['POST'])
@jwt_required()
def kick_member():
    """Remove member from kitchen (host or co-host only)"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        member_id_to_kick = data.get('member_id')
        
        try:
            kitchen_id = int(kitchen_id)
            member_id_to_kick = int(member_id_to_kick)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID or member ID'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_host = kitchen.host_id == user_id
        is_co_host = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == user_id,
            KitchenMember.member_type == 'co-host'
        ).first() is not None
        
        if not (is_host or is_co_host):
            return jsonify({'error': 'Only the host or co-host can kick members'}), 403
        
        if member_id_to_kick == kitchen.host_id or member_id_to_kick == user_id:
            return jsonify({'error': 'Cannot kick the host or yourself'}), 403
        
        member_to_kick = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == member_id_to_kick
        ).first()
        
        if not member_to_kick:
            return jsonify({'error': 'Member not found in the kitchen'}), 404
        
        session.delete(member_to_kick)
        session.commit()
        
        return jsonify({'message': 'Member has been removed from the kitchen successfully'}), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/make_cohost', methods=['POST'])
@jwt_required()
def make_cohost():
    """Promote member to co-host (host only)"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        member_id = data.get('member_id')
        
        try:
            kitchen_id = int(kitchen_id)
            member_id = int(member_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID or member ID'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        if kitchen.host_id != user_id:
            return jsonify({'error': 'Only the host can make a member a co-host'}), 403
        
        member = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == member_id
        ).first()
        
        if not member:
            return jsonify({'error': 'Member not found in the kitchen'}), 404
        
        if member.member_type == 'co-host':
            return jsonify({'error': 'This member is already a co-host'}), 409
        
        member.member_type = 'co-host'
        session.commit()
        
        return jsonify({'message': 'Member has been promoted to co-host successfully'}), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()

@kitchen_management_blueprint.route('/api/kitchen/demote_cohost', methods=['POST'])
@jwt_required()
def demote_cohost():
    """Demote co-host to regular member (host only)"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        member_id = data.get('member_id')
        
        # Validate input
        try:
            kitchen_id = int(kitchen_id)
            member_id = int(member_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID or member ID'}), 400
        
        # Fetch kitchen
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        # Check if requester is the host
        if kitchen.host_id != user_id:
            return jsonify({'error': 'Only the host can demote a co-host'}), 403
        
        # Find the member to demote
        member = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == member_id
        ).first()
        
        if not member:
            return jsonify({'error': 'Member not found in the kitchen'}), 404
        
        # Check if member is actually a co-host
        if member.member_type != 'co-host':
            return jsonify({'error': 'This member is not a co-host'}), 409
        
        # Demote to regular member
        member.member_type = 'member'
        session.commit()
        
        return jsonify({'message': 'Co-host has been demoted to member successfully'}), 200
        
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()
# ============================================================
# INVENTORY MANAGEMENT ENDPOINTS (14-19)
# ============================================================

@kitchen_management_blueprint.route('/api/kitchen/add_items', methods=['POST'])
@jwt_required()
def add_items_to_kitchen():
    """Add items to kitchen inventory (host and co-host only).
    Members should use /api/kitchen/request_add_items instead."""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        items = data.get('items', [])
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_host = kitchen.host_id == user_id
        is_co_host = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == user_id,
            KitchenMember.member_type == 'co-host'
        ).first() is not None
        
        if not (is_host or is_co_host):
            return jsonify({
                'error': 'Only the host or co-hosts can add items directly. '
                         'Members can request items via /api/kitchen/request_add_items'
            }), 403
        
        for item in items:
            if 'name' not in item or not item['name']:
                return jsonify({'error': 'Each item must have a name'}), 400

        new_item_ids = []

        for new_item in items:
            item_id, needs_thumbnail = _insert_item_into_kitchen(session, kitchen_id, new_item)
            if needs_thumbnail:
                new_item_ids.append(item_id)
        
        session.commit()
        add_items_to_kitchen_history(kitchen_id, [item['name'].strip().lower() for item in items], session)
        session.commit()

        if new_item_ids:
            t = threading.Thread(
                target=generate_thumbnails_background,
                args=(new_item_ids,),
                daemon=True
            )
            t.start()
            print(f"Background thumbnail generation started for {len(new_item_ids)} new items")
        
        return jsonify({'message': 'Items have been added to the kitchen successfully'}), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/list_items', methods=['GET'])
@jwt_required()
def list_kitchen_items():
    """List kitchen items with expiry and stock status"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        kitchen_id = request.args.get('kitchen_id')
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_host = kitchen.host_id == user_id
        is_member = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == user_id
        ).first() is not None
        
        if not (is_host or is_member):
            return jsonify({'error': 'You do not have permission to view items in this kitchen'}), 403
        
        items = session.query(KitchenItem).filter(KitchenItem.kitchen_id == kitchen_id).all()
        
        def calculate_expiry_status(added_at, expiry_date_str):
            if not added_at or not expiry_date_str:
                return None
            try:
                if added_at.tzinfo is None:
                    added_at = added_at.replace(tzinfo=timezone.utc)
                expiry_parts = expiry_date_str.lower().strip().split()
                if len(expiry_parts) != 2:
                    return None
                amount = int(expiry_parts[0])
                unit = expiry_parts[1]
                if 'day' in unit:
                    days = amount
                elif 'week' in unit:
                    days = amount * 7
                elif 'month' in unit:
                    days = amount * 30
                elif 'year' in unit:
                    days = amount * 365
                else:
                    return None
                expiration_date = added_at + timedelta(days=days)
                current_date = datetime.now(timezone.utc)
                days_remaining = (expiration_date - current_date).days
                if days_remaining < 0:
                    return "expired"
                elif days_remaining <= 2:
                    return "expiring_soon"
                else:
                    return "fresh"
            except:
                return None
        
        def calculate_stock_status(quantity, unit):
            try:
                qty = float(quantity)
                unit_lower = unit.lower()
                if qty == 0:
                    return "out_of_stock"
                if unit_lower in ['count', 'piece', 'pieces']:
                    if qty <= 2:
                        return "low_stock"
                elif unit_lower in ['kg', 'litre', 'liter', 'l']:
                    if qty <= 0.5:
                        return "low_stock"
                elif unit_lower in ['grams', 'g', 'ml', 'millilitre']:
                    if qty <= 100:
                        return "low_stock"
                else:
                    if qty <= 1:
                        return "low_stock"
                return "in_stock"
            except:
                return "in_stock"
        
        items_list = [{
            'item_id': item.item_id,
            'name': item.name,
            'quantity': item.quantity,
            'unit': item.unit,
            'group': item.group,
            'thumbnail': item.thumbnail,
            'expiry_date': item.expiry_date,
            'added_at': item.added_at.isoformat() if item.added_at else None,
            'expiry_status': calculate_expiry_status(item.added_at, item.expiry_date),
            'stock_status': calculate_stock_status(item.quantity, item.unit)
        } for item in items]
        
        return jsonify({'items': items_list}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/remove_items', methods=['POST'])
@jwt_required()
def remove_items_from_kitchen():
    """Remove items from kitchen (with consumption logging)"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        item_ids_to_remove = data.get('item_ids', [])
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        if not item_ids_to_remove:
            return jsonify({'error': 'item_ids array is required'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_host = kitchen.host_id == user_id
        is_co_host = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == user_id,
            KitchenMember.member_type == 'co-host'
        ).first() is not None
        
        if not (is_host or is_co_host):
            return jsonify({'error': 'Only the host or co-hosts can remove items'}), 403
        
        current_time = datetime.now(timezone.utc)
        items_to_remove = []
        
        for item_id in item_ids_to_remove:
            item = session.query(KitchenItem).filter(
                KitchenItem.kitchen_id == kitchen_id,
                KitchenItem.item_id == item_id
            ).first()
            
            if item:
                items_to_remove.append(item)
                if item.quantity > 0 and item.added_at:
                    consumption_event = ConsumptionEvent(
                        kitchen_id=kitchen_id,
                        item_id=item.item_id,
                        item_name=item.name.lower(),
                        quantity=item.quantity,
                        unit=item.unit,
                        added_at=item.added_at,
                        depleted_at=current_time,
                        days_lasted=(current_time - item.added_at).days or 1,
                        method='manual',
                        created_at=current_time
                    )
                    session.add(consumption_event)
                session.delete(item)
        
        if not items_to_remove:
            return jsonify({'error': f"Items not found"}), 404
        
        session.commit()
        return jsonify({'message': f'{len(items_to_remove)} item(s) removed successfully'}), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/update_items', methods=['POST'])
@jwt_required()
def update_kitchen_items():
    """Update kitchen items"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        items_to_update = data.get('items', [])
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_host = kitchen.host_id == user_id
        is_co_host = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == user_id,
            KitchenMember.member_type == 'co-host'
        ).first() is not None
        
        if not (is_host or is_co_host):
            return jsonify({'error': 'Only the host or co-hosts can update items'}), 403
        
        for item in items_to_update:
            if 'item_id' not in item:
                return jsonify({'error': 'Each item must have an item_id'}), 400
        
        items_not_found = []
        
        for update_data in items_to_update:
            item_id = update_data.get('item_id')
            item = session.query(KitchenItem).filter(
                KitchenItem.kitchen_id == kitchen_id,
                KitchenItem.item_id == item_id
            ).first()
            
            if not item:
                items_not_found.append(item_id)
                continue
            
            if 'quantity' in update_data:
                try:
                    new_quantity = float(update_data['quantity'])
                    if new_quantity > 0:
                        item.quantity = new_quantity
                    else:
                        session.delete(item)
                        continue
                except ValueError:
                    return jsonify({'error': f"Invalid quantity for item_id '{item_id}'"}), 400
            
            if 'name' in update_data:
                item.name = update_data['name']
            if 'unit' in update_data:
                item.unit = update_data['unit']
            if 'group' in update_data:
                item.group = update_data.get('group', 'pantry').strip().lower()
            if 'thumbnail' in update_data:
                item.thumbnail = update_data['thumbnail']
            if 'expiry_date' in update_data:
                item.expiry_date = update_data['expiry_date']
                item.added_at = datetime.now(timezone.utc)
        
        if items_not_found:
            session.rollback()
            return jsonify({'error': f"Items {items_not_found} not found"}), 404
        
        session.commit()
        return jsonify({'message': 'Items have been updated successfully'}), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/mark_recipe_finished', methods=['POST'])
@jwt_required()
def mark_recipe_as_finished():
    """Mark recipe as finished and deduct ingredients from inventory"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        recipe_id = data.get('recipe_id')
        
        try:
            kitchen_id = int(kitchen_id)
            recipe_id = int(recipe_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID or recipe ID'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_host = kitchen.host_id == user_id
        is_co_host = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == user_id,
            KitchenMember.member_type == 'co-host'
        ).first() is not None
        
        if not (is_host or is_co_host):
            return jsonify({'error': 'Only the host or co-hosts can mark recipes as finished'}), 403
        
        recipe = session.query(GeneratedRecipe).filter(GeneratedRecipe.id == recipe_id).first()
        if not recipe:
            return jsonify({'error': 'Recipe not found'}), 404
        
        recipe_ingredients = recipe.ingredients or []
        if not recipe_ingredients:
            return jsonify({'error': 'Recipe has no ingredients to deduct'}), 400
        
        # Unit normalization
        def normalize_unit(unit):
            unit_lower = unit.strip().lower()
            unit_map = {
                ('g', 'gram', 'grams'): 'grams',
                ('kg', 'kilogram', 'kilograms', 'kgs'): 'kg',
                ('ml', 'millilitre', 'milliliter'): 'ml',
                ('l', 'litre', 'liter'): 'litre',
                ('count', 'piece', 'pieces', 'pcs', 'pc'): 'count',
                ('lb', 'lbs', 'pound', 'pounds'): 'kg',
                ('oz', 'ounce', 'ounces'): 'grams'
            }
            for keys, value in unit_map.items():
                if unit_lower in keys:
                    return value
            return unit_lower
        
        def convert_to_base_unit(amount, unit):
            amount_float = float(amount)
            unit_normalized = normalize_unit(unit)
            conversions = {
                'kg': (amount_float * 1000, 'grams'),
                'grams': (amount_float, 'grams'),
                'litre': (amount_float * 1000, 'ml'),
                'ml': (amount_float, 'ml'),
                'count': (amount_float, 'count')
            }
            if unit_normalized in conversions:
                return conversions[unit_normalized]
            raise ValueError(f"Unsupported unit: {unit}")
        
        def convert_from_base_unit(amount_base, base_unit, target_unit):
            target_normalized = normalize_unit(target_unit)
            if base_unit == 'grams':
                return amount_base / 1000 if target_normalized == 'kg' else amount_base
            elif base_unit == 'ml':
                return amount_base / 1000 if target_normalized == 'litre' else amount_base
            return amount_base
        
        current_time = datetime.now(timezone.utc)
        not_found_items = []
        
        for recipe_ingredient in recipe_ingredients:
            ingredient_name = recipe_ingredient['name'].strip().lower()
            recipe_amount_str = recipe_ingredient['amount']
            recipe_unit = recipe_ingredient['unit'].strip()
            
            try:
                recipe_amount_base, recipe_base_unit = convert_to_base_unit(recipe_amount_str, recipe_unit)
            except (ValueError, TypeError) as e:
                not_found_items.append({
                    'name': recipe_ingredient['name'],
                    'amount': recipe_amount_str,
                    'unit': recipe_unit,
                    'reason': str(e)
                })
                continue
            
            matching_item = None
            kitchen_items = session.query(KitchenItem).filter(
                KitchenItem.kitchen_id == kitchen_id,
                func.lower(KitchenItem.name) == ingredient_name
            ).all()
            
            for item in kitchen_items:
                try:
                    item_amount_base, item_base_unit = convert_to_base_unit(item.quantity, item.unit)
                    if item_base_unit == recipe_base_unit:
                        matching_item = item
                        break
                except (ValueError, TypeError):
                    continue
            
            if matching_item:
                try:
                    current_amount_base, base_unit = convert_to_base_unit(matching_item.quantity, matching_item.unit)
                    new_amount_base = current_amount_base - recipe_amount_base
                    
                    quantity_used = convert_from_base_unit(recipe_amount_base, base_unit, matching_item.unit)
                    quantity_remaining = max(0, convert_from_base_unit(new_amount_base, base_unit, matching_item.unit))
                    
                    usage_event = ConsumptionUsageEvent(
                        usage_id=uuid.uuid4().hex,
                        kitchen_id=kitchen_id,
                        item_id=matching_item.item_id,
                        item_name=matching_item.name.lower(),
                        quantity_used=float(quantity_used),
                        quantity_remaining=float(quantity_remaining),
                        unit=matching_item.unit,
                        used_at=current_time,
                        method='recipe',
                        recipe_id=recipe_id,
                        created_at=current_time
                    )
                    session.add(usage_event)
                    
                    if new_amount_base <= 0:
                        consumption_event = ConsumptionEvent(
                            kitchen_id=kitchen_id,
                            item_id=matching_item.item_id,
                            item_name=matching_item.name.lower(),
                            quantity=matching_item.quantity,
                            unit=matching_item.unit,
                            added_at=matching_item.added_at,
                            depleted_at=current_time,
                            days_lasted=(current_time - matching_item.added_at).days if matching_item.added_at else 1,
                            method='recipe',
                            created_at=current_time
                        )
                        session.add(consumption_event)
                        session.delete(matching_item)
                    else:
                        new_amount_original = convert_from_base_unit(new_amount_base, base_unit, matching_item.unit)
                        matching_item.quantity = round(new_amount_original, 3)
                except Exception as e:
                    not_found_items.append({
                        'name': recipe_ingredient['name'],
                        'amount': recipe_amount_str,
                        'unit': recipe_unit,
                        'reason': str(e)
                    })
            else:
                not_found_items.append({
                    'name': recipe_ingredient['name'],
                    'amount': recipe_amount_str,
                    'unit': recipe_unit,
                    'reason': 'Not found in inventory'
                })
        
        session.commit()
        
        response_message = 'Recipe marked as finished and inventory updated successfully.'
        if not_found_items:
            return jsonify({
                'message': response_message,
                'warning': f"{len(not_found_items)} ingredient(s) not found or incompatible",
                'missing_ingredients': not_found_items,
                'inventory_updated': True
            }), 200
        
        return jsonify({'message': response_message}), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/set_date_range', methods=['POST'])
@jwt_required()
def set_kitchen_date_range():
    """Set or update kitchen date range"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if not kitchen_id or not start_date or not end_date:
            return jsonify({'error': 'kitchen_id, start_date, and end_date are required'}), 400
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_member = (
            kitchen.host_id == user_id or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == kitchen_id,
                KitchenMember.user_id == user_id
            ).first() is not None
        )

        if not is_member:
            return jsonify({'error': 'You are not a member of this kitchen'}), 403
        
        try:
            start_date_obj = datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
            end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        if end_date_obj <= start_date_obj:
            return jsonify({'error': 'end_date must be after start_date'}), 400
        
        kitchen.start_date = start_date
        kitchen.end_date = end_date
        kitchen.date_range_updated_at = datetime.now(timezone.utc)
        session.commit()
        
        return jsonify({
            'message': 'Kitchen date range set successfully',
            'kitchen_id': str(kitchen_id),
            'start_date': start_date,
            'end_date': end_date
        }), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/get_date_range', methods=['GET'])
@jwt_required()
def get_kitchen_date_range():
    """Get kitchen date range"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        kitchen_id = request.args.get('kitchen_id')
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Valid kitchen_id is required'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_member = (
            kitchen.host_id == user_id or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == kitchen_id,
                KitchenMember.user_id == user_id
            ).first() is not None
        )
        
        if not is_member:
            return jsonify({'error': 'You are not a member of this kitchen'}), 403
        
        response = {
            'kitchen_id': str(kitchen_id),
            'kitchen_name': kitchen.kitchen_name,
            'start_date': kitchen.start_date,
            'end_date': kitchen.end_date
        }
        
        if kitchen.date_range_updated_at:
            response['date_range_updated_at'] = kitchen.date_range_updated_at.isoformat()
        
        return jsonify(response), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


# ============================================================
# SHOPPING LIST ENDPOINTS (20-27)
# ============================================================

@kitchen_management_blueprint.route('/api/kitchen/add_item_to_list', methods=['POST'])
@jwt_required()
def add_item_to_list():
    """Add single item to shopping list (mylist or requested)"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        name = data.get('name', '').strip()
        quantity = data.get('quantity')
        unit = data.get('unit', '').strip()
        bucket_type = data.get('bucket_type', '').strip()
        thumbnail = data.get('thumbnail')
        expiry_date = data.get('expiry_date')
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        if not name or not quantity or not unit or bucket_type not in ['requested', 'mylist']:
            return jsonify({'error': 'Missing or invalid required fields'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_host = kitchen.host_id == user_id
        is_co_host = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == user_id,
            KitchenMember.member_type == 'co-host'
        ).first() is not None
        is_member = is_host or is_co_host or session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == user_id
        ).first() is not None
        
        if bucket_type == 'mylist' and not (is_host or is_co_host):
            return jsonify({'error': 'Only host or co-host can add to mylist'}), 403
        if bucket_type == 'requested' and not is_member:
            return jsonify({'error': 'You are not a member of this kitchen'}), 403
        
        item = MyList(
            item_id=uuid.uuid4().hex,
            kitchen_id=kitchen_id,
            user_id=user_id,
            name=name,
            quantity=quantity,
            unit=unit,
            bucket_type=bucket_type,
            thumbnail=thumbnail,
            expiry_date=expiry_date,
            created_at=datetime.now(timezone.utc)
        )
        session.add(item)
        session.commit()
        
        return jsonify({
            'message': f"Item added to '{bucket_type}' successfully.",
            'mongo_id': str(item.id),
            'item_id': item.item_id
        }), 201
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/request_item', methods=['POST'])
@jwt_required()
def request_item():
    """Request items (batch add to shopping list)"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        items = data.get('items', [])
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        if not items or not isinstance(items, list):
            return jsonify({'error': 'Items list is required'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_member = (
            kitchen.host_id == user_id or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == kitchen_id,
                KitchenMember.user_id == user_id
            ).first() is not None
        )
        
        if not is_member:
            return jsonify({'error': 'You are not a member of this kitchen'}), 403
        
        created_items = []
        
        for item_data in items:
            name = item_data.get('name', '').strip()
            quantity = item_data.get('quantity')
            unit = item_data.get('unit', '').strip()
            
            if not name or not quantity or not unit:
                continue
            
            item_id = uuid.uuid4().hex
            item = MyList(
                item_id=item_id,
                kitchen_id=kitchen_id,
                user_id=user_id,
                name=name,
                quantity=quantity,
                unit=unit,
                bucket_type='requested',
                created_at=datetime.now(timezone.utc)
            )
            session.add(item)
            created_items.append({'item_id': item_id, 'name': name, 'quantity': quantity, 'unit': unit})
        
        session.commit()
        
        return jsonify({
            'message': f'{len(created_items)} item(s) requested successfully',
            'requested_items': created_items
        }), 201
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/delete_items', methods=['POST'])
@jwt_required()
def delete_items():
    """Delete items from shopping list"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        item_ids = data.get('item_ids')
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        if not item_ids:
            return jsonify({'error': 'item_ids is required'}), 400
        if isinstance(item_ids, str):
            item_ids = [item_ids]
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_authorized = (
            kitchen.host_id == user_id or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == kitchen_id,
                KitchenMember.user_id == user_id,
                KitchenMember.member_type == 'co-host'
            ).first() is not None
        )
        
        if not is_authorized:
            return jsonify({'error': 'Unauthorized access'}), 403
        
        result = session.query(MyList).filter(
            MyList.kitchen_id == kitchen_id,
            MyList.item_id.in_(item_ids)
        ).delete(synchronize_session=False)
        
        session.commit()
        
        return jsonify({
            'message': f"{result} item(s) deleted.",
            'deleted_count': result,
            'attempted_ids': item_ids
        }), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/update_item', methods=['POST'])
@jwt_required()
def update_item():
    """Update shopping list item"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        item_id = data.get('item_id', '').strip()
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        if not item_id:
            return jsonify({'error': 'item_id is required'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        item = session.query(MyList).filter(
            MyList.kitchen_id == kitchen_id,
            MyList.item_id == item_id
        ).first()
        
        if not item:
            return jsonify({'error': 'Item not found'}), 404
        
        bucket_type = item.bucket_type
        
        if bucket_type == 'mylist':
            is_authorized = (
                kitchen.host_id == user_id or
                session.query(KitchenMember).filter(
                    KitchenMember.kitchen_id == kitchen_id,
                    KitchenMember.user_id == user_id,
                    KitchenMember.member_type == 'co-host'
                ).first() is not None
            )
            if not is_authorized:
                return jsonify({'error': 'Only host or co-host can update mylist items'}), 403
        elif bucket_type == 'requested':
            if item.user_id != user_id:
                return jsonify({'error': 'You can only update your own requested items'}), 403
        
        if data.get('name'):
            item.name = data['name']
        if data.get('quantity') is not None:
            item.quantity = data['quantity']
        if data.get('unit'):
            item.unit = data['unit']
        if 'thumbnail' in data:
            item.thumbnail = data['thumbnail']
        if 'expiry_date' in data:
            item.expiry_date = data['expiry_date']
        
        item.modified_at = datetime.now(timezone.utc)
        session.commit()
        
        return jsonify({'message': 'Item updated successfully'}), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/update_bucket_type', methods=['POST'])
@jwt_required()
def update_bucket_type():
    """Move items between mylist and requested"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        item_ids = data.get('item_ids')
        new_type = data.get('bucket_type')
        
        if new_type not in ['requested', 'mylist']:
            return jsonify({'error': 'Invalid bucket_type'}), 400
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        if not item_ids:
            return jsonify({'error': 'item_ids is required'}), 400
        if isinstance(item_ids, str):
            item_ids = [item_ids]
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_authorized = (
            kitchen.host_id == user_id or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == kitchen_id,
                KitchenMember.user_id == user_id,
                KitchenMember.member_type == 'co-host'
            ).first() is not None
        )
        
        if not is_authorized:
            return jsonify({'error': 'Unauthorized access'}), 403
        
        current_time = datetime.now(timezone.utc)
        result = session.query(MyList).filter(
            MyList.kitchen_id == kitchen_id,
            MyList.item_id.in_(item_ids)
        ).update({'bucket_type': new_type, 'modified_at': current_time}, synchronize_session=False)
        
        session.commit()
        
        return jsonify({
            'message': f"{result} item(s) moved to {new_type}.",
            'modified_count': result
        }), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/get_all_mylist_items', methods=['GET'])
@jwt_required()
def get_all_mylist_items():
    """Get shopping list items with filters"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        kitchen_id = request.args.get('kitchen_id')
        bucket_type = request.args.get('bucket_type')
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_member = (
            kitchen.host_id == user_id or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == kitchen_id,
                KitchenMember.user_id == user_id
            ).first() is not None
        )

        if not is_member:
            return jsonify({'error': 'You are not a member of this kitchen'}), 403
        
        query = session.query(MyList).filter(MyList.kitchen_id == kitchen_id)
        if bucket_type in ['requested', 'mylist']:
            query = query.filter(MyList.bucket_type == bucket_type)
        
        items = query.all()
        
        def calculate_expiry_status(created_at, expiry_date_str):
            if not created_at or not expiry_date_str:
                return None
            try:
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                expiry_parts = expiry_date_str.lower().strip().split()
                if len(expiry_parts) != 2:
                    return None
                amount = int(expiry_parts[0])
                unit = expiry_parts[1]
                if 'day' in unit:
                    days = amount
                elif 'week' in unit:
                    days = amount * 7
                elif 'month' in unit:
                    days = amount * 30
                elif 'year' in unit:
                    days = amount * 365
                else:
                    return None
                expiration_date = created_at + timedelta(days=days)
                current_date = datetime.now(timezone.utc)
                days_remaining = (expiration_date - current_date).days
                if days_remaining < 0:
                    return "expired"
                elif days_remaining <= 2:
                    return "expiring_soon"
                else:
                    return "fresh"
            except:
                return None
        
        def calculate_stock_status(quantity, unit):
            try:
                qty = float(quantity)
                unit_lower = unit.lower()
                if qty == 0:
                    return "out_of_stock"
                if unit_lower in ['count', 'piece', 'pieces']:
                    if qty <= 2:
                        return "low_stock"
                elif unit_lower in ['kg', 'litre', 'liter', 'l']:
                    if qty <= 0.5:
                        return "low_stock"
                elif unit_lower in ['grams', 'g', 'ml', 'millilitre']:
                    if qty <= 100:
                        return "low_stock"
                else:
                    if qty <= 1:
                        return "low_stock"
                return "in_stock"
            except:
                return "in_stock"
        
        items_list = [{
            '_id': str(item.id),
            'item_id': item.item_id,
            'kitchen_id': str(item.kitchen_id),
            'user_id': str(item.user_id),
            'name': item.name,
            'quantity': item.quantity,
            'unit': item.unit,
            'bucket_type': item.bucket_type,
            'thumbnail': item.thumbnail,
            'expiry_date': item.expiry_date,
            'created_at': item.created_at.isoformat() if item.created_at else None,
            'modified_at': item.modified_at.isoformat() if item.modified_at else None,
            'expiry_status': calculate_expiry_status(item.created_at, item.expiry_date),
            'stock_status': calculate_stock_status(item.quantity, item.unit),
            'auto_added': item.auto_added
        } for item in items]
        
        return jsonify({'items': items_list}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/get_user_requested_items', methods=['GET'])
@jwt_required()
def get_user_requested_items():
    """Get current user's requested items"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        kitchen_id = request.args.get('kitchen_id')
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_member = (
            kitchen.host_id == user_id or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == kitchen_id,
                KitchenMember.user_id == user_id
            ).first() is not None
        )
        
        if not is_member:
            return jsonify({'error': 'You are not a member of this kitchen'}), 403
        
        items = session.query(MyList).filter(
            MyList.kitchen_id == kitchen_id,
            MyList.user_id == user_id
        ).all()
        
        items_list = [{
            '_id': str(item.id),
            'item_id': item.item_id,
            'kitchen_id': str(item.kitchen_id),
            'user_id': str(item.user_id),
            'name': item.name,
            'quantity': item.quantity,
            'unit': item.unit,
            'bucket_type': item.bucket_type,
            'thumbnail': item.thumbnail,
            'expiry_date': item.expiry_date,
            'created_at': item.created_at.isoformat() if item.created_at else None,
            'modified_at': item.modified_at.isoformat() if item.modified_at else None
        } for item in items]
        
        return jsonify({'user_items': items_list}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/add_mylist_items_to_kitchen_inventory', methods=['POST'])
@jwt_required()
def add_mylist_items_to_kitchen_inventory():
    """Move all mylist items to kitchen inventory"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid or missing kitchen ID'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_host = kitchen.host_id == user_id
        is_co_host = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == user_id,
            KitchenMember.member_type == 'co-host'
        ).first() is not None
        
        if not (is_host or is_co_host):
            return jsonify({'error': 'Only host or co-host can perform this action'}), 403
        
        mylist_items = session.query(MyList).filter(
            MyList.kitchen_id == kitchen_id,
            MyList.bucket_type == 'mylist'
        ).all()
        
        if not mylist_items:
            return jsonify({'message': 'No items found in mylist to process'}), 200
        
        for item in mylist_items:
            name = item.name.strip().lower()
            unit = item.unit.strip().lower()
            
            try:
                quantity = float(item.quantity)
            except (ValueError, TypeError):
                continue
            
            group = item.group if hasattr(item, 'group') and item.group else 'pantry'
            group = group.strip().lower()
            
            existing_item = session.query(KitchenItem).filter(
                KitchenItem.kitchen_id == kitchen_id,
                func.lower(KitchenItem.name) == name,
                func.lower(KitchenItem.unit) == unit,
                func.lower(KitchenItem.group) == group
            ).first()
            
            if existing_item:
                try:
                    existing_quantity = float(existing_item.quantity)
                    existing_item.quantity = existing_quantity + quantity
                except ValueError:
                    continue
            else:
                kitchen_item = KitchenItem(
                    item_id=uuid.uuid4().hex,
                    kitchen_id=kitchen_id,
                    name=item.name,
                    quantity=quantity,
                    unit=item.unit,
                    group=group,
                    added_at=datetime.now(timezone.utc)
                )
                session.add(kitchen_item)
        
        add_items_to_kitchen_history(
            kitchen_id,
            [item.name.strip().lower() for item in mylist_items],
            session
        )
        
        item_ids_to_delete = [item.item_id for item in mylist_items]
        session.query(MyList).filter(
            MyList.kitchen_id == kitchen_id,
            MyList.item_id.in_(item_ids_to_delete),
            MyList.bucket_type == 'mylist'
        ).delete(synchronize_session=False)
        
        session.commit()
        
        return jsonify({
            'message': f"{len(mylist_items)} item(s) added to inventory and removed from mylist.",
            'added_to_inventory': len(mylist_items)
        }), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


# ============================================================
# PANTRY MANAGEMENT ENDPOINTS (28-30)
# ============================================================

@kitchen_management_blueprint.route('/api/kitchen/pantry/create', methods=['POST'])
@jwt_required()
def create_pantry():
    """Create pantries/storage areas (batch)"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        pantries_list = data.get('pantries', [])
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        if not pantries_list or not isinstance(pantries_list, list):
            return jsonify({'error': 'Pantries list is required'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_host = kitchen.host_id == user_id
        is_co_host = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == user_id,
            KitchenMember.member_type == 'co-host'
        ).first() is not None
        
        if not (is_host or is_co_host):
            return jsonify({'error': 'Only host or co-host can create pantries'}), 403
        
        existing_pantries = session.query(Pantry).filter(Pantry.kitchen_id == kitchen_id).all()
        existing_names = {p.pantry_name.lower() for p in existing_pantries}
        
        created_pantries = []
        skipped_pantries = []
        
        for pantry_data in pantries_list:
            pantry_name = pantry_data.get('pantry_name', '').strip()
            
            if not pantry_name:
                continue
            
            if pantry_name.lower() in existing_names:
                skipped_pantries.append(pantry_name)
                continue
            
            pantry_id = uuid.uuid4().hex
            pantry = Pantry(
                pantry_id=pantry_id,
                pantry_name=pantry_name,
                kitchen_id=kitchen_id,
                created_by=user_id,
                created_at=datetime.now(timezone.utc)
            )
            session.add(pantry)
            created_pantries.append({'pantry_id': pantry_id, 'pantry_name': pantry_name})
            existing_names.add(pantry_name.lower())
        
        session.commit()
        
        response = {
            'message': f'{len(created_pantries)} pantry(ies) created successfully',
            'created_pantries': created_pantries
        }
        
        if skipped_pantries:
            response['skipped'] = skipped_pantries
            response['message'] += f', {len(skipped_pantries)} skipped (duplicates)'
        
        return jsonify(response), 201
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/pantry/list', methods=['GET'])
@jwt_required()
def list_pantries():
    """List all pantries for a kitchen"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        kitchen_id = request.args.get('kitchen_id')
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_member = (
            kitchen.host_id == user_id or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == kitchen_id,
                KitchenMember.user_id == user_id
            ).first() is not None
        )
        
        if not is_member:
            return jsonify({'error': 'You are not a member of this kitchen'}), 403
        
        pantries = session.query(Pantry).filter(Pantry.kitchen_id == kitchen_id).all()
        
        pantries_list = [{
            'pantry_id': pantry.pantry_id,
            'pantry_name': pantry.pantry_name,
            '_id': str(pantry.id),
            'created_at': pantry.created_at.isoformat() if pantry.created_at else None
        } for pantry in pantries]
        
        return jsonify({'pantries': pantries_list}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@kitchen_management_blueprint.route('/api/kitchen/pantry/delete', methods=['POST'])
@jwt_required()
def delete_pantry():
    """Delete a pantry"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        kitchen_id = data.get('kitchen_id')
        pantry_id = data.get('pantry_id', '').strip()
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        if not pantry_id:
            return jsonify({'error': 'Pantry ID is required'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_host = kitchen.host_id == user_id
        is_co_host = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == user_id,
            KitchenMember.member_type == 'co-host'
        ).first() is not None
        
        if not (is_host or is_co_host):
            return jsonify({'error': 'Only host or co-host can delete pantries'}), 403
        
        pantry = session.query(Pantry).filter(
            Pantry.pantry_id == pantry_id,
            Pantry.kitchen_id == kitchen_id
        ).first()
        
        if not pantry:
            return jsonify({'error': 'Pantry not found'}), 404
        
        session.delete(pantry)
        session.commit()
        
        return jsonify({'message': 'Pantry deleted successfully'}), 200
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


# ============================================================
# UTILITY ENDPOINTS (31-32)
# ============================================================

@kitchen_management_blueprint.route('/api/kitchen/get_ai_generated_list', methods=['GET'])
@jwt_required()
def get_ai_generated_list():
    """Get missing items from kitchen history"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        kitchen_id = request.args.get('kitchen_id')
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400
        
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_host = kitchen.host_id == user_id
        is_member = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == user_id
        ).first() is not None
        is_co_host = session.query(KitchenMember).filter(
            KitchenMember.kitchen_id == kitchen_id,
            KitchenMember.user_id == user_id,
            KitchenMember.member_type == 'co-host'
        ).first() is not None
        
        if not (is_host or is_member or is_co_host):
            return jsonify({'error': 'You are not a member of this kitchen'}), 403
        
        history = session.query(KitchenItemsHistory).filter(
            KitchenItemsHistory.kitchen_id == kitchen_id
        ).first()
        
        historical_items = set(history.item_names if history and history.item_names else [])
        
        current_items = session.query(KitchenItem).filter(KitchenItem.kitchen_id == kitchen_id).all()
        current_items_set = {item.name.strip().lower() for item in current_items}
        
        mylist_items = session.query(MyList).filter(MyList.kitchen_id == kitchen_id).all()
        mylist_items_set = {item.name.strip().lower() for item in mylist_items}
        
        unavailable_items = historical_items - current_items_set - mylist_items_set
        missing_items = sorted(list(unavailable_items))
        
        return jsonify({'missing_items': missing_items}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()