import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.receipt_enhancer import ReceiptEnhancer
from utils.expiry_baselines import get_expiry_baseline
from openai import OpenAI


class AdvancedReceiptScanner:
    """
    Receipt scanning system using OpenAI Vision (GPT-4o) for direct image analysis.
    Pipeline:
      1. GPT-4o Vision → extract raw food item lines from receipt image
      2. GPT-4o Text   → enhance/normalize items (quantities, units, storage)
      3. Expiry Baseline DB → assign expiry dates (never AI-guessed)
      4. DALL-E 2       → generate food thumbnails (background)
    """

    def __init__(self):
        """Initialize the scanner"""
        self.enhancer = ReceiptEnhancer()

        api_key = os.getenv('OPENAI_API_KEY')
        if api_key:
            self.openai_client = OpenAI(api_key=api_key)
        else:
            self.openai_client = None
            print("⚠️  OPENAI_API_KEY not set, scanner will not function")

    # ============================================================
    # THUMBNAIL GENERATION
    # ============================================================

    def generate_thumbnail(self, item_name: str) -> Optional[str]:
        """Generate 256x256 thumbnail using DALL-E 2"""
        if not self.openai_client:
            return None

        try:
            prompt = f"A simple, realistic photo of {item_name} on white background, professional food photography"

            response = self.openai_client.images.generate(
                model="dall-e-2",
                prompt=prompt,
                size="256x256",
                n=1
            )

            image_url = response.data[0].url

            import requests
            import base64
            image_response = requests.get(image_url, timeout=10)

            if image_response.status_code == 200:
                return base64.b64encode(image_response.content).decode('utf-8')

            return None

        except Exception as e:
            print(f"   ⚠️  Thumbnail generation failed for {item_name}: {str(e)}")
            return None

    # ============================================================
    # MAIN ENTRY POINT
    # ============================================================

    def scan_receipt(self, image_bytes: bytes, mime_type: str,
                     currency: str = "USD", country: str = "USA",
                     generate_thumbnails: bool = True) -> Dict:
        """
        Scan a receipt image using OpenAI Vision + Enhancement pipeline.

        Args:
            image_bytes:        Receipt image as bytes
            mime_type:          Image MIME type (image/jpeg or image/png)
            currency:           Currency code (USD, CAD, PKR, EUR, etc.)
            country:            Country name for market-specific estimations
            generate_thumbnails: Whether to generate DALL-E thumbnails

        Returns:
            dict with keys: success, merchant, receipt_date, currency, country,
                            total_items, items, scan_timestamp, mode, metadata
        """
        try:
            print("\n" + "=" * 60)
            print("🧾 RECEIPT SCANNING START")
            print(f"   Currency: {currency}")
            print(f"   Country:  {country}")
            print(f"   Mode:     OpenAI Vision")
            print("=" * 60 + "\n")

            if not self.openai_client:
                raise ValueError("OpenAI client is not available. Check OPENAI_API_KEY.")

            # --------------------------------------------------------
            # STEP 1: Extract raw item lines via GPT-4o Vision
            # --------------------------------------------------------
            print("👁️  Step 1: Extracting items with GPT-4o Vision...")
            raw_items = self._extract_items_with_vision(image_bytes, currency, country)
            print(f"   ✅ Vision extracted {len(raw_items)} item lines")
            for i, item in enumerate(raw_items, 1):
                print(f"      {i}. {item}")

            if not raw_items:
                return {
                    'success': False,
                    'error': 'No food items found on the receipt.',
                    'items': [],
                    'scan_timestamp': datetime.now().isoformat()
                }

            # --------------------------------------------------------
            # STEP 2: Enhance items with GPT-4o (text only, no image)
            # --------------------------------------------------------
            print(f"\n🤖 Step 2: Enhancing items with GPT-4o...")
            print(f"   Items to process: {len(raw_items)}")

            enhanced_result = self.enhancer.enhance_receipt_items(
                raw_items,
                currency=currency,
                country=country
            )

            enhanced_items = enhanced_result['items']
            print(f"   ✅ Enhanced {len(enhanced_items)} food items")

            # --------------------------------------------------------
            # STEP 3: Assign expiry dates from baseline DB
            # --------------------------------------------------------
            print("\n📅 Step 3: Adding expiry dates from baseline...")
            items_with_expiry = []
            purchase_date = datetime.now()

            for item in enhanced_items:
                expiry_days = item.get('expiry_days', 30)

                if not isinstance(expiry_days, (int, float)) or expiry_days <= 0:
                    expiry_days = 30

                expiry_date = purchase_date + timedelta(days=int(expiry_days))

                items_with_expiry.append({
                    'name':                 item.get('full_name', 'Unknown Item').lower(),
                    'amount':               str(item.get('quantity', 1)),
                    'unit':                 item.get('unit', 'count'),
                    'expiry_date':          f"{int(expiry_days)} days",
                    'expiry_date_absolute': expiry_date.strftime('%Y-%m-%d'),
                    'recommended_storage':  item.get('storage', 'pantry'),
                    'price':                item.get('price'),
                    'confidence':           item.get('confidence', 'medium'),
                    'raw_text':             item.get('raw_text', ''),
                    'expiry_source':        item.get('expiry_source', 'storage_default'),
                    'thumbnail':            None,
                })

            print(f"   ✅ Assigned expiry dates for {len(items_with_expiry)} items")

            # --------------------------------------------------------
            # STEP 4: Generate thumbnails (DALL-E 2)
            # --------------------------------------------------------
            thumbnails_generated = 0

            if generate_thumbnails and self.openai_client:
                print(f"\n🖼️  Step 4: Generating thumbnails ({len(items_with_expiry)} items)...")

                def _add_thumbnail(item):
                    thumb = self.generate_thumbnail(item['name'])
                    if thumb:
                        item['thumbnail'] = f"data:image/png;base64,{thumb}"
                        return True
                    else:
                        item['thumbnail'] = self._get_placeholder_thumbnail()
                        return False

                with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = {executor.submit(_add_thumbnail, item): item for item in items_with_expiry}
                    for future in as_completed(futures):
                        if future.result():
                            thumbnails_generated += 1

                print(f"   ✅ Generated {thumbnails_generated}/{len(items_with_expiry)} thumbnails")
            else:
                for item in items_with_expiry:
                    item['thumbnail'] = self._get_placeholder_thumbnail()

            # --------------------------------------------------------
            # STEP 5: Build final response
            # --------------------------------------------------------
            result = {
                'success':        True,
                'merchant':       'Unknown',
                'receipt_date':   None,
                'currency':       currency,
                'country':        country,
                'total_items':    len(items_with_expiry),
                'items':          items_with_expiry,
                'scan_timestamp': datetime.now().isoformat(),
                'mode':           'vision_direct',
                'metadata': {
                    'thumbnails_generated':  thumbnails_generated,
                    'thumbnails_total':      len(items_with_expiry),
                    'baseline_expiry_count': len([i for i in items_with_expiry if i['expiry_source'] == 'baseline']),
                    'default_expiry_count':  len([i for i in items_with_expiry if i['expiry_source'] == 'storage_default']),
                }
            }

            print("\n" + "=" * 60)
            print("✅ SCANNING COMPLETE")
            print(f"   Mode:            OpenAI Vision")
            print(f"   Total items:     {result['total_items']}")
            print(f"   Baseline expiry: {result['metadata']['baseline_expiry_count']}")
            print(f"   Default expiry:  {result['metadata']['default_expiry_count']}")
            print(f"   Thumbnails:      {thumbnails_generated}")
            print("=" * 60 + "\n")

            return result

        except Exception as e:
            print(f"\n❌ SCANNING FAILED: {str(e)}\n")
            import traceback
            traceback.print_exc()

            return {
                'success': False,
                'error': str(e),
                'items': [],
                'scan_timestamp': datetime.now().isoformat()
            }

    # ============================================================
    # PRIVATE: Vision extraction
    # ============================================================

    def _extract_items_with_vision(self, image_bytes: bytes, currency: str, country: str) -> List[str]:
        """
        Extract ALL item lines from the receipt image using GPT-4o Vision.

        Key rules:
        - Extract EVERY product line - do NOT filter food vs non-food here (filtering happens in Step 2)
        - Merge multi-line entries: if a quantity/price line follows an item (e.g. "2 @ $8.49"), 
          combine it with the item line above so quantity context is never lost
        - Preserve quantity prefixes like "2@", "3@", "4@" exactly as written
        - max_tokens raised to 4000 to handle long receipts without truncation
        """
        import base64
        import re

        image_base64 = base64.b64encode(image_bytes).decode('utf-8')

        vision_prompt = f"""You are reading a grocery receipt from {country} (prices in {currency}).

YOUR TASK: Extract EVERY purchased item line from this receipt — ALL of them, from top to bottom.

CRITICAL RULES:

1. EXTRACT ALL ITEMS — do NOT skip anything yet. Include groceries, dairy, meat, bakery, seafood, baby food, beverages, produce, and also non-food items like personal care, household. We will filter later. Do NOT miss any item.

2. MERGE MULTI-LINE ENTRIES — receipts often split one item across two lines:
   Example on receipt:
       NN EGGS WH LRG  MRJ
       2 @ $8.49                16.98
   → Merge into ONE line: "NN EGGS WH LRG MRJ  2 @ $8.49  16.98"
   
   Another example:
       ALMOND ORIGINAL  MRJ
       $3.49 lmt 4, $4.19 ea
       2 @ $3.49 ea             6.98
   → Merge into ONE line: "ALMOND ORIGINAL MRJ  2 @ $3.49 ea  6.98"

3. PRESERVE QUANTITY PREFIXES — keep "2@", "3@", "4@", "2 @" exactly as written. Never remove them.

4. INCLUDE PRODUCT CODES — if a barcode/SKU appears before the item name, include it.

5. ONE MERGED LINE PER ITEM — output exactly one line per purchased product.

6. SKIP non-item lines — skip: store name, address, phone, subtotal, tax, total, change, cashier name, section headers (like "22-DAIRY"), deposit/recycling fee lines, coupon/savings lines, membership lines.

Receipt is from {country}, prices in {currency}.

Return ONLY the item lines, one per line, no numbering, no bullets, no extra commentary."""

        response = self.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": vision_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=4000  # Raised from 2000 — long receipts were getting truncated
        )

        vision_text = response.choices[0].message.content

        # Split into lines, strip whitespace, remove empty lines
        raw_items = [line.strip() for line in vision_text.split('\n') if line.strip()]

        # Only strip leading list numbering like "1. " or "1) " but NOT "2@" quantity prefixes.
        # Old regex ^\d+\.\s* was incorrectly matching "2." in "2@ BIBIGO" — fixed below.
        raw_items = [re.sub(r'^\d+[.)]\s+', '', item) for item in raw_items]

        return raw_items

    # ============================================================
    # PRIVATE: Placeholder thumbnail
    # ============================================================

    def _get_placeholder_thumbnail(self) -> str:
        """Return a simple SVG placeholder as base64"""
        import base64
        svg = '''<svg width="256" height="256" xmlns="http://www.w3.org/2000/svg">
  <rect width="256" height="256" fill="#f5f5f5"/>
  <text x="50%" y="50%" font-family="Arial" font-size="20" fill="#999"
        text-anchor="middle" dy=".3em">Food Item</text>
</svg>'''
        return base64.b64encode(svg.encode()).decode()

    # ============================================================
    # CONVENIENCE: Scan from file path
    # ============================================================

    def scan_receipt_from_file(self, file_path: str, currency: str = "USD",
                               country: str = "USA") -> Dict:
        """Convenience method: scan receipt from a file path"""
        with open(file_path, 'rb') as f:
            image_bytes = f.read()

        mime_type = 'image/png' if file_path.lower().endswith('.png') else 'image/jpeg'

        return self.scan_receipt(
            image_bytes,
            mime_type,
            currency=currency,
            country=country
        )