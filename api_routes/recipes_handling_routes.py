from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from flask import Blueprint, request, jsonify
import os
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
import utils.recipe_generator_ai

# PostgreSQL imports
from db_connection import get_session
from models import Kitchen, KitchenMember, KitchenItem, GeneratedRecipe, FavouriteRecipe

# Create a Blueprint object
recipes_handling_blueprint = Blueprint('recipes_handling_blueprint', __name__)


@recipes_handling_blueprint.route('/api/generate_recipes', methods=['POST'])
@jwt_required()
def generate_recipes_r():
    """Generate recipes using OpenAI based on available kitchen items"""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    session = get_session()
    try:
        # Get user identity and request data
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])
        data = request.get_json()

        # Extract kitchen_id and instructions from the request
        kitchen_id = data.get('kitchen_id', '')
        user_instructions = data.get('instructions', '')

        # Validate kitchen_id (now an integer)
        try:
            kitchen_id = int(kitchen_id)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid kitchen ID'}), 400

        # Fetch the kitchen data from the database
        kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()

        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404

        # Check if the user is either the host or a member of the kitchen
        is_authorized = (
            kitchen.host_id == user_id or
            session.query(KitchenMember).filter(
                KitchenMember.kitchen_id == kitchen_id,
                KitchenMember.user_id == user_id,
                KitchenMember.member_type.in_(['host', 'co-host', 'member'])
            ).first() is not None
        )
        
        if not is_authorized:
            return jsonify({
                'error': 'You are not authorized to generate recipes for this kitchen'
            }), 403

        # Fetch the available ingredients from the kitchen
        available_ingredients = session.query(KitchenItem).filter(
            KitchenItem.kitchen_id == kitchen_id
        ).all()
        
        lightweight_ingredients = []
        for item in available_ingredients:
            lightweight_ingredients.append({
                'name': item.name,
                'quantity': item.quantity,
                'unit': item.unit
            })
        
        # Generate recipes using the AI utility with lightweight ingredients
        ai_generated_recipes = utils.recipe_generator_ai.generate_recipes_with_openai(
            user_instructions, lightweight_ingredients)

        if ai_generated_recipes['success']:
            # Function to generate thumbnail for a single recipe
            def generate_thumbnail_for_recipe(recipe):
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
            
            # Generate all thumbnails in parallel using ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=3) as executor:
                # Submit all thumbnail generation tasks
                future_to_recipe = {
                    executor.submit(generate_thumbnail_for_recipe, recipe): recipe 
                    for recipe in ai_generated_recipes['recipes']
                }
                
                # Wait for all to complete and collect results
                completed_recipes = []
                for future in as_completed(future_to_recipe):
                    try:
                        completed_recipe = future.result()
                        completed_recipes.append(completed_recipe)
                    except Exception as e:
                        print(f"Error in thumbnail generation: {str(e)}")
                        # Add recipe with null thumbnail if generation fails
                        original_recipe = future_to_recipe[future]
                        original_recipe['thumbnail'] = None
                        completed_recipes.append(original_recipe)
            
            # Use the completed recipes with thumbnails
            ai_generated_recipes['recipes'] = completed_recipes
            
            # Insert generated recipes into the database
            recipe_objects = []
            for recipe_data in ai_generated_recipes['recipes']:
                recipe = GeneratedRecipe(
                    title=recipe_data['title'],
                    calories=recipe_data.get('calories'),
                    cooking_time=recipe_data.get('cooking_time'),
                    ingredients=recipe_data['ingredients'],
                    recipe_short_summary=recipe_data.get('recipe_short_summary'),
                    cooking_steps=recipe_data['cooking_steps'],
                    missing_items=recipe_data.get('missing_items', False),
                    missing_items_list=recipe_data.get('missing_items_list', []),
                    thumbnail=recipe_data.get('thumbnail'),
                    expiring_items_used=recipe_data.get('expiring_items_used'),
                    expiring_items_count=recipe_data.get('expiring_items_count', 0),
                    created_at=datetime.now(timezone.utc)
                )
                session.add(recipe)
                recipe_objects.append(recipe)
            
            # Commit to get IDs
            session.commit()
            
            # Refresh to get IDs and update response
            for i, recipe_obj in enumerate(recipe_objects):
                session.refresh(recipe_obj)
                ai_generated_recipes['recipes'][i]['_id'] = str(recipe_obj.id)

            return jsonify({'recipes': ai_generated_recipes['recipes']}), 200

        else:
            # Handle AI generation errors
            error_message = ai_generated_recipes.get('error', 'An error occurred')
            if 'rate limit' in error_message.lower():
                return jsonify({
                    'error': "Too Many Requests: Please slow down your requests and try again later."
                }), 429
            elif 'invalid' in error_message.lower():
                return jsonify({'error': error_message}), 400
            else:
                return jsonify({'error': error_message}), 500

    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@recipes_handling_blueprint.route('/api/recipe/add_to_fav', methods=['POST'])
@jwt_required()
def add_to_fav_r():
    """Add a recipe to user's favorites"""
    session = get_session()
    try:
        user_identity = get_jwt()
        data = request.get_json()

        # Check if _id (recipe ID) is provided
        if not data or '_id' not in data:
            return jsonify({'error': 'Missing recipe "_id" in request body'}), 400

        recipe_id = data['_id']
        user_id = int(user_identity['user_id'])

        # Validate recipe_id (now an integer)
        try:
            recipe_id = int(recipe_id)
        except (ValueError, TypeError):
            return jsonify({'error': f'Invalid recipe _id: {recipe_id}.'}), 400

        # Try to find the recipe in the generated_recipes table
        recipe = session.query(GeneratedRecipe).filter(
            GeneratedRecipe.id == recipe_id
        ).first()

        if not recipe:
            return jsonify({'error': f'Recipe with id {recipe_id} not found'}), 404

        # Check if the recipe is already in the user's favourites
        existing_favourite = session.query(FavouriteRecipe).filter(
            FavouriteRecipe.user_id == user_id,
            FavouriteRecipe.recipe_id == recipe_id
        ).first()

        if existing_favourite:
            return jsonify({'error': 'Recipe is already in your favourites'}), 409

        # Create the favourite recipe entry
        favourite_recipe = FavouriteRecipe(
            user_id=user_id,
            recipe_id=recipe_id,
            added_at=datetime.now(timezone.utc)
        )

        # Insert the recipe into the favourite_recipes table
        session.add(favourite_recipe)
        session.commit()
        
        # Refresh to get ID
        session.refresh(favourite_recipe)

        # Return a success response
        return jsonify({
            'message': 'Recipe added to favourites successfully',
            'favourite_recipe_id': str(favourite_recipe.id)
        }), 201

    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@recipes_handling_blueprint.route('/api/recipe/remove_from_fav', methods=['POST'])
@jwt_required()
def remove_from_fav_r():
    """Remove a recipe from user's favorites"""
    session = get_session()
    try:
        user_identity = get_jwt()
        data = request.get_json()

        # Check if recipe_id is provided
        if 'recipe_id' not in data:
            return jsonify({
                'error': 'recipe_id must be provided in the request body'
            }), 400

        user_id = int(user_identity['user_id'])
        recipe_id = data['recipe_id']

        # Validate recipe_id
        try:
            recipe_id = int(recipe_id)
        except (ValueError, TypeError):
            return jsonify({'error': f'Invalid recipe_id: {recipe_id}.'}), 400

        # Find and delete the favorite recipe
        favourite = session.query(FavouriteRecipe).filter(
            FavouriteRecipe.user_id == user_id,
            FavouriteRecipe.recipe_id == recipe_id
        ).first()

        if not favourite:
            return jsonify({
                'error': f'No favourite found for this user and recipe_id {recipe_id}.'
            }), 404

        # Delete the favourite
        session.delete(favourite)
        session.commit()

        # Return a success response
        return jsonify({
            'message': f'Recipe with id {recipe_id} removed from favourites successfully.'
        }), 200

    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@recipes_handling_blueprint.route('/api/recipe/list_fav', methods=['GET'])
@jwt_required()
def list_fav_r():
    """Get user's favorite recipes"""
    session = get_session()
    try:
        user_identity = get_jwt()

        # Extract user_id from the JWT token
        user_id = int(user_identity['user_id'])

        # Get the favourite recipes for the user
        favourites = session.query(FavouriteRecipe).filter(
            FavouriteRecipe.user_id == user_id
        ).all()

        # Extract the recipe_ids from the favourites
        recipe_ids = [fav.recipe_id for fav in favourites]

        # If the user has no favorite recipes, return an empty list
        if not recipe_ids:
            return jsonify({'favourite_recipes': []}), 200

        # Fetch all the recipes at once using IN clause
        recipes = session.query(GeneratedRecipe).filter(
            GeneratedRecipe.id.in_(recipe_ids)
        ).all()

        # Convert to list of dicts with _id as string for compatibility
        fav_recipes_list = []
        for recipe in recipes:
            fav_recipes_list.append({
                '_id': str(recipe.id),
                'title': recipe.title,
                'calories': recipe.calories,
                'cooking_time': recipe.cooking_time,
                'ingredients': recipe.ingredients,
                'recipe_short_summary': recipe.recipe_short_summary,
                'cooking_steps': recipe.cooking_steps,
                'missing_items': recipe.missing_items,
                'missing_items_list': recipe.missing_items_list,
                'thumbnail': recipe.thumbnail,
                'expiring_items_used': recipe.expiring_items_used,
                'expiring_items_count': recipe.expiring_items_count,
                'available': True
            })

        # Return the list of favorite recipes
        return jsonify({'favourite_recipes': fav_recipes_list}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()