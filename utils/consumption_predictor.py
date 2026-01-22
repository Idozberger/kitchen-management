# consumption_predictor.py
"""
Core logic for predictive consumption algorithm - PostgreSQL VERSION
Handles baseline predictions and personalized learning.
CONVERTED from MongoDB to PostgreSQL with SQLAlchemy
"""

from datetime import datetime, timezone, timedelta
from db_connection import get_session
from models import (
    Kitchen, KitchenItem, KitchenConsumptionPattern, ConsumptionEvent,
    ConsumptionUsageEvent, PendingConfirmation, MyList, ConsumptionBaseline
)
from utils.consumption_baselines import get_baseline_consumption, get_default_consumption_days
import uuid


class ConsumptionPredictor:
    """
    Handles consumption prediction and pattern learning.
    Enhanced with quantity tracking, FIFO depletion, adaptive learning, and caching.
    PostgreSQL version with proper session management.
    """
    
    _baseline_cache = {}  # Stores baselines in memory
    _cache_loaded = False  # Flag to track if cache is initialized
    
    def __init__(self):
        """
        Initialize predictor.
        Database sessions are created per-operation (not stored in instance).
        """
        # Minimum samples needed to trust personalized data
        self.min_samples_for_personalization = 2
        
        # Load baseline cache once
        if not ConsumptionPredictor._cache_loaded:
            self._load_baseline_cache()
    
    
    def _load_baseline_cache(self):
        """
        Load baselines from DB into memory cache.
        This runs ONCE when the first ConsumptionPredictor is created.
        """
        session = get_session()
        try:
            print("📄 Loading baseline cache from database...")
            
            # Fetch all baselines from PostgreSQL
            baselines = session.query(ConsumptionBaseline).all()
            
            # Store in class-level cache
            for baseline in baselines:
                ConsumptionPredictor._baseline_cache[baseline.item_name] = {
                    'days': baseline.avg_consumption_days,
                    'category': baseline.category
                }
            
            # Mark cache as loaded
            ConsumptionPredictor._cache_loaded = True
            
            print(f"✅ Loaded {len(ConsumptionPredictor._baseline_cache)} baselines into cache")
            
        except Exception as e:
            print(f"⚠️ Warning: Could not load baseline cache: {str(e)}")
            print("   Falling back to Python dictionary baselines")
        finally:
            session.close()
    
    
    def get_predicted_consumption_days(self, kitchen_id, item_name):
        """
        Get predicted consumption days for an item in a kitchen.
        Uses cache for baseline lookups.
        
        Phase 1: Returns baseline if no personalized data exists
        Phase 2: Returns personalized average if kitchen has history
        
        Args:
            kitchen_id (int): Kitchen ID
            item_name (str): Item name
        
        Returns:
            int: Predicted consumption days
        """
        session = get_session()
        try:
            kitchen_id = int(kitchen_id)
            item_name_lower = item_name.strip().lower()
            
            # Check for personalized pattern (Phase 2)
            pattern = session.query(KitchenConsumptionPattern).filter(
                KitchenConsumptionPattern.kitchen_id == kitchen_id,
                KitchenConsumptionPattern.item_name == item_name_lower
            ).first()
            
            if pattern and pattern.sample_count >= self.min_samples_for_personalization:
                # Use personalized data
                print(f"🎯 Using personalized prediction for '{item_name}': {pattern.personalized_days} days")
                return int(round(pattern.personalized_days))
            
            # Use cache for baseline lookup
            if ConsumptionPredictor._baseline_cache:
                baseline = ConsumptionPredictor._baseline_cache.get(item_name_lower)
                
                if baseline:
                    print(f"📊 Using cached baseline for '{item_name}': {baseline['days']} days")
                    return baseline['days']
            else:
                # Fallback to Python dictionary if cache not loaded
                baseline = get_baseline_consumption(item_name_lower)
                
                if baseline:
                    print(f"📊 Using baseline prediction for '{item_name}': {baseline['days']} days")
                    return baseline['days']
            
            # Default if item not in baseline
            default_days = get_default_consumption_days()
            print(f"⚠️ No baseline for '{item_name}', using default: {default_days} days")
            return default_days
            
        finally:
            session.close()
    
    
    def _get_adaptive_learning_rate(self, sample_count, confidence):
        """
        Calculate adaptive learning rate based on confidence level.
        
        Low confidence (1-2 samples): Conservative (30% new, 70% old)
        Medium confidence (3-9 samples): Balanced (50% new, 50% old)
        High confidence (10+ samples): Responsive (70% new, 30% old)
        
        Args:
            sample_count (int): Number of observations
            confidence (str): 'low', 'medium', or 'high'
        
        Returns:
            float: Learning rate between 0 and 1
        """
        if confidence == 'low':
            return 0.3  # Conservative - trust history more
        elif confidence == 'medium':
            return 0.5  # Balanced
        else:  # high confidence
            return 0.7  # Responsive - trust recent behavior more
    
    
    def update_consumption_pattern(self, kitchen_id, item_name, days_lasted, quantity=None, unit=None):
        """
        Update personalized consumption pattern (Phase 2 learning).
        Uses adaptive EMA weights based on confidence.
        
        Args:
            kitchen_id (int): Kitchen ID
            item_name (str): Item name
            days_lasted (int): Actual days the item lasted
            quantity (float, optional): Quantity consumed
            unit (str, optional): Unit of measurement
        """
        session = get_session()
        try:
            kitchen_id = int(kitchen_id)
            item_name_lower = item_name.strip().lower()
            
            # Check if pattern already exists
            pattern = session.query(KitchenConsumptionPattern).filter(
                KitchenConsumptionPattern.kitchen_id == kitchen_id,
                KitchenConsumptionPattern.item_name == item_name_lower
            ).first()
            
            # Calculate consumption rate if quantity provided
            consumption_rate = None
            if quantity and quantity > 0:
                try:
                    consumption_rate = float(quantity) / days_lasted
                except (ValueError, TypeError, ZeroDivisionError):
                    consumption_rate = None
            
            current_time = datetime.now(timezone.utc)
            
            if pattern:
                # Update existing pattern
                old_avg = pattern.personalized_days
                sample_count = pattern.sample_count
                
                # Calculate adaptive learning rate
                confidence = self._get_confidence_level(sample_count + 1)
                learning_rate = self._get_adaptive_learning_rate(sample_count + 1, confidence)
                
                # Adaptive EMA formula
                new_avg = (learning_rate * days_lasted) + ((1 - learning_rate) * old_avg)
                
                # Update pattern
                pattern.personalized_days = new_avg
                pattern.sample_count = sample_count + 1
                pattern.last_consumption_date = current_time
                pattern.confidence = confidence
                pattern.learning_rate = learning_rate
                pattern.updated_at = current_time
                
                # Update consumption rate if available
                if consumption_rate:
                    old_rate = pattern.consumption_rate or consumption_rate
                    new_rate = (learning_rate * consumption_rate) + ((1 - learning_rate) * old_rate)
                    pattern.consumption_rate = new_rate
                    pattern.unit = unit
                
                session.commit()
                
                if consumption_rate:
                    print(f"📈 Updated pattern for '{item_name}': {old_avg:.1f} → {new_avg:.1f} days, "
                          f"rate: {pattern.consumption_rate:.3f} {unit}/day, learning_rate: {learning_rate:.0%} "
                          f"(sample #{sample_count + 1}, {confidence} confidence)")
                else:
                    print(f"📈 Updated pattern for '{item_name}': {old_avg:.1f} → {new_avg:.1f} days, "
                          f"learning_rate: {learning_rate:.0%} (sample #{sample_count + 1}, {confidence} confidence)")
            
            else:
                # Create new pattern (first observation)
                confidence = self._get_confidence_level(1)
                learning_rate = self._get_adaptive_learning_rate(1, confidence)
                
                new_pattern = KitchenConsumptionPattern(
                    kitchen_id=kitchen_id,
                    item_name=item_name_lower,
                    personalized_days=float(days_lasted),
                    sample_count=1,
                    consumption_rate=consumption_rate,
                    unit=unit,
                    confidence=confidence,
                    learning_rate=learning_rate,
                    last_consumption_date=current_time,
                    created_at=current_time,
                    updated_at=current_time
                )
                session.add(new_pattern)
                session.commit()
                
                if consumption_rate:
                    print(f"🆕 Created new pattern for '{item_name}': {days_lasted} days, "
                          f"rate: {consumption_rate:.3f} {unit}/day (sample #1, {confidence} confidence)")
                else:
                    print(f"🆕 Created new pattern for '{item_name}': {days_lasted} days "
                          f"(sample #1, {confidence} confidence)")
                    
        except Exception as e:
            session.rollback()
            print(f"❌ Error updating pattern: {str(e)}")
            raise
        finally:
            session.close()
    
    
    def log_consumption_event(self, kitchen_id, item_data, depleted_at, method='auto'):
        """
        Log a consumption event for tracking and learning.
        Only called when user CONFIRMS depletion (method='confirmed')
        
        Args:
            kitchen_id (int): Kitchen ID
            item_data (dict): Item data with name, quantity, unit, added_at
            depleted_at (datetime): When item was depleted
            method (str): 'confirmed', 'manual', or 'recipe'
        """
        session = get_session()
        try:
            kitchen_id = int(kitchen_id)
            
            added_at = item_data.get('added_at')
            quantity = item_data.get('quantity', 0)
            unit = item_data.get('unit', 'count')
            
            # Validate data before logging
            if not added_at:
                print(f"⚠️ Cannot log consumption event: no added_at timestamp")
                return
            
            # Skip if quantity is invalid
            if quantity <= 0:
                print(f"⚠️ Cannot log consumption event: invalid quantity {quantity}")
                return
            
            # Ensure added_at is timezone-aware
            if isinstance(added_at, str):
                added_at = datetime.fromisoformat(added_at.replace('Z', '+00:00'))
            if not isinstance(added_at, datetime):
                print(f"⚠️ Invalid added_at type: {type(added_at)}")
                return
            if added_at.tzinfo is None:
                added_at = added_at.replace(tzinfo=timezone.utc)
            
            # Calculate days lasted
            days_lasted = (depleted_at - added_at).days
            
            # Ensure minimum 1 day (if depleted same day)
            if days_lasted < 1:
                days_lasted = 1
            
            # Calculate consumption rate
            consumption_rate = None
            try:
                consumption_rate = float(quantity) / days_lasted
            except (ValueError, TypeError, ZeroDivisionError):
                consumption_rate = None
            
            event = ConsumptionEvent(
                kitchen_id=kitchen_id,
                item_id=item_data.get('item_id'),
                item_name=item_data.get('name', '').lower(),
                quantity=quantity,
                unit=unit,
                added_at=added_at,
                depleted_at=depleted_at,
                days_lasted=days_lasted,
                consumption_rate=consumption_rate,
                method=method,
                created_at=datetime.now(timezone.utc)
            )
            session.add(event)
            session.commit()
            
            # Enhanced logging
            if consumption_rate:
                print(f"📝 Logged consumption: '{item_data.get('name')}' {quantity} {unit} lasted {days_lasted} days "
                      f"(rate: {consumption_rate:.3f} {unit}/day, {method})")
            else:
                print(f"📝 Logged consumption: '{item_data.get('name')}' lasted {days_lasted} days ({method})")
            
            # Update personalized pattern
            self.update_consumption_pattern(
                kitchen_id, 
                item_data.get('name'), 
                days_lasted,
                quantity=quantity,
                unit=unit
            )
            
        except Exception as e:
            session.rollback()
            print(f"❌ Error logging consumption: {str(e)}")
            raise
        finally:
            session.close()
    
    
    def log_usage_event(self, kitchen_id, item_data, quantity_used, quantity_remaining, method='recipe', recipe_id=None):
        """
        Log partial usage event (item NOT fully depleted).
        
        This tracks when items are used but not finished (e.g., recipes using partial quantities).
        
        Args:
            kitchen_id (int): Kitchen ID
            item_data (dict): Item data with name, unit, item_id
            quantity_used (float): Amount used in this event
            quantity_remaining (float): Amount left in inventory
            method (str): 'recipe' or 'manual'
            recipe_id (int, optional): Recipe ID if method='recipe'
        """
        session = get_session()
        try:
            kitchen_id = int(kitchen_id)
            
            usage_event = ConsumptionUsageEvent(
                usage_id=uuid.uuid4().hex,
                kitchen_id=kitchen_id,
                item_id=item_data.get('item_id'),
                item_name=item_data.get('name', '').lower(),
                quantity_used=float(quantity_used),
                quantity_remaining=float(quantity_remaining),
                unit=item_data.get('unit', 'count'),
                used_at=datetime.now(timezone.utc),
                method=method,
                recipe_id=recipe_id,
                created_at=datetime.now(timezone.utc)
            )
            
            session.add(usage_event)
            session.commit()
            
            print(f"📊 Logged usage: '{item_data.get('name')}' used {quantity_used} {item_data.get('unit')}, "
                  f"{quantity_remaining} {item_data.get('unit')} remaining ({method})")
            
        except Exception as e:
            session.rollback()
            print(f"❌ Error logging usage: {str(e)}")
            raise
        finally:
            session.close()
    
    
    def create_pending_confirmation(self, kitchen_id, item_data, predicted_depletion_date):
        """
        Create pending confirmation for predicted depletion.
        
        Instead of auto-removing, ask user to confirm.
        
        Args:
            kitchen_id (int): Kitchen ID
            item_data (dict): Item data with item_id, name, quantity, unit, added_at
            predicted_depletion_date (datetime): When system predicted depletion
        
        Returns:
            str: confirmation_id
        """
        session = get_session()
        try:
            kitchen_id = int(kitchen_id)
            
            confirmation_id = uuid.uuid4().hex
            
            confirmation = PendingConfirmation(
                confirmation_id=confirmation_id,
                kitchen_id=kitchen_id,
                item_id=item_data.get('item_id'),
                item_name=item_data.get('name', ''),
                quantity=item_data.get('quantity', 0),
                unit=item_data.get('unit', 'count'),
                added_at=item_data.get('added_at'),
                predicted_depletion_date=predicted_depletion_date,
                status='pending',
                expires_at=predicted_depletion_date + timedelta(days=7),  # Auto-expire after 7 days
                created_at=datetime.now(timezone.utc)
            )
            
            session.add(confirmation)
            session.commit()
            
            print(f"❓ Created pending confirmation for '{item_data.get('name')}' (expires in 7 days)")
            
            return confirmation_id
            
        except Exception as e:
            session.rollback()
            print(f"❌ Error creating confirmation: {str(e)}")
            raise
        finally:
            session.close()
    
    
    def check_and_deplete_items(self):
        """
        Check all kitchens for items that should be depleted.
        
        Creates pending confirmations instead of automatically removing items.
        PERFORMANCE IMPROVEMENTS:
        - Batched database queries
        - Early returns for empty data
        - Reduced duplicate checks
        - Index-optimized queries
        
        Returns:
            dict: Summary of actions taken
        """
        print("\n" + "="*60)
        print("🔄 Starting predictive consumption check...")
        print("="*60)
        
        session = get_session()
        try:
            current_time = datetime.now(timezone.utc)
            summary = {
                'kitchens_checked': 0,
                'items_checked': 0,
                'confirmations_created': 0,
                'confirmations_skipped': 0,
                'errors': []
            }
            
            # Fetch only kitchens that have items
            kitchens = session.query(Kitchen).filter(
                Kitchen.id.in_(
                    session.query(KitchenItem.kitchen_id).distinct()
                )
            ).all()
            
            if not kitchens:
                print("ℹ️ No kitchens with items found")
                return summary
            
            print(f"📊 Found {len(kitchens)} kitchens with items")
            
            # Batch fetch ALL pending confirmations at once
            all_kitchen_ids = [k.id for k in kitchens]
            existing_confirmations = session.query(
                PendingConfirmation.kitchen_id,
                PendingConfirmation.item_id
            ).filter(
                PendingConfirmation.kitchen_id.in_(all_kitchen_ids),
                PendingConfirmation.status == 'pending'
            ).all()
            
            # Create lookup set for O(1) checks
            pending_lookup = {(conf.kitchen_id, conf.item_id) for conf in existing_confirmations}
            
            print(f"📋 Found {len(pending_lookup)} existing pending confirmations")
            
            # Process each kitchen
            for kitchen in kitchens:
                summary['kitchens_checked'] += 1
                kitchen_id = kitchen.id
                kitchen_name = kitchen.kitchen_name or 'Unknown'
                
                print(f"\n🏠 Checking kitchen: {kitchen_name}")
                
                # Fetch items for this kitchen
                items = session.query(KitchenItem).filter(
                    KitchenItem.kitchen_id == kitchen_id
                ).all()
                
                if not items:
                    continue
                
                # Group items by name
                items_by_name = {}
                for item in items:
                    name = item.name.lower() if item.name else ''
                    if not name:
                        continue
                    
                    # Skip items without required fields
                    if not item.added_at or item.quantity <= 0:
                        continue
                    
                    if name not in items_by_name:
                        items_by_name[name] = []
                    items_by_name[name].append(item)
                
                if not items_by_name:
                    print(f"  ⏭️ No valid items to check")
                    continue
                
                # Process each item group (FIFO - oldest first)
                for item_name, item_group in items_by_name.items():
                    summary['items_checked'] += len(item_group)
                    
                    # Sort by added_at (oldest first)
                    item_group.sort(key=lambda x: x.added_at or datetime.min.replace(tzinfo=timezone.utc))
                    
                    # Check only the oldest instance
                    oldest_item = item_group[0]
                    item_id = oldest_item.item_id
                    added_at = oldest_item.added_at
                    
                    # Ensure added_at is timezone-aware
                    if isinstance(added_at, str):
                        added_at = datetime.fromisoformat(added_at.replace('Z', '+00:00'))
                    if added_at.tzinfo is None:
                        added_at = added_at.replace(tzinfo=timezone.utc)
                    
                    # Calculate days since added
                    days_elapsed = (current_time - added_at).days
                    
                    # Get predicted consumption days
                    predicted_days = self.get_predicted_consumption_days(kitchen_id, item_name)
                    
                    # Cap maximum prediction at 90 days
                    predicted_days = min(predicted_days, 90)
                    
                    # Check if item should be considered for depletion
                    if days_elapsed >= predicted_days:
                        print(f"  ⏰ '{item_name}' (oldest) predicted depleted ({days_elapsed} >= {predicted_days} days)")
                        
                        try:
                            # Use pre-fetched lookup (O(1) instead of DB query)
                            lookup_key = (kitchen_id, item_id)
                            
                            if lookup_key in pending_lookup:
                                print(f"  ⏭️ Confirmation already pending for '{item_name}' - skipping")
                                summary['confirmations_skipped'] += 1
                                continue
                            
                            # Create pending confirmation
                            confirmation_id = self.create_pending_confirmation(
                                kitchen_id,
                                {
                                    'item_id': oldest_item.item_id,
                                    'name': oldest_item.name,
                                    'quantity': oldest_item.quantity,
                                    'unit': oldest_item.unit,
                                    'added_at': oldest_item.added_at
                                },
                                current_time
                            )
                            
                            # Add to lookup for subsequent iterations
                            pending_lookup.add(lookup_key)
                            
                            summary['confirmations_created'] += 1
                            print(f"  ✅ Created confirmation request for '{item_name}'")
                            
                        except Exception as e:
                            error_msg = f"Error creating confirmation for '{item_name}' in kitchen '{kitchen_name}': {str(e)}"
                            print(f"  ❌ {error_msg}")
                            summary['errors'].append(error_msg)
            
            # Summary
            print("\n" + "="*60)
            print("📊 Summary:")
            print(f"  Kitchens checked: {summary['kitchens_checked']}")
            print(f"  Items checked: {summary['items_checked']}")
            print(f"  Confirmations created: {summary['confirmations_created']}")
            print(f"  Confirmations skipped (already pending): {summary['confirmations_skipped']}")
            print(f"  Errors: {len(summary['errors'])}")
            print("="*60 + "\n")
            
            return summary
            
        except Exception as e:
            print(f"❌ Critical error in check_and_deplete_items: {str(e)}")
            summary['errors'].append(str(e))
            return summary
        finally:
            session.close()
    
    
    def _get_confidence_level(self, sample_count):
        """
        Calculate confidence level based on number of samples.
        
        Args:
            sample_count (int): Number of observations
        
        Returns:
            str: 'low', 'medium', or 'high'
        """
        if sample_count < 3:
            return 'low'
        elif sample_count < 10:
            return 'medium'
        else:
            return 'high'
    
    
    def get_kitchen_patterns(self, kitchen_id):
        """
        Get all personalized consumption patterns for a kitchen.
        
        Args:
            kitchen_id (int): Kitchen ID
        
        Returns:
            list: List of pattern dictionaries
        """
        session = get_session()
        try:
            kitchen_id = int(kitchen_id)
            
            patterns = session.query(KitchenConsumptionPattern).filter(
                KitchenConsumptionPattern.kitchen_id == kitchen_id
            ).all()
            
            # Convert to dictionaries for JSON serialization
            patterns_list = []
            for pattern in patterns:
                pattern_dict = {
                    '_id': str(pattern.id),
                    'kitchen_id': str(pattern.kitchen_id),
                    'item_name': pattern.item_name,
                    'personalized_days': pattern.personalized_days,
                    'sample_count': pattern.sample_count,
                    'consumption_rate': pattern.consumption_rate,
                    'unit': pattern.unit,
                    'confidence': pattern.confidence,
                    'learning_rate': pattern.learning_rate,
                    'last_consumption_date': pattern.last_consumption_date.isoformat() if pattern.last_consumption_date else None,
                    'created_at': pattern.created_at.isoformat() if pattern.created_at else None,
                    'updated_at': pattern.updated_at.isoformat() if pattern.updated_at else None
                }
                patterns_list.append(pattern_dict)
            
            return patterns_list
            
        finally:
            session.close()
    
    
    def get_consumption_history(self, kitchen_id, item_name=None, limit=50):
        """
        Get consumption event history for a kitchen.
        
        Args:
            kitchen_id (int): Kitchen ID
            item_name (str, optional): Filter by specific item
            limit (int): Maximum number of events to return
        
        Returns:
            list: List of consumption event dictionaries
        """
        session = get_session()
        try:
            kitchen_id = int(kitchen_id)
            
            query = session.query(ConsumptionEvent).filter(
                ConsumptionEvent.kitchen_id == kitchen_id
            )
            
            if item_name:
                query = query.filter(ConsumptionEvent.item_name == item_name.strip().lower())
            
            events = query.order_by(ConsumptionEvent.depleted_at.desc()).limit(limit).all()
            
            # Convert to dictionaries
            events_list = []
            for event in events:
                event_dict = {
                    '_id': str(event.id),
                    'kitchen_id': str(event.kitchen_id),
                    'item_id': event.item_id,
                    'item_name': event.item_name,
                    'quantity': event.quantity,
                    'unit': event.unit,
                    'added_at': event.added_at.isoformat() if event.added_at else None,
                    'depleted_at': event.depleted_at.isoformat() if event.depleted_at else None,
                    'days_lasted': event.days_lasted,
                    'consumption_rate': event.consumption_rate,
                    'method': event.method,
                    'created_at': event.created_at.isoformat() if event.created_at else None
                }
                events_list.append(event_dict)
            
            return events_list
            
        finally:
            session.close()
    
    
    def get_predicted_consumption_days_for_quantity(self, kitchen_id, item_name, quantity, unit):
        """
        Get predicted consumption days for a SPECIFIC quantity.
        Uses consumption rate if available.
        
        Args:
            kitchen_id (int): Kitchen ID
            item_name (str): Item name
            quantity (float): Quantity to predict for
            unit (str): Unit of measurement
        
        Returns:
            int: Predicted consumption days for this quantity
        """
        session = get_session()
        try:
            kitchen_id = int(kitchen_id)
            item_name_lower = item_name.strip().lower()
            
            # Check for personalized pattern with rate
            pattern = session.query(KitchenConsumptionPattern).filter(
                KitchenConsumptionPattern.kitchen_id == kitchen_id,
                KitchenConsumptionPattern.item_name == item_name_lower
            ).first()
            
            if pattern and pattern.sample_count >= self.min_samples_for_personalization:
                consumption_rate = pattern.consumption_rate
                pattern_unit = pattern.unit
                
                if consumption_rate and pattern_unit == unit:
                    predicted_days = quantity / consumption_rate
                    print(f"🎯 Rate-based prediction for '{item_name}' ({quantity} {unit}): {predicted_days:.1f} days "
                          f"(rate: {consumption_rate:.3f} {unit}/day)")
                    return int(round(predicted_days))
            
            # Fallback to standard prediction
            return self.get_predicted_consumption_days(kitchen_id, item_name)
            
        finally:
            session.close()


# Export for easy import
__all__ = ['ConsumptionPredictor']