"""
Expiry Date Calculator Utility
Automatically calculates expiry dates for items using:
1. EXPIRY_BASELINES (primary source)
2. OpenAI GPT-4o (fallback if not in baseline)
"""

from openai import OpenAI
import json
import os
from typing import Optional, Dict
from utils.expiry_baselines import get_expiry_baseline


class ExpiryCalculator:
    """
    Calculates expiry dates for food items automatically
    """
    
    def __init__(self):
        """Initialize OpenAI client"""
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            print("⚠️ Warning: OPENAI_API_KEY not set, will only use baseline")
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key)
    
    def calculate_expiry_date(self, item_name: str, storage: str = None) -> Optional[str]:
        """
        Calculate expiry date for an item
        
        Args:
            item_name: Name of the food item (e.g., "chicken breast", "milk")
            storage: Optional storage location hint (fridge, freezer, pantry, cabinet)
        
        Returns:
            Expiry date string (e.g., "2 days", "1 week", "30 days") or None
        """
        
        print(f"🔍 Calculating expiry for: '{item_name}' (storage: {storage})")
        
        # Step 1: Try EXPIRY_BASELINES first
        baseline = get_expiry_baseline(item_name)
        
        if baseline:
            days = baseline['days']
            expiry_str = self._format_expiry_days(days)
            print(f"   ✅ Found in baseline: {expiry_str} ({baseline['storage']})")
            return expiry_str
        
        # Step 2: Baseline not found, use OpenAI
        print(f"   ⚠️ Not in baseline, using OpenAI...")
        
        if not self.client:
            print(f"   ❌ OpenAI not available, using storage defaults")
            return self._get_storage_default_expiry(storage, item_name)
        
        try:
            expiry_days = self._ask_openai_for_expiry(item_name, storage)
            if expiry_days:
                expiry_str = self._format_expiry_days(expiry_days)
                print(f"   ✅ OpenAI calculated: {expiry_str}")
                return expiry_str
            else:
                print(f"   ⚠️ OpenAI failed, using storage defaults")
                return self._get_storage_default_expiry(storage, item_name)
        except Exception as e:
            print(f"   ❌ OpenAI error: {str(e)}, using storage defaults")
            return self._get_storage_default_expiry(storage, item_name)
    
    def _ask_openai_for_expiry(self, item_name: str, storage: str = None) -> Optional[int]:
        """
        Ask OpenAI to estimate expiry days for an item
        
        Returns:
            Number of days the item typically lasts, or None if failed
        """
        
        storage_context = f" (stored in {storage})" if storage else ""
        
        prompt = f"""You are a food safety and shelf life expert.

ITEM: {item_name}{storage_context}

TASK: Estimate how many DAYS this food item typically lasts before expiring.

RULES:
1. Consider typical storage conditions for this item
2. Use CONSERVATIVE estimates (err on the side of safety)
3. Consider whether it's fresh, frozen, canned, packaged, etc.
4. Return ONLY a JSON object with "days" field

STORAGE GUIDELINES:
- Fresh meat/fish (fridge): 1-3 days
- Dairy (fridge): 5-14 days
- Fresh produce (fridge): 5-14 days
- Frozen items: 90-365 days
- Pantry dry goods: 180-730 days
- Canned goods: 365-1095 days
- Spices/seasonings: 365-1095 days

OUTPUT FORMAT (JSON only):
{{
  "days": <number>,
  "reasoning": "brief explanation"
}}

Return ONLY valid JSON, no markdown or extra text."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",  # Using mini for cost efficiency
                messages=[
                    {
                        "role": "system",
                        "content": "You are a food safety expert. Always return valid JSON with estimated shelf life in days."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,  # Low for consistency
                max_tokens=200
            )
            
            content = response.choices[0].message.content.strip()
            
            # Remove markdown if present
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()
            
            # Parse JSON
            result = json.loads(content)
            days = result.get('days')
            reasoning = result.get('reasoning', '')
            
            if days and isinstance(days, (int, float)) and days > 0:
                print(f"   🤖 OpenAI: {days} days - {reasoning}")
                return int(days)
            else:
                print(f"   ⚠️ Invalid OpenAI response: {result}")
                return None
                
        except Exception as e:
            print(f"   ❌ OpenAI API error: {str(e)}")
            return None
    
    def _format_expiry_days(self, days: int) -> str:
        """
        Convert days to human-readable expiry string
        
        Examples:
            2 -> "2 days"
            7 -> "1 week"
            14 -> "2 weeks"
            30 -> "1 month"
            365 -> "1 year"
        """
        if days == 1:
            return "1 day"
        elif days < 7:
            return f"{days} days"
        elif days == 7:
            return "1 week"
        elif days < 30:
            weeks = days // 7
            return f"{weeks} weeks"
        elif days < 365:
            months = days // 30
            if months == 1:
                return "1 month"
            else:
                return f"{months} months"
        else:
            years = days // 365
            if years == 1:
                return "1 year"
            else:
                return f"{years} years"
    
    def _get_storage_default_expiry(self, storage: str, item_name: str) -> str:
        """
        Get conservative default expiry based on storage location
        Used as last resort when baseline and OpenAI both fail
        """
        
        # Category-specific defaults based on item name keywords
        meat_keywords = ['chicken', 'beef', 'pork', 'fish', 'meat', 'steak', 'turkey', 'lamb', 'shrimp', 'salmon']
        dairy_keywords = ['milk', 'yogurt', 'cream', 'cheese', 'butter']
        produce_keywords = ['lettuce', 'spinach', 'tomato', 'pepper', 'carrot', 'broccoli', 'apple', 'banana']
        
        name_lower = item_name.lower()
        
        # Category-specific defaults (conservative)
        if any(kw in name_lower for kw in meat_keywords):
            days = 2  # Fresh meat: 2 days
        elif any(kw in name_lower for kw in dairy_keywords):
            days = 7  # Dairy: 1 week
        elif any(kw in name_lower for kw in produce_keywords):
            days = 5  # Produce: 5 days
        else:
            # Storage-based defaults
            storage_defaults = {
                'fridge': 7,      # 1 week
                'freezer': 180,   # 6 months
                'pantry': 365,    # 1 year
                'cabinet': 730,   # 2 years
                'counter': 7      # 1 week
            }
            days = storage_defaults.get(storage, 30) if storage else 30
        
        return self._format_expiry_days(days)


# Singleton instance for easy import
_expiry_calculator_instance = None

def get_expiry_calculator() -> ExpiryCalculator:
    """Get or create singleton ExpiryCalculator instance"""
    global _expiry_calculator_instance
    if _expiry_calculator_instance is None:
        _expiry_calculator_instance = ExpiryCalculator()
    return _expiry_calculator_instance


def calculate_item_expiry(item_name: str, storage: str = None) -> Optional[str]:
    """
    Convenience function to calculate expiry date for an item
    
    Args:
        item_name: Name of the food item
        storage: Optional storage location (fridge, freezer, pantry, cabinet)
    
    Returns:
        Expiry date string (e.g., "2 days", "1 week") or None
    """
    calculator = get_expiry_calculator()
    return calculator.calculate_expiry_date(item_name, storage)


# Test function
if __name__ == '__main__':
    print("\n" + "="*60)
    print("🧪 Testing Expiry Calculator")
    print("="*60)
    
    test_items = [
        ("milk", "fridge"),
        ("chicken breast", "fridge"),
        ("rice", "pantry"),
        ("frozen vegetables", "freezer"),
        ("dragon fruit", "fridge"),  # Not in baseline
        ("exotic spice blend", "cabinet")  # Not in baseline
    ]
    
    for item_name, storage in test_items:
        print(f"\n📦 Item: {item_name}")
        expiry = calculate_item_expiry(item_name, storage)
        print(f"   ⏰ Expiry: {expiry}")