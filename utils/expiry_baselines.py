"""
Expiry Date Baseline Database
Created from Master Shelf Life Listing document
Used for automatic expiry date estimation during receipt scanning
"""

# Comprehensive expiry baseline for common kitchen items
# Format: {item_name: {'days': X, 'storage': 'fridge'|'freezer'|'pantry'|'cabinet'|'counter'}}

EXPIRY_BASELINES = {
    # DAIRY PRODUCTS (Fridge)
    'milk': {'days': 7, 'storage': 'fridge', 'category': 'dairy'},
    'whole milk': {'days': 7, 'storage': 'fridge', 'category': 'dairy'},
    'skim milk': {'days': 7, 'storage': 'fridge', 'category': 'dairy'},
    'almond milk': {'days': 7, 'storage': 'fridge', 'category': 'dairy'},
    'soy milk': {'days': 7, 'storage': 'fridge', 'category': 'dairy'},
   'oat milk': {'days': 7, 'storage': 'fridge', 'category': 'dairy'},
    'cream': {'days': 14, 'storage': 'fridge', 'category': 'dairy'},
    'whipped cream': {'days': 14, 'storage': 'fridge', 'category': 'dairy'},
    'heavy cream': {'days': 14, 'storage': 'fridge', 'category': 'dairy'},
    'half and half': {'days': 14, 'storage': 'fridge', 'category': 'dairy'},
    'sour cream': {'days': 21, 'storage': 'fridge', 'category': 'dairy'},
    'yogurt': {'days': 7, 'storage': 'fridge', 'category': 'dairy'},
    'greek yogurt': {'days': 7, 'storage': 'fridge', 'category': 'dairy'},
    'butter': {'days': 90, 'storage': 'fridge', 'category': 'dairy'},
    'margarine': {'days': 90, 'storage': 'fridge', 'category': 'dairy'},
    'cheese': {'days': 30, 'storage': 'fridge', 'category': 'dairy'},
    'cheddar cheese': {'days': 30, 'storage': 'fridge', 'category': 'dairy'},
    'mozzarella': {'days': 14, 'storage': 'fridge', 'category': 'dairy'},
    'mozzarella cheese': {'days': 14, 'storage': 'fridge', 'category': 'dairy'},
    'parmesan': {'days': 60, 'storage': 'fridge', 'category': 'dairy'},
    'parmesan cheese': {'days': 60, 'storage': 'fridge', 'category': 'dairy'},
    'swiss cheese': {'days': 30, 'storage': 'fridge', 'category': 'dairy'},
    'cream cheese': {'days': 14, 'storage': 'fridge', 'category': 'dairy'},
    'cottage cheese': {'days': 7, 'storage': 'fridge', 'category': 'dairy'},
    'string cheese': {'days': 14, 'storage': 'fridge', 'category': 'dairy'},
    'cheese curds': {'days': 14, 'storage': 'fridge', 'category': 'dairy'},
    'eggs': {'days': 21, 'storage': 'fridge', 'category': 'dairy'},
    'egg whites': {'days': 7, 'storage': 'fridge', 'category': 'dairy'},
    
    # MEAT & PROTEIN (Fridge/Freezer)
    'chicken': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'chicken breast': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'chicken thigh': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'chicken drumstick': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'chicken wings': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'ground chicken': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'turkey': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'turkey breast': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'ground turkey': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'beef': {'days': 3, 'storage': 'fridge', 'category': 'protein'},
    'ground beef': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'steak': {'days': 3, 'storage': 'fridge', 'category': 'protein'},
    'beef steak': {'days': 3, 'storage': 'fridge', 'category': 'protein'},
    'pork': {'days': 3, 'storage': 'fridge', 'category': 'protein'},
    'pork chops': {'days': 3, 'storage': 'fridge', 'category': 'protein'},
    'pork loin': {'days': 3, 'storage': 'fridge', 'category': 'protein'},
    'ground pork': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'bacon': {'days': 7, 'storage': 'fridge', 'category': 'protein'},
    'sausage': {'days': 7, 'storage': 'fridge', 'category': 'protein'},
    'hot dogs': {'days': 14, 'storage': 'fridge', 'category': 'protein'},
    'deli meat': {'days': 5, 'storage': 'fridge', 'category': 'protein'},
    'ham': {'days': 7, 'storage': 'fridge', 'category': 'protein'},
    'salmon': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'fish': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'tilapia': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'cod': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'shrimp': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'tuna': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'crab': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'lobster': {'days': 2, 'storage': 'fridge', 'category': 'protein'},
    'mussels': {'days': 1, 'storage': 'fridge', 'category': 'protein'},
    'oysters': {'days': 1, 'storage': 'fridge', 'category': 'protein'},
    'tofu': {'days': 7, 'storage': 'fridge', 'category': 'protein'},
    
    # FROZEN ITEMS
    'frozen chicken': {'days': 365, 'storage': 'freezer', 'category': 'frozen'},
    'frozen beef': {'days': 365, 'storage': 'freezer', 'category': 'frozen'},
    'frozen pork': {'days': 365, 'storage': 'freezer', 'category': 'frozen'},
    'frozen fish': {'days': 180, 'storage': 'freezer', 'category': 'frozen'},
    'frozen shrimp': {'days': 180, 'storage': 'freezer', 'category': 'frozen'},
    'frozen vegetables': {'days': 365, 'storage': 'freezer', 'category': 'frozen'},
    'frozen pizza': {'days': 180, 'storage': 'freezer', 'category': 'frozen'},
    'ice cream': {'days': 90, 'storage': 'freezer', 'category': 'frozen'},
    'frozen berries': {'days': 365, 'storage': 'freezer', 'category': 'frozen'},
    'frozen fruit': {'days': 365, 'storage': 'freezer', 'category': 'frozen'},
    
    # PRODUCE (Fridge/Counter)
    'lettuce': {'days': 7, 'storage': 'fridge', 'category': 'produce'},
    'spinach': {'days': 7, 'storage': 'fridge', 'category': 'produce'},
    'kale': {'days': 7, 'storage': 'fridge', 'category': 'produce'},
    'arugula': {'days': 5, 'storage': 'fridge', 'category': 'produce'},
    'cabbage': {'days': 14, 'storage': 'fridge', 'category': 'produce'},
    'broccoli': {'days': 7, 'storage': 'fridge', 'category': 'produce'},
    'cauliflower': {'days': 7, 'storage': 'fridge', 'category': 'produce'},
    'carrots': {'days': 21, 'storage': 'fridge', 'category': 'produce'},
    'celery': {'days': 14, 'storage': 'fridge', 'category': 'produce'},
    'cucumber': {'days': 7, 'storage': 'fridge', 'category': 'produce'},
    'zucchini': {'days': 7, 'storage': 'fridge', 'category': 'produce'},
    'bell pepper': {'days': 7, 'storage': 'fridge', 'category': 'produce'},
    'green pepper': {'days': 7, 'storage': 'fridge', 'category': 'produce'},
    'red pepper': {'days': 7, 'storage': 'fridge', 'category': 'produce'},
    'jalapeno': {'days': 14, 'storage': 'fridge', 'category': 'produce'},
    'mushrooms': {'days': 7, 'storage': 'fridge', 'category': 'produce'},
    'tomatoes': {'days': 7, 'storage': 'counter', 'category': 'produce'},
    'cherry tomatoes': {'days': 7, 'storage': 'fridge', 'category': 'produce'},
    'green beans': {'days': 7, 'storage': 'fridge', 'category': 'produce'},
    'asparagus': {'days': 5, 'storage': 'fridge', 'category': 'produce'},
    'avocado': {'days': 5, 'storage': 'counter', 'category': 'produce'},
    'bananas': {'days': 5, 'storage': 'counter', 'category': 'produce'},
    'apples': {'days': 21, 'storage': 'fridge', 'category': 'produce'},
    'oranges': {'days': 14, 'storage': 'counter', 'category': 'produce'},
    'grapes': {'days': 7, 'storage': 'fridge', 'category': 'produce'},
    'strawberries': {'days': 5, 'storage': 'fridge', 'category': 'produce'},
    'blueberries': {'days': 7, 'storage': 'fridge', 'category': 'produce'},
    'raspberries': {'days': 3, 'storage': 'fridge', 'category': 'produce'},
    'blackberries': {'days': 5, 'storage': 'fridge', 'category': 'produce'},
    'mango': {'days': 5, 'storage': 'counter', 'category': 'produce'},
    'pineapple': {'days': 5, 'storage': 'counter', 'category': 'produce'},
    'watermelon': {'days': 7, 'storage': 'fridge', 'category': 'produce'},
    'cantaloupe': {'days': 7, 'storage': 'fridge', 'category': 'produce'},
    'potatoes': {'days': 30, 'storage': 'pantry', 'category': 'produce'},
    'sweet potatoes': {'days': 30, 'storage': 'pantry', 'category': 'produce'},
    'onions': {'days': 30, 'storage': 'pantry', 'category': 'produce'},
    'garlic': {'days': 90, 'storage': 'pantry', 'category': 'produce'},
    'ginger': {'days': 21, 'storage': 'fridge', 'category': 'produce'},
    'lemons': {'days': 21, 'storage': 'fridge', 'category': 'produce'},
    'limes': {'days': 21, 'storage': 'fridge', 'category': 'produce'},
    
    # BREAD & BAKERY (Counter/Pantry)
    'bread': {'days': 7, 'storage': 'counter', 'category': 'bakery'},
    'white bread': {'days': 7, 'storage': 'counter', 'category': 'bakery'},
    'whole wheat bread': {'days': 7, 'storage': 'counter', 'category': 'bakery'},
    'bagels': {'days': 7, 'storage': 'counter', 'category': 'bakery'},
    'english muffins': {'days': 14, 'storage': 'counter', 'category': 'bakery'},
    'tortillas': {'days': 30, 'storage': 'fridge', 'category': 'bakery'},
    'pita bread': {'days': 7, 'storage': 'counter', 'category': 'bakery'},
    'croissant': {'days': 2, 'storage': 'counter', 'category': 'bakery'},
    'muffins': {'days': 7, 'storage': 'counter', 'category': 'bakery'},
    'donuts': {'days': 2, 'storage': 'counter', 'category': 'bakery'},
    'cake': {'days': 5, 'storage': 'counter', 'category': 'bakery'},
    'cookies': {'days': 14, 'storage': 'pantry', 'category': 'bakery'},
    
    # PANTRY STAPLES (Pantry/Cabinet)
    'pasta': {'days': 720, 'storage': 'pantry', 'category': 'pantry'},
    'spaghetti': {'days': 720, 'storage': 'pantry', 'category': 'pantry'},
    'penne': {'days': 720, 'storage': 'pantry', 'category': 'pantry'},
    'macaroni': {'days': 720, 'storage': 'pantry', 'category': 'pantry'},
    'noodles': {'days': 720, 'storage': 'pantry', 'category': 'pantry'},
    'rice': {'days': 730, 'storage': 'pantry', 'category': 'pantry'},
    'white rice': {'days': 730, 'storage': 'pantry', 'category': 'pantry'},
    'brown rice': {'days': 180, 'storage': 'pantry', 'category': 'pantry'},
    'quinoa': {'days': 730, 'storage': 'pantry', 'category': 'pantry'},
    'oats': {'days': 365, 'storage': 'pantry', 'category': 'pantry'},
    'cereal': {'days': 180, 'storage': 'pantry', 'category': 'pantry'},
    'granola': {'days': 180, 'storage': 'pantry', 'category': 'pantry'},
    'flour': {'days': 365, 'storage': 'pantry', 'category': 'pantry'},
    'all purpose flour': {'days': 365, 'storage': 'pantry', 'category': 'pantry'},
    'whole wheat flour': {'days': 180, 'storage': 'pantry', 'category': 'pantry'},
    'sugar': {'days': 730, 'storage': 'pantry', 'category': 'pantry'},
    'brown sugar': {'days': 365, 'storage': 'pantry', 'category': 'pantry'},
    'powdered sugar': {'days': 730, 'storage': 'pantry', 'category': 'pantry'},
    'honey': {'days': 1095, 'storage': 'pantry', 'category': 'pantry'},
    'maple syrup': {'days': 365, 'storage': 'pantry', 'category': 'pantry'},
    'peanut butter': {'days': 180, 'storage': 'pantry', 'category': 'pantry'},
    'almond butter': {'days': 180, 'storage': 'pantry', 'category': 'pantry'},
    'jam': {'days': 180, 'storage': 'pantry', 'category': 'pantry'},
    'jelly': {'days': 180, 'storage': 'pantry', 'category': 'pantry'},
    'olive oil': {'days': 365, 'storage': 'pantry', 'category': 'pantry'},
    'vegetable oil': {'days': 365, 'storage': 'pantry', 'category': 'pantry'},
    'canola oil': {'days': 365, 'storage': 'pantry', 'category': 'pantry'},
    'coconut oil': {'days': 730, 'storage': 'pantry', 'category': 'pantry'},
    'vinegar': {'days': 1095, 'storage': 'pantry', 'category': 'pantry'},
    'balsamic vinegar': {'days': 1095, 'storage': 'pantry', 'category': 'pantry'},
    'soy sauce': {'days': 730, 'storage': 'pantry', 'category': 'pantry'},
    'ketchup': {'days': 180, 'storage': 'pantry', 'category': 'condiment'},
    'mustard': {'days': 365, 'storage': 'pantry', 'category': 'condiment'},
    'mayonnaise': {'days': 90, 'storage': 'fridge', 'category': 'condiment'},
    'salsa': {'days': 30, 'storage': 'fridge', 'category': 'condiment'},
    'hot sauce': {'days': 365, 'storage': 'pantry', 'category': 'condiment'},
    
    # CANNED GOODS (Pantry)
    'canned beans': {'days': 730, 'storage': 'pantry', 'category': 'canned'},
    'canned tomatoes': {'days': 730, 'storage': 'pantry', 'category': 'canned'},
    'canned soup': {'days': 730, 'storage': 'pantry', 'category': 'canned'},
    'canned tuna': {'days': 1095, 'storage': 'pantry', 'category': 'canned'},
    'canned corn': {'days': 730, 'storage': 'pantry', 'category': 'canned'},
    'canned peas': {'days': 730, 'storage': 'pantry', 'category': 'canned'},
    'canned chicken': {'days': 1095, 'storage': 'pantry', 'category': 'canned'},
    
    # BEVERAGES (Pantry/Fridge)
    'water': {'days': 730, 'storage': 'pantry', 'category': 'beverage'},
    'juice': {'days': 7, 'storage': 'fridge', 'category': 'beverage'},
    'orange juice': {'days': 7, 'storage': 'fridge', 'category': 'beverage'},
    'apple juice': {'days': 7, 'storage': 'fridge', 'category': 'beverage'},
    'soda': {'days': 270, 'storage': 'pantry', 'category': 'beverage'},
    'coffee': {'days': 180, 'storage': 'pantry', 'category': 'beverage'},
    'tea': {'days': 365, 'storage': 'pantry', 'category': 'beverage'},
    
    # SPICES & SEASONINGS (Cabinet)
    'salt': {'days': 1825, 'storage': 'cabinet', 'category': 'spice'},
    'pepper': {'days': 1095, 'storage': 'cabinet', 'category': 'spice'},
    'black pepper': {'days': 1095, 'storage': 'cabinet', 'category': 'spice'},
    'garlic powder': {'days': 730, 'storage': 'cabinet', 'category': 'spice'},
    'onion powder': {'days': 730, 'storage': 'cabinet', 'category': 'spice'},
    'paprika': {'days': 730, 'storage': 'cabinet', 'category': 'spice'},
    'cumin': {'days': 730, 'storage': 'cabinet', 'category': 'spice'},
    'cinnamon': {'days': 730, 'storage': 'cabinet', 'category': 'spice'},
    'oregano': {'days': 730, 'storage': 'cabinet', 'category': 'spice'},
    'basil': {'days': 730, 'storage': 'cabinet', 'category': 'spice'},
    'thyme': {'days': 730, 'storage': 'cabinet', 'category': 'spice'},
    'rosemary': {'days': 730, 'storage': 'cabinet', 'category': 'spice'},
    'vanilla extract': {'days': 1095, 'storage': 'cabinet', 'category': 'spice'},
    
    # SNACKS (Pantry)
    'chips': {'days': 90, 'storage': 'pantry', 'category': 'snack'},
    'potato chips': {'days': 90, 'storage': 'pantry', 'category': 'snack'},
    'pretzels': {'days': 180, 'storage': 'pantry', 'category': 'snack'},
    'crackers': {'days': 180, 'storage': 'pantry', 'category': 'snack'},
    'popcorn': {'days': 730, 'storage': 'pantry', 'category': 'snack'},
    'nuts': {'days': 180, 'storage': 'pantry', 'category': 'snack'},
    'almonds': {'days': 180, 'storage': 'pantry', 'category': 'snack'},
    'cashews': {'days': 180, 'storage': 'pantry', 'category': 'snack'},
    'peanuts': {'days': 180, 'storage': 'pantry', 'category': 'snack'},
    'walnuts': {'days': 180, 'storage': 'pantry', 'category': 'snack'},
    'trail mix': {'days': 180, 'storage': 'pantry', 'category': 'snack'},
    'candy': {'days': 270, 'storage': 'pantry', 'category': 'snack'},
    'chocolate': {'days': 270, 'storage': 'pantry', 'category': 'snack'},
    
    # BABY FOOD (Pantry/Fridge)
    'baby food': {'days': 730, 'storage': 'pantry', 'category': 'baby'},
    'formula': {'days': 365, 'storage': 'pantry', 'category': 'baby'},
    'baby cereal': {'days': 365, 'storage': 'pantry', 'category': 'baby'},
    'diapers': {'days': 1825, 'storage': 'pantry', 'category': 'baby'},
}


def get_expiry_baseline(item_name):
    """
    Get expiry baseline for an item
    Returns None if item not found in baseline
    """
    item_lower = item_name.lower().strip()
    
    # Direct match
    if item_lower in EXPIRY_BASELINES:
        return EXPIRY_BASELINES[item_lower]
    
    # Partial match (e.g., "organic milk" contains "milk")
    for key, value in EXPIRY_BASELINES.items():
        if key in item_lower or item_lower in key:
            return value
    
    return None


def search_expiry_baseline(query):
    """
    Search for items matching a query
    """
    query_lower = query.lower().strip()
    results = []
    
    for item_name, data in EXPIRY_BASELINES.items():
        if query_lower in item_name or item_name in query_lower:
            results.append({
                'name': item_name,
                'days': data['days'],
                'storage': data['storage'],
                'category': data['category']
            })
    
    return results


# Total items in baseline
print(f"Total items in expiry baseline: {len(EXPIRY_BASELINES)}")