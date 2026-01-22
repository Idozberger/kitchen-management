"""
SQLAlchemy Models for Kitchen Guardian
Converted from MongoDB collections to PostgreSQL tables
"""

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, 
    ForeignKey, UniqueConstraint, Index, JSON
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

Base = declarative_base()


# ============================================
# USER MODEL
# ============================================
class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password = Column(String(255), nullable=False)  # bcrypt hash
    verified = Column(Integer, default=0)  # 0 = not verified, 1 = verified
    verification_code = Column(String(10), nullable=True)
    reset_code = Column(String(10), nullable=True)
    avatar = Column(Text, nullable=True)  # Base64 encoded image
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    hosted_kitchens = relationship('Kitchen', back_populates='host', foreign_keys='Kitchen.host_id')
    kitchen_memberships = relationship('KitchenMember', back_populates='user')
    favourite_recipes = relationship('FavouriteRecipe', back_populates='user')
    meal_plans = relationship('MealPlan', back_populates='creator')
    scan_history = relationship('ScanHistory', back_populates='user')
    
    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}')>"


# ============================================
# KITCHEN MODEL
# ============================================
class Kitchen(Base):
    __tablename__ = 'kitchens'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    kitchen_name = Column(String(255), nullable=False)
    host_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    invitation_code = Column(String(6), unique=True, nullable=False, index=True)
    start_date = Column(String(10), nullable=True)  # YYYY-MM-DD
    end_date = Column(String(10), nullable=True)    # YYYY-MM-DD
    start_date_obj = Column(DateTime(timezone=True), nullable=True)
    end_date_obj = Column(DateTime(timezone=True), nullable=True)
    date_range_updated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    host = relationship('User', back_populates='hosted_kitchens', foreign_keys=[host_id])
    members = relationship('KitchenMember', back_populates='kitchen', cascade='all, delete-orphan')
    items = relationship('KitchenItem', back_populates='kitchen', cascade='all, delete-orphan')
    pantries = relationship('Pantry', back_populates='kitchen', cascade='all, delete-orphan')
    invitations = relationship('Invitation', back_populates='kitchen', cascade='all, delete-orphan')
    my_lists = relationship('MyList', back_populates='kitchen', cascade='all, delete-orphan')
    meal_plans = relationship('MealPlan', back_populates='kitchen', cascade='all, delete-orphan')
    consumption_patterns = relationship('KitchenConsumptionPattern', back_populates='kitchen', cascade='all, delete-orphan')
    consumption_events = relationship('ConsumptionEvent', back_populates='kitchen', cascade='all, delete-orphan')
    usage_events = relationship('ConsumptionUsageEvent', back_populates='kitchen', cascade='all, delete-orphan')
    pending_confirmations = relationship('PendingConfirmation', back_populates='kitchen', cascade='all, delete-orphan')
    items_history = relationship('KitchenItemsHistory', back_populates='kitchen', uselist=False, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f"<Kitchen(id={self.id}, name='{self.kitchen_name}')>"


# ============================================
# KITCHEN MEMBER MODEL
# ============================================
class KitchenMember(Base):
    __tablename__ = 'kitchen_members'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    kitchen_id = Column(Integer, ForeignKey('kitchens.id', ondelete='CASCADE'), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    member_type = Column(String(20), nullable=False)  # 'host', 'co-host', 'member'
    joined_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    kitchen = relationship('Kitchen', back_populates='members')
    user = relationship('User', back_populates='kitchen_memberships')
    
    # Unique constraint: user can only be member of kitchen once
    __table_args__ = (
        UniqueConstraint('kitchen_id', 'user_id', name='uq_kitchen_user'),
        Index('idx_kitchen_member_lookup', 'kitchen_id', 'user_id', 'member_type'),
    )
    
    def __repr__(self):
        return f"<KitchenMember(kitchen_id={self.kitchen_id}, user_id={self.user_id}, type='{self.member_type}')>"


# ============================================
# KITCHEN ITEM MODEL (Inventory)
# ============================================
class KitchenItem(Base):
    __tablename__ = 'kitchen_items'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    kitchen_id = Column(Integer, ForeignKey('kitchens.id', ondelete='CASCADE'), nullable=False, index=True)
    item_id = Column(String(32), unique=True, nullable=False, index=True)  # UUID hex
    name = Column(String(255), nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    unit = Column(String(50), nullable=False)
    group = Column(String(100), default='pantry')  # pantry, fridge, freezer, etc.
    thumbnail = Column(Text, nullable=True)  # Base64 encoded image
    expiry_date = Column(String(50), nullable=True)  # "7 days", "2 weeks", etc.
    added_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    kitchen = relationship('Kitchen', back_populates='items')
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_kitchen_item_name', 'kitchen_id', 'name'),
        Index('idx_kitchen_item_group', 'kitchen_id', 'group'),
    )
    
    def __repr__(self):
        return f"<KitchenItem(id={self.id}, name='{self.name}', quantity={self.quantity})>"


# ============================================
# KITCHEN ITEMS HISTORY MODEL
# ============================================
class KitchenItemsHistory(Base):
    __tablename__ = 'kitchen_items_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    kitchen_id = Column(Integer, ForeignKey('kitchens.id', ondelete='CASCADE'), unique=True, nullable=False, index=True)
    item_names = Column(JSON, nullable=False, default=list)  # List of item names (lowercase)
    
    # Relationships
    kitchen = relationship('Kitchen', back_populates='items_history')
    
    def __repr__(self):
        return f"<KitchenItemsHistory(kitchen_id={self.kitchen_id}, items_count={len(self.item_names)})>"


# ============================================
# PANTRY MODEL
# ============================================
class Pantry(Base):
    __tablename__ = 'pantries'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    kitchen_id = Column(Integer, ForeignKey('kitchens.id', ondelete='CASCADE'), nullable=False, index=True)
    pantry_id = Column(String(32), unique=True, nullable=False, index=True)  # UUID hex
    pantry_name = Column(String(255), nullable=False)
    created_by = Column(Integer, ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    kitchen = relationship('Kitchen', back_populates='pantries')
    
    # Unique constraint: pantry name must be unique per kitchen
    __table_args__ = (
        UniqueConstraint('kitchen_id', 'pantry_name', name='uq_kitchen_pantry_name'),
    )
    
    def __repr__(self):
        return f"<Pantry(id={self.id}, name='{self.pantry_name}')>"


# ============================================
# INVITATION MODEL
# ============================================
class Invitation(Base):
    __tablename__ = 'invitations'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    invitation_id = Column(String(36), unique=True, nullable=False, index=True)  # UUID
    kitchen_id = Column(Integer, ForeignKey('kitchens.id', ondelete='CASCADE'), nullable=False, index=True)
    kitchen_name = Column(String(255), nullable=False)
    inviter_name = Column(String(255), nullable=False)
    invitee_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    status = Column(String(20), default='pending', index=True)  # 'pending', 'accepted', 'denied'
    url = Column(String(500), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    denied_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    kitchen = relationship('Kitchen', back_populates='invitations')
    
    # Index for pending invitations lookup
    __table_args__ = (
        Index('idx_invitation_status', 'invitee_id', 'status'),
    )
    
    def __repr__(self):
        return f"<Invitation(id={self.id}, status='{self.status}')>"


# ============================================
# MY LIST MODEL (Shopping List)
# ============================================
class MyList(Base):
    __tablename__ = 'my_lists'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    kitchen_id = Column(Integer, ForeignKey('kitchens.id', ondelete='CASCADE'), nullable=False, index=True)
    item_id = Column(String(32), unique=True, nullable=False, index=True)  # UUID hex
    name = Column(String(255), nullable=False)
    quantity = Column(Float, nullable=False)
    unit = Column(String(50), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    bucket_type = Column(String(20), nullable=False, index=True)  # 'mylist' or 'requested'
    thumbnail = Column(Text, nullable=True)
    expiry_date = Column(String(50), nullable=True)
    auto_added = Column(Boolean, default=False)
    predicted_depletion = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    requested_at = Column(DateTime(timezone=True), nullable=True)
    modified_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    kitchen = relationship('Kitchen', back_populates='my_lists')
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_mylist_bucket', 'kitchen_id', 'bucket_type'),
        Index('idx_mylist_auto', 'kitchen_id', 'bucket_type', 'auto_added'),
    )
    
    def __repr__(self):
        return f"<MyList(id={self.id}, name='{self.name}', bucket='{self.bucket_type}')>"


# ============================================
# GENERATED RECIPE MODEL
# ============================================
class GeneratedRecipe(Base):
    __tablename__ = 'generated_recipes'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False)
    calories = Column(String(50), nullable=True)
    cooking_time = Column(String(50), nullable=True)
    ingredients = Column(JSON, nullable=False)  # List of dicts
    recipe_short_summary = Column(Text, nullable=True)
    cooking_steps = Column(JSON, nullable=False)  # List of strings
    missing_items = Column(Boolean, default=False)
    missing_items_list = Column(JSON, nullable=True)  # List of dicts
    thumbnail = Column(Text, nullable=True)  # Base64 encoded image
    expiring_items_used = Column(JSON, nullable=True)  # List of item names
    expiring_items_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    favourite_recipes = relationship('FavouriteRecipe', back_populates='recipe')
    meal_plans = relationship('MealPlan', back_populates='recipe')
    
    def __repr__(self):
        return f"<GeneratedRecipe(id={self.id}, title='{self.title}')>"


# ============================================
# FAVOURITE RECIPE MODEL
# ============================================
class FavouriteRecipe(Base):
    __tablename__ = 'favourite_recipes'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    recipe_id = Column(Integer, ForeignKey('generated_recipes.id', ondelete='CASCADE'), nullable=False, index=True)
    added_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship('User', back_populates='favourite_recipes')
    recipe = relationship('GeneratedRecipe', back_populates='favourite_recipes')
    
    # Unique constraint: user can only favourite a recipe once
    __table_args__ = (
        UniqueConstraint('user_id', 'recipe_id', name='uq_user_recipe'),
    )
    
    def __repr__(self):
        return f"<FavouriteRecipe(user_id={self.user_id}, recipe_id={self.recipe_id})>"


# ============================================
# MEAL PLAN MODEL
# ============================================
class MealPlan(Base):
    __tablename__ = 'meal_plans'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    meal_plan_id = Column(String(32), unique=True, nullable=False, index=True)  # UUID hex
    kitchen_id = Column(Integer, ForeignKey('kitchens.id', ondelete='CASCADE'), nullable=False, index=True)
    created_by = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    date_obj = Column(DateTime(timezone=True), nullable=False, index=True)
    meal_type = Column(String(20), nullable=False, index=True)  # 'breakfast', 'lunch', 'dinner', 'snack'
    recipe_id = Column(Integer, ForeignKey('generated_recipes.id', ondelete='CASCADE'), nullable=False)
    
    # Denormalized recipe fields for performance
    title = Column(String(500), nullable=True)
    calories = Column(String(50), nullable=True)
    cooking_time = Column(String(50), nullable=True)
    thumbnail = Column(Text, nullable=True)
    ingredients = Column(JSON, nullable=True)
    cooking_steps = Column(JSON, nullable=True)
    missing_items = Column(Boolean, default=False)
    missing_items_list = Column(JSON, nullable=True)
    recipe_short_summary = Column(Text, nullable=True)
    
    notes = Column(Text, nullable=True)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    kitchen = relationship('Kitchen', back_populates='meal_plans')
    creator = relationship('User', back_populates='meal_plans')
    recipe = relationship('GeneratedRecipe', back_populates='meal_plans')
    
    # Unique constraint: only one meal per kitchen/date/meal_type
    __table_args__ = (
        UniqueConstraint('kitchen_id', 'date', 'meal_type', name='uq_kitchen_date_meal'),
        Index('idx_meal_date_range', 'kitchen_id', 'date_obj'),
    )
    
    def __repr__(self):
        return f"<MealPlan(id={self.id}, date='{self.date}', meal_type='{self.meal_type}')>"


# ============================================
# SCAN HISTORY MODEL
# ============================================
class ScanHistory(Base):
    __tablename__ = 'scan_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    items = Column(JSON, nullable=False)  # List of scanned items
    scanned_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    
    # Relationships
    user = relationship('User', back_populates='scan_history')
    
    def __repr__(self):
        return f"<ScanHistory(id={self.id}, user_id={self.user_id})>"


# ============================================
# CONSUMPTION PATTERN MODEL
# ============================================
class KitchenConsumptionPattern(Base):
    __tablename__ = 'kitchen_consumption_patterns'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    kitchen_id = Column(Integer, ForeignKey('kitchens.id', ondelete='CASCADE'), nullable=False, index=True)
    item_name = Column(String(255), nullable=False, index=True)
    personalized_days = Column(Float, nullable=False)
    sample_count = Column(Integer, default=1)
    consumption_rate = Column(Float, nullable=True)  # quantity/day
    unit = Column(String(50), nullable=True)
    confidence = Column(String(20), nullable=False)  # 'low', 'medium', 'high'
    learning_rate = Column(Float, nullable=True)
    last_consumption_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    kitchen = relationship('Kitchen', back_populates='consumption_patterns')
    
    # Unique constraint: one pattern per kitchen/item
    __table_args__ = (
        UniqueConstraint('kitchen_id', 'item_name', name='uq_kitchen_item_pattern'),
        Index('idx_pattern_confidence', 'kitchen_id', 'confidence'),
    )
    
    def __repr__(self):
        return f"<KitchenConsumptionPattern(kitchen_id={self.kitchen_id}, item='{self.item_name}', days={self.personalized_days})>"


# ============================================
# CONSUMPTION EVENT MODEL
# ============================================
class ConsumptionEvent(Base):
    __tablename__ = 'consumption_events'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    kitchen_id = Column(Integer, ForeignKey('kitchens.id', ondelete='CASCADE'), nullable=False, index=True)
    item_id = Column(String(32), nullable=True, index=True)
    item_name = Column(String(255), nullable=False, index=True)
    quantity = Column(Float, nullable=False)
    unit = Column(String(50), nullable=False)
    added_at = Column(DateTime(timezone=True), nullable=False)
    depleted_at = Column(DateTime(timezone=True), nullable=False, index=True)
    days_lasted = Column(Integer, nullable=False)
    consumption_rate = Column(Float, nullable=True)
    method = Column(String(20), nullable=False, index=True)  # 'confirmed', 'manual', 'recipe'
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    kitchen = relationship('Kitchen', back_populates='consumption_events')
    
    # Indexes for analytics queries
    __table_args__ = (
        Index('idx_event_kitchen_date', 'kitchen_id', 'depleted_at'),
        Index('idx_event_kitchen_item', 'kitchen_id', 'item_name', 'depleted_at'),
        Index('idx_event_method', 'kitchen_id', 'method'),
    )
    
    def __repr__(self):
        return f"<ConsumptionEvent(id={self.id}, item='{self.item_name}', days={self.days_lasted})>"


# ============================================
# CONSUMPTION USAGE EVENT MODEL
# ============================================
class ConsumptionUsageEvent(Base):
    __tablename__ = 'consumption_usage_events'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    usage_id = Column(String(32), unique=True, nullable=False, index=True)  # UUID hex
    kitchen_id = Column(Integer, ForeignKey('kitchens.id', ondelete='CASCADE'), nullable=False, index=True)
    item_id = Column(String(32), nullable=True, index=True)
    item_name = Column(String(255), nullable=False, index=True)
    quantity_used = Column(Float, nullable=False)
    quantity_remaining = Column(Float, nullable=False)
    unit = Column(String(50), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=False, index=True)
    method = Column(String(20), nullable=False)  # 'recipe', 'manual'
    recipe_id = Column(Integer, ForeignKey('generated_recipes.id', ondelete='SET NULL'), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # Relationships
    kitchen = relationship('Kitchen', back_populates='usage_events')
    
    # Indexes for analytics
    __table_args__ = (
        Index('idx_usage_kitchen_date', 'kitchen_id', 'used_at'),
        Index('idx_usage_kitchen_item', 'kitchen_id', 'item_name'),
    )
    
    def __repr__(self):
        return f"<ConsumptionUsageEvent(id={self.id}, item='{self.item_name}', used={self.quantity_used})>"


# ============================================
# PENDING CONFIRMATION MODEL
# ============================================
class PendingConfirmation(Base):
    __tablename__ = 'pending_confirmations'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    confirmation_id = Column(String(32), unique=True, nullable=False, index=True)  # UUID hex
    kitchen_id = Column(Integer, ForeignKey('kitchens.id', ondelete='CASCADE'), nullable=False, index=True)
    item_id = Column(String(32), nullable=False, index=True)
    item_name = Column(String(255), nullable=False)
    quantity = Column(Float, nullable=False)
    unit = Column(String(50), nullable=False)
    added_at = Column(DateTime(timezone=True), nullable=False)
    predicted_depletion_date = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), default='pending', index=True)  # 'pending', 'confirmed', 'denied'
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    actual_quantity_remaining = Column(Float, nullable=True)
    
    # Relationships
    kitchen = relationship('Kitchen', back_populates='pending_confirmations')
    
    # Critical index for duplicate prevention
    __table_args__ = (
        Index('idx_confirmation_lookup', 'kitchen_id', 'item_id', 'status'),
        Index('idx_confirmation_expires', 'expires_at', 'status'),
        Index('idx_confirmation_user_query', 'kitchen_id', 'status', 'created_at'),
    )
    
    def __repr__(self):
        return f"<PendingConfirmation(id={self.id}, item='{self.item_name}', status='{self.status}')>"


# ============================================
# CONSUMPTION BASELINE MODEL
# ============================================
class ConsumptionBaseline(Base):
    __tablename__ = 'consumption_baselines'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    item_name = Column(String(255), unique=True, nullable=False, index=True)
    avg_consumption_days = Column(Integer, nullable=False)
    category = Column(String(50), nullable=False, index=True)
    
    def __repr__(self):
        return f"<ConsumptionBaseline(item='{self.item_name}', days={self.avg_consumption_days})>"