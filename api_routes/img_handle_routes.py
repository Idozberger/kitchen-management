"""
UPDATED Image Handling Routes
Now uses Google Document AI + OpenAI for SUPERIOR receipt scanning
"""

from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from flask import Blueprint, request, jsonify, url_for
import os
from werkzeug.utils import secure_filename
import uuid
import json
from datetime import datetime, timezone

# NEW: Advanced scanning imports
from utils.advanced_receipt_scanner import AdvancedReceiptScanner

# PostgreSQL imports
from db_connection import get_session, engine
from models import Kitchen, KitchenMember, ScanHistory
from sqlalchemy import text

# Create a Blueprint object
img_api_blueprint = Blueprint('img_api_blueprint', __name__)

# Define a folder to store the uploaded files
UPLOAD_FOLDER = 'temp_files'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Limit the size of the uploaded file to 10MB
MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB

# Initialize the advanced scanner (singleton)
advanced_scanner = None


def get_advanced_scanner():
    """Get or create advanced scanner instance"""
    global advanced_scanner
    if advanced_scanner is None:
        advanced_scanner = AdvancedReceiptScanner()
    return advanced_scanner


def allowed_file(filename):
    """Check if the file extension is allowed"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@img_api_blueprint.route('/api/test', methods=['POST'])
def test_r():
    """Test endpoint"""
    return "API url working"


def user_is_host_or_cohost(user_id):
    """
    Checks if user is host or co-host in any kitchen.
    Returns True if user is host or co-host, False otherwise.
    """
    session = get_session()
    try:
        user_id = int(user_id)
        
        # Check for host
        is_host = session.query(Kitchen).filter(Kitchen.host_id == user_id).first()
        if is_host:
            return True
        
        # Check for co-host
        is_cohost = session.query(KitchenMember).filter(
            KitchenMember.user_id == user_id,
            KitchenMember.member_type == 'co-host'
        ).first()
        if is_cohost:
            return True
        
        return False
    finally:
        session.close()


def store_scan_history(user_id, scanned_items):
    """
    Store the scanned items list in the scan_history table for the user.
    - user_id: int
    - scanned_items: list of dicts (parsed item details)
    """
    session = get_session()
    try:
        user_id = int(user_id)
        
        scan_history = ScanHistory(
            user_id=user_id,
            scanned_at=datetime.now(timezone.utc),
            items=scanned_items
        )
        
        session.add(scan_history)
        session.commit()
    finally:
        session.close()


@img_api_blueprint.route('/api/scan_recipt', methods=['POST'])
@jwt_required()
def scan_recipt_r():
    """
    NEW ADVANCED RECEIPT SCANNING with TWO MODES
    Uses Google Document AI + OpenAI GPT-4 OR OpenAI Vision directly
    
    Request Parameters (form-data):
    - file: Receipt image (required)
    - currency: Currency code (optional, default: USD)
    - country: Country code (optional, default: USA)  
    - use_google_document: "true" or "false" (optional, default: "true")
      * "true" = Google Document AI + OpenAI Enhancement
      * "false" = OpenAI Vision Direct Analysis
    
    Returns:
    {
        "success": true,
        "mode": "Google Document AI" or "OpenAI Vision",
        "merchant": "Store Name",
        "total_items": 10,
        "items": [...]
    }
    """
    print("🔍 Advanced Receipt Scanning Request Incoming...")

    user_identity = get_jwt()
    user_id = user_identity['user_id']

    # Check if user is host or co-host
    if not user_is_host_or_cohost(user_id):
        return jsonify({
            'error': 'You are not authorized to scan receipts. Only hosts or co-hosts can perform this action.'
        }), 403

    if request.content_length > MAX_CONTENT_LENGTH:
        return jsonify({'error': 'File size exceeds the 10MB limit'}), 413

    if 'file' not in request.files:
        return jsonify({'error': 'No file part in the request'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if not (file and allowed_file(file.filename)):
        return jsonify({
            'error': 'File type not allowed. Only images (png, jpg, jpeg) are accepted.'
        }), 400

    try:
        # Get optional parameters
        currency = request.form.get('currency', 'USD').upper()
        country = request.form.get('country', 'USA').upper()
        use_google_document = request.form.get('use_google_document', 'true').lower() == 'true'
        
        print(f"   Currency: {currency}, Country: {country}")
        print(f"   Mode: {'Google Document AI' if use_google_document else 'OpenAI Vision'}")
        
        # Save file temporarily
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        file.save(file_path)
        
        print(f"   Saved to: {file_path}")

        # Read image bytes
        with open(file_path, 'rb') as f:
            image_bytes = f.read()
        
        # Detect MIME type
        mime_type = 'image/jpeg'
        if filename.lower().endswith('.png'):
            mime_type = 'image/png'
        
        # NEW: Use advanced scanner with mode selection
        scanner = get_advanced_scanner()
        result = scanner.scan_receipt(
            image_bytes=image_bytes,
            mime_type=mime_type,
            currency=currency,
            country=country,
            use_google_document=use_google_document
        )
        
        # Clean up temp file
        os.remove(file_path)
        print(f"   Cleaned up: {file_path}")
        
        if not result['success']:
            return jsonify({
                'error': f"Scanning failed: {result.get('error', 'Unknown error')}"
            }), 400
        
        # Store in scan history
        items_list = result['items']
        store_scan_history(user_id, items_list)
        
        print(f"✅ Successfully scanned {result['total_items']} items")
        
        return jsonify({
            'message': 'Receipt successfully scanned!',
            'success': True,
            'mode': 'Google Document AI' if use_google_document else 'OpenAI Vision',
            'merchant': result.get('merchant', 'Unknown'),
            'currency': currency,
            'total_items': result['total_items'],
            'items': items_list,
            'metadata': result.get('metadata', {}),
            'scan_timestamp': result.get('scan_timestamp')
        }), 200
        
    except Exception as e:
        print(f"❌ Scanning error: {str(e)}")
        # Clean up file if it exists
        if 'file_path' in locals() and os.path.exists(file_path):
            os.remove(file_path)
        
        return jsonify({
            'error': f'Error scanning receipt: {str(e)}',
            'success': False
        }), 500


@img_api_blueprint.route('/api/get_scan_history', methods=['GET'])
@jwt_required()
def get_scan_history():
    """Get scan history for the user with pagination"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_id = int(user_identity['user_id'])

        # Pagination
        try:
            page = int(request.args.get('page', 0))
            if page < 0:
                page = 0
        except ValueError:
            page = 0

        page_size = 10

        # Query with pagination
        history_query = session.query(ScanHistory).filter(
            ScanHistory.user_id == user_id
        ).order_by(ScanHistory.scanned_at.desc()).offset(page * page_size).limit(page_size)
        
        history_records = history_query.all()

        # Debug logging
        print(f"User ID from JWT: {user_id} (type: {type(user_id)})")
        print(f"Found {len(history_records)} scan history records")

        # Convert to dict
        history = []
        for record in history_records:
            history.append({
                'user_id': str(record.user_id),
                'scanned_at': record.scanned_at.isoformat() if record.scanned_at else None,
                'items': record.items
            })

        return jsonify({
            'page': page,
            'page_size': page_size,
            'count': len(history),
            'history': history
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@img_api_blueprint.route('/api/admin/database_stats', methods=['GET'])
@jwt_required()
def get_database_stats():
    """Check database size and table stats (PostgreSQL version)"""
    session = get_session()
    try:
        # Get database size
        size_query = text("""
            SELECT pg_size_pretty(pg_database_size(current_database())) as size,
                   pg_database_size(current_database()) as size_bytes
        """)
        size_result = session.execute(size_query).fetchone()
        
        # Get table stats
        tables_query = text("""
            SELECT 
                schemaname,
                tablename,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size,
                pg_total_relation_size(schemaname||'.'||tablename) AS size_bytes,
                n_live_tup as row_count
            FROM pg_stat_user_tables
            ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
        """)
        tables_result = session.execute(tables_query).fetchall()
        
        # Format results
        tables = {}
        for row in tables_result:
            tables[row.tablename] = {
                'count': row.row_count,
                'size_bytes': row.size_bytes,
                'size_mb': round(row.size_bytes / (1024 * 1024), 2),
                'size_pretty': row.size
            }
        
        total_size_bytes = size_result.size_bytes if size_result else 0
        total_size_mb = round(total_size_bytes / (1024 * 1024), 2)
        
        return jsonify({
            'status': 'success',
            'database': 'kitchen_guardian_db',
            'database_type': 'PostgreSQL',
            'total_size_mb': total_size_mb,
            'total_size_pretty': size_result.size if size_result else '0 bytes',
            'tables': tables
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500
    finally:
        session.close()


@img_api_blueprint.route('/api/admin/reset_database', methods=['POST'])
@jwt_required()
def reset_database():
    """
    DANGER: Delete ALL data from ALL tables!
    For development use only.
    """
    session = get_session()
    try:
        # Get all table names
        tables_query = text("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public'
        """)
        tables_result = session.execute(tables_query).fetchall()
        
        deleted_stats = {}
        total_deleted = 0
        
        # Delete all data from each table
        for row in tables_result:
            table_name = row.tablename
            
            # Get count before deletion
            count_query = text(f"SELECT COUNT(*) FROM {table_name}")
            count_before = session.execute(count_query).scalar()
            
            # Delete all rows
            delete_query = text(f"DELETE FROM {table_name}")
            session.execute(delete_query)
            
            deleted_stats[table_name] = {
                'rows_deleted': count_before,
                'count_before': count_before
            }
            total_deleted += count_before
        
        # Commit all deletions
        session.commit()
        
        return jsonify({
            'status': 'success',
            'message': '🗑️ Database completely wiped! All data deleted.',
            'total_rows_deleted': total_deleted,
            'tables_cleared': deleted_stats
        }), 200
        
    except Exception as e:
        session.rollback()
        return jsonify({
            'status': 'error',
            'error': str(e),
            'message': 'Failed to reset database'
        }), 500
    finally:
        session.close()