from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
import utils.recipe_generator_ai

# PostgreSQL imports
from db_connection import get_session
from models import Kitchen, KitchenMember, KitchenItem, GeneratedRecipe

# Create a Blueprint for expiring items recipe suggestions
expiring_items_recipe_blueprint = Blueprint('expiring_items_recipe_blueprint', __name__)


def calculate_expiry_status(added_at, expiry_date_str):
    """
    Calculate if item is expired, expiring soon, or fresh.
    
    Args:
        added_at: datetime when item was added to inventory
        expiry_date_str: string like "7 days", "2 weeks", "3 months", "1 year"
    
    Returns:
        str: "expired", "expiring_soon", "fresh", or None if invalid
    """
    if not added_at or not expiry_date_str:
        return None
    
    try:
        # Ensure added_at is a datetime object
        if isinstance(added_at, str):
            added_at = datetime.fromisoformat(added_at.replace('Z', '+00:00'))
        
        if not isinstance(added_at, datetime):
            return None
        
        # Make added_at timezone-aware if it's naive
        if added_at.tzinfo is None:
            added_at = added_at.replace(tzinfo=timezone.utc)
        
        # Parse expiry_date like "7 days", "2 weeks", "3 months", "1 year"
        expiry_parts = expiry_date_str.lower().strip().split()
        if len(expiry_parts) != 2:
            return None
        
        amount = int(expiry_parts[0])
        unit = expiry_parts[1]
        
        # Convert to days
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
        
        # Calculate expiration date
        expiration_date = added_at + timedelta(days=days)
        current_date = datetime.now(timezone.utc)
        
        days_remaining = (expiration_date - current_date).days
        
        if days_remaining < 0:
            return "expired"
        elif days_remaining <= 2:
            return "expiring_soon"
        else:
            return "fresh"
    except Exception as e:
        print(f"Error calculating expiry status: {e}")
        return None


def get_expiring_items(kitchen_items):
    """
    Filter items that have expiry_status = 'expiring_soon' ONLY.
    Expired items are excluded for food safety.
    
    Args:
        kitchen_items: list of KitchenItem objects
    
    Returns:
        list: items that are expiring soon (NOT expired) with their details
    """
    expiring = []
    
    for item in kitchen_items:
        added_at = item.added_at
        expiry_date = item.expiry_date
        
        # Skip items without expiry info
        if not added_at or not expiry_date:
            continue
        
        # Calculate expiry status
        expiry_status = calculate_expiry_status(added_at, expiry_date)
        
        # ✅ ONLY include 'expiring_soon' items (NOT 'expired')
        if expiry_status == 'expiring_soon':
            expiring.append({
                'name': item.name,
                'quantity': item.quantity,
                'unit': item.unit,
                'expiry_status': expiry_status,
                'item_id': item.item_id,
                'group': item.group or 'pantry'
            })
    
    return expiring


def build_expiring_items_prompt(expiring_items, other_items):
    """
    Build an AI prompt that emphasizes using expiring ingredients.
    Modified to generate ONLY 1 recipe using expiring_soon items.
    Limits other_items to prevent token overflow.
    
    Args:
        expiring_items: list of items expiring soon (NOT expired)
        other_items: list of other available items (limited to prevent token overflow)
    
    Returns:
        str: formatted prompt for AI recipe generation
    """
    prompt = "⚠️ URGENT EXPIRING INGREDIENTS (MUST USE AS MANY AS POSSIBLE):\n"
    
    for item in expiring_items:
        # All items here are 'expiring_soon' (expired items are filtered out for safety)
        prompt += f"- {item['name']} ({item['quantity']} {item['unit']}) [EXPIRING SOON - PRIORITY]\n"
    
    prompt += "\n\n📦 OTHER AVAILABLE INGREDIENTS (you can use these if needed):\n"
    for item in other_items:
        prompt += f"- {item['name']} ({item['quantity']} {item['unit']})\n"
    
    prompt += """

🎯 CRITICAL RECIPE GENERATION REQUIREMENTS:
1. Generate EXACTLY 1 recipe (not 3, just ONE single recipe)
2. The recipe MUST use AS MANY expiring ingredients as possible (these are marked PRIORITY above)
3. You can also use other available ingredients from the list to make a complete recipe
4. If you need 1-2 missing ingredients to make a great recipe, that's fine - list them in missing_items_list
5. Use the EXACT ingredient names and units provided above
6. Make the recipe practical, delicious, and minimize food waste
7. Ensure the recipe is easy to follow with clear cooking steps
8. Basic pantry staples (salt, pepper, oil, water, sugar) are always assumed available
9. IMPORTANT: Generate only ONE recipe, not multiple recipes
10. Focus on using ALL the expiring items marked as PRIORITY
"""
    
    return prompt


def annotate_recipe_with_expiring_items(recipe, expiring_items):
    """
    Add information about which expiring items the recipe uses.
    
    Args:
        recipe: recipe dict from AI generation
        expiring_items: list of expiring items
    
    Returns:
        dict: recipe with added 'expiring_items_used' and 'expiring_items_count' fields
    """
    expiring_names = {item['name'].lower() for item in expiring_items}
    
    # Check which recipe ingredients are from expiring list
    used_expiring = []
    for ingredient in recipe.get('ingredients', []):
        if ingredient['name'].lower() in expiring_names:
            used_expiring.append(ingredient['name'])
    
    # Add annotation to recipe
    recipe['expiring_items_used'] = used_expiring
    recipe['expiring_items_count'] = len(used_expiring)
    
    return recipe


def generate_thumbnail_for_recipe(recipe):
    """
    Generate thumbnail for a single recipe.
    
    Args:
        recipe: recipe dict
    
    Returns:
        dict: recipe with thumbnail added
    """
    try:
        thumbnail_base64 = utils.recipe_generator_ai.generate_recipe_thumbnail(
            recipe['title'], 
            recipe.get('recipe_short_summary', '')
        )
        recipe['thumbnail'] = thumbnail_base64
    except Exception as e:
        print(f"Error generating thumbnail for {recipe['title']}: {str(e)}")
        recipe['thumbnail'] = None
    return recipe


@expiring_items_recipe_blueprint.route('/api/kitchen/suggest_recipes_expiring_items', methods=['GET'])
@jwt_required()
def suggest_recipes_for_expiring_items():
    """
    Suggest 1 recipe based on items that are expiring soon in the kitchen.
    Returns null if no items are expiring.
    
    Query Parameters:
        kitchen_id (required): The kitchen ID to check for expiring items
    
    Returns:
        200: Success with recipe or message about no expiring items
        400: Invalid kitchen_id
        403: User is not a member of the kitchen
        404: Kitchen not found
        500: Recipe generation failed
    """
    session = get_session()
    try:
        # Get authenticated user
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        
        # Get kitchen_id from query params
        kitchen_id = request.args.get('kitchen_id')
        
        # Validate kitchen_id
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Valid kitchen_id is required'}), 400
        
        # Fetch kitchen from database
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404
        
        # Check if user is a member of the kitchen (host, co-host, or member)
        is_host = kitchen.host_id == user_id
        is_member = (
            is_host or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == kitchen_id,
                KitchenMember.user_id == user_id
            ).first() is not None
        )
        
        if not is_member:
            return jsonify({'error': 'You are not a member of this kitchen'}), 403
        
        # Get kitchen inventory
        kitchen_items = session.query(KitchenItem).filter(
            KitchenItem.kitchen_id == kitchen_id
        ).all()

        if not kitchen_items:
            return jsonify({
                'message': 'No items in kitchen inventory',
                'recipe': None,
                'expiring_items_count': 0,
                'expiring_items': []
            }), 200

        # Filter items that are expiring soon
        expiring_items = get_expiring_items(kitchen_items)

        # EARLY RETURN: No expiring items found
        if not expiring_items:
            return jsonify({
                'message': 'No items are expiring soon',
                'recipe': None,
                'expiring_items_count': 0,
                'expiring_items': []
            }), 200

        # Separate expiring items from other available items
        expiring_names = {item['name'].lower() for item in expiring_items}
        other_items = []
        for item in kitchen_items:
            if item.name.lower() not in expiring_names:
                other_items.append({
                    'name': item.name,
                    'quantity': item.quantity,
                    'unit': item.unit,
                    'group': item.group or 'pantry'
                })

        # LIMIT other items to prevent token overflow (keep most common 40 items)
        MAX_OTHER_ITEMS = 40
        limited_other_items = other_items[:MAX_OTHER_ITEMS]

        # Build AI prompt emphasizing expiring ingredients
        ai_prompt = build_expiring_items_prompt(expiring_items, limited_other_items)

        # Combine items for AI (all expiring + limited other items)
        items_for_ai = expiring_items + limited_other_items

        # Generate recipes using AI (from recipe_generator_ai.py)
        ai_result = utils.recipe_generator_ai.generate_recipes_with_openai(
            ai_prompt, 
            items_for_ai
        )

        # Handle AI generation errors
        if not ai_result.get('success'):
            error_message = ai_result.get('error', 'Failed to generate recipe')
            
            # Handle specific error types
            if 'rate limit' in error_message.lower():
                return jsonify({
                    'error': 'Too many requests. Please try again later.'
                }), 429
            else:
                return jsonify({'error': error_message}), 500

        recipes = ai_result.get('recipes', [])

        # If AI generated multiple recipes, take only the first one
        if not recipes:
            return jsonify({'error': 'Failed to generate recipe'}), 500

        # Take only the first recipe
        recipe = recipes[0]

        # Annotate recipe with expiring items info
        annotate_recipe_with_expiring_items(recipe, expiring_items)

        # Generate thumbnail for the recipe
        recipe = generate_thumbnail_for_recipe(recipe)

        # Store generated recipe in database
        recipe_obj = GeneratedRecipe(
            title=recipe['title'],
            calories=recipe.get('calories'),
            cooking_time=recipe.get('cooking_time'),
            ingredients=recipe['ingredients'],
            recipe_short_summary=recipe.get('recipe_short_summary'),
            cooking_steps=recipe['cooking_steps'],
            missing_items=recipe.get('missing_items', False),
            missing_items_list=recipe.get('missing_items_list', []),
            thumbnail=recipe.get('thumbnail'),
            expiring_items_used=recipe.get('expiring_items_used'),
            expiring_items_count=recipe.get('expiring_items_count', 0),
            created_at=datetime.now(timezone.utc)
        )
        
        session.add(recipe_obj)
        session.commit()
        session.refresh(recipe_obj)

        # Add MongoDB _id to recipe for compatibility
        recipe['_id'] = str(recipe_obj.id)

        # Return success response with single recipe
        return jsonify({
            'message': '1 recipe suggested to use expiring items',
            'expiring_items_count': len(expiring_items),
            'expiring_items': expiring_items,
            'recipe': recipe
        }), 200

    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()