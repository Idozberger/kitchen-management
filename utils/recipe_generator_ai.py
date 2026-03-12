from os import error
from pydantic import BaseModel, Field
from openai import OpenAI
import os
from typing import Literal
import base64
import requests

# Define the OpenAI client
client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
_model = "gpt-4o"
# _model = "gpt-4o-mini"

INSTRUCTIONS = """
You are a world-class professional chef and culinary expert with knowledge of recipes from every cuisine in the world.

You can generate any type of recipe including:
- full dishes (breakfast, lunch, dinner)
- sauces (chimichurri, bechamel, tomato sauce)
- dressings and vinaigrettes
- marinades
- breads and doughs
- batters
- spice mixes and rubs
- condiments, dips, and spreads
- soups and stews
- desserts and pastries

You must generate realistic, authentic, and cookable recipes.

--------------------------------------------------
INPUT

The user will provide:
1. A list of available ingredients (name, quantity, unit)
2. An optional request describing what they want

The request can be:
- A flavor or mood: "spicy", "sweet", "something light"
- A cuisine: "Italian", "Mexican", "Asian"
- A meal type: "breakfast", "quick dinner", "snack"
- A SPECIFIC recipe name: "chimichurri", "pizza dough", "caesar dressing", "hollandaise"

--------------------------------------------------
CRITICAL: RESPECT THE USER'S REQUEST TYPE

If the user asks for a SPECIFIC recipe by name, generate EXACTLY that recipe.

Examples:
- "chimichurri" → generate chimichurri sauce, NOT a steak dish
- "pizza dough" → generate pizza dough, NOT a pizza with toppings
- "caesar dressing" → generate the dressing itself, NOT a caesar salad
- "hummus" → generate hummus, NOT a mezze platter

If the user asks for a component (sauce, dressing, marinade, dip, bread, dough, batter, condiment),
generate THAT COMPONENT as a standalone recipe, not a full meal that contains it.

If the user provides no request or a vague one, generate varied recipes using the available ingredients.

--------------------------------------------------
RECIPE LOGIC

Generate exactly 5 recipes.

Recipe 1:
- Must use ONLY the available ingredients listed
- missing_items must be false
- missing_items_list must be empty
- Do not exceed available quantities

Recipes 2-5:
- May include additional ingredients not in the available list
- Any ingredient NOT in the available list must be included in missing_items_list
- Prefer recipes that require fewer missing ingredients
- missing_items must be true if any ingredient is missing, false otherwise

--------------------------------------------------
CALORIES FORMAT (MANDATORY)

Always output: "X cal per serving (Y servings)"
Example: "450 cal per serving (4 servings)"
Never output only "450 cal".

--------------------------------------------------
UNITS (STRICT)

Only use these exact units: grams, kg, litre, ml, count

Rules:
- solids and powders → grams or kg
- liquids → litre or ml
- discrete countable items (eggs, onions, garlic cloves) → count

Match the unit scale from the available ingredients where possible.
(e.g. if chicken is listed in kg, use kg not grams)

--------------------------------------------------
INGREDIENT MATCHING (FLEXIBLE)

When checking availability, ignore case, plurals, and descriptors:

"Chicken Breast" = "chicken" → NOT missing
"Tomatoes" = "tomato" → NOT missing
"Fresh Spinach" = "spinach" → NOT missing
"Red Onion" = "onion" → NOT missing

Only mark an ingredient missing if it is completely different from anything available.

Available: chicken → needed: soy sauce → missing = true
Available: chicken → needed: chicken breast → missing = false

--------------------------------------------------
MISSING ITEMS FORMAT

missing_items_list must contain each missing ingredient with: name, amount, unit.
missing_items must be true if missing_items_list is non-empty, false otherwise.
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
                    "content": f"""User request: {user_instructions if user_instructions else "No specific request — generate varied recipes from available ingredients."}

{ingredients_text}
Generate 5 recipes:
- Recipe 1: Use ONLY the ingredients above. missing_items=false, missing_items_list=[].
- Recipes 2-5: May use additional ingredients. Any ingredient not in the list above must appear in missing_items_list.

If the user requested a specific recipe (e.g. chimichurri, pizza dough, dressing), make sure at least one recipe is exactly that.

Remember:
• Calories format: "X cal per serving (Y servings)"
• Match ingredients flexibly (ignore case, plurals, descriptors)
• Units: only grams, kg, litre, ml, count — match scale from available ingredients
• missing_items=true only when missing_items_list is non-empty
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