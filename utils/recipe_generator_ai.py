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
You are tasked with generating recipes based solely on the ingredients provided by the user. Follow these instructions precisely:

1. The user will provide:
   - A list of available ingredients.
   - Instructions indicating what type of dish they want, e.g., spicy, sweet, salty, bitter, sour, bland, etc. If no preference is provided, assume no specific flavor direction is desired.
   
2. Your job is to:
   - Create three recipes. One recipe must use only the ingredients provided by the user. The other two recipes can have a single or very few ingredients which are not originally present in the available ingredients, but in that case missing_items will be true.
   - Provide a recipe title.
   - Estimate the calories per 100g of the dish.
   - Include a cooking time range (e.g., 20-30 minutes).
   - Provide a detailed list of ingredients with amounts and units.
   
3. CRITICAL UNIT REQUIREMENTS:
   - ONLY use these units: grams, kg, litre, ml, count
   - Use the EXACT SAME unit as in the available ingredients list
   - If available ingredient is in kg, use kg (e.g., 0.5 kg, NOT 500 grams)
   - If available ingredient is in litre, use litre (e.g., 0.2 litre, NOT 200 ml)
   - If available ingredient is in grams, use grams
   - If available ingredient is in ml, use ml
   - For countable items (eggs, apples), use count
   - DO NOT convert units - match exactly what's in the available ingredients
   
4. CRITICAL NAME MATCHING:
   - Use the EXACT spelling from available ingredients list
   - If available ingredients has 'chiken', use 'chiken' (not 'chicken')
   - If available ingredients has 'tomatoe', use 'tomatoe' (not 'tomato')
   - Match capitalization exactly as provided
   
5. Recipe Requirements:
   - Write a short summary of the cooking steps.
   - List the complete cooking steps in clear & detailed manner that will guide the user step-by-step.
   - Make steps very easy to follow with all necessary details.
   - IMPORTANT: For missing_items_list, include ONLY the ingredients that are NOT in the available ingredients list. Format each missing item with name, amount, and unit (using only allowed units: grams, kg, litre, ml, count).

REMEMBER: Use ONLY these units: grams, kg, litre, ml, count. Never use pounds, ounces, mL, or any other units.
"""


class ingredientsList(BaseModel):
    name: str = Field(..., example="mushroom")
    amount: str = Field(..., example="50")
    unit: Literal["grams", "kg", "litre", "ml", "count"] = Field(..., example="grams")


class Recipe(BaseModel):
    title: str = Field(..., example="Chow Mein")
    calories: str = Field(..., example="110 cal")
    cooking_time: str = Field(..., example="10-15 mins")
    ingredients: list[ingredientsList]
    recipe_short_summary: str = Field(
        ..., example="Brown the beef better. Lean ground...")
    cooking_steps: list[str] = Field(
        ..., example=["Brown the beef in the oven", 'add 2 spoon oil'])
    missing_items: bool = Field(..., example=False)
    missing_items_list: list[ingredientsList] = Field(default=[], example=[])


# Define a Pydantic model for a list of recipes
class RecipeResponse(BaseModel):
    recipes: list[Recipe]


def generate_recipes_with_openai(user_instructions, available_ingredients):

    try:
        recipes = []
        completion = client.beta.chat.completions.parse(
            model=_model,
            messages=[
                {
                    "role": "system",
                    "content": INSTRUCTIONS
                },
                {
                    "role":
                    "user",
                    "content":
                    f"""
                    instructions: {user_instructions}\nGenerate the recipe. Make sure to use exactly the same unit as in the available ingredients list. Ig something is in KG and you suggest to use half kg then you must use 0.5 KG, not 500g.
                    Available ingredients:
                    {available_ingredients}
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