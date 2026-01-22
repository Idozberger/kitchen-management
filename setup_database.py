#!/usr/bin/env python3
"""
Database Setup Script for Kitchen Guardian (PostgreSQL)
Creates all tables and initial data.
Run this ONCE after installing PostgreSQL.
"""

from db_connection import engine, get_session
from models import Base
from sqlalchemy import inspect

def create_all_tables():
    """Create all database tables defined in models.py"""
    print("\n" + "="*60)
    print("🗄️  Creating Database Tables...")
    print("="*60 + "\n")
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    # Get inspector to check created tables
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    print(f"✅ Created {len(table_names)} tables:\n")
    for table_name in sorted(table_names):
        print(f"   ✓ {table_name}")
    
    print("\n" + "="*60)
    print("✅ All tables created successfully!")
    print("="*60 + "\n")
    
    return len(table_names)


def verify_tables():
    """Verify all expected tables exist"""
    print("🔍 Verifying tables...\n")
    
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    
    expected_tables = [
        'users', 'kitchens', 'kitchen_members', 'kitchen_items',
        'pantries', 'generated_recipes',  # ← Removed recipe_ingredients
        'favourite_recipes', 'meal_plans', 'my_lists', 'invitations',
        'scan_history', 'kitchen_consumption_patterns', 'consumption_events',
        'consumption_usage_events', 'pending_confirmations', 'consumption_baselines',
        'kitchen_items_history'  # ← Add this (it exists!)
    ]
    
    missing_tables = []
    for table in expected_tables:
        if table in table_names:
            print(f"   ✅ {table}")
        else:
            print(f"   ❌ {table} - MISSING!")
            missing_tables.append(table)
    
    if missing_tables:
        print(f"\n⚠️  WARNING: {len(missing_tables)} tables are missing!")
        print("   Missing tables:", ', '.join(missing_tables))
        return False
    else:
        print(f"\n✅ All {len(expected_tables)} expected tables exist!")
        return True


def populate_initial_data():
    """Populate baseline consumption data"""
    print("\n" + "="*60)
    print("📊 Populating Initial Data...")
    print("="*60 + "\n")
    
    from utils.consumption_baselines import populate_baselines_to_db
    
    try:
        populate_baselines_to_db()
        print("\n✅ Initial data populated successfully!")
    except Exception as e:
        print(f"\n⚠️  Warning: Could not populate initial data: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 Kitchen Guardian - Database Setup")
    print("="*60)
    
    try:
        # Step 1: Create tables
        num_tables = create_all_tables()
        
        if num_tables == 0:
            print("\n⚠️  WARNING: No tables were created!")
            print("   This might mean:")
            print("   1. Tables already exist (run DROP ALL tables first)")
            print("   2. Database connection issue")
            print("   3. Check models.py for errors")
            exit(1)
        
        # Step 2: Verify tables
        if verify_tables():
            # Step 3: Populate initial data
            populate_initial_data()
            
            print("\n" + "="*60)
            print("🎉 Database setup complete!")
            print("="*60)
            print("\n💡 Next steps:")
            print("   1. Run: python main.py")
            print("   2. Open: http://localhost:5000/docs")
            print("   3. Test your API!\n")
        else:
            print("\n⚠️  Setup completed with warnings. Check missing tables above.")
            
    except Exception as e:
        print("\n" + "="*60)
        print("❌ Database Setup Failed!")
        print("="*60)
        print(f"\nError: {str(e)}\n")
        import traceback
        traceback.print_exc()