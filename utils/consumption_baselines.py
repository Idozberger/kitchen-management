# consumption_baselines.py
"""
Baseline consumption data for common grocery items.
These are average consumption times in days for a typical household.
"""

CONSUMPTION_BASELINES = {
    # Dairy Products
    'milk': {'days': 1, 'category': 'dairy'},
    'yogurt': {'days': 1, 'category': 'dairy'},
    'cheese': {'days': 1, 'category': 'dairy'},
    'butter': {'days': 1, 'category': 'dairy'},
    'cream': {'days': 1, 'category': 'dairy'},
    'sour cream': {'days': 1, 'category': 'dairy'},
    
    # Proteins
    'eggs': {'days': 14, 'category': 'protein'},
    'chicken': {'days': 3, 'category': 'protein'},
    'beef': {'days': 1, 'category': 'protein'},
    'pork': {'days': 1, 'category': 'protein'},
    'fish': {'days': 1, 'category': 'protein'},
    'salmon': {'days': 1, 'category': 'protein'},
    'shrimp': {'days': 2, 'category': 'protein'},
    'bacon': {'days': 10, 'category': 'protein'},
    'sausage': {'days': 7, 'category': 'protein'},
    'ham': {'days': 7, 'category': 'protein'},
    'turkey': {'days': 3, 'category': 'protein'},
    
    # Bread & Bakery
    'bread': {'days': 5, 'category': 'bakery'},
    'bagels': {'days': 7, 'category': 'bakery'},
    'tortillas': {'days': 10, 'category': 'bakery'},
    'pita': {'days': 7, 'category': 'bakery'},
    'croissant': {'days': 3, 'category': 'bakery'},
    'muffins': {'days': 5, 'category': 'bakery'},
    
    # Fruits (Fresh)
    'apple': {'days': 10, 'category': 'fruit'},
    'banana': {'days': 5, 'category': 'fruit'},
    'orange': {'days': 10, 'category': 'fruit'},
    'grape': {'days': 7, 'category': 'fruit'},
    'strawberry': {'days': 5, 'category': 'fruit'},
    'blueberry': {'days': 7, 'category': 'fruit'},
    'watermelon': {'days': 7, 'category': 'fruit'},
    'pineapple': {'days': 5, 'category': 'fruit'},
    'mango': {'days': 5, 'category': 'fruit'},
    'peach': {'days': 5, 'category': 'fruit'},
    'pear': {'days': 7, 'category': 'fruit'},
    'lemon': {'days': 14, 'category': 'fruit'},
    'lime': {'days': 14, 'category': 'fruit'},
    'avocado': {'days': 5, 'category': 'fruit'},
    
    # Vegetables (Fresh)
    'tomato': {'days': 7, 'category': 'vegetable'},
    'potato': {'days': 21, 'category': 'vegetable'},
    'onion': {'days': 21, 'category': 'vegetable'},
    'garlic': {'days': 30, 'category': 'vegetable'},
    'carrot': {'days': 14, 'category': 'vegetable'},
    'broccoli': {'days': 7, 'category': 'vegetable'},
    'cauliflower': {'days': 7, 'category': 'vegetable'},
    'lettuce': {'days': 5, 'category': 'vegetable'},
    'spinach': {'days': 5, 'category': 'vegetable'},
    'cucumber': {'days': 7, 'category': 'vegetable'},
    'bell pepper': {'days': 7, 'category': 'vegetable'},
    'zucchini': {'days': 7, 'category': 'vegetable'},
    'mushroom': {'days': 7, 'category': 'vegetable'},
    'corn': {'days': 5, 'category': 'vegetable'},
    'green beans': {'days': 7, 'category': 'vegetable'},
    'celery': {'days': 10, 'category': 'vegetable'},
    'cabbage': {'days': 14, 'category': 'vegetable'},
    
    # Condiments & Sauces
    'ketchup': {'days': 90, 'category': 'condiment'},
    'mustard': {'days': 90, 'category': 'condiment'},
    'mayonnaise': {'days': 60, 'category': 'condiment'},
    'soy sauce': {'days': 180, 'category': 'condiment'},
    'hot sauce': {'days': 90, 'category': 'condiment'},
    'salsa': {'days': 14, 'category': 'condiment'},
    'bbq sauce': {'days': 60, 'category': 'condiment'},
    'ranch dressing': {'days': 30, 'category': 'condiment'},
    
    # Beverages
    'orange juice': {'days': 7, 'category': 'beverage'},
    'apple juice': {'days': 7, 'category': 'beverage'},
    'soda': {'days': 30, 'category': 'beverage'},
    'beer': {'days': 60, 'category': 'beverage'},
    'wine': {'days': 30, 'category': 'beverage'},
    'water': {'days': 7, 'category': 'beverage'},
    'coffee': {'days': 30, 'category': 'beverage'},
    'tea': {'days': 60, 'category': 'beverage'},
    
    # Pantry Staples
    'rice': {'days': 180, 'category': 'pantry'},
    'pasta': {'days': 180, 'category': 'pantry'},
    'flour': {'days': 90, 'category': 'pantry'},
    'sugar': {'days': 180, 'category': 'pantry'},
    'salt': {'days': 365, 'category': 'pantry'},
    'oil': {'days': 90, 'category': 'pantry'},
    'olive oil': {'days': 90, 'category': 'pantry'},
    'vegetable oil': {'days': 90, 'category': 'pantry'},
    'cereal': {'days': 30, 'category': 'pantry'},
    'oatmeal': {'days': 60, 'category': 'pantry'},
    'beans': {'days': 180, 'category': 'pantry'},
    'canned tomatoes': {'days': 180, 'category': 'pantry'},
    'peanut butter': {'days': 60, 'category': 'pantry'},
    'jam': {'days': 60, 'category': 'pantry'},
    'honey': {'days': 365, 'category': 'pantry'},
    'nuts': {'days': 60, 'category': 'pantry'},
    
    # Frozen Foods
    'frozen vegetables': {'days': 90, 'category': 'frozen'},
    'frozen fruits': {'days': 90, 'category': 'frozen'},
    'ice cream': {'days': 30, 'category': 'frozen'},
    'frozen pizza': {'days': 60, 'category': 'frozen'},
    'frozen meals': {'days': 60, 'category': 'frozen'},
    
    # Snacks
    'chips': {'days': 14, 'category': 'snack'},
    'crackers': {'days': 30, 'category': 'snack'},
    'cookies': {'days': 21, 'category': 'snack'},
    'popcorn': {'days': 30, 'category': 'snack'},
    'chocolate': {'days': 30, 'category': 'snack'},
    'candy': {'days': 60, 'category': 'snack'},
}


def get_baseline_consumption(item_name):
    """
    Get baseline consumption days for an item.
    Returns None if item not found in baseline data.
    
    Args:
        item_name (str): Name of the item (case insensitive)
    
    Returns:
        dict or None: {'days': int, 'category': str} or None
    """
    item_name_lower = item_name.strip().lower()
    return CONSUMPTION_BASELINES.get(item_name_lower)


def get_default_consumption_days():
    """
    Default consumption days if item not found in baseline.
    Conservative estimate.
    """
    return 14  # 2 weeks default


def populate_baselines_to_db():
    """
    Populate baseline data into PostgreSQL.
    Call this once during setup or migration.
    """
    from db_connection import get_session
    from models import ConsumptionBaseline
    
    session = get_session()
    try:
        baseline_objects = []
        for item_name, data in CONSUMPTION_BASELINES.items():
            baseline = ConsumptionBaseline(
                item_name=item_name,
                avg_consumption_days=data['days'],
                category=data['category']
            )
            baseline_objects.append(baseline)
        
        if baseline_objects:
            session.bulk_save_objects(baseline_objects)
            session.commit()
            print(f"✅ Populated {len(baseline_objects)} baseline consumption records")
        else:
            print("⚠️ No baseline data to populate")
    except Exception as e:
        session.rollback()
        print(f"❌ Error populating baselines: {str(e)}")
        raise
    finally:
        session.close()


# Export for easy import
__all__ = [
    'CONSUMPTION_BASELINES',
    'get_baseline_consumption',
    'get_default_consumption_days',
    'populate_baselines_to_db'
]