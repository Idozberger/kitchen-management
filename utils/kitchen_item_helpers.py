"""
utils/kitchen_item_helpers.py

Shared helper for inserting items into the kitchen inventory.
Used by:
  - kitchen_management_routes.py  (/api/kitchen/add_items)
  - item_request_routes.py        (/api/kitchen/respond_to_item_request)
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import func

from models import KitchenItem
from utils.expiry_calculator import calculate_item_expiry


def _insert_item_into_kitchen(session, kitchen_id: int, new_item: dict) -> tuple:
    """
    Core item-insertion logic.

    Merges into an existing inventory row (quantity +=) when an item with the
    same name/unit/group already exists in the kitchen. Otherwise creates a
    new KitchenItem row.

    Does NOT commit — the caller is responsible for session.commit().

    Args:
        session:    Active SQLAlchemy session.
        kitchen_id: ID of the kitchen to insert into.
        new_item:   Dict with keys: name (required), quantity, unit, group,
                    expiry_date, thumbnail.

    Returns:
        (item_id: str, needs_thumbnail: bool)
        - item_id:         UUID hex of the affected KitchenItem row.
        - needs_thumbnail: True if a new row was created without a thumbnail
                           (caller should queue background DALL-E generation).

    Raises:
        ValueError: if quantity value cannot be converted to float.
    """
    new_item_name = new_item['name'].strip().lower()

    unit_value = new_item.get('unit')
    new_item_unit = (
        unit_value.strip().lower()
        if (unit_value and isinstance(unit_value, str) and unit_value.strip())
        else 'count'
    )

    new_item_group = new_item.get('group', '').strip().lower() or 'pantry'

    quantity_value = new_item.get('quantity')
    if quantity_value is not None:
        try:
            new_item_quantity = float(quantity_value)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid quantity for '{new_item['name']}'")
    else:
        new_item_quantity = 1.0

    # ── Merge path ────────────────────────────────────────────────
    existing_item = session.query(KitchenItem).filter(
        KitchenItem.kitchen_id == kitchen_id,
        func.lower(KitchenItem.name) == new_item_name,
        func.lower(KitchenItem.unit) == new_item_unit,
        func.lower(KitchenItem.group) == new_item_group
    ).first()

    if existing_item:
        existing_item.quantity += new_item_quantity

        if new_item.get('thumbnail'):
            existing_item.thumbnail = new_item['thumbnail']

        if new_item.get('expiry_date'):
            existing_item.expiry_date = new_item['expiry_date']
            existing_item.added_at = datetime.now(timezone.utc)
        else:
            try:
                auto_expiry = calculate_item_expiry(new_item['name'], new_item_group)
                if auto_expiry:
                    existing_item.expiry_date = auto_expiry
                    existing_item.added_at = datetime.now(timezone.utc)
            except Exception as e:
                print(f"   [kitchen_item_helpers] Error calculating expiry: {str(e)}")

        return existing_item.item_id, False   # existing row — thumbnail already present

    # ── Create path ───────────────────────────────────────────────
    expiry_date_value = new_item.get('expiry_date')
    if not expiry_date_value:
        try:
            auto_expiry = calculate_item_expiry(new_item['name'], new_item_group)
            if auto_expiry:
                expiry_date_value = auto_expiry
        except Exception as e:
            print(f"   [kitchen_item_helpers] Error calculating expiry: {str(e)}")

    thumbnail = new_item.get('thumbnail') or None
    new_item_id = uuid.uuid4().hex

    kitchen_item = KitchenItem(
        item_id=new_item_id,
        kitchen_id=kitchen_id,
        name=new_item['name'].strip(),
        quantity=new_item_quantity,
        unit=new_item_unit,
        group=new_item_group,
        thumbnail=thumbnail,
        expiry_date=expiry_date_value,
        added_at=datetime.now(timezone.utc)
    )
    session.add(kitchen_item)

    needs_thumbnail = not thumbnail
    return new_item_id, needs_thumbnail