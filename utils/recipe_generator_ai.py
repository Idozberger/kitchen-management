from os import error
from pydantic import BaseModel, Field
from openai import OpenAI
import os
from typing import Literal
import base64
import requests

# Define the OpenAI client
client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
_model = "gpt-4o-mini"
# _model = "gpt-4o-mini"

INSTRUCTIONS = """
Generate 3 recipes using provided ingredients. Follow these rules:

1. The user will provide:
   - A list of available ingredients with name, quantity, and unit.
   - Instructions indicating what type of dish they want, e.g., spicy, sweet, salty, bitter, sour, bland, etc. If no preference is provided, assume no specific flavor direction is desired.

2. RECIPE STRUCTURE:
   - Recipe #1: Use ONLY available ingredients and provide best recipe (no missing items)
   - Recipes #2-3: May include missing ingredients if needed to produce a best recipe
   - Each recipe needs: title, calories, cooking_time, ingredients, summary, steps

3. CALORIES - CRITICAL FORMAT:
   - Always specify "per serving" with serving count
   - Format: "X cal per serving (Y servings)" 
   - Example: "450 cal per serving (4 servings)"
   - This is MANDATORY - never just say "450 cal"

4. UNITS (strict):
   - Only use: grams, kg, litre, ml, count
   - Match the unit from available ingredients (i.e if ingredient is in kg, use kg not grams)

5. INGREDIENT MATCHING (flexible):
   When checking if ingredient is available, ignore case/plurals/descriptors:
   - "Chicken Breast" matches "chicken" ✓
   - "Tomatoes" matches "tomato" ✓  
   - "GARLIC" matches "garlic" ✓
   - "Fresh Spinach" matches "spinach" ✓

6. MISSING ITEMS:
   Only mark as missing if it's a DIFFERENT ingredient entirely
   - "Chicken Breast" available → "chicken" needed = NOT missing ✓
   - "Chicken" available → "soy sauce" needed = IS missing ✗

Double-check: Don't mark ingredients as missing when they're available in any form!
"""


class ingredientsList(BaseModel):
    name: str = Field(..., example="mushroom")
    amount: str = Field(..., example="50")
    unit: Literal["grams", "kg", "litre", "ml", "count"] = Field(..., example="grams")


class Recipe(BaseModel):
    title: str = Field(..., example="Chicken Stir Fry")
    calories: str = Field(..., example="450 cal per serving (4 servings)", description="Must include 'per serving' and serving count")
    cooking_time: str = Field(..., example="20-30 mins")
    ingredients: list[ingredientsList]
    recipe_short_summary: str = Field(
        ..., example="Quick and healthy stir fry with tender chicken and vegetables")
    cooking_steps: list[str] = Field(
        ..., example=["Heat oil in a wok", "Add chicken and cook until golden"])
    missing_items: bool = Field(..., example=False)
    missing_items_list: list[ingredientsList] = Field(default=[], example=[])


# Define a Pydantic model for a list of recipes
class RecipeResponse(BaseModel):
    recipes: list[Recipe]


def generate_recipes_with_openai(user_instructions, available_ingredients):

    try:
        recipes = []
        
        # Format available ingredients clearly
        ingredients_text = "AVAILABLE INGREDIENTS:\n"
        for idx, item in enumerate(available_ingredients, 1):
            ingredients_text += f"{idx}. {item['name']} - {item['quantity']} {item['unit']}\n"
        
        completion = client.beta.chat.completions.parse(
            model=_model,
            messages=[
                {
                    "role": "system",
                    "content": INSTRUCTIONS
                },
                {
                    "role": "user",
                    "content": f"""User wants: {user_instructions}

{ingredients_text}
Generate 3 recipes:
- Recipe 1: Only use ingredients above (no missing items)
- Recipes 2-3: Can include missing ingredients

Remember:
• Calories format: "X cal per serving (Y servings)"
• Match ingredients flexibly (ignore case/plurals/descriptors)
• Use same units as available ingredients
"""
                },
            ],
            response_format=RecipeResponse,
        )
        # print(completion.choices[0].message)
        event = completion.choices[0].message.parsed

        for i in event.recipes:
            the_recipe = {
                'title':
                i.title,
                'calories':
                i.calories,
                'cooking_time':
                i.cooking_time,
                "missing_items":
                i.missing_items,
                'missing_items_list': [{
                    'name': ing.name,
                    'amount': ing.amount,
                    'unit': ing.unit
                } for ing in i.missing_items_list],
                'recipe_short_summary':
                i.recipe_short_summary,
                'ingredients': [{
                    'name': ing.name,
                    'amount': ing.amount,
                    'unit': ing.unit
                } for ing in i.ingredients],
                'cooking_steps': [step for step in i.cooking_steps]
            }
            recipes.append(the_recipe)

        print("the_recipe:\n", recipes)
        return {"success": True, "recipes": recipes}
    except Exception as e:
        print('error when generating recipe: ', str(e))
        return {"success": False, "error": str(e)}


def generate_recipe_thumbnail(recipe_title, recipe_summary):
    """
    Generate a thumbnail image for a recipe using OpenAI DALL-E.
    Returns base64 encoded image string.
    
    Args:
        recipe_title: The title of the recipe
        recipe_summary: A short summary of the recipe
    
    Returns:
        str: Base64 encoded image or None if generation fails
    """
    
    try:
        # Create a descriptive prompt for DALL-E
        prompt = f"A professional, appetizing food photography of {recipe_title}. {recipe_summary}. High quality, well-lit, restaurant-style presentation on a clean plate."
        
        # Generate image using DALL-E
        response = client.images.generate(
            model="dall-e-2",
            prompt=prompt,
            size="256x256",
            n=1,
            response_format="url"
        )
        
        # Get the image URL from response
        image_url = response.data[0].url
        
        # Download the image and convert to base64
        image_response = requests.get(image_url)
        if image_response.status_code == 200:
            image_base64 = base64.b64encode(image_response.content).decode('utf-8')
            return f"data:image/png;base64,{image_base64}"
        else:
            print(f"Failed to download image from URL: {image_url}")
            return None
            
    except Exception as e:
        print(f"Error generating thumbnail: {str(e)}")
        return None