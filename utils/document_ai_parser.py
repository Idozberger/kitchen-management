"""
Google Document AI Integration for Receipt OCR
Uses Google Cloud Document AI for superior receipt text extraction
"""

from google.cloud import documentai_v1 as documentai
from google.oauth2 import service_account
import json
import os
import re  # For regex pattern matching


class DocumentAIParser:
    """
    Google Document AI client for receipt parsing
    """
    
    def __init__(self):
        """
        Initialize Document AI client with credentials
        """
        # Load credentials from environment or file
        creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'google_creds.json')
        
        if os.path.exists(creds_path):
            credentials = service_account.Credentials.from_service_account_file(creds_path)
            self.client = documentai.DocumentProcessorServiceClient(credentials=credentials)
        else:
            # If credentials are in env variable as JSON string
            creds_json = os.getenv('GOOGLE_CREDS_JSON')
            if creds_json:
                creds_dict = json.loads(creds_json)
                credentials = service_account.Credentials.from_service_account_info(creds_dict)
                self.client = documentai.DocumentProcessorServiceClient(credentials=credentials)
            else:
                raise ValueError("Google credentials not found. Set GOOGLE_APPLICATION_CREDENTIALS or GOOGLE_CREDS_JSON")
        
        # Processor ID from client
        self.processor_name = os.getenv(
            'DOCUMENT_AI_PROCESSOR',
            'projects/886872470388/locations/us/processors/df617e61a2b86572'
        )
    
    def parse_receipt(self, image_bytes, mime_type='image/jpeg'):
        """
        Parse receipt image using Google Document AI
        
        Args:
            image_bytes: Image file bytes
            mime_type: MIME type of the image (image/jpeg, image/png)
        
        Returns:
            dict: Parsed receipt data with text and entities
        """
        try:
            # Create the document
            raw_document = documentai.RawDocument(
                content=image_bytes,
                mime_type=mime_type
            )
            
            # Configure the process request
            request = documentai.ProcessRequest(
                name=self.processor_name,
                raw_document=raw_document
            )
            
            # Process the document
            result = self.client.process_document(request=request)
            document = result.document
            
            # Extract text and structured data
            parsed_data = {
                'full_text': document.text,
                'entities': [],
                'line_items': [],
                'total': None,
                'date': None,
                'merchant': None
            }
            
            # Extract entities (Document AI automatically detects these)
            for entity in document.entities:
                entity_dict = {
                    'type': entity.type_,
                    'mention_text': entity.mention_text,
                    'confidence': entity.confidence
                }
                
                # Categorize important entities
                if entity.type_ == 'line_item':
                    parsed_data['line_items'].append(entity.mention_text)
                elif entity.type_ == 'total_amount' or entity.type_ == 'total':
                    parsed_data['total'] = entity.mention_text
                elif entity.type_ == 'receipt_date' or entity.type_ == 'date':
                    parsed_data['date'] = entity.mention_text
                elif entity.type_ == 'supplier_name' or entity.type_ == 'merchant':
                    parsed_data['merchant'] = entity.mention_text
                
                parsed_data['entities'].append(entity_dict)
            
            # If no structured entities found, parse text manually
            if not parsed_data['line_items']:
                parsed_data['line_items'] = self._extract_line_items_from_text(document.text)
            
            return parsed_data
            
        except Exception as e:
            print(f"Document AI error: {str(e)}")
            raise
    
    def _extract_line_items_from_text(self, text):
        """
        Enhanced method to extract line items from raw text
        Preserves COMPLETE lines including all product information
        """
        lines = text.split('\n')
        line_items = []
        
        # Keywords to skip (headers, footers, etc.)
        skip_keywords = ['total', 'subtotal', 'tax', 'change', 'tender', 'thank', 
                        'receipt', 'cashier', 'welcome', 'transaction', 'debit', 
                        'credit', 'balance', 'approval', 'trans.', 'type:', 'visa',
                        'mastercard', 'g=gst', 'p=pst', 'card']
        
        # Category headers to skip
        category_pattern = re.compile(r'^\d{2}-[A-Z]+\s*$')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Skip empty lines or very short lines
            if not line or len(line) < 3:
                i += 1
                continue
            
            # Skip headers/footers
            if any(keyword in line.lower() for keyword in skip_keywords):
                i += 1
                continue
            
            # Skip category headers (e.g., "21-GROCERY", "22-DAIRY")
            if category_pattern.match(line):
                i += 1
                continue
            
            # Check if line has a product code at start (10+ digits)
            has_product_code = bool(re.match(r'^\d{10,}\s+', line))
            
            # Check if line has a price (X.XX format at end or standalone)
            has_price = bool(re.search(r'\d+\.\d{2}\s*$', line))
            
            if has_product_code:
                # This is a product line - keep it complete
                # Sometimes price is on the same line, sometimes next line
                
                if has_price:
                    # Complete item on one line
                    line_items.append(line)
                else:
                    # Price might be on next line - check
                    next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                    
                    # Check if next line is just a price or has additional info
                    if re.match(r'^\d+\.\d{2}\s*$', next_line):
                        # Next line is just the price - combine them
                        line_items.append(f"{line} {next_line}")
                        i += 1  # Skip the price line since we combined it
                    elif next_line and len(next_line) < 20 and not re.match(r'^\d{10,}', next_line):
                        # Next line might be continuation (like "MRJ" or unit)
                        # Check if there's a price after that
                        next_next_line = lines[i + 2].strip() if i + 2 < len(lines) else ""
                        if re.match(r'^\d+\.\d{2}\s*$', next_next_line):
                            # Price is two lines down
                            line_items.append(f"{line} {next_line} {next_next_line}")
                            i += 2  # Skip both continuation lines
                        else:
                            # Just add what we have
                            line_items.append(line)
                    else:
                        # Just add the line as is
                        line_items.append(line)
            
            elif has_price and not has_product_code:
                # Line has price but no product code
                # Might be continuation of previous item or standalone
                # Only add if it looks like a complete item (has text before price)
                text_before_price = re.sub(r'\d+\.\d{2}\s*$', '', line).strip()
                if text_before_price and len(text_before_price) > 3:
                    line_items.append(line)
            
            i += 1
        
        return line_items


def test_document_ai():
    """
    Test function for Document AI
    """
    parser = DocumentAIParser()
    
    # Test with a sample receipt
    with open('test_receipt.jpg', 'rb') as f:
        image_bytes = f.read()
    
    result = parser.parse_receipt(image_bytes)
    print("Parsed Receipt:")
    print(f"Merchant: {result['merchant']}")
    print(f"Date: {result['date']}")
    print(f"Total: {result['total']}")
    print(f"\nLine Items ({len(result['line_items'])}):")
    for item in result['line_items'][:10]:
        print(f"  - {item}")


if __name__ == '__main__':
    test_document_ai()