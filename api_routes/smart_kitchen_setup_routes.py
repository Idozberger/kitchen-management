"""
Smart Kitchen Setup Routes
Handles AI-powered kitchen photo scanning during onboarding and re-scans.

Endpoints:
  POST /api/kitchen/setup/scan     → Scan 1-5 kitchen area images, returns detected items
  PUT  /api/kitchen/setup/edit     → Edit a pending scan session's detected items
  POST /api/kitchen/setup/confirm  → Confirm items and populate kitchen inventory
  GET  /api/kitchen/setup/history  → Get scan session history for a kitchen
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from datetime import datetime, timezone
import os
import base64
import json
import re
import uuid
import threading
from openai import OpenAI

from db_connection import get_session
from models import Kitchen, KitchenMember, KitchenItem, KitchenItemsHistory, KitchenSetupSession
from sqlalchemy import func
from utils.gpt_vision import generate_thumbnails_background
from utils.expiry_baselines import get_expiry_baseline
from utils.expiry_calculator import calculate_item_expiry, calculate_items_expiry_batch

smart_kitchen_setup_blueprint = Blueprint('smart_kitchen_setup_blueprint', __name__)

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────
ALLOWED_AREA_LABELS = ['fridge', 'freezer', 'pantry', 'spices', 'miscellaneous']
CONFIDENCE_THRESHOLD = 70  # items >= this are auto_confirmed, below go to needs_review

_openai_client = None


def _get_openai_client():
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))
    return _openai_client


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _get_mime_type(filename: str) -> str:
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpeg'
    return 'image/png' if ext == 'png' else 'image/jpeg'


def _is_host_or_cohost(session, user_id: int, kitchen_id: int) -> bool:
    kitchen = session.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
    if not kitchen:
        return False
    if kitchen.host_id == user_id:
        return True
    cohost = session.query(KitchenMember).filter(
        KitchenMember.kitchen_id == kitchen_id,
        KitchenMember.user_id == user_id,
        KitchenMember.member_type == 'co-host'
    ).first()
    return cohost is not None


def _get_expiry_for_item(item_name: str, storage: str) -> str:
    """
    Single-item expiry lookup — used by /edit and /confirm where items
    arrive one at a time (user corrections). Uses baseline then calculator fallback.
    """
    baseline = get_expiry_baseline(item_name)
    if baseline:
        days = baseline['days']
        if days <= 14:
            return f"{days} days"
        elif days <= 30:
            weeks = round(days / 7)
            return f"{weeks} week{'s' if weeks > 1 else ''}"
        elif days <= 365:
            months = round(days / 30)
            return f"{months} month{'s' if months > 1 else ''}"
        else:
            years = round(days / 365)
            return f"{years} year{'s' if years > 1 else ''}"

    result = calculate_item_expiry(item_name, storage)
    return result if result else "30 days"


def _resolve_expiry_for_all(raw_items: list) -> dict:
    """
    Resolve expiry for all detected items in one shot using the batch function.
    Baseline hits are free; all OpenAI fallbacks are combined into ONE API call.

    Returns dict: {item_name_lowercase -> expiry_string}
    """
    batch_input = [
        {
            'name': item.get('name', '').strip().lower(),
            'storage': item.get('recommended_storage', 'pantry')
        }
        for item in raw_items
        if item.get('name', '').strip()
    ]
    return calculate_items_expiry_batch(batch_input)


# ─────────────────────────────────────────────
# Core AI scanner
# ─────────────────────────────────────────────

def _scan_kitchen_image(image_bytes: bytes, mime_type: str, area_label: str) -> list:
    """
    Send one kitchen area image to GPT-4o Vision.
    Returns a list of raw detected item dicts.
    Expiry is NOT requested from the AI — it is resolved from baselines afterwards.
    """
    client = _get_openai_client()

    area_storage_map = {
        'fridge':        'fridge',
        'freezer':       'freezer',
        'pantry':        'pantry',
        'spices':        'cabinet',
        'miscellaneous': 'pantry',
    }
    expected_storage = area_storage_map.get(area_label, 'pantry')

    image_b64 = base64.b64encode(image_bytes).decode('utf-8')

    prompt = f"""You are an expert kitchen inventory assistant analyzing a photo of someone's {area_label.upper()}.

TASK: Identify every visible food item, ingredient, condiment, spice, or beverage in the image.

For each item produce a JSON entry with these exact fields:

"name"
  - Clear, descriptive, lowercase ingredient name.
  - Include brand if clearly readable (e.g. "heinz tomato ketchup", "quaker rolled oats").
  - Otherwise use a generic name (e.g. "whole milk", "basmati rice", "turmeric powder").
  - Be specific: prefer "chicken breast" over "chicken", "extra virgin olive oil" over "oil".

"quantity"
  - Numeric estimate of amount present.
  - Full sealed container: use typical package size (1L milk carton → 1, 500g pasta box → 500).
  - Partially used container: estimate remaining fraction (half of 1L bottle → 0.5).
  - Loose produce (e.g. 6 apples visible): count them.
  - Truly unclear: use 1.

"unit"
  - MUST be one of: kg | grams | litre | mL | pounds | ounces | count
  - Liquids in bottles/cartons: litre or mL.
  - Solid packaged goods (flour, sugar, pasta): grams or kg.
  - Individual discrete items (eggs, apples, cans of soda): count.

"confidence"
  - Integer 0–100 for how certain you are.
  - 85–100: Clearly visible, label readable, high certainty.
  - 60–84: Visible but label unclear or partially hidden.
  - 0–59: Guessed from shape/colour only, low certainty.

"recommended_storage"
  - Default: "{expected_storage}" (appropriate for this {area_label} area).
  - Override only when clearly wrong (e.g. a frozen item inside the fridge → "freezer").
  - Allowed values: fridge | freezer | pantry | cabinet | counter

"brand"
  - Brand name string if clearly readable (e.g. "Heinz"), otherwise null.

RULES:
✅ Include: food, beverages, condiments, sauces, spices, oils, dairy, produce, grains, canned goods, frozen items.
❌ Exclude: cleaning products, paper towels, foil, plastic bags, non-food items, completely empty shelves.
❌ Do NOT include an expiry_date field — expiry is handled separately.
❌ Do NOT invent items you cannot actually see in the photo.

Return ONLY a valid JSON object (no markdown, no explanation):
{{
  "items": [
    {{
      "name": "whole milk",
      "quantity": 2,
      "unit": "litre",
      "confidence": 95,
      "recommended_storage": "fridge",
      "brand": null
    }},
    {{
      "name": "heinz tomato ketchup",
      "quantity": 500,
      "unit": "mL",
      "confidence": 90,
      "recommended_storage": "fridge",
      "brand": "Heinz"
    }}
  ]
}}"""

    response = client.chat.completions.create(
        model='gpt-4o',
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,{image_b64}",
                        "detail": "high"
                    }
                }
            ]
        }],
        max_tokens=2500,
        temperature=0.1
    )

    content = response.choices[0].message.content.strip()

    # Strip markdown fences if present
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        items = json.loads(content).get('items', [])
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            items = json.loads(match.group()).get('items', [])
        else:
            print(f"[smart_kitchen_setup] Could not parse GPT response for area '{area_label}'")
            items = []

    # Tag each item with its source area
    for item in items:
        item['area'] = area_label

    return items


def _deduplicate_items(all_items: list) -> list:
    """
    Merge items with the same name detected across multiple area photos.
    Keeps the highest-confidence entry and sums quantities.
    """
    merged = {}
    for item in all_items:
        key = item['name'].strip().lower()
        if key not in merged:
            merged[key] = dict(item)
        else:
            if item.get('confidence', 0) > merged[key].get('confidence', 0):
                prev_qty = merged[key].get('quantity', 1)
                merged[key].update(item)
                merged[key]['quantity'] = prev_qty + item.get('quantity', 1)
            else:
                merged[key]['quantity'] = merged[key].get('quantity', 1) + item.get('quantity', 1)
    return list(merged.values())


def _build_entries(raw_items: list, expiry_map: dict) -> list:
    """
    Build standardised item entry dicts using a pre-resolved expiry map.
    expiry_map comes from _resolve_expiry_for_all() — already computed in one batch call.
    """
    entries = []
    for raw in raw_items:
        name = raw.get('name', '').strip().lower()
        if not name:
            continue
        storage = raw.get('recommended_storage', 'pantry').strip().lower()
        if storage not in ['fridge', 'freezer', 'pantry', 'cabinet', 'counter']:
            storage = 'pantry'
        entries.append({
            'temp_id':             uuid.uuid4().hex,
            'name':                name,
            'quantity':            raw.get('quantity', 1),
            'unit':                raw.get('unit', 'count'),
            'confidence':          raw.get('confidence', 0),
            'recommended_storage': storage,
            'expiry_date':         expiry_map.get(name, '30 days'),
            'brand':               raw.get('brand', None),
            'area':                raw.get('area', 'miscellaneous'),
        })
    return entries


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 1 — Scan Images
# POST /api/kitchen/setup/scan
# ─────────────────────────────────────────────────────────────────────────────
@smart_kitchen_setup_blueprint.route('/api/kitchen/setup/scan', methods=['POST'])
@jwt_required()
def scan_kitchen_setup():
    """
    Smart Kitchen Setup - Scan Images

    Accepts 1-5 kitchen area photos (multipart/form-data).
    Detects food items via GPT-4o Vision, resolves expiry from existing baselines,
    and saves a pending scan session.

    Form fields:
      kitchen_id (required)
      Image field naming - use ONE of these approaches:
        Option A (named areas): image_fridge, image_freezer, image_pantry, image_spices, image_miscellaneous
        Option B (indexed):     image_0 .. image_4  (+ optional area_0 .. area_4 for labels)
        Option C (single):      image               (+ optional 'area' field)

    Returns:
      session_id, auto_confirmed[], needs_review[]
    """
    user_identity = get_jwt()
    user_id = int(user_identity['user_id'])

    # ── Validate kitchen_id ────────────────────────────────
    try:
        kitchen_id = int(request.form.get('kitchen_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'kitchen_id is required (as a form field)'}), 400

    db = get_session()
    try:
        if not _is_host_or_cohost(db, user_id, kitchen_id):
            return jsonify({'error': 'Only the host or co-host can run the kitchen setup scan'}), 403
    finally:
        db.close()

    # ── Collect uploaded images ────────────────────────────
    image_entries = []  # (area_label, image_bytes, mime_type)

    # Option A: named area fields
    for area in ALLOWED_AREA_LABELS:
        f = request.files.get(f'image_{area}')
        if f and f.filename:
            image_entries.append((area, f.read(), _get_mime_type(f.filename)))

    # Option B: indexed fields
    if not image_entries:
        for i in range(5):
            f = request.files.get(f'image_{i}')
            if f and f.filename:
                default_area = ALLOWED_AREA_LABELS[i] if i < len(ALLOWED_AREA_LABELS) else 'miscellaneous'
                area = request.form.get(f'area_{i}', default_area).lower().strip()
                if area not in ALLOWED_AREA_LABELS:
                    area = 'miscellaneous'
                image_entries.append((area, f.read(), _get_mime_type(f.filename)))

    # Option C: single image
    if not image_entries:
        f = request.files.get('image')
        if f and f.filename:
            area = request.form.get('area', 'miscellaneous').lower().strip()
            if area not in ALLOWED_AREA_LABELS:
                area = 'miscellaneous'
            image_entries.append((area, f.read(), _get_mime_type(f.filename)))

    if not image_entries:
        return jsonify({
            'error': 'No images provided. Use image_fridge / image_freezer / image_pantry / '
                     'image_spices / image_miscellaneous  OR  image_0..image_4  OR  a single "image" field.',
        }), 400

    if len(image_entries) > 5:
        return jsonify({'error': 'Maximum 5 images allowed per scan'}), 400

    # ── Run AI scan on each image ──────────────────────────
    all_raw = []
    areas_scanned = []

    for area_label, image_bytes, mime_type in image_entries:
        print(f"[smart_kitchen_setup] Scanning area: {area_label}")
        try:
            detected = _scan_kitchen_image(image_bytes, mime_type, area_label)
            all_raw.extend(detected)
            areas_scanned.append(area_label)
            print(f"[smart_kitchen_setup]   → {len(detected)} items in {area_label}")
        except Exception as e:
            print(f"[smart_kitchen_setup] Error scanning {area_label}: {e}")
            # Continue with remaining images

    # ── Deduplicate across areas ──────────────────────────
    all_raw = _deduplicate_items(all_raw)

    # ── Resolve ALL expiry dates in ONE batch call ─────────
    # Baseline hits are free; all OpenAI fallbacks combined into a single API call
    expiry_map = _resolve_expiry_for_all(all_raw)

    # ── Build entries and split by confidence ──────────────
    all_entries = _build_entries(all_raw, expiry_map)

    auto_confirmed = []
    needs_review   = []

    for entry in all_entries:
        if entry['confidence'] >= CONFIDENCE_THRESHOLD:
            auto_confirmed.append(entry)
        else:
            needs_review.append(entry)

    # ── Persist scan session ───────────────────────────────
    db = get_session()
    try:
        scan_session = KitchenSetupSession(
            session_id=uuid.uuid4().hex,
            kitchen_id=kitchen_id,
            scanned_by=user_id,
            areas_scanned=areas_scanned,
            raw_detected=auto_confirmed + needs_review,
            status='pending',
            total_detected=len(auto_confirmed) + len(needs_review),
            scanned_at=datetime.now(timezone.utc)
        )
        db.add(scan_session)
        db.commit()
        session_id = scan_session.session_id
    except Exception as e:
        db.rollback()
        return jsonify({'error': f'Failed to save scan session: {str(e)}'}), 500
    finally:
        db.close()

    return jsonify({
        'success':              True,
        'session_id':           session_id,
        'kitchen_id':           kitchen_id,
        'areas_scanned':        areas_scanned,
        'total_detected':       len(auto_confirmed) + len(needs_review),
        'confidence_threshold': CONFIDENCE_THRESHOLD,
        'auto_confirmed':       auto_confirmed,
        'needs_review':         needs_review,
        'auto_confirmed_count': len(auto_confirmed),
        'needs_review_count':   len(needs_review),
        'message': (
            f"Scanned {len(areas_scanned)} area(s). "
            f"{len(auto_confirmed)} items ready, {len(needs_review)} need review."
        )
    }), 200


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 2 — Edit Pending Session
# PUT /api/kitchen/setup/edit
# ─────────────────────────────────────────────────────────────────────────────
@smart_kitchen_setup_blueprint.route('/api/kitchen/setup/edit', methods=['PUT'])
@jwt_required()
def edit_kitchen_setup():
    """
    Smart Kitchen Setup - Edit Detected Items

    After scanning, the user reviews the AI-detected list and may:
      - Edit name, quantity, unit, recommended_storage, expiry_date
      - Remove items (just don't include them)
      - Add new items manually

    Sending the updated list here overwrites the session's item list.
    Expiry is auto-resolved from baselines for any item that has no expiry_date.

    Body (JSON):
    {
      "session_id": "<from /scan response>",
      "items": [
        {
          "name": "whole milk",
          "quantity": 2,
          "unit": "litre",
          "recommended_storage": "fridge",
          "expiry_date": "7 days"    // optional - auto-calculated if blank
        }
      ]
    }
    """
    user_identity = get_jwt()
    user_id = int(user_identity['user_id'])

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    session_id = data.get('session_id', '').strip()
    items       = data.get('items', [])

    if not session_id:
        return jsonify({'error': 'session_id is required'}), 400
    if not isinstance(items, list):
        return jsonify({'error': 'items must be a list'}), 400

    db = get_session()
    try:
        scan_session = db.query(KitchenSetupSession).filter(
            KitchenSetupSession.session_id == session_id
        ).first()

        if not scan_session:
            return jsonify({'error': 'Scan session not found'}), 404
        if scan_session.status == 'confirmed':
            return jsonify({'error': 'This session is already confirmed and cannot be edited'}), 409
        if not _is_host_or_cohost(db, user_id, scan_session.kitchen_id):
            return jsonify({'error': 'Only the host or co-host can edit this scan session'}), 403

        cleaned_items = []
        for raw in items:
            name = str(raw.get('name', '')).strip().lower()
            if not name:
                continue

            storage = str(raw.get('recommended_storage', 'pantry')).strip().lower()
            if storage not in ['fridge', 'freezer', 'pantry', 'cabinet', 'counter']:
                storage = 'pantry'

            try:
                quantity = float(raw.get('quantity', 1))
            except (ValueError, TypeError):
                quantity = 1.0

            unit = str(raw.get('unit', 'count')).strip().lower() or 'count'

            # Respect user-provided expiry; fill in from baseline if missing
            expiry_date = raw.get('expiry_date', None)
            if not expiry_date:
                expiry_date = _get_expiry_for_item(name, storage)

            cleaned_items.append({
                'temp_id':              raw.get('temp_id', uuid.uuid4().hex),
                'name':                 name,
                'quantity':             quantity,
                'unit':                 unit,
                'recommended_storage':  storage,
                'expiry_date':          expiry_date,
                'brand':                raw.get('brand', None),
                'area':                 raw.get('area', 'miscellaneous'),
                'confidence':           raw.get('confidence', 100),
            })

        scan_session.raw_detected = cleaned_items
        db.commit()

        return jsonify({
            'success':    True,
            'session_id': session_id,
            'item_count': len(cleaned_items),
            'items':      cleaned_items,
            'message':    f'{len(cleaned_items)} items saved. Call /confirm when ready to add to inventory.'
        }), 200

    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 3 — Confirm & Populate Inventory
# POST /api/kitchen/setup/confirm
# ─────────────────────────────────────────────────────────────────────────────
@smart_kitchen_setup_blueprint.route('/api/kitchen/setup/confirm', methods=['POST'])
@jwt_required()
def confirm_kitchen_setup():
    """
    Smart Kitchen Setup - Confirm and Populate Inventory

    Finalises the setup by adding confirmed items to the kitchen inventory.
    Uses the session's current item list (updated by /edit if called).
    Optionally accepts an inline 'items' override in the request body.

    Body (JSON):
    {
      "session_id": "<from /scan response>",
      "items": [...]    // optional override; omit to use the session's saved list
    }

    Items are saved to DB immediately and the API returns fast.
    Thumbnails are generated in the background (DALL-E) without blocking the response.
    Expiry is always resolved from baselines. Only host or co-host can call this.
    """
    user_identity = get_jwt()
    user_id = int(user_identity['user_id'])

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    session_id     = data.get('session_id', '').strip()
    override_items = data.get('items', None)

    if not session_id:
        return jsonify({'error': 'session_id is required'}), 400

    db = get_session()
    try:
        scan_session = db.query(KitchenSetupSession).filter(
            KitchenSetupSession.session_id == session_id
        ).first()

        if not scan_session:
            return jsonify({'error': 'Scan session not found'}), 404
        if scan_session.status == 'confirmed':
            return jsonify({'error': 'This session has already been confirmed'}), 409

        kitchen_id = scan_session.kitchen_id

        if not _is_host_or_cohost(db, user_id, kitchen_id):
            return jsonify({'error': 'Only the host or co-host can confirm the kitchen setup'}), 403

        # Items to add: inline override takes priority, else session list
        items_to_add = (
            override_items if (override_items is not None and isinstance(override_items, list))
            else (scan_session.raw_detected or [])
        )

        if not items_to_add:
            return jsonify({'error': 'No items to confirm. Scan again or provide items in the request body.'}), 400

        added_items        = []
        updated_items      = []
        errors             = []
        new_item_ids       = []   # item_ids of newly inserted items — for background thumbnail job

        for raw in items_to_add:
            item_name = str(raw.get('name', '')).strip().lower()
            if not item_name:
                continue

            unit = str(raw.get('unit', 'count')).strip().lower() or 'count'

            try:
                quantity = float(raw.get('quantity', 1))
            except (ValueError, TypeError):
                quantity = 1.0

            group = str(raw.get('recommended_storage', 'pantry')).strip().lower()
            if group not in ['fridge', 'freezer', 'pantry', 'cabinet', 'counter']:
                group = 'pantry'

            # Resolve expiry from baseline (respect user-provided value if present)
            expiry_date = raw.get('expiry_date', None)
            if not expiry_date:
                expiry_date = _get_expiry_for_item(item_name, group)

            try:
                existing = db.query(KitchenItem).filter(
                    KitchenItem.kitchen_id == kitchen_id,
                    func.lower(KitchenItem.name) == item_name,
                    func.lower(KitchenItem.unit) == unit,
                    func.lower(KitchenItem.group) == group
                ).first()

                if existing:
                    # Item already in inventory — just update quantity & expiry
                    existing.quantity   += quantity
                    existing.expiry_date = expiry_date
                    existing.added_at    = datetime.now(timezone.utc)
                    updated_items.append(item_name)
                else:
                    # New item — save immediately with thumbnail=None
                    # Thumbnail will be filled in by the background thread
                    new_item_id = uuid.uuid4().hex
                    db.add(KitchenItem(
                        kitchen_id=kitchen_id,
                        item_id=new_item_id,
                        name=item_name,
                        quantity=quantity,
                        unit=unit,
                        group=group,
                        thumbnail=None,          # Background thread sets this
                        expiry_date=expiry_date,
                        added_at=datetime.now(timezone.utc)
                    ))
                    added_items.append(item_name)
                    new_item_ids.append(new_item_id)

            except Exception as item_err:
                errors.append({'item': item_name, 'error': str(item_err)})
                print(f"[smart_kitchen_setup] Error adding '{item_name}': {item_err}")

        # Update kitchen item name history
        all_names = [str(i.get('name', '')).strip().lower() for i in items_to_add if i.get('name')]
        if all_names:
            history = db.query(KitchenItemsHistory).filter(
                KitchenItemsHistory.kitchen_id == kitchen_id
            ).first()
            if history:
                existing_set = set(history.item_names or [])
                existing_set.update(all_names)
                history.item_names = list(existing_set)
            else:
                db.add(KitchenItemsHistory(kitchen_id=kitchen_id, item_names=all_names))

        # Mark session confirmed
        scan_session.status          = 'confirmed'
        scan_session.confirmed_items = [{'name': n} for n in added_items + updated_items]
        scan_session.total_confirmed = len(added_items) + len(updated_items)
        scan_session.confirmed_at    = datetime.now(timezone.utc)

        # ── Commit everything before returning ─────────────
        db.commit()

        # ── Fire background thumbnail generation ───────────
        # Only for newly added items (not updated ones which may already have thumbnails)
        if new_item_ids:
            t = threading.Thread(
                target=generate_thumbnails_background,
                args=(new_item_ids,),
                daemon=True
            )
            t.start()

        return jsonify({
            'success':            True,
            'session_id':         session_id,
            'kitchen_id':         kitchen_id,
            'added_count':        len(added_items),
            'updated_count':      len(updated_items),
            'added_items':        added_items,
            'updated_items':      updated_items,
            'errors':             errors,
            'thumbnails_status':  'generating_in_background' if new_item_ids else 'not_needed',
            'message': (
                f"Kitchen inventory populated! "
                f"{len(added_items)} items added, {len(updated_items)} updated. "
                f"Thumbnails are being generated in the background."
            )
        }), 200

    except Exception as e:
        db.rollback()
        print(f"[smart_kitchen_setup] Confirm error: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT 4 — Scan Session History
# GET /api/kitchen/setup/history?kitchen_id=1&page=0
# ─────────────────────────────────────────────────────────────────────────────
@smart_kitchen_setup_blueprint.route('/api/kitchen/setup/history', methods=['GET'])
@jwt_required()
def kitchen_setup_history():
    """
    Smart Kitchen Setup - Scan Session History

    Returns paginated list of all setup scan sessions for a kitchen.
    Supports the 'Re-scan My Kitchen' feature in Profile Settings.

    Query params:
      kitchen_id  (required)
      page        (optional, default 0, page size = 10)
    """
    user_identity = get_jwt()
    user_id = int(user_identity['user_id'])

    try:
        kitchen_id = int(request.args.get('kitchen_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'kitchen_id is required as a query parameter'}), 400

    try:
        page = max(0, int(request.args.get('page', 0)))
    except (ValueError, TypeError):
        page = 0

    page_size = 10

    db = get_session()
    try:
        kitchen = db.query(Kitchen).filter(Kitchen.id == kitchen_id).first()
        if not kitchen:
            return jsonify({'error': 'Kitchen not found'}), 404

        is_member = (
            kitchen.host_id == user_id or
            db.query(KitchenMember).filter(
                KitchenMember.kitchen_id == kitchen_id,
                KitchenMember.user_id == user_id
            ).first() is not None
        )
        if not is_member:
            return jsonify({'error': 'You are not a member of this kitchen'}), 403

        sessions = (
            db.query(KitchenSetupSession)
            .filter(KitchenSetupSession.kitchen_id == kitchen_id)
            .order_by(KitchenSetupSession.scanned_at.desc())
            .offset(page * page_size)
            .limit(page_size)
            .all()
        )

        total = (
            db.query(KitchenSetupSession)
            .filter(KitchenSetupSession.kitchen_id == kitchen_id)
            .count()
        )

        history = [{
            'session_id':      s.session_id,
            'status':          s.status,
            'areas_scanned':   s.areas_scanned,
            'total_detected':  s.total_detected,
            'total_confirmed': s.total_confirmed,
            'scanned_at':      s.scanned_at.isoformat() if s.scanned_at else None,
            'confirmed_at':    s.confirmed_at.isoformat() if s.confirmed_at else None,
        } for s in sessions]

        return jsonify({
            'success':    True,
            'kitchen_id': kitchen_id,
            'page':       page,
            'page_size':  page_size,
            'total':      total,
            'count':      len(history),
            'sessions':   history
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()