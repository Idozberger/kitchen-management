from openai import OpenAI
import json
import os
from typing import List, Dict, Optional
from utils.expiry_baselines import get_expiry_baseline, EXPIRY_BASELINES


# ============================================
# CURRENCY CONVERSION TABLE
# ============================================
CURRENCY_TO_USD = {
    'USD': 1.0,
    'CAD': 0.74,      # 1 CAD = 0.74 USD
    'PKR': 0.0036,    # 1 PKR = 0.0036 USD (Pakistani Rupee)
    'EUR': 1.10,      # 1 EUR = 1.10 USD
    'GBP': 1.27,      # 1 GBP = 1.27 USD
    'AUD': 0.66,      # 1 AUD = 0.66 USD
    'INR': 0.012,     # 1 INR = 0.012 USD (Indian Rupee)
    'MXN': 0.059,     # 1 MXN = 0.059 USD (Mexican Peso)
    'JPY': 0.0067,    # 1 JPY = 0.0067 USD (Japanese Yen)
}


class ReceiptEnhancer:
    """
    Uses OpenAI GPT-4 to intelligently enhance receipt item data
    """
    
    def __init__(self):
        """Initialize OpenAI client"""
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        self.client = OpenAI(api_key=self.api_key)
    
    def enhance_receipt_items(self, raw_items: List[str], currency: str = "USD", country: str = "USA") -> List[Dict]:
        """
        Intelligently enhance raw receipt items with full names, measurements, storage, etc.
        
        Args:
            raw_items: List of raw text lines from receipt (e.g., ["MOZZAR 9.69", "CHK DRUM 11.68"])
            currency: Currency code (USD, CAD, PKR, EUR, etc.)
            country: Country code for market-specific estimations
        
        Returns:
            List of enhanced item dictionaries
        """
        
        print(f"🌍 Processing receipt: {currency} in {country}")
        
        # Create comprehensive prompt with proper currency handling
        prompt = self._create_enhancement_prompt(raw_items, currency, country)
        
        try:
            # Call OpenAI GPT-4o
            print(f"🤖 Calling GPT-4o for enhancement...")
            response = self.client.chat.completions.create(
                model="gpt-4o",  # Using latest model as you requested
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert grocery receipt analyzer with deep knowledge of food products, pricing, measurements, and storage requirements across different countries and currencies."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,  # Very low for consistency
                max_tokens=4000
            )
            
            # Extract JSON response
            content = response.choices[0].message.content.strip()
            
            print(f"   📄 GPT-4o response received ({len(content)} chars)")
            
            # Remove markdown code blocks if present
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()
            
            # Parse JSON
            enhanced_data = json.loads(content)
            
            # Extract items array
            if isinstance(enhanced_data, dict) and 'items' in enhanced_data:
                enhanced_items = enhanced_data['items']
            elif isinstance(enhanced_data, list):
                enhanced_items = enhanced_data
            else:
                raise ValueError(f"Unexpected response format: {type(enhanced_data)}")
            
            print(f"   ✅ Extracted {len(enhanced_items)} items from GPT-4o")
            
            # Filter out non-food items
            food_items = []
            skipped_items = []
            
            for item in enhanced_items:
                # Check if item is marked as food
                is_food = item.get('is_food', True)
                
                # Additional filtering based on keywords (backup)
                item_name = item.get('full_name', '').lower()
                non_food_keywords = ['diaper', 'wipe', 'cleaning', 'detergent', 'soap', 
                                    'shampoo', 'deodorant', 'toothpaste', 'toilet paper',
                                    'paper towel', 'garbage bag', 'pet food', 'dog food',
                                    'cat food', 'cigarette', 'tobacco', 'lighter', 'tissue']
                
                has_non_food_keyword = any(keyword in item_name for keyword in non_food_keywords)
                
                if is_food and not has_non_food_keyword:
                    food_items.append(item)
                else:
                    skipped_items.append(item)
                    print(f"   ⚠️  Skipped non-food: {item.get('full_name', 'Unknown')}")
            
            print(f"   ✅ Kept {len(food_items)} food items, skipped {len(skipped_items)} non-food")
            
            # ============================================
            # CRITICAL FIX: FORCE BASELINE EXPIRY DATES
            # ============================================
            for item in food_items:
                item = self._add_expiry_date_from_baseline(item)
            
            return {'items': food_items}
            
        except json.JSONDecodeError as e:
            print(f"❌ OpenAI JSON parsing error: {str(e)}")
            print(f"Content that failed to parse: {content[:500]}")
            raise
        except Exception as e:
            print(f"❌ OpenAI enhancement error: {str(e)}")
            import traceback
            traceback.print_exc()
            raise
    
    def _create_enhancement_prompt(self, raw_items: List[str], currency: str, country: str) -> str:
        """
        Create comprehensive prompt with PROPER CURRENCY HANDLING
        """
        
        items_text = "\n".join([f"{i+1}. {item}" for i, item in enumerate(raw_items)])
        
        # ============================================
        # CURRENCY CONVERSION - CRITICAL FIX
        # ============================================
        conversion_rate = CURRENCY_TO_USD.get(currency.upper(), 1.0)
        
        def convert_price_range(usd_low, usd_high):
            """Convert USD base prices to target currency"""
            local_low = round(usd_low / conversion_rate, 1)
            local_high = round(usd_high / conversion_rate, 1)
            return f"{currency} {local_low:g}-{local_high:g}"
        
        # Build currency-specific pricing examples
        chicken_range = convert_price_range(10, 15)
        beef_range = convert_price_range(15, 25)
        fish_range = convert_price_range(12, 18)
        milk_1l = convert_price_range(2, 4)
        milk_2l = convert_price_range(5, 7)
        yogurt_single = convert_price_range(0.50, 1.50)
        yogurt_large = convert_price_range(3, 6)
        cheese_small = convert_price_range(4, 8)
        pasta_range = convert_price_range(2, 5)
        rice_range = convert_price_range(3, 7)
        
        # Show conversion info for debugging
        print(f"   💱 Currency conversion: 1 {currency} = {conversion_rate} USD")
        print(f"   📊 Example: Chicken in {currency}: {chicken_range} per kg")
        
        prompt = f"""
You are analyzing a grocery receipt from {country} with ALL PRICES IN {currency}.

🚨 CRITICAL CURRENCY INSTRUCTION:
- Every price on this receipt is in {currency}
- {currency} 100 is NOT the same as USD 100!
- 1 {currency} = {conversion_rate} USD
- Use the {currency} price ranges below, NOT USD ranges

RAW RECEIPT LINES:
{items_text}

TASK: Extract ONLY FOOD items with accurate quantities based on {currency} pricing.

STEP 1: IDENTIFY FOOD ITEMS
✅ Include: dairy, meat, produce, pantry, bakery, snacks, beverages, frozen food
❌ Skip: diapers, cleaning supplies, personal care, household, tobacco, pet food

STEP 2: EXPAND ABBREVIATIONS (use COMPLETE context!)
Examples:
- "TAGLIATELLE NEST MRJ" → "tagliatelle pasta nests" (pasta, not jam)
- "PC SPLENDIDO PAR" → "President's Choice Splendido parmesan cheese"
- "CHK DRUM" → "chicken drumsticks"

Brand codes: PC=President's Choice, KFT=Kraft, DO=Dole

STEP 3: ESTIMATE QUANTITIES FROM {currency} PRICES

⚠️  USE THESE {currency} RANGES (NOT USD!):

If explicit quantity shown (e.g., "2@", "3x") → USE IT EXACTLY

Otherwise estimate from price:

MEAT & PROTEIN ({currency} prices):
- Chicken/turkey: {chicken_range} per kg
- Beef/steak: {beef_range} per kg
- Fish: {fish_range} per kg
- Under half the kg price → estimate 0.5 kg

DAIRY ({currency} prices):
- Milk: {milk_1l} per litre, {milk_2l} per 2L
- Yogurt (single): {yogurt_single} = 150-200g
- Yogurt (large): {yogurt_large} = 650-750g  
- Cheese (small block): {cheese_small} = 200-250g

PANTRY ({currency} prices):
- Pasta: {pasta_range} = 450-500g
- Rice: {rice_range} = 1 kg

PRODUCE:
- Estimate based on typical package sizes for that item

STEP 4: UNITS
- Solids → grams or kg
- Liquids → ml or litre
- Discrete items (eggs, cans) → count

STEP 5: STORAGE
- fridge: meat, dairy, eggs, fresh produce
- freezer: items with "FROZEN"
- pantry: dry goods, pasta, rice, cereals
- cabinet: spices, oils

🚨 DO NOT ADD EXPIRY FIELDS
- NO expiry_days
- NO expiry_date
- NO expiry_source
(Expiry handled separately from database)

OUTPUT (JSON only, no markdown):
{{
  "items": [
    {{
      "raw_text": "exact receipt text",
      "full_name": "clear, complete product name",
      "quantity": <number>,
      "unit": "grams|kg|litre|ml|count",
      "price": <number>,
      "storage": "fridge|freezer|pantry|cabinet",
      "confidence": "high|medium|low",
      "estimation_notes": "how quantity was determined",
      "is_food": true
    }}
  ]
}}

CRITICAL REMINDERS:
1. Use {currency} prices, NOT USD!
2. {chicken_range} per kg of chicken in {currency}
3. {milk_1l} per litre of milk in {currency}
4. Skip non-food items
5. NO expiry fields
6. Return only JSON
"""
        
        return prompt
    
    def _add_expiry_date_from_baseline(self, item: Dict) -> Dict:
        """
        FORCE expiry dates from baseline database
        Never let AI hallucinate expiry dates!
        """
        item_name = item.get('full_name', '').lower()
        
        # Try exact match first
        baseline = get_expiry_baseline(item_name)
        
        if baseline:
            # Found in database - USE IT!
            item['expiry_days'] = baseline['days']
            item['expiry_source'] = 'baseline'
            
            # Override storage if baseline is more specific
            if baseline.get('storage') and baseline['storage'] != item.get('storage'):
                print(f"   🔄 Overriding storage for '{item_name}': {item.get('storage')} → {baseline['storage']}")
                item['storage'] = baseline['storage']
            
            print(f"   ✅ Baseline expiry: '{item_name}' = {baseline['days']} days ({baseline['storage']})")
        else:
            # Not in baseline - use conservative defaults by storage type
            storage = item.get('storage', 'pantry')
            item['expiry_days'] = self._get_conservative_expiry(storage, item_name)
            item['expiry_source'] = 'storage_default'
            
            print(f"   ⚠️  No baseline for '{item_name}', using {storage} default: {item['expiry_days']} days")
        
        return item
    
    def _get_conservative_expiry(self, storage: str, item_name: str) -> int:
        """
        Conservative expiry estimates when item not in baseline
        """
        
        # Check category from name
        meat_keywords = ['chicken', 'beef', 'pork', 'fish', 'meat', 'steak', 'turkey']
        dairy_keywords = ['milk', 'yogurt', 'cream', 'cheese']
        produce_keywords = ['lettuce', 'spinach', 'tomato', 'pepper', 'carrot']
        
        name_lower = item_name.lower()
        
        # Category-specific defaults (conservative)
        if any(kw in name_lower for kw in meat_keywords):
            return 2  # Fresh meat: 2 days
        elif any(kw in name_lower for kw in dairy_keywords):
            return 7  # Dairy: 1 week
        elif any(kw in name_lower for kw in produce_keywords):
            return 5  # Produce: 5 days
        
        # Fallback to storage-based defaults
        storage_defaults = {
            'fridge': 7,      # 1 week
            'freezer': 180,   # 6 months
            'pantry': 365,    # 1 year
            'cabinet': 730,   # 2 years
            'counter': 7      # 1 week
        }
        
        return storage_defaults.get(storage, 30)


def test_currency_handling():
    """
    Test that currency conversions work properly
    """
    enhancer = ReceiptEnhancer()
    
    # Test case: Same item, different currencies
    raw_items_usd = ["CHICKEN BREAST 11.50"]
    raw_items_pkr = ["CHICKEN BREAST 3200"]  # ~11.50 USD at 1 PKR = 0.0036 USD
    raw_items_cad = ["CHICKEN BREAST 15.50"]  # ~11.50 USD at 1 CAD = 0.74 USD
    
    print("\n" + "="*60)
    print("Testing Currency Handling")
    print("="*60)
    
    print("\n1. USD Test:")
    result_usd = enhancer.enhance_receipt_items(raw_items_usd, currency="USD", country="USA")
    for item in result_usd['items']:
        print(f"   {item['full_name']}: {item['quantity']} {item['unit']}")
    
    print("\n2. PKR Test:")
    result_pkr = enhancer.enhance_receipt_items(raw_items_pkr, currency="PKR", country="Pakistan")
    for item in result_pkr['items']:
        print(f"   {item['full_name']}: {item['quantity']} {item['unit']}")
    
    print("\n3. CAD Test:")
    result_cad = enhancer.enhance_receipt_items(raw_items_cad, currency="CAD", country="Canada")
    for item in result_cad['items']:
        print(f"   {item['full_name']}: {item['quantity']} {item['unit']}")


def test_expiry_baseline_enforcement():
    """
    Test that expiry dates come from baseline, not AI
    """
    enhancer = ReceiptEnhancer()
    
    raw_items = [
        "WHOLE MILK 2.89",
        "CHICKEN BREAST 11.50",
        "PASTA 3.99"
    ]
    
    print("\n" + "="*60)
    print("Testing Expiry Baseline Enforcement")
    print("="*60)
    
    result = enhancer.enhance_receipt_items(raw_items, currency="USD", country="USA")
    
    for item in result['items']:
        print(f"\n{item['full_name']}:")
        print(f"  Expiry: {item['expiry_days']} days")
        print(f"  Source: {item['expiry_source']}")
        print(f"  Storage: {item['storage']}")


if __name__ == '__main__':
    print("🧪 Running tests...\n")
    test_currency_handling()
    test_expiry_baseline_enforcement()