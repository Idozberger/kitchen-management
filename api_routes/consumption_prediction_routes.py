# api_routes/consumption_prediction_routes.py
"""
API routes for consumption prediction system - COMPLETE POSTGRESQL VERSION
Provides endpoints for manual testing, monitoring, and user insights.
Enhanced with quantity-aware predictions and detailed analytics.

CONVERTED FROM MONGODB TO POSTGRESQL
Original: 1013 lines with 10+ endpoints
"""

from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
import uuid

# PostgreSQL imports
from db_connection import get_session
from models import (
    Kitchen, KitchenMember, KitchenItem, KitchenConsumptionPattern, ConsumptionEvent,
    ConsumptionUsageEvent, PendingConfirmation, MyList
)
from sqlalchemy import func, and_, or_

# Create blueprint
consumption_prediction_blueprint = Blueprint('consumption_prediction_blueprint', __name__)

from utils.consumption_predictor import ConsumptionPredictor
from utils.scheduler import ConsumptionScheduler

# Initialize predictor (no parameters needed)
predictor = ConsumptionPredictor()


@consumption_prediction_blueprint.route('/api/consumption/predict', methods=['GET'])
@jwt_required()
def get_prediction():
    """
    Get predicted consumption days for a specific item in a kitchen.
    Enhanced with quantity-aware predictions.
    
    Query Parameters:
        kitchen_id (required): Kitchen ID
        item_name (required): Item name
        quantity (optional): Quantity to predict for
        unit (optional): Unit of measurement (required if quantity provided)
    """
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        
        kitchen_id = request.args.get('kitchen_id')
        item_name = request.args.get('item_name')
        quantity = request.args.get('quantity', type=float)
        unit = request.args.get('unit')
        
        # Validate required parameters
        if not kitchen_id or not item_name:
            return jsonify({'error': 'kitchen_id and item_name are required'}), 400
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen_id'}), 400
        
        # Validate quantity parameters
        if quantity is not None and not unit:
            return jsonify({'error': 'unit is required when quantity is provided'}), 400
        
        # Check user is member of kitchen
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
        
        predicted_days = predictor.get_predicted_consumption_days(kitchen_id, item_name)

        # Get pattern for additional info
        pattern = session.query(KitchenConsumptionPattern).filter(
            KitchenConsumptionPattern.kitchen_id == kitchen_id,
            KitchenConsumptionPattern.item_name == item_name.strip().lower()
        ).first()
        
        response = {
            'kitchen_id': str(kitchen_id),
            'item_name': item_name,
            'predicted_days': int(predicted_days),
            'prediction_type': 'personalized' if pattern and pattern.sample_count >= 2 else 'baseline'
        }
        
        # Add quantity-specific info if provided
        if quantity and unit:
            response['quantity'] = quantity
            response['unit'] = unit
            # ✅ Use quantity-aware prediction
            predicted_days = predictor.get_predicted_consumption_days_for_quantity(
                kitchen_id, item_name, quantity, unit
            )
            response['predicted_days'] = predicted_days
        
        # Add pattern details if exists
        if pattern:
            pattern_info = {
                'personalized_days': pattern.personalized_days,
                'sample_count': pattern.sample_count,
                'confidence': pattern.confidence
            }
            
            # Add rate info if available
            if pattern.consumption_rate:
                pattern_info['consumption_rate'] = pattern.consumption_rate
                pattern_info['rate_unit'] = f"{pattern.unit}/day"
            
            response['pattern'] = pattern_info
        
        return jsonify(response), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@consumption_prediction_blueprint.route('/api/consumption/patterns', methods=['GET'])
@jwt_required()
def get_kitchen_patterns():
    """
    Get all personalized consumption patterns for a kitchen.
    Includes consumption rate data for quantity-aware predictions.
    
    Query Parameters:
        kitchen_id (required): Kitchen ID
        sort_by (optional): Sort field ('item_name', 'personalized_days', 'confidence', 'sample_count')
        order (optional): Sort order ('asc' or 'desc', default 'asc')
    """
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        
        kitchen_id = request.args.get('kitchen_id')
        sort_by = request.args.get('sort_by', 'item_name')
        order = request.args.get('order', 'asc')
        
        if not kitchen_id:
            return jsonify({'error': 'kitchen_id is required'}), 400
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen_id'}), 400
        
        # Validate sort parameters
        valid_sort_fields = ['item_name', 'personalized_days', 'confidence', 'sample_count']
        if sort_by not in valid_sort_fields:
            return jsonify({'error': f'Invalid sort_by. Must be one of: {", ".join(valid_sort_fields)}'}), 400
        
        if order not in ['asc', 'desc']:
            return jsonify({'error': 'Invalid order. Must be "asc" or "desc"'}), 400
        
        # Check user is member
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
        
        # Get patterns with sorting
        query = session.query(KitchenConsumptionPattern).filter(
            KitchenConsumptionPattern.kitchen_id == kitchen_id
        )
        
        # Apply sorting
        if sort_by == 'personalized_days':
            query = query.order_by(
                KitchenConsumptionPattern.personalized_days.desc() if order == 'desc' 
                else KitchenConsumptionPattern.personalized_days.asc()
            )
        elif sort_by == 'sample_count':
            query = query.order_by(
                KitchenConsumptionPattern.sample_count.desc() if order == 'desc'
                else KitchenConsumptionPattern.sample_count.asc()
            )
        elif sort_by == 'confidence':
            query = query.order_by(
                KitchenConsumptionPattern.confidence.desc() if order == 'desc'
                else KitchenConsumptionPattern.confidence.asc()
            )
        else:  # item_name
            query = query.order_by(
                KitchenConsumptionPattern.item_name.desc() if order == 'desc'
                else KitchenConsumptionPattern.item_name.asc()
            )
        
        patterns = query.all()
        
        # Convert to dict
        patterns_list = []
        for pattern in patterns:
            pattern_dict = {
                '_id': str(pattern.id),
                'kitchen_id': str(pattern.kitchen_id),
                'item_name': pattern.item_name,
                'personalized_days': pattern.personalized_days,
                'sample_count': pattern.sample_count,
                'confidence': pattern.confidence,
                'last_consumption_date': pattern.last_consumption_date.isoformat() if pattern.last_consumption_date else None,
                'created_at': pattern.created_at.isoformat() if pattern.created_at else None,
                'updated_at': pattern.updated_at.isoformat() if pattern.updated_at else None
            }
            
            # Add rate info if available
            if pattern.consumption_rate:
                pattern_dict['consumption_rate'] = pattern.consumption_rate
                pattern_dict['unit'] = pattern.unit
                pattern_dict['rate_display'] = f"{pattern.consumption_rate:.3f} {pattern.unit}/day"
            
            patterns_list.append(pattern_dict)
        
        return jsonify({
            'kitchen_id': str(kitchen_id),
            'patterns_count': len(patterns_list),
            'patterns': patterns_list,
            'sort_by': sort_by,
            'order': order
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@consumption_prediction_blueprint.route('/api/consumption/history', methods=['GET'])
@jwt_required()
def get_consumption_history():
    """
    Get consumption event history for a kitchen.
    
    Query Parameters:
        kitchen_id (required): Kitchen ID
        item_name (optional): Filter by specific item
        method (optional): Filter by method ('auto', 'manual', 'recipe', 'confirmed')
        limit (optional): Max number of events (default 50, max 200)
        days (optional): Only show events from last N days
    """
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        
        kitchen_id = request.args.get('kitchen_id')
        item_name = request.args.get('item_name')
        method = request.args.get('method')
        limit = min(int(request.args.get('limit', 50)), 200)
        days = request.args.get('days', type=int)
        
        if not kitchen_id:
            return jsonify({'error': 'kitchen_id is required'}), 400
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen_id'}), 400
        
        # Validate method parameter
        if method and method not in ['auto', 'manual', 'recipe', 'confirmed']:
            return jsonify({'error': 'Invalid method. Must be "auto", "manual", "recipe", or "confirmed"'}), 400
        
        # Check user is member
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
        
        # Build query
        query = session.query(ConsumptionEvent).filter(
            ConsumptionEvent.kitchen_id == kitchen_id
        )
        
        if item_name:
            query = query.filter(ConsumptionEvent.item_name == item_name.strip().lower())
        
        if method:
            query = query.filter(ConsumptionEvent.method == method)
        
        if days:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            query = query.filter(ConsumptionEvent.depleted_at >= cutoff_date)
        
        # Get events
        events = query.order_by(ConsumptionEvent.depleted_at.desc()).limit(limit).all()
        
        # Convert to dict
        events_list = []
        for event in events:
            event_dict = {
                '_id': str(event.id),
                'kitchen_id': str(event.kitchen_id),
                'item_id': event.item_id,
                'item_name': event.item_name,
                'quantity': event.quantity,
                'unit': event.unit,
                'added_at': event.added_at.isoformat() if event.added_at else None,
                'depleted_at': event.depleted_at.isoformat() if event.depleted_at else None,
                'days_lasted': event.days_lasted,
                'consumption_rate': event.consumption_rate,
                'method': event.method,
                'created_at': event.created_at.isoformat() if event.created_at else None
            }
            
            # Add rate display if available
            if event.consumption_rate:
                event_dict['rate_display'] = f"{event.consumption_rate:.3f} {event.unit}/day"
            
            events_list.append(event_dict)
        
        # Calculate analytics
        analytics = {
            'total_events': len(events_list),
            'by_method': {
                'auto': sum(1 for e in events_list if e.get('method') == 'auto'),
                'manual': sum(1 for e in events_list if e.get('method') == 'manual'),
                'recipe': sum(1 for e in events_list if e.get('method') == 'recipe'),
                'confirmed': sum(1 for e in events_list if e.get('method') == 'confirmed')
            }
        }
        
        if events_list:
            days_lasted_values = [e.get('days_lasted', 0) for e in events_list if e.get('days_lasted')]
            if days_lasted_values:
                analytics['average_days'] = sum(days_lasted_values) / len(days_lasted_values)
                analytics['min_days'] = min(days_lasted_values)
                analytics['max_days'] = max(days_lasted_values)
        
        return jsonify({
            'kitchen_id': str(kitchen_id),
            'item_name': item_name,
            'method': method,
            'days_filter': days,
            'events_count': len(events_list),
            'events': events_list,
            'analytics': analytics
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@consumption_prediction_blueprint.route('/api/consumption/check_now', methods=['POST'])
@jwt_required()
def manual_consumption_check():
    """
    Manually trigger consumption prediction check immediately.
    Useful for testing and debugging. Restricted to kitchen hosts.
    
    Body Parameters:
        kitchen_id (optional): Check specific kitchen only
    """
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        
        data = request.get_json() or {}
        specific_kitchen_id = data.get('kitchen_id')
        
        # If specific kitchen requested, validate access
        if specific_kitchen_id:
            try:
                specific_kitchen_id = int(specific_kitchen_id)
            except (ValueError, TypeError):
                return jsonify({'error': 'Invalid kitchen_id'}), 400
            
            kitchen = session.query(Kitchen).filter(Kitchen.id == specific_kitchen_id).first()
            
            if not kitchen:
                return jsonify({'error': 'Kitchen not found'}), 404
            
            # Check if user is host
            is_host = kitchen.host_id == user_id
            
            if not is_host:
                return jsonify({'error': 'Only kitchen host can trigger manual check'}), 403
        
        scheduler = ConsumptionScheduler()
        summary = scheduler.run_check_now()

        return jsonify({
            'message': 'Manual consumption check completed',
            'summary': summary,
            'triggered_by': str(user_id),
            'specific_kitchen': str(specific_kitchen_id) if specific_kitchen_id else None
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@consumption_prediction_blueprint.route('/api/consumption/scheduler/status', methods=['GET'])
@jwt_required()
def get_scheduler_status():
    """
    Get status of scheduled jobs and next run time.

    """
    scheduler = ConsumptionScheduler()
    jobs = scheduler.get_scheduled_jobs()

    return jsonify({
        'status': 'running',
        'jobs_count': len(jobs),
        'jobs': jobs
    }), 200


@consumption_prediction_blueprint.route('/api/consumption/stats', methods=['GET'])
@jwt_required()
def get_consumption_stats():
    """
    Get comprehensive consumption statistics for a kitchen.
    Provides insights and analytics dashboard data.
    
    Query Parameters:
        kitchen_id (required): Kitchen ID
    """
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        
        kitchen_id = request.args.get('kitchen_id')
        
        if not kitchen_id:
            return jsonify({'error': 'kitchen_id is required'}), 400
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen_id'}), 400
        
        # Check user is member
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
        
        # Gather statistics
        patterns_count = session.query(KitchenConsumptionPattern).filter(
            KitchenConsumptionPattern.kitchen_id == kitchen_id
        ).count()
        
        events_count = session.query(ConsumptionEvent).filter(
            ConsumptionEvent.kitchen_id == kitchen_id
        ).count()
        
        # Get confidence breakdown
        patterns = session.query(KitchenConsumptionPattern).filter(
            KitchenConsumptionPattern.kitchen_id == kitchen_id
        ).all()
        
        confidence_breakdown = {
            'low': sum(1 for p in patterns if p.confidence == 'low'),
            'medium': sum(1 for p in patterns if p.confidence == 'medium'),
            'high': sum(1 for p in patterns if p.confidence == 'high')
        }
        
        # Get recent events (last 30 days)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        recent_events = session.query(ConsumptionEvent).filter(
            ConsumptionEvent.kitchen_id == kitchen_id,
            ConsumptionEvent.depleted_at >= thirty_days_ago
        ).all()
        
        # Method breakdown
        method_breakdown = {
            'auto': sum(1 for e in recent_events if e.method == 'auto'),
            'manual': sum(1 for e in recent_events if e.method == 'manual'),
            'recipe': sum(1 for e in recent_events if e.method == 'recipe'),
            'confirmed': sum(1 for e in recent_events if e.method == 'confirmed')
        }
        
        # Top consumed items
        item_consumption = {}
        for event in recent_events:
            item = event.item_name or 'unknown'
            item_consumption[item] = item_consumption.get(item, 0) + 1
        
        top_items = sorted(item_consumption.items(), key=lambda x: x[1], reverse=True)[:10]
        
        # Calculate average accuracy
        patterns_with_samples = [p for p in patterns if p.sample_count >= 3]
        avg_confidence = len(patterns_with_samples) / len(patterns) * 100 if patterns else 0
        
        return jsonify({
            'kitchen_id': str(kitchen_id),
            'total_patterns': patterns_count,
            'total_events': events_count,
            'confidence_breakdown': confidence_breakdown,
            'recent_events_30_days': len(recent_events),
            'method_breakdown': method_breakdown,
            'top_consumed_items': [{'item': item, 'count': count} for item, count in top_items],
            'learning_progress': {
                'patterns_learned': patterns_count,
                'confidence_percentage': round(avg_confidence, 1),
                'total_observations': events_count
            }
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@consumption_prediction_blueprint.route('/api/consumption/insights', methods=['GET'])
@jwt_required()
def get_consumption_insights():
    """
    Get AI-powered insights and recommendations for a kitchen.
    Provides actionable insights based on consumption patterns.
    
    Query Parameters:
        kitchen_id (required): Kitchen ID
    """
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        
        kitchen_id = request.args.get('kitchen_id')
        
        if not kitchen_id:
            return jsonify({'error': 'kitchen_id is required'}), 400
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen_id'}), 400
        
        # Check user is member
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
        
        insights = []
        
        # Get patterns
        patterns = session.query(KitchenConsumptionPattern).filter(
            KitchenConsumptionPattern.kitchen_id == kitchen_id
        ).all()
        
        # Insight 1: Items with high confidence
        high_confidence = [p for p in patterns if p.confidence == 'high']
        if high_confidence:
            insights.append({
                'type': 'success',
                'title': 'Well-Learned Items',
                'message': f"System has high confidence predictions for {len(high_confidence)} items",
                'items': [p.item_name for p in high_confidence[:5]],
                'icon': '✅'
            })
        
        # Insight 2: Items needing more data
        low_confidence = [p for p in patterns if p.confidence == 'low']
        if low_confidence:
            insights.append({
                'type': 'info',
                'title': 'Learning in Progress',
                'message': f"{len(low_confidence)} items need more consumption data for better predictions",
                'items': [p.item_name for p in low_confidence[:5]],
                'icon': '📊'
            })
        
        # Insight 3: Fast consuming items
        fast_items = [p for p in patterns if p.personalized_days < 5]
        if fast_items:
            insights.append({
                'type': 'warning',
                'title': 'Fast-Consuming Items',
                'message': f"{len(fast_items)} items are consumed quickly (less than 5 days)",
                'items': [{'name': p.item_name, 'days': p.personalized_days} for p in fast_items],
                'recommendation': 'Consider buying in larger quantities or more frequently',
                'icon': '⚡'
            })
        
        # Insight 4: Slow consuming items
        slow_items = [p for p in patterns if p.personalized_days > 30]
        if slow_items:
            insights.append({
                'type': 'info',
                'title': 'Long-Lasting Items',
                'message': f"{len(slow_items)} items last over 30 days",
                'items': [{'name': p.item_name, 'days': p.personalized_days} for p in slow_items],
                'recommendation': 'These items can be bought in bulk to save trips',
                'icon': '🢢'
            })
        
        # Insight 5: System maturity
        total_patterns = len(patterns)
        if total_patterns == 0:
            insights.append({
                'type': 'info',
                'title': 'Getting Started',
                'message': 'System is still learning your consumption patterns',
                'recommendation': 'Continue using your kitchen normally, predictions will improve over time',
                'icon': '🌱'
            })
        elif total_patterns < 10:
            insights.append({
                'type': 'info',
                'title': 'Early Learning Stage',
                'message': f'Learned patterns for {total_patterns} items so far',
                'recommendation': 'As you use more items, predictions will become more accurate',
                'icon': '📈'
            })
        else:
            insights.append({
                'type': 'success',
                'title': 'Mature System',
                'message': f'System has learned patterns for {total_patterns} items',
                'recommendation': 'Predictions are becoming increasingly personalized to your household',
                'icon': '🎯'
            })
        
        return jsonify({
            'kitchen_id': str(kitchen_id),
            'insights_count': len(insights),
            'insights': insights,
            'generated_at': datetime.now(timezone.utc).isoformat()
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


# ============================================================
# PENDING CONFIRMATIONS ENDPOINTS
# ============================================================

@consumption_prediction_blueprint.route('/api/consumption/confirmations/pending', methods=['GET'])
@jwt_required()
def get_pending_confirmations():
    """
    Get all pending depletion confirmations for a kitchen.
    Returns items that system thinks are depleted but need user confirmation.
    
    Query Parameters:
        kitchen_id (required): Kitchen ID
    """
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        
        kitchen_id = request.args.get('kitchen_id')
        
        # Validate kitchen_id
        if not kitchen_id:
            return jsonify({'error': 'Valid kitchen_id is required'}), 400
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen_id'}), 400
        
        # Check kitchen exists
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        # Check user is member
        is_member = (
            kitchen.host_id == user_id or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == kitchen_id,
                KitchenMember.user_id == user_id
            ).first() is not None
        )
        
        if not is_member:
            return jsonify({'error': 'You are not a member of this kitchen'}), 403
        
        # Get pending confirmations (not expired)
        confirmations = session.query(PendingConfirmation).filter(
            PendingConfirmation.kitchen_id == kitchen_id,
            PendingConfirmation.status == 'pending',
            PendingConfirmation.expires_at > datetime.now(timezone.utc)
        ).order_by(PendingConfirmation.created_at.desc()).all()
        
        # Convert to JSON-serializable format
        confirmations_list = []
        for conf in confirmations:
            confirmations_list.append({
                '_id': str(conf.id),
                'confirmation_id': conf.confirmation_id,
                'kitchen_id': str(conf.kitchen_id),
                'item_id': conf.item_id,
                'item_name': conf.item_name,
                'quantity': conf.quantity,
                'unit': conf.unit,
                'added_at': conf.added_at.isoformat() if conf.added_at else None,
                'predicted_depletion_date': conf.predicted_depletion_date.isoformat() if conf.predicted_depletion_date else None,
                'expires_at': conf.expires_at.isoformat() if conf.expires_at else None,
                'created_at': conf.created_at.isoformat() if conf.created_at else None,
                'status': conf.status
            })
        
        return jsonify({
            'kitchen_id': str(kitchen_id),
            'confirmations': confirmations_list,
            'count': len(confirmations_list)
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@consumption_prediction_blueprint.route('/api/consumption/confirmations/respond', methods=['POST'])
@jwt_required()
def respond_to_confirmation():
    """
    User confirms or denies item depletion.
    Only logs consumption when user CONFIRMS (ground truth).
    
    Body Parameters:
        confirmation_id (required): Confirmation ID
        response (required): 'confirmed' or 'denied'
        actual_quantity_remaining (optional): Remaining quantity if denied
    """
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        
        confirmation_id = data.get('confirmation_id')
        response = data.get('response')  # 'confirmed' or 'denied'
        actual_quantity = data.get('actual_quantity_remaining')
        
        # Validate
        if not confirmation_id:
            return jsonify({'error': 'confirmation_id is required'}), 400
        
        if response not in ['confirmed', 'denied']:
            return jsonify({'error': 'response must be "confirmed" or "denied"'}), 400
        
        # Get confirmation
        confirmation = session.query(PendingConfirmation).filter(
            PendingConfirmation.confirmation_id == confirmation_id,
            PendingConfirmation.status == 'pending'
        ).first()
        
        if not confirmation:
            return jsonify({'error': 'Confirmation not found or already processed'}), 404
        
        # Check user is member of kitchen
        kitchen = session.query(Kitchen).filter(Kitchen.id == confirmation.kitchen_id).first()
        
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        is_member = (
            kitchen.host_id == user_id or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == confirmation.kitchen_id,
                KitchenMember.user_id == user_id
            ).first() is not None
        )
        
        if not is_member:
            return jsonify({'error': 'You are not a member of this kitchen'}), 403
        
        current_time = datetime.now(timezone.utc)
        
        if response == 'confirmed':
            # User confirms item is finished - THIS IS GROUND TRUTH
            
            # Remove from inventory
            item_removed = session.query(KitchenItem).filter(
                KitchenItem.kitchen_id == confirmation.kitchen_id,
                KitchenItem.item_id == confirmation.item_id
            ).delete()
            
            if item_removed > 0:
                item_data = {
                    'item_id': confirmation.item_id,
                    'name': confirmation.item_name,
                    'quantity': confirmation.quantity,
                    'unit': confirmation.unit,
                    'added_at': confirmation.added_at
                }
                predictor.log_consumption_event(
                    confirmation.kitchen_id,
                    item_data,
                    current_time,
                    method='confirmed'
                )
                
                # Add to shopping list
                shopping_item = MyList(
                    item_id=str(uuid.uuid4().hex),
                    name=confirmation.item_name,
                    quantity=confirmation.quantity,
                    unit=confirmation.unit,
                    kitchen_id=confirmation.kitchen_id,
                    bucket_type='mylist',
                    user_id=user_id,
                    created_at=current_time,
                    modified_at=current_time,
                    auto_added=True
                )
                session.add(shopping_item)
                
                # Update confirmation status
                confirmation.status = 'confirmed'
                confirmation.confirmed_at = current_time
                
                session.commit()
                
                return jsonify({
                    'message': 'Depletion confirmed - item removed and added to shopping list',
                    'item_removed': True,
                    'added_to_shopping_list': True,
                    'consumption_logged': True
                }), 200
            else:
                session.rollback()
                return jsonify({'error': 'Item not found in inventory (already removed?)'}), 404
        
        else:  # response == 'denied'
            # User says item still exists - DON'T log consumption
            
            # Update confirmation status
            confirmation.status = 'denied'
            confirmation.confirmed_at = current_time
            
            if actual_quantity is not None:
                confirmation.actual_quantity_remaining = float(actual_quantity)
            
            session.commit()
            
            return jsonify({
                'message': 'Depletion denied - item remains in inventory',
                'item_removed': False,
                'consumption_logged': False,
                'note': 'No changes made to inventory or learning data'
            }), 200

    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@consumption_prediction_blueprint.route('/api/consumption/confirmations/count', methods=['GET'])
@jwt_required()
def get_pending_confirmations_count():
    """
    Get count of pending confirmations for a kitchen (for badge display).
    
    Query Parameters:
        kitchen_id (required): Kitchen ID
    """
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        
        kitchen_id = request.args.get('kitchen_id')
        
        if not kitchen_id:
            return jsonify({'error': 'Valid kitchen_id is required'}), 400
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen_id'}), 400
        
        # Check user is member
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
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Count pending confirmations
        count = session.query(PendingConfirmation).filter(
            PendingConfirmation.kitchen_id == kitchen_id,
            PendingConfirmation.status == 'pending',
            PendingConfirmation.expires_at > datetime.now(timezone.utc)
        ).count()
        
        return jsonify({
            'kitchen_id': str(kitchen_id),
            'pending_count': count
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


# ============================================================
# USAGE EVENTS ENDPOINTS (partial consumption)
# ============================================================

@consumption_prediction_blueprint.route('/api/consumption/usage/history', methods=['GET'])
@jwt_required()
def get_usage_history():
    """
    Get partial usage event history for a kitchen.
    Shows when items were used (but not fully depleted).
    
    Query Parameters:
        kitchen_id (required): Kitchen ID
        item_name (optional): Filter by specific item
        limit (optional): Max number of events (default 50, max 200)
        days (optional): Only show events from last N days
    """
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        
        kitchen_id = request.args.get('kitchen_id')
        item_name = request.args.get('item_name')
        limit = min(int(request.args.get('limit', 50)), 200)
        days = request.args.get('days', type=int)
        
        if not kitchen_id:
            return jsonify({'error': 'Valid kitchen_id is required'}), 400
        
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen_id'}), 400
        
        # Check user is member
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
            return jsonify({'error': 'Unauthorized'}), 403
        
        # Build query
        query = session.query(ConsumptionUsageEvent).filter(
            ConsumptionUsageEvent.kitchen_id == kitchen_id
        )
        
        if item_name:
            query = query.filter(ConsumptionUsageEvent.item_name == item_name.strip().lower())
        
        if days:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            query = query.filter(ConsumptionUsageEvent.used_at >= cutoff_date)
        
        # Get usage events
        usage_events = query.order_by(ConsumptionUsageEvent.used_at.desc()).limit(limit).all()
        
        # Convert to JSON-serializable
        events_list = []
        for event in usage_events:
            events_list.append({
                '_id': str(event.id),
                'kitchen_id': str(event.kitchen_id),
                'item_id': event.item_id,
                'item_name': event.item_name,
                'quantity_used': event.quantity_used,
                'quantity_remaining': event.quantity_remaining,
                'unit': event.unit,
                'used_at': event.used_at.isoformat() if event.used_at else None,
                'method': event.method,
                'recipe_id': str(event.recipe_id) if event.recipe_id else None,
                'created_at': event.created_at.isoformat() if event.created_at else None
            })
        
        # Calculate analytics
        analytics = {
            'total_events': len(events_list),
            'by_method': {
                'recipe': sum(1 for e in events_list if e.get('method') == 'recipe'),
                'manual': sum(1 for e in events_list if e.get('method') == 'manual')
            }
        }
        
        if events_list:
            analytics['total_quantity_used'] = sum(e.get('quantity_used', 0) for e in events_list)
        
        return jsonify({
            'kitchen_id': str(kitchen_id),
            'item_name': item_name,
            'usage_events': events_list,
            'count': len(events_list),
            'analytics': analytics
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


# Export blueprint
__all__ = ['consumption_prediction_blueprint']