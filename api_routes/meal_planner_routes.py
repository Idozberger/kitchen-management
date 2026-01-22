from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
import uuid

# PostgreSQL imports
from db_connection import get_session
from models import Kitchen, KitchenMember, MealPlan, GeneratedRecipe

# Create a Blueprint object
meal_planner_blueprint = Blueprint('meal_planner_blueprint', __name__)


@meal_planner_blueprint.route('/api/meal_plan/create', methods=['POST'])
@jwt_required()
def create_meal_plan():
    """Create a new meal plan"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        
        kitchen_id = data.get('kitchen_id')
        date = data.get('date')  # "2025-11-02"
        meal_type = data.get('meal_type')  # "breakfast", "lunch", "dinner", "snack"
        recipe_id = data.get('recipe_id')
        notes = data.get('notes', '')
        
        # Validate required fields
        if not all([kitchen_id, date, meal_type, recipe_id]):
            return jsonify({'error': 'kitchen_id, date, meal_type, and recipe_id are required'}), 400
        
        # Validate IDs
        try:
            kitchen_id = int(kitchen_id)
            recipe_id = int(recipe_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID or recipe ID'}), 400
        
        # Validate meal_type
        valid_meal_types = ['breakfast', 'lunch', 'dinner', 'snack']
        if meal_type not in valid_meal_types:
            return jsonify({'error': f'meal_type must be one of: {", ".join(valid_meal_types)}'}), 400
        
        # Check kitchen exists and user is a member
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
        
        # Parse date
        try:
            date_obj = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except ValueError:
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        # Check for duplicate (same kitchen + date + meal_type)
        existing = session.query(MealPlan).filter(
            MealPlan.kitchen_id == kitchen_id,
            MealPlan.date == date,
            MealPlan.meal_type == meal_type
        ).first()
        
        if existing:
            return jsonify({'error': f'A meal plan already exists for {meal_type} on {date}'}), 409
        
        # Fetch recipe from generated_recipes
        recipe = session.query(GeneratedRecipe).filter(GeneratedRecipe.id == recipe_id).first()
        
        if not recipe:
            return jsonify({'error': 'Recipe not found'}), 404
        
        # Create meal plan with denormalized recipe data
        meal_plan_id = uuid.uuid4().hex
        meal_plan = MealPlan(
            meal_plan_id=meal_plan_id,
            kitchen_id=kitchen_id,
            created_by=user_id,
            date=date,
            date_obj=date_obj,
            meal_type=meal_type,
            recipe_id=recipe_id,
            # Denormalized recipe data
            title=recipe.title,
            calories=recipe.calories,
            cooking_time=recipe.cooking_time,
            thumbnail=recipe.thumbnail,
            ingredients=recipe.ingredients,
            cooking_steps=recipe.cooking_steps,
            missing_items=recipe.missing_items,
            missing_items_list=recipe.missing_items_list,
            recipe_short_summary=recipe.recipe_short_summary,
            notes=notes,
            is_completed=False,
            completed_at=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        
        session.add(meal_plan)
        session.commit()
        session.refresh(meal_plan)
        
        return jsonify({
            'message': 'Meal plan created successfully',
            'meal_plan_id': meal_plan_id,
            '_id': str(meal_plan.id)
        }), 201

    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@meal_planner_blueprint.route('/api/meal_plan/list', methods=['GET'])
@jwt_required()
def list_meal_plans():
    """List meal plans with filters"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        
        kitchen_id = request.args.get('kitchen_id')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        meal_type = request.args.get('meal_type')
        status = request.args.get('status', 'all')  # 'all', 'completed', 'pending'
        
        # Validate kitchen_id
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Valid kitchen_id is required'}), 400
        
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
        query = session.query(MealPlan).filter(MealPlan.kitchen_id == kitchen_id)
        
        if start_date and end_date:
            query = query.filter(MealPlan.date >= start_date, MealPlan.date <= end_date)
        elif start_date:
            query = query.filter(MealPlan.date >= start_date)
        elif end_date:
            query = query.filter(MealPlan.date <= end_date)
        
        if meal_type and meal_type in ['breakfast', 'lunch', 'dinner', 'snack']:
            query = query.filter(MealPlan.meal_type == meal_type)
        
        if status == 'completed':
            query = query.filter(MealPlan.is_completed == True)
        elif status == 'pending':
            query = query.filter(MealPlan.is_completed == False)
        
        # Fetch meal plans
        meal_plans = query.order_by(MealPlan.date_obj.asc()).all()
        
        # Convert to dict
        meal_plans_list = []
        for plan in meal_plans:
            meal_plans_list.append({
                '_id': str(plan.id),
                'meal_plan_id': plan.meal_plan_id,
                'kitchen_id': str(plan.kitchen_id),
                'created_by': str(plan.created_by),
                'date': plan.date,
                'date_obj': plan.date_obj.isoformat() if plan.date_obj else None,
                'meal_type': plan.meal_type,
                'recipe_id': str(plan.recipe_id),
                'title': plan.title,
                'calories': plan.calories,
                'cooking_time': plan.cooking_time,
                'thumbnail': plan.thumbnail,
                'ingredients': plan.ingredients,
                'cooking_steps': plan.cooking_steps,
                'missing_items': plan.missing_items,
                'missing_items_list': plan.missing_items_list,
                'recipe_short_summary': plan.recipe_short_summary,
                'notes': plan.notes,
                'is_completed': plan.is_completed,
                'completed_at': plan.completed_at.isoformat() if plan.completed_at else None,
                'created_at': plan.created_at.isoformat() if plan.created_at else None,
                'updated_at': plan.updated_at.isoformat() if plan.updated_at else None
            })
        
        return jsonify({'meal_plans': meal_plans_list}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@meal_planner_blueprint.route('/api/meal_plan/get_by_date', methods=['GET'])
@jwt_required()
def get_meal_plans_by_date():
    """Get meal plans for a specific date"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        
        kitchen_id = request.args.get('kitchen_id')
        date = request.args.get('date')  # "2025-11-02"
        
        # Validate
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Valid kitchen_id is required'}), 400
        
        if not date:
            return jsonify({'error': 'date is required (YYYY-MM-DD)'}), 400
        
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
        
        # Fetch meal plans for this date
        meal_plans = session.query(MealPlan).filter(
            MealPlan.kitchen_id == kitchen_id,
            MealPlan.date == date
        ).order_by(MealPlan.meal_type.asc()).all()
        
        # Convert to dict
        meals_list = []
        for plan in meal_plans:
            meals_list.append({
                '_id': str(plan.id),
                'meal_plan_id': plan.meal_plan_id,
                'kitchen_id': str(plan.kitchen_id),
                'created_by': str(plan.created_by),
                'date': plan.date,
                'date_obj': plan.date_obj.isoformat() if plan.date_obj else None,
                'meal_type': plan.meal_type,
                'recipe_id': str(plan.recipe_id),
                'title': plan.title,
                'calories': plan.calories,
                'cooking_time': plan.cooking_time,
                'thumbnail': plan.thumbnail,
                'ingredients': plan.ingredients,
                'cooking_steps': plan.cooking_steps,
                'missing_items': plan.missing_items,
                'missing_items_list': plan.missing_items_list,
                'recipe_short_summary': plan.recipe_short_summary,
                'notes': plan.notes,
                'is_completed': plan.is_completed,
                'completed_at': plan.completed_at.isoformat() if plan.completed_at else None,
                'created_at': plan.created_at.isoformat() if plan.created_at else None,
                'updated_at': plan.updated_at.isoformat() if plan.updated_at else None
            })
        
        return jsonify({
            'date': date,
            'meals': meals_list
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@meal_planner_blueprint.route('/api/meal_plan/update', methods=['POST'])
@jwt_required()
def update_meal_plan():
    """Update a meal plan"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        
        meal_plan_id = data.get('meal_plan_id')
        recipe_id = data.get('recipe_id')
        meal_type = data.get('meal_type')
        notes = data.get('notes')
        
        if not meal_plan_id:
            return jsonify({'error': 'meal_plan_id is required'}), 400
        
        meal_plan = session.query(MealPlan).filter(MealPlan.meal_plan_id == meal_plan_id).first()
        
        if not meal_plan:
            return jsonify({'error': 'Meal plan not found'}), 404
        
        # Check permissions
        kitchen = session.query(Kitchen).filter(Kitchen.id == meal_plan.kitchen_id).first()
        
        is_host_or_cohost = (
            kitchen.host_id == user_id or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == meal_plan.kitchen_id,
                KitchenMember.user_id == user_id,
                KitchenMember.member_type == 'co-host'
            ).first() is not None
        )
        is_creator = meal_plan.created_by == user_id
        
        if not (is_host_or_cohost or is_creator):
            return jsonify({'error': 'You do not have permission to update this meal plan'}), 403
        
        # Update recipe if provided
        if recipe_id:
            try:
                recipe_id = int(recipe_id)
            except (ValueError, TypeError):
                return jsonify({'error': 'Invalid recipe ID'}), 400
            
            recipe = session.query(GeneratedRecipe).filter(GeneratedRecipe.id == recipe_id).first()
            
            if not recipe:
                return jsonify({'error': 'Recipe not found'}), 404
            
            # Update denormalized recipe data
            meal_plan.recipe_id = recipe_id
            meal_plan.title = recipe.title
            meal_plan.calories = recipe.calories
            meal_plan.cooking_time = recipe.cooking_time
            meal_plan.thumbnail = recipe.thumbnail
            meal_plan.ingredients = recipe.ingredients
            meal_plan.cooking_steps = recipe.cooking_steps
            meal_plan.missing_items = recipe.missing_items
            meal_plan.missing_items_list = recipe.missing_items_list
            meal_plan.recipe_short_summary = recipe.recipe_short_summary
        
        # Update meal_type if provided
        if meal_type:
            valid_meal_types = ['breakfast', 'lunch', 'dinner', 'snack']
            if meal_type not in valid_meal_types:
                return jsonify({'error': f'meal_type must be one of: {", ".join(valid_meal_types)}'}), 400
            meal_plan.meal_type = meal_type
        
        # Update notes if provided
        if notes is not None:
            meal_plan.notes = notes
        
        meal_plan.updated_at = datetime.now(timezone.utc)
        session.commit()
        
        return jsonify({'message': 'Meal plan updated successfully'}), 200

    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@meal_planner_blueprint.route('/api/meal_plan/delete', methods=['POST'])
@jwt_required()
def delete_meal_plan():
    """Delete a meal plan (by ID or by date)"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        
        date = data.get('date')
        kitchen_id = data.get('kitchen_id')
        meal_plan_id = data.get('meal_plan_id')
        
        # Case 1: Delete all plans for a specific date in a kitchen
        if date and kitchen_id:
            try:
                kitchen_id = int(kitchen_id)
            except (ValueError, TypeError):
                return jsonify({'error': 'Invalid kitchen ID'}), 400
            
            # Check kitchen exists
            kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
            if not kitchen:
                return jsonify({'error': 'Kitchen not found'}), 404
            
            # Check permissions (only host or co-host can delete by date)
            is_host_or_cohost = (
                kitchen.host_id == user_id or
                session.query(KitchenMember).filter(
                    KitchenMember.kitchen_id == kitchen_id,
                    KitchenMember.user_id == user_id,
                    KitchenMember.member_type == 'co-host'
                ).first() is not None
            )
            
            if not is_host_or_cohost:
                return jsonify({'error': 'Only host or co-host can delete all plans for a date'}), 403
            
            # Delete all meal plans for this date
            deleted_count = session.query(MealPlan).filter(
                MealPlan.kitchen_id == kitchen_id,
                MealPlan.date == date
            ).delete()
            
            session.commit()
            
            return jsonify({
                'message': f'{deleted_count} meal plan(s) deleted successfully for date {date}',
                'deleted_count': deleted_count
            }), 200
        
        # Case 2: Delete by meal_plan_id
        elif meal_plan_id:
            meal_plan = session.query(MealPlan).filter(MealPlan.meal_plan_id == meal_plan_id).first()
            
            if not meal_plan:
                return jsonify({'error': 'Meal plan not found'}), 404
            
            # Check permissions
            kitchen = session.query(Kitchen).filter(Kitchen.id == meal_plan.kitchen_id).first()
            
            is_host_or_cohost = (
                kitchen.host_id == user_id or
                session.query(KitchenMember).filter(
                    KitchenMember.kitchen_id == meal_plan.kitchen_id,
                    KitchenMember.user_id == user_id,
                    KitchenMember.member_type == 'co-host'
                ).first() is not None
            )
            is_creator = meal_plan.created_by == user_id
            
            if not (is_host_or_cohost or is_creator):
                return jsonify({'error': 'You do not have permission to delete this meal plan'}), 403
            
            # Delete the meal plan
            session.delete(meal_plan)
            session.commit()
            
            return jsonify({'message': 'Meal plan deleted successfully'}), 200
        
        else:
            return jsonify({'error': 'Either (date + kitchen_id) or meal_plan_id is required'}), 400

    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@meal_planner_blueprint.route('/api/meal_plan/mark_completed', methods=['POST'])
@jwt_required()
def mark_meal_completed():
    """Mark a meal plan as completed"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()
        
        meal_plan_id = data.get('meal_plan_id')
        
        if not meal_plan_id:
            return jsonify({'error': 'meal_plan_id is required'}), 400
        
        meal_plan = session.query(MealPlan).filter(MealPlan.meal_plan_id == meal_plan_id).first()
        
        if not meal_plan:
            return jsonify({'error': 'Meal plan not found'}), 404
        
        # Check user is member
        kitchen = session.query(Kitchen).filter(Kitchen.id == meal_plan.kitchen_id).first()
        
        is_member = (
            kitchen.host_id == user_id or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == meal_plan.kitchen_id,
                KitchenMember.user_id == user_id
            ).first() is not None
        )
        
        if not is_member:
            return jsonify({'error': 'You are not a member of this kitchen'}), 403
        
        # Mark as completed
        completed_at = datetime.now(timezone.utc)
        meal_plan.is_completed = True
        meal_plan.completed_at = completed_at
        meal_plan.updated_at = completed_at
        session.commit()
        
        return jsonify({
            'message': 'Meal marked as completed',
            'completed_at': completed_at.isoformat()
        }), 200

    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()