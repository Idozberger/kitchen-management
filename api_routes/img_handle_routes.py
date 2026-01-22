from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from flask import Blueprint, request, jsonify, url_for
import os
from werkzeug.utils import secure_filename
import uuid
import utils.gpt_vision
from random import randint
import json
from datetime import datetime, timezone

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
    """Scan receipt using OpenAI Vision API"""
    print("Request incoming....")

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

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4().hex}_{filename}"
        print("Unique filename: ", unique_filename)
        file_path = os.path.join(UPLOAD_FOLDER, unique_filename)
        file.save(file_path)

        res = utils.gpt_vision.analyze_image_with_openai(file_path)
        os.remove(file_path)
        
        try:
            print("res", type(res), res)
            parsed_json = json.loads(res)
        except Exception as e:
            print("error when converting response to json: ", e)
            return jsonify({'error': "Couldn't Scan anything in the given image."}), 400

        items_list = parsed_json.get('items', [])
        store_scan_history(user_id, items_list)

        return jsonify({
            'message': 'File successfully uploaded',
            'res': parsed_json
        }), 200
    else:
        return jsonify({
            'error': 'File type not allowed. Only images (png, jpg, jpeg) are accepted.'
        }), 400


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