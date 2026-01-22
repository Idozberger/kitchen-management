import os
import base64
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import Literal
import requests
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
_model = 'gpt-4.1'

INSTRUCTIONS = """
You are given a receipt containing various items. Scan the receipt and identify only the items that are ingredients used for cooking, eating or drinking. For each ingredient, create a JSON object with the following structure: `{'item':'<name>','amount':'<quantity>','unit':'<unit>', 'thumbnail':'<generate 256x256 image>', 'expiry_date':'<estimated shelf life>', 'recommended_storage':'<storage location>'}`. The item names should be in lowercase, and only use units: kg, litre, count, mL, grams, pounds, ounces.

For the thumbnail: Generate a simple, realistic 256x256 pixel image of the food item.
For the expiry_date: Provide an estimated shelf life from purchase date (e.g., "3 days", "2 weeks", "3 months", "1 year") based on typical storage conditions for that ingredient.
For the recommended_storage: Specify the best storage location for the ingredient. Use only these options: "fridge", "freezer", "cabinet", "pantry", or "counter". Choose based on food safety and preservation best practices.
"""


class itemDetails(BaseModel):
    name: str = Field(..., example="Mashroom")
    amount: str = Field(..., example="50")
    unit: Literal["grams", "kg", "litre", "mL", "pounds", "ounces",
                  "count"] = Field(..., example="kg")
    thumbnail: str = Field(..., example="data:image/png;base64,...")
    expiry_date: str = Field(..., example="7 days")
    recommended_storage: Literal["fridge", "freezer", "cabinet", "pantry", "counter"] = Field(..., example="fridge")


class itemsList(BaseModel):
    items: list[itemDetails]

def generate_food_thumbnail(item_name):
    """Generate a 256x256 thumbnail for a food item using DALL-E"""
    try:
        prompt = f"A simple, realistic photo of {item_name} on a white background, professional food photography, well-lit"
        
        response = client.images.generate(
            model="dall-e-2",
            prompt=prompt,
            size="256x256",
            n=1
        )
        
        image_url = response.data[0].url
        image_response = requests.get(image_url)
        
        if image_response.status_code == 200:
            return base64.b64encode(image_response.content).decode('utf-8')
        return None
    except Exception as e:
        print(f"Error generating thumbnail for {item_name}: {str(e)}")
        return None


def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def analyze_image_with_openai(image_path):
    """
    Analyze receipt image and extract items with accurate quantities and expiry dates.
    """
    base64_image = encode_image(image_path)
    
    # ✅ IMPROVED PROMPT - Concise but accurate
    enhanced_prompt = """You are an expert at reading grocery receipts with HIGH ACCURACY.

CRITICAL INSTRUCTIONS:

1. QUANTITY EXTRACTION:
   - Extract the EXACT quantity shown on the receipt
   - If receipt shows "2 lbs", output "2" with unit "pounds" (not "1" or "3")
   - If quantity is unclear or not visible, default to "1"
   - Common formats: "2.5 lbs", "1 gallon", "500g", "12 count", "6 pack"
   - DO NOT guess - accuracy is critical for user trust

2. EXPIRY DATE ASSIGNMENT:
   - Assign REALISTIC expiry dates based on USA food safety standards
   - Use your knowledge of USDA/FDA guidelines for typical shelf life
   - Format: "X days", "X weeks", "X months", or "X year" from purchase date
   - EXPIRY DATE (USA Market Standards - Accuracy is Very Important for user trust)

3. UNIT STANDARDS (USA):
   - Weight: pounds, ounces, grams, kg
   - Volume: litre, mL, gallons
   - Count: count, pack, dozen
   - Convert if needed (e.g., "1 qt" → "1 litre")

4. STORAGE LOCATION:
   - fridge: Fresh meat, dairy, eggs, most produce
   - freezer: Frozen items only
   - pantry: Dry goods, canned items, oils, grains
   - cabinet: Spices, baking supplies
   - counter: Bananas, bread (short-term), tomatoes

5. ITEM FILTERING:
   - ONLY extract food/beverage items
   - SKIP: toiletries, household items, paper products, cleaning supplies

OUTPUT FORMAT (JSON only, no markdown):
{
  "items": [
    {
      "name": "chicken breast",
      "amount": "2",
      "unit": "pounds",
      "expiry_date": "2 days",
      "recommended_storage": "fridge"
    }
  ]
}

IMPORTANT: 
- Double-check quantities match receipt EXACTLY
- Use realistic, food-safe expiry dates for USA market
- Item names should be lowercase and clear"""

    response = client.chat.completions.create(
        model='gpt-4o', 
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": enhanced_prompt
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}",
                        "detail": "high"
                    }
                }
            ]
        }],
        max_tokens=2000,
        temperature=0.2
    )
    
    content = response.choices[0].message.content
    print("Raw GPT response:", content)
    
    # Clean response (remove markdown if present)
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()
    
    # Parse JSON
    try:
        items_data = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"JSON Parse Error: {e}")
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            items_data = json.loads(json_match.group())
        else:
            raise Exception("Could not parse response as JSON")
    
    items = items_data.get('items', [])
    
    # Generate thumbnails in parallel
    def add_thumbnail(item):
        thumbnail = generate_food_thumbnail(item['name'])
        item['thumbnail'] = f"data:image/png;base64,{thumbnail}" if thumbnail else None
        return item
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        items = list(executor.map(add_thumbnail, items))
    
    return json.dumps({"items": items})




# Example usage

# Try syncing the item spelling if exactly same item already exist in inventory list. If they're different ingredients then make sure to consider them different use the original identified spelling of item from recipt