import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils.document_ai_parser import DocumentAIParser
from utils.receipt_enhancer import ReceiptEnhancer
from utils.expiry_baselines import get_expiry_baseline
from openai import OpenAI


class AdvancedReceiptScanner:
    """
    Complete receipt scanning system with intelligent mode selection and fallback
    """
    
    def __init__(self):
        """Initialize the scanner with all services"""
        # Try to initialize Document AI (might fail if credentials missing)
        try:
            self.doc_ai = DocumentAIParser()
            self.doc_ai_available = True
            print("✅ Document AI initialized successfully")
        except Exception as e:
            self.doc_ai = None
            self.doc_ai_available = False
            print(f"⚠️  Document AI not available: {str(e)}")
            print("   Will use Vision mode only")
        
        self.enhancer = ReceiptEnhancer()
        
        # Initialize OpenAI for thumbnails
        api_key = os.getenv('OPENAI_API_KEY')
        if api_key:
            self.openai_client = OpenAI(api_key=api_key)
        else:
            self.openai_client = None
            print("⚠️  OPENAI_API_KEY not set, thumbnail generation disabled")
    
    def generate_thumbnail(self, item_name: str) -> Optional[str]:
        """
        Generate 256x256 thumbnail using DALL-E
        """
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
            
            # Download and convert to base64
            import requests
            import base64
            image_response = requests.get(image_url, timeout=10)
            
            if image_response.status_code == 200:
                return base64.b64encode(image_response.content).decode('utf-8')
            
            return None
            
        except Exception as e:
            print(f"   ⚠️  Thumbnail generation failed for {item_name}: {str(e)}")
            return None
    
    def scan_receipt(self, image_bytes: bytes, mime_type: str, 
                    currency: str = "USD", country: str = "USA",
                    use_google_document: bool = None,
                    generate_thumbnails: bool = True) -> Dict:
        """
        Scan receipt with intelligent processing and automatic fallback
        
        Args:
            image_bytes: Receipt image as bytes
            mime_type: Image MIME type
            currency: Currency code (USD, CAD, PKR, EUR, etc.)
            country: Country code
            use_google_document: True=Document AI, False=Vision, None=Auto-detect
            generate_thumbnails: Whether to generate DALL-E thumbnails
        
        Returns:
            dict: Scanning results with enhanced items
        """
        
        try:
            print("\n" + "="*60)
            print(f"🧾 RECEIPT SCANNING START")
            print(f"   Currency: {currency}")
            print(f"   Country: {country}")
            print("="*60 + "\n")
            
            # ============================================
            # INTELLIGENT MODE SELECTION WITH FALLBACK
            # ============================================
            
            # Auto-detect mode if not specified
            if use_google_document is None:
                if self.doc_ai_available:
                    use_google_document = True
                    print("🤖 Auto-selected: Document AI mode (available)")
                else:
                    use_google_document = False
                    print("👁️  Auto-selected: Vision mode (Document AI unavailable)")
            
            # Try primary mode, fallback to secondary if fails
            merchant = 'Unknown'
            receipt_date = None
            raw_items = []
            mode_used = None
            
            # ============================================
            # TRY MODE 1: DOCUMENT AI + ENHANCEMENT
            # ============================================
            if use_google_document and self.doc_ai_available:
                try:
                    print("📄 Attempting: Document AI + OpenAI Enhancement")
                    
                    # CORRECTED: Use parse_receipt (not process_receipt!)
                    print("🔍 Step 1: Extracting text with Google Document AI...")
                    doc_result = self.doc_ai.parse_receipt(image_bytes, mime_type)
                    
                    # Check if we got text
                    if not doc_result or not doc_result.get('full_text'):
                        raise ValueError("Document AI returned no text")
                    
                    full_text = doc_result['full_text']
                    merchant = doc_result.get('merchant', 'Unknown')
                    receipt_date = doc_result.get('date')
                    
                    print(f"   ✅ Extracted {len(full_text)} characters")
                    print(f"   Merchant: {merchant}")
                    
                    # Extract item lines from full text
                    raw_items = doc_result.get('line_items', [])
                    
                    if not raw_items:
                        print("   ⚠️  No line items from Document AI, extracting manually...")
                        raw_items = self._extract_items_from_full_text(full_text)
                    
                    print(f"   ✅ Found {len(raw_items)} item lines")
                    mode_used = 'document_ai'
                    
                except Exception as doc_ai_error:
                    print(f"   ❌ Document AI failed: {str(doc_ai_error)}")
                    print(f"   🔄 FALLING BACK to Vision mode...")
                    
                    # Fallback to vision mode
                    use_google_document = False
            
            # ============================================
            # MODE 2: VISION DIRECT (or fallback)
            # ============================================
            if not use_google_document or not mode_used:
                print("👁️  Using: OpenAI Vision Direct Analysis")
                
                # For vision mode, pass image to enhancer
                # We'll use a special marker for vision analysis
                raw_items = self._extract_items_with_vision(image_bytes, currency, country)
                mode_used = 'vision_direct'
            
            # ============================================
            # STEP 2: Enhance items with OpenAI
            # ============================================
            print(f"\n🤖 Step 2: Enhancing items with GPT-4o...")
            print(f"   Currency: {currency}")
            print(f"   Items to process: {len(raw_items)}")
            
            # Use the receipt enhancer (with proper currency handling!)
            enhanced_result = self.enhancer.enhance_receipt_items(
                raw_items,
                currency=currency,
                country=country
            )
            
            enhanced_items = enhanced_result['items']
            print(f"   ✅ Enhanced {len(enhanced_items)} food items")
            
            # ============================================
            # STEP 3: Calculate expiry dates FROM BASELINE
            # ============================================
            print("\n📅 Step 3: Adding expiry dates from baseline...")
            items_with_expiry = []
            purchase_date = datetime.now()
            
            for item in enhanced_items:
                # Get expiry days (already added by enhancer from baseline!)
                expiry_days = item.get('expiry_days', 30)
                
                # Validate expiry days
                if not isinstance(expiry_days, (int, float)) or expiry_days <= 0:
                    print(f"   ⚠️  Invalid expiry_days {expiry_days} for {item['full_name']}, using 30")
                    expiry_days = 30
                elif expiry_days > 1825:  # Cap at 5 years
                    print(f"   ⚠️  Capping expiry_days {expiry_days} → 730 for {item['full_name']}")
                    expiry_days = 730
                
                expiry_date = purchase_date + timedelta(days=int(expiry_days))
                
                # Validate quantity
                quantity = item.get('quantity', 1)
                if not isinstance(quantity, (int, float)) or quantity <= 0:
                    print(f"   ⚠️  Invalid quantity {quantity} for {item['full_name']}, using 1")
                    quantity = 1
                elif quantity > 1000:  # Sanity check
                    print(f"   ⚠️  Unrealistic quantity {quantity} for {item['full_name']}, capping at 100")
                    quantity = 100
                
                # Format for database
                db_item = {
                    'name': item['full_name'],
                    'quantity': float(quantity),
                    'unit': item.get('unit', 'count'),
                    'price': float(item.get('price', 0)),
                    'expiry_date': expiry_date.strftime('%Y-%m-%d'),
                    'purchase_date': purchase_date.strftime('%Y-%m-%d'),
                    'storage': item.get('storage', 'pantry'),
                    'confidence': item.get('confidence', 'medium'),
                    'raw_receipt_text': item.get('raw_text', ''),
                    'expiry_source': item.get('expiry_source', 'unknown'),
                    'estimation_notes': item.get('estimation_notes', ''),
                    'thumbnail': None  # Will be populated next
                }
                
                items_with_expiry.append(db_item)
            
            print(f"   ✅ All {len(items_with_expiry)} items validated and ready")
            
            # ============================================
            # STEP 4: Generate thumbnails (optional)
            # ============================================
            thumbnails_generated = 0
            
            if generate_thumbnails and self.openai_client:
                print(f"\n🖼️  Step 4: Generating thumbnails...")
                
                # Estimate cost
                estimated_cost = len(items_with_expiry) * 0.02
                print(f"   💰 Estimated cost: ${estimated_cost:.2f}")
                
                if estimated_cost > 1.00:
                    print(f"   ⚠️  HIGH COST WARNING: ${estimated_cost:.2f} for thumbnails!")
                
                def generate_thumbnail_for_item(item):
                    """Helper for concurrent execution"""
                    thumbnail = self.generate_thumbnail(item['name'])
                    return item['name'], thumbnail
                
                # Use ThreadPoolExecutor for speed
                with ThreadPoolExecutor(max_workers=10) as executor:
                    future_to_item = {
                        executor.submit(generate_thumbnail_for_item, item): item 
                        for item in items_with_expiry
                    }
                    
                    for future in as_completed(future_to_item):
                        item = future_to_item[future]
                        try:
                            item_name, thumbnail = future.result()
                            if thumbnail:
                                item['thumbnail'] = thumbnail
                                thumbnails_generated += 1
                            else:
                                # Use placeholder for failed thumbnails
                                item['thumbnail'] = self._get_placeholder_thumbnail()
                                print(f"   ⚠️  Using placeholder for: {item_name}")
                        except Exception as e:
                            item['thumbnail'] = self._get_placeholder_thumbnail()
                            print(f"   ❌ Thumbnail error for {item['name']}: {str(e)}")
                
                print(f"   ✅ Generated {thumbnails_generated}/{len(items_with_expiry)} thumbnails")
            else:
                print("\n   ⏭️  Skipping thumbnails (disabled or no API key)")
                # Set all to placeholder
                for item in items_with_expiry:
                    item['thumbnail'] = self._get_placeholder_thumbnail()
            
            # ============================================
            # STEP 5: Prepare final response
            # ============================================
            result = {
                'success': True,
                'merchant': merchant,
                'receipt_date': receipt_date,
                'currency': currency,
                'country': country,
                'total_items': len(items_with_expiry),
                'items': items_with_expiry,
                'scan_timestamp': datetime.now().isoformat(),
                'mode': mode_used,
                'metadata': {
                    'thumbnails_generated': thumbnails_generated,
                    'thumbnails_total': len(items_with_expiry),
                    'baseline_expiry_count': len([i for i in items_with_expiry if i['expiry_source'] == 'baseline']),
                    'default_expiry_count': len([i for i in items_with_expiry if i['expiry_source'] == 'storage_default']),
                }
            }
            
            print("\n" + "="*60)
            print(f"✅ SCANNING COMPLETE")
            print(f"   Mode used: {mode_used}")
            print(f"   Total items: {result['total_items']}")
            print(f"   Baseline expiry: {result['metadata']['baseline_expiry_count']}")
            print(f"   Default expiry: {result['metadata']['default_expiry_count']}")
            print(f"   Thumbnails: {thumbnails_generated}")
            print("="*60 + "\n")
            
            return result
            
        except Exception as e:
            print(f"\n❌ SCANNING COMPLETELY FAILED: {str(e)}\n")
            import traceback
            traceback.print_exc()
            
            return {
                'success': False,
                'error': str(e),
                'items': [],
                'scan_timestamp': datetime.now().isoformat()
            }
    
    def _extract_items_with_vision(self, image_bytes: bytes, currency: str, country: str) -> List[str]:
        """
        Extract items using GPT-4 Vision directly on the image
        """
        if not self.openai_client:
            raise ValueError("OpenAI client not available for vision mode")
        
        try:
            import base64
            
            # Convert image to base64
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            
            print("   👁️  Analyzing receipt with GPT-4 Vision...")
            
            # Simple prompt for vision to extract just the item lines
            vision_prompt = f"""
Extract ALL food item lines from this receipt.

For each item line, provide:
- The exact text as it appears
- Include product code if visible
- Include price if visible

Return as simple list, one item per line.

Receipt is from {country} with prices in {currency}.

ONLY extract FOOD items (skip diapers, cleaning, household items).
"""
            
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
                max_tokens=2000
            )
            
            # Extract text response
            vision_text = response.choices[0].message.content
            
            # Split into lines
            raw_items = [line.strip() for line in vision_text.split('\n') if line.strip()]
            
            # Remove numbering if present (1. , 2. , etc.)
            import re
            raw_items = [re.sub(r'^\d+\.\s*', '', item) for item in raw_items]
            
            print(f"   ✅ Vision extracted {len(raw_items)} item lines")
            
            return raw_items
            
        except Exception as e:
            print(f"   ❌ Vision extraction failed: {str(e)}")
            raise
    
    def _extract_items_from_full_text(self, full_text: str) -> List[str]:
        """
        Extract item lines from full receipt text
        """
        lines = full_text.split('\n')
        items = []
        
        for line in lines:
            line = line.strip()
            
            # Look for lines with prices (contain numbers and likely currency symbols)
            if line and any(c.isdigit() for c in line):
                # Skip header/footer lines
                lower = line.lower()
                skip_keywords = ['total', 'subtotal', 'tax', 'change', 'tender', 
                               'thank', 'receipt', 'store', 'visit', 'save', 'member']
                
                if not any(kw in lower for kw in skip_keywords):
                    if len(line) > 3:  # Minimum length
                        items.append(line)
        
        return items
    
    def _get_placeholder_thumbnail(self) -> str:
        """
        Return a simple placeholder SVG as base64
        """
        # Simple gray placeholder
        svg = '''<svg width="256" height="256" xmlns="http://www.w3.org/2000/svg">
  <rect width="256" height="256" fill="#f5f5f5"/>
  <text x="50%" y="50%" font-family="Arial" font-size="20" fill="#999" 
        text-anchor="middle" dy=".3em">Food Item</text>
</svg>'''
        import base64
        return base64.b64encode(svg.encode()).decode()
    
    def scan_receipt_from_file(self, file_path: str, currency: str = "USD", 
                               country: str = "USA", use_google_document: bool = None) -> Dict:
        """
        Convenience method: Scan receipt from file path
        """
        with open(file_path, 'rb') as f:
            image_bytes = f.read()
        
        # Detect MIME type
        mime_type = 'image/jpeg'
        if file_path.lower().endswith('.png'):
            mime_type = 'image/png'
        
        return self.scan_receipt(
            image_bytes, 
            mime_type, 
            currency=currency,
            country=country,
            use_google_document=use_google_document
        )


if __name__ == '__main__':
    # Test the scanner
    scanner = AdvancedReceiptScanner()
    
    test_file = 'WhatsApp_Image_20260127_at_5_28_45_PM.jpeg'
    
    if os.path.exists(test_file):
        print("Testing scanner...")
        result = scanner.scan_receipt_from_file(
            test_file,
            currency='USD',
            country='USA',
            use_google_document=None  # Auto-detect
        )
        
        if result['success']:
            print(f"\n✅ Success! Extracted {result['total_items']} items")
            print(f"Mode used: {result['mode']}")
        else:
            print(f"\n❌ Failed: {result['error']}")
    else:
        print(f"Test file not found: {test_file}")