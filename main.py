from dotenv import load_dotenv
load_dotenv()
import os
import warnings

# Fix timezone warning
os.environ.setdefault('TZ', 'UTC')

# Suppress tzlocal warning on Replit
if os.environ.get('REPL_ID'):
    warnings.filterwarnings('ignore', message='Can not find any timezone configuration')

# Apply timezone setting
try:
    import time
    time.tzset()
except (AttributeError, OSError):
    pass

from db_connection import engine, get_session
from models import Base, ConsumptionBaseline

# Check if running on Railway (Railway sets DATABASE_URL or PORT)
IS_RAILWAY = os.environ.get('DATABASE_URL') or os.environ.get('RAILWAY_ENVIRONMENT')

if IS_RAILWAY:
    print("\n" + "="*60)
    print("🚂 Railway environment detected - initializing database...")
    print("="*60)
    
    try:
        # Create all tables
        Base.metadata.create_all(engine)
        print("✅ Database tables created!")
        
        # Populate baselines if empty
        session = get_session()
        try:
            baseline_count = session.query(ConsumptionBaseline).count()
            if baseline_count == 0:
                print("📊 Populating baseline consumption data...")
                from utils.consumption_baselines import populate_baselines_to_db
                populate_baselines_to_db()
                print("✅ Baselines populated successfully!")
            else:
                print(f"✅ Baselines already exist ({baseline_count} records)")
        finally:
            session.close()
    except Exception as e:
        print(f"❌ Database initialization error: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("="*60 + "\n")

from flask import Flask
from datetime import timedelta
from api_routes.img_handle_routes import img_api_blueprint
from api_routes.recipes_handling_routes import recipes_handling_blueprint
from api_routes.users_handling_routes import users_handling_blueprint
from api_routes.kitchen_management_routes import kitchen_management_blueprint
from api_routes.meal_planner_routes import meal_planner_blueprint
from flask_jwt_extended import JWTManager
from flask_cors import CORS
import os
from flask_mail import Mail, Message
from flask_swagger_ui import get_swaggerui_blueprint

from api_routes.expiring_items_recipe_routes import expiring_items_recipe_blueprint

from db_connection import get_session
from models import ConsumptionBaseline
from utils.scheduler import ConsumptionScheduler
from utils.consumption_baselines import populate_baselines_to_db
from api_routes.consumption_prediction_routes import consumption_prediction_blueprint
from api_routes.smart_kitchen_setup_routes import smart_kitchen_setup_blueprint
import atexit

app = Flask(__name__)

# Enable CORS for all domains
# CORS(app, resources={r"/*": {"origins": "*"}})
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

app.config['JWT_SECRET_KEY'] = os.environ['JWT_SECRET']
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(days=6)
jwt = JWTManager(app)

app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '587'))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', 'Kitchensguardian@gmail.com')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', 'clkn vkjq jqvm xznq')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 
                                                     os.environ.get('MAIL_USERNAME', 'Kitchensguardian@gmail.com'))
mail = Mail(app)

# Register blueprints
app.register_blueprint(img_api_blueprint)
app.register_blueprint(recipes_handling_blueprint)
app.register_blueprint(users_handling_blueprint)
app.register_blueprint(kitchen_management_blueprint)
app.register_blueprint(meal_planner_blueprint)
app.register_blueprint(expiring_items_recipe_blueprint)
app.register_blueprint(consumption_prediction_blueprint) 
app.register_blueprint(smart_kitchen_setup_blueprint)

# ADD THESE LINES FOR AUTO SWAGGER UI
SWAGGER_URL = '/docs'
API_URL = '/swagger.json'

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "Kitchen Guardian API"
    }
)
app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

@app.route('/swagger.json')
def swagger_json():
    """Auto-generate swagger spec from Flask routes with parameter detection"""
    from flask import jsonify, request
    import inspect
    
    # ✅ FIXED: Properly detect HTTPS on Railway
    if os.environ.get('DATABASE_URL') or os.environ.get('RAILWAY_ENVIRONMENT'):
        scheme = 'https'  # Railway always uses HTTPS
    elif request.headers.get('X-Forwarded-Proto') == 'https':
        scheme = 'https'  # Behind HTTPS proxy
    elif request.is_secure:
        scheme = 'https'  # Direct HTTPS
    else:
        scheme = 'http'   # Local development
    
    swagger_spec = {
        "swagger": "2.0",
        "info": {
            "title": "Kitchen Guardian API",
            "description": "Kitchen Management and Recipe Generation API",
            "version": "1.0.0"
        },
        "basePath": "/",
        "schemes": [scheme],  # ✅ Now correctly uses HTTPS on Railway
        "securityDefinitions": {
            "Bearer": {
                "type": "apiKey",
                "name": "Authorization",
                "in": "header",
                "description": "JWT Authorization header. Example: 'Bearer {token}'"
            }
        },
        "paths": {}
    }
    
    # Define parameter templates for common endpoints
    endpoint_params = {
        # User endpoints
        '/api/register_user': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['first_name', 'last_name', 'email', 'password'],
                        'properties': {
                            'first_name': {'type': 'string', 'example': 'John'},
                            'last_name': {'type': 'string', 'example': 'Doe'},
                            'email': {'type': 'string', 'example': 'john@example.com'},
                            'password': {'type': 'string', 'example': 'password123'}
                        }
                    }
                }],
                'tags': ['Authentication']
            }
        },
        '/api/login': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['email', 'password'],
                        'properties': {
                            'email': {'type': 'string', 'example': 'john@example.com'},
                            'password': {'type': 'string', 'example': 'password123'}
                        }
                    }
                }],
                'tags': ['Authentication']
            }
        },
        '/api/verify_user': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['email', 'verification_code'],
                        'properties': {
                            'email': {'type': 'string', 'example': 'john@example.com'},
                            'verification_code': {'type': 'string', 'example': 'abc12'}
                        }
                    }
                }],
                'tags': ['Authentication']
            }
        },
        '/api/send_verification_code': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['email'],
                        'properties': {
                            'email': {'type': 'string', 'example': 'john@example.com'}
                        }
                    }
                }],
                'tags': ['Authentication']
            }
        },
        '/api/forgot_password': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['email'],
                        'properties': {
                            'email': {'type': 'string', 'example': 'john@example.com'}
                        }
                    }
                }],
                'tags': ['Authentication']
            }
        },
        '/api/reset_password': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['email', 'reset_code', 'new_password'],
                        'properties': {
                            'email': {'type': 'string', 'example': 'john@example.com'},
                            'reset_code': {'type': 'string', 'example': 'abc12'},
                            'new_password': {'type': 'string', 'example': 'newpassword123'}
                        }
                    }
                }],
                'tags': ['Authentication']
            }
        },
        '/api/change_password': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['current_password', 'new_password'],
                        'properties': {
                            'current_password': {'type': 'string', 'example': 'oldpassword123'},
                            'new_password': {'type': 'string', 'example': 'newpassword123'}
                        }
                    }
                }],
                'tags': ['Authentication'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/edit_user': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'first_name': {'type': 'string', 'example': 'John', 'description': 'Optional - User first name'},
                            'last_name': {'type': 'string', 'example': 'Doe', 'description': 'Optional - User last name'},
                            'avatar': {'type': 'string', 'example': 'data:image/png;base64,iVBORw0KGgoAAAANS...', 'description': 'Optional - Base64 encoded profile picture'}
                        }
                    }
                }],
                'tags': ['Authentication'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/get_user_profile': {
            'GET': {
                'parameters': [],
                'tags': ['Authentication'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': 'Returns current user profile including avatar (base64)'
                    }
                }
            }
        },
        # Kitchen endpoints
        '/api/kitchen/create': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_name'],
                        'properties': {
                            'kitchen_name': {'type': 'string', 'example': 'My Home Kitchen'}
                        }
                    }
                }],
                'tags': ['Kitchen Management'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/join_with_code': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['invitation_code'],
                        'properties': {
                            'invitation_code': {'type': 'string', 'example': '123456'},
                            'user_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011', 'description': 'Optional - Required only when adding member without authentication (for host approval flow)'}
                        }
                    }
                }],
                'tags': ['Kitchen Management']
            }
        },
        '/api/kitchen/add_items': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id', 'items'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'},
                            'items': {
                                'type': 'array',
                                'items': {
                                    'type': 'object',
                                    'required': ['name', 'quantity', 'unit'],
                                    'properties': {
                                        'name': {'type': 'string', 'example': 'tomato'},
                                        'quantity': {'type': 'number', 'example': 5},
                                        'unit': {'type': 'string', 'example': 'kg'},
                                        'group': {'type': 'string', 'example': 'vegetables'},
                                        'thumbnail': {'type': 'string', 'example': 'data:image/png;base64,...', 'description': 'Optional base64 encoded image'},
                                        'expiry_date': {'type': 'string', 'example': '7 days', 'description': 'Optional expiry date (e.g., "7 days", "2 weeks", "3 months")'}
                                    }
                                }
                            }
                        }
                    }
                }],
                'tags': ['Kitchen Inventory'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/remove_items': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id', 'item_ids'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'},
                            'item_ids': {
                                'type': 'array',
                                'items': {'type': 'string'},
                                'example': ['abc123def456', 'xyz789ghi012'],
                                'description': 'Array of item_ids to remove'
                            }
                        }
                    }
                }],
                'tags': ['Kitchen Inventory'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/update_items': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id', 'items'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'},
                            'items': {
                                'type': 'array',
                                'items': {
                                    'type': 'object',
                                    'required': ['item_id'],
                                    'properties': {
                                        'item_id': {'type': 'string', 'example': 'abc123def456', 'description': 'Required - unique item identifier'},
                                        'name': {'type': 'string', 'example': 'tomato', 'description': 'Optional - update item name'},
                                        'quantity': {'type': 'number', 'example': 10, 'description': 'Optional - update quantity (0 or less removes item)'},
                                        'unit': {'type': 'string', 'example': 'kg', 'description': 'Optional - update unit'},
                                        'group': {'type': 'string', 'example': 'vegetables', 'description': 'Optional - update group'},
                                        'thumbnail': {'type': 'string', 'example': 'data:image/png;base64,...', 'description': 'Optional - update thumbnail'},
                                        'expiry_date': {'type': 'string', 'example': '7 days', 'description': 'Optional - update expiry date'}
                                    }
                                }
                            }
                        }
                    }
                }],
                'tags': ['Kitchen Inventory'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/list_items': {
            'GET': {
                'parameters': [{
                    'name': 'kitchen_id',
                    'in': 'query',
                    'required': True,
                    'type': 'string',
                    'description': 'Kitchen ID',
                    'example': '507f1f77bcf86cd799439011'
                }],
                'tags': ['Kitchen Inventory'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/view': {
            'GET': {
                'parameters': [{
                    'name': 'kitchen_id',
                    'in': 'query',
                    'required': True,
                    'type': 'string',
                    'description': 'Kitchen ID'
                }],
                'tags': ['Kitchen Management'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/set_date_range': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id', 'start_date', 'end_date'],
                        'properties': {
                            'kitchen_id': {
                                'type': 'string', 
                                'example': '507f1f77bcf86cd799439011',
                                'description': 'Kitchen ID'
                            },
                            'start_date': {
                                'type': 'string',
                                'example': '2025-11-20',
                                'description': 'Start date in YYYY-MM-DD format'
                            },
                            'end_date': {
                                'type': 'string',
                                'example': '2025-12-20',
                                'description': 'End date in YYYY-MM-DD format (must be after start_date)'
                            }
                        }
                    }
                }],
                'tags': ['Kitchen Management'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': 'Kitchen date range set successfully'
                    },
                    '400': {
                        'description': 'Invalid input or end_date before start_date'
                    },
                    '403': {
                        'description': 'Only host or co-host can set date range'
                    }
                }
            }
        },
        '/api/kitchen/get_date_range': {
            'GET': {
                'parameters': [{
                    'name': 'kitchen_id',
                    'in': 'query',
                    'required': True,
                    'type': 'string',
                    'description': 'Kitchen ID',
                    'example': '507f1f77bcf86cd799439011'
                }],
                'tags': ['Kitchen Management'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': 'Returns kitchen date range (may be null if not set)'
                    },
                    '403': {
                        'description': 'User is not a member of the kitchen'
                    }
                }
            }
        },
        '/api/kitchen/suggest_recipes_expiring_items': {
            'GET': {
                'parameters': [{
                    'name': 'kitchen_id',
                    'in': 'query',
                    'required': True,
                    'type': 'string',
                    'description': 'Kitchen ID to check for expiring items',
                    'example': '507f1f77bcf86cd799439011'
                }],
                'tags': ['AI Features'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': 'Returns 1 recipe using expiring items, or null if no items are expiring'
                    },
                    '400': {
                        'description': 'Invalid kitchen_id'
                    },
                    '403': {
                        'description': 'User is not a member of the kitchen'
                    },
                    '404': {
                        'description': 'Kitchen not found'
                    },
                    '429': {
                        'description': 'Too many requests to AI service'
                    },
                    '500': {
                        'description': 'Recipe generation failed'
                    }
                }
            }
        },
        '/api/kitchen/get_members': {
            'GET': {
                'parameters': [{
                    'name': 'kitchen_id',
                    'in': 'query',
                    'required': True,
                    'type': 'string',
                    'description': 'Kitchen ID'
                }],
                'tags': ['Kitchen Management'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/remove': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'}
                        }
                    }
                }],
                'tags': ['Kitchen Management'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/kick_member': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id', 'member_id'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'},
                            'member_id': {'type': 'string', 'example': '507f1f77bcf86cd799439012'}
                        }
                    }
                }],
                'tags': ['Kitchen Management'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/make_cohost': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id', 'member_id'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'},
                            'member_id': {'type': 'string', 'example': '507f1f77bcf86cd799439012'}
                        }
                    }
                }],
                'tags': ['Kitchen Management'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/demote_cohost': {
            'POST': {
                'summary': 'Demote co-host to member',
                'description': 'Demote a co-host back to regular member status. Only the kitchen host can perform this action.',
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id', 'member_id'],
                        'properties': {
                            'kitchen_id': {
                                'type': 'string', 
                                'example': '1',
                                'description': 'The ID of the kitchen'
                            },
                            'member_id': {
                                'type': 'string', 
                                'example': '2',
                                'description': 'The ID of the co-host member to demote'
                            }
                        }
                    }
                }],
                'tags': ['Kitchen Management'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': 'Co-host successfully demoted to member'
                    },
                    '400': {
                        'description': 'Invalid kitchen ID or member ID'
                    },
                    '403': {
                        'description': 'Only the host can demote co-hosts'
                    },
                    '404': {
                        'description': 'Kitchen or member not found'
                    },
                    '409': {
                        'description': 'Member is not a co-host'
                    }
                }
            }
        },
        '/api/kitchen/leave': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'}
                        }
                    }
                }],
                'tags': ['Kitchen Management'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/refresh_invitation_code': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'}
                        }
                    }
                }],
                'tags': ['Kitchen Management'],
                'security': [{'Bearer': []}]
            }
        },
        # Recipe endpoints
        '/api/generate_recipes': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'},
                            'instructions': {'type': 'string', 'example': 'Make something spicy'}
                        }
                    }
                }],
                'tags': ['Recipes'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/recipe/add_to_fav': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['_id'],
                        'properties': {
                            '_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'}
                        }
                    }
                }],
                'tags': ['Recipes'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/recipe/remove_from_fav': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['recipe_id'],
                        'properties': {
                            'recipe_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'}
                        }
                    }
                }],
                'tags': ['Recipes'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/recipe/list_fav': {
            'GET': {
                'parameters': [],
                'tags': ['Recipes'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/mark_recipe_finished': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id', 'recipe_id'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'},
                            'recipe_id': {'type': 'string', 'example': '507f1f77bcf86cd799439012'}
                        }
                    }
                }],
                'tags': ['Recipes'],
                'security': [{'Bearer': []}]
            }
        },
        # Shopping list endpoints
        '/api/kitchen/add_item_to_list': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id', 'name', 'quantity', 'unit', 'bucket_type'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'},
                            'name': {'type': 'string', 'example': 'milk'},
                            'quantity': {'type': 'number', 'example': 2},
                            'unit': {'type': 'string', 'example': 'litre'},
                            'bucket_type': {'type': 'string', 'enum': ['mylist', 'requested'], 'example': 'mylist'},
                            'thumbnail': {'type': 'string', 'example': 'data:image/png;base64,...', 'description': 'Optional base64 encoded image'},
                            'expiry_date': {'type': 'string', 'example': '7 days', 'description': 'Optional expiry date'}
                        }
                    }
                }],
                'tags': ['Shopping Lists'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/request_item': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id', 'items'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'},
                            'items': {
                                'type': 'array',
                                'items': {
                                    'type': 'object',
                                    'required': ['name', 'quantity', 'unit'],
                                    'properties': {
                                        'name': {'type': 'string', 'example': 'bread'},
                                        'quantity': {'type': 'number', 'example': 1},
                                        'unit': {'type': 'string', 'example': 'count'}
                                    }
                                }
                            }
                        }
                    }
                }],
                'tags': ['Shopping Lists'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/delete_items': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id', 'item_ids'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'},
                            'item_ids': {
                                'type': 'array',
                                'items': {'type': 'string'},
                                'example': ['item_id_1', 'item_id_2']
                            }
                        }
                    }
                }],
                'tags': ['Shopping Lists'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/update_item': {
                    'POST': {
                        'parameters': [{
                            'name': 'body',
                            'in': 'body',
                            'required': True,
                            'schema': {
                                'type': 'object',
                                'required': ['kitchen_id', 'item_id'],
                                'properties': {
                                    'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'},
                                    'item_id': {'type': 'string', 'example': 'abc123def456'},
                                    'name': {'type': 'string', 'example': 'milk'},
                                    'quantity': {'type': 'number', 'example': 3},
                                    'unit': {'type': 'string', 'example': 'litre'},
                                    'thumbnail': {'type': 'string', 'example': 'data:image/png;base64,...', 'description': 'Optional base64 encoded image'},
                                    'expiry_date': {'type': 'string', 'example': '7 days', 'description': 'Optional expiry date'}
                                }
                            }
                        }],
                        'tags': ['Shopping Lists'],
                        'security': [{'Bearer': []}]
                    }
                },
        '/api/kitchen/update_bucket_type': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id', 'item_ids', 'bucket_type'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'},
                            'item_ids': {
                                'type': 'array',
                                'items': {'type': 'string'},
                                'example': ['item_id_1', 'item_id_2']
                            },
                            'bucket_type': {'type': 'string', 'enum': ['mylist', 'requested'], 'example': 'mylist'}
                        }
                    }
                }],
                'tags': ['Shopping Lists'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/get_all_mylist_items': {
            'GET': {
                'parameters': [
                    {
                        'name': 'kitchen_id',
                        'in': 'query',
                        'required': True,
                        'type': 'string',
                        'description': 'Kitchen ID'
                    },
                    {
                        'name': 'bucket_type',
                        'in': 'query',
                        'required': False,
                        'type': 'string',
                        'enum': ['mylist', 'requested'],
                        'description': 'Filter by bucket type'
                    }
                ],
                'tags': ['Shopping Lists'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/get_user_requested_items': {
            'GET': {
                'parameters': [{
                    'name': 'kitchen_id',
                    'in': 'query',
                    'required': True,
                    'type': 'string',
                    'description': 'Kitchen ID'
                }],
                'tags': ['Shopping Lists'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/add_mylist_items_to_kitchen_inventory': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'}
                        }
                    }
                }],
                'tags': ['Shopping Lists'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/get_ai_generated_list': {
            'GET': {
                'parameters': [{
                    'name': 'kitchen_id',
                    'in': 'query',
                    'required': True,
                    'type': 'string',
                    'description': 'Kitchen ID'
                }],
                'tags': ['AI Features'],
                'security': [{'Bearer': []}]
            }
        },
        # Pantry endpoints
        '/api/kitchen/pantry/create': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id', 'pantries'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'},
                            'pantries': {
                                'type': 'array',
                                'items': {
                                    'type': 'object',
                                    'properties': {
                                        'pantry_name': {'type': 'string', 'example': 'Fridge'}
                                    }
                                },
                                'example': [
                                    {'pantry_name': 'Fridge'},
                                    {'pantry_name': 'Freezer'},
                                    {'pantry_name': 'Cabinet'}
                                ]
                            }
                        }
                    }
                }],
                'tags': ['Pantry Management'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/pantry/list': {
            'GET': {
                'parameters': [{
                    'name': 'kitchen_id',
                    'in': 'query',
                    'required': True,
                    'type': 'string',
                    'description': 'Kitchen ID'
                }],
                'tags': ['Pantry Management'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/pantry/delete': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id', 'pantry_id'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'},
                            'pantry_id': {'type': 'string', 'example': 'abc123def456'}
                        }
                    }
                }],
                'tags': ['Pantry Management'],
                'security': [{'Bearer': []}]
            }
        },
        # Receipt scanning
        '/api/scan_recipt': {
            'POST': {
                'consumes': ['multipart/form-data'],
                'parameters': [
                    {
                        'name': 'file',
                        'in': 'formData',
                        'type': 'file',
                        'required': True,
                        'description': 'Receipt image (PNG, JPG, JPEG - max 10MB)'
                    },
                    {
                        'name': 'currency',
                        'in': 'formData',
                        'type': 'string',
                        'required': False,
                        'default': 'USD',
                        'description': 'Currency code (e.g., USD, EUR). Default: USD'
                    },
                    {
                        'name': 'country',
                        'in': 'formData',
                        'type': 'string',
                        'required': False,
                        'default': 'USA',
                        'description': 'Country code (e.g., USA, GBR). Default: USA'
                    },
                    {
                        'name': 'use_google_document',
                        'in': 'formData',
                        'type': 'boolean',
                        'required': False,
                        'default': True,
                        'description': (
                            'Select scanning mode. '
                            'true = Google Document AI + OpenAI enhancement, '
                            'false = OpenAI Vision direct.'
                        )
                    }
                ],
                'tags': ['Receipt Scanning'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': 'Receipt successfully scanned'
                    },
                    '400': {
                        'description': 'Bad request / scanning failed'
                    },
                    '403': {
                        'description': 'Not authorized (host/co-host only)'
                    },
                    '413': {
                        'description': 'File too large (>10MB)'
                    },
                    '500': {
                        'description': 'Server error'
                    }
                }
            }
        },


        '/api/get_scan_history': {
            'GET': {
                'parameters': [{
                    'name': 'page',
                    'in': 'query',
                    'required': False,
                    'type': 'integer',
                    'default': 0,
                    'description': 'Page number (default: 0)'
                }],
                'tags': ['Receipt Scanning'],
                'security': [{'Bearer': []}]
            }
        },
        # Admin, DB clean ednpoints
        '/api/admin/database_stats': {
            'GET': {
                'parameters': [],
                'tags': ['Admin'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': 'Returns database size, quota usage, and collection statistics'
                    }
                }
            }
        },
        '/api/admin/reset_database': {
            'POST': {
                'parameters': [],
                'tags': ['Admin'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': '⚠️ DANGER: Deletes ALL data from ALL collections. Development only!'
                    }
                }
            }
        },

        # Invitations
        '/api/kitchen/invite': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id', 'email'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'},
                            'email': {'type': 'string', 'example': 'friend@example.com'}
                        }
                    }
                }],
                'tags': ['Invitations'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/respond_to_invitation': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['invitation_id', 'response'],
                        'properties': {
                            'invitation_id': {'type': 'string', 'example': 'inv_123456'},
                            'response': {'type': 'string', 'enum': ['accepted', 'denied'], 'example': 'accepted'}
                        }
                    }
                }],
                'tags': ['Invitations'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/invitations': {
            'GET': {
                'parameters': [],
                'tags': ['Invitations'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/kitchen/list_user_kitchens': {
            'GET': {
                'parameters': [],
                'tags': ['Kitchen Management'],
                'security': [{'Bearer': []}]
            }
        },
        # Meal Planner Endpoints
        '/api/meal_plan/create': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['kitchen_id', 'date', 'meal_type', 'recipe_id'],
                        'properties': {
                            'kitchen_id': {'type': 'string', 'example': '507f1f77bcf86cd799439011'},
                            'date': {'type': 'string', 'example': '2025-11-02', 'description': 'Date in YYYY-MM-DD format'},
                            'meal_type': {'type': 'string', 'enum': ['breakfast', 'lunch', 'dinner', 'snack'], 'example': 'breakfast'},
                            'recipe_id': {'type': 'string', 'example': '507f1f77bcf86cd799439012', 'description': 'ID of recipe from generated_recipes'},
                            'notes': {'type': 'string', 'example': 'Add extra cheese', 'description': 'Optional notes'}
                        }
                    }
                }],
                'tags': ['Meal Planner'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/meal_plan/list': {
            'GET': {
                'parameters': [
                    {
                        'name': 'kitchen_id',
                        'in': 'query',
                        'required': True,
                        'type': 'string',
                        'description': 'Kitchen ID'
                    },
                    {
                        'name': 'start_date',
                        'in': 'query',
                        'required': False,
                        'type': 'string',
                        'description': 'Filter from date (YYYY-MM-DD)'
                    },
                    {
                        'name': 'end_date',
                        'in': 'query',
                        'required': False,
                        'type': 'string',
                        'description': 'Filter until date (YYYY-MM-DD)'
                    },
                    {
                        'name': 'meal_type',
                        'in': 'query',
                        'required': False,
                        'type': 'string',
                        'enum': ['breakfast', 'lunch', 'dinner', 'snack'],
                        'description': 'Filter by meal type'
                    },
                    {
                        'name': 'status',
                        'in': 'query',
                        'required': False,
                        'type': 'string',
                        'enum': ['all', 'completed', 'pending'],
                        'description': 'Filter by completion status (default: all)'
                    }
                ],
                'tags': ['Meal Planner'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/meal_plan/get_by_date': {
            'GET': {
                'parameters': [
                    {
                        'name': 'kitchen_id',
                        'in': 'query',
                        'required': True,
                        'type': 'string',
                        'description': 'Kitchen ID'
                    },
                    {
                        'name': 'date',
                        'in': 'query',
                        'required': True,
                        'type': 'string',
                        'description': 'Specific date (YYYY-MM-DD)'
                    }
                ],
                'tags': ['Meal Planner'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/meal_plan/update': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['meal_plan_id'],
                        'properties': {
                            'meal_plan_id': {'type': 'string', 'example': 'abc123def456', 'description': 'Required - Meal plan ID'},
                            'recipe_id': {'type': 'string', 'example': '507f1f77bcf86cd799439015', 'description': 'Optional - Change recipe'},
                            'meal_type': {'type': 'string', 'enum': ['breakfast', 'lunch', 'dinner', 'snack'], 'description': 'Optional - Change meal type'},
                            'notes': {'type': 'string', 'example': 'Updated notes', 'description': 'Optional - Update notes'}
                        }
                    }
                }],
                'tags': ['Meal Planner'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/meal_plan/delete': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'properties': {
                            'meal_plan_id': {
                                'type': 'string', 
                                'example': 'abc123def456',
                                'description': 'Delete a specific meal plan by ID'
                            },
                            'kitchen_id': {
                                'type': 'string',
                                'example': '507f1f77bcf86cd799439011',
                                'description': 'Required when deleting by date - Kitchen ID'
                            },
                            'date': {
                                'type': 'string',
                                'example': '2025-11-02',
                                'description': 'Required when deleting by date - Date in YYYY-MM-DD format (deletes all plans for this date)'
                            }
                        },
                        'description': 'Provide either meal_plan_id OR (kitchen_id + date)'
                    }
                }],
                'tags': ['Meal Planner'],
                'security': [{'Bearer': []}]
            }
        },
        '/api/meal_plan/mark_completed': {
            'POST': {
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['meal_plan_id'],
                        'properties': {
                            'meal_plan_id': {'type': 'string', 'example': 'abc123def456'}
                        }
                    }
                }],
                'tags': ['Meal Planner'],
                'security': [{'Bearer': []}]
            }
        },
    # ============ Consumption Algorithm endpoint ============
        '/api/consumption/predict': {
            'GET': {
                'summary': 'Get predicted consumption days for an item',
                'description': 'Returns predicted consumption time with optional quantity-aware predictions',
                'parameters': [
                    {
                        'name': 'kitchen_id',
                        'in': 'query',
                        'required': True,
                        'type': 'string',
                        'description': 'Kitchen ID'
                    },
                    {
                        'name': 'item_name',
                        'in': 'query',
                        'required': True,
                        'type': 'string',
                        'description': 'Item name to get prediction for'
                    },
                    {
                        'name': 'quantity',
                        'in': 'query',
                        'required': False,
                        'type': 'number',
                        'description': 'Quantity to predict for (optional)'
                    },
                    {
                        'name': 'unit',
                        'in': 'query',
                        'required': False,
                        'type': 'string',
                        'description': 'Unit of measurement (required if quantity provided)'
                    }
                ],
                'tags': ['Consumption Prediction'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': 'Returns predicted consumption days and pattern details'
                    },
                    '400': {
                        'description': 'Invalid parameters'
                    },
                    '403': {
                        'description': 'Unauthorized - not a member of this kitchen'
                    },
                    '404': {
                        'description': 'Kitchen not found'
                    }
                }
            }
        },
        
        '/api/consumption/patterns': {
            'GET': {
                'summary': 'Get all personalized consumption patterns',
                'description': 'Returns all learned consumption patterns for a kitchen with sorting options',
                'parameters': [
                    {
                        'name': 'kitchen_id',
                        'in': 'query',
                        'required': True,
                        'type': 'string',
                        'description': 'Kitchen ID'
                    },
                    {
                        'name': 'sort_by',
                        'in': 'query',
                        'required': False,
                        'type': 'string',
                        'enum': ['item_name', 'personalized_days', 'confidence', 'sample_count'],
                        'description': 'Field to sort by'
                    },
                    {
                        'name': 'order',
                        'in': 'query',
                        'required': False,
                        'type': 'string',
                        'enum': ['asc', 'desc'],
                        'description': 'Sort order (default: asc)'
                    }
                ],
                'tags': ['Consumption Prediction'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': 'Returns list of consumption patterns with rate information'
                    }
                }
            }
        },
        
        '/api/consumption/history': {
            'GET': {
                'summary': 'Get consumption event history',
                'description': 'Returns consumption events with filtering and analytics',
                'parameters': [
                    {
                        'name': 'kitchen_id',
                        'in': 'query',
                        'required': True,
                        'type': 'string',
                        'description': 'Kitchen ID'
                    },
                    {
                        'name': 'item_name',
                        'in': 'query',
                        'required': False,
                        'type': 'string',
                        'description': 'Filter by specific item'
                    },
                    {
                        'name': 'method',
                        'in': 'query',
                        'required': False,
                        'type': 'string',
                        'enum': ['auto', 'manual', 'recipe'],
                        'description': 'Filter by consumption method'
                    },
                    {
                        'name': 'limit',
                        'in': 'query',
                        'required': False,
                        'type': 'integer',
                        'default': 50,
                        'description': 'Maximum number of events (max 200)'
                    },
                    {
                        'name': 'days',
                        'in': 'query',
                        'required': False,
                        'type': 'integer',
                        'description': 'Only show events from last N days'
                    }
                ],
                'tags': ['Consumption Prediction'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': 'Returns consumption events with analytics'
                    }
                }
            }
        },
        
        '/api/consumption/check_now': {
            'POST': {
                'summary': 'Manually trigger consumption check',
                'description': 'Forces immediate consumption prediction check (hosts only)',
                'parameters': [
                    {
                        'name': 'body',
                        'in': 'body',
                        'required': False,
                        'schema': {
                            'type': 'object',
                            'properties': {
                                'kitchen_id': {
                                    'type': 'string',
                                    'description': 'Check specific kitchen only (optional)'
                                }
                            }
                        }
                    }
                ],
                'tags': ['Consumption Prediction'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': 'Returns check summary with detailed results'
                    }
                }
            }
        },
        
        '/api/consumption/scheduler/status': {
            'GET': {
                'summary': 'Get scheduler status',
                'description': 'Returns status of scheduled jobs and next run time',
                'parameters': [],
                'tags': ['Consumption Prediction'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': 'Returns scheduler status'
                    }
                }
            }
        },
        
        '/api/consumption/stats': {
            'GET': {
                'summary': 'Get consumption statistics',
                'description': 'Returns comprehensive statistics and analytics for a kitchen',
                'parameters': [
                    {
                        'name': 'kitchen_id',
                        'in': 'query',
                        'required': True,
                        'type': 'string',
                        'description': 'Kitchen ID'
                    }
                ],
                'tags': ['Consumption Prediction'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': 'Returns comprehensive statistics dashboard data'
                    }
                }
            }
        },
        
        '/api/consumption/insights': {
            'GET': {
                'summary': 'Get AI-powered insights',
                'description': 'Returns actionable insights and recommendations based on consumption patterns',
                'parameters': [
                    {
                        'name': 'kitchen_id',
                        'in': 'query',
                        'required': True,
                        'type': 'string',
                        'description': 'Kitchen ID'
                    }
                ],
                'tags': ['Consumption Prediction'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': 'Returns AI-powered insights and recommendations'
                    }
                }
            }
        },
        '/api/consumption/confirmations/pending': {
            'GET': {
                'summary': 'Get pending depletion confirmations',
                'description': 'Returns items that system predicts are depleted and need user confirmation',
                'parameters': [
                    {
                        'name': 'kitchen_id',
                        'in': 'query',
                        'required': True,
                        'type': 'string',
                        'description': 'Kitchen ID'
                    }
                ],
                'tags': ['Consumption Prediction'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': 'Returns list of pending confirmations with item details'
                    },
                    '403': {
                        'description': 'Unauthorized - not a member'
                    },
                    '404': {
                        'description': 'Kitchen not found'
                    }
                }
            }
        },
        
        '/api/consumption/confirmations/respond': {
            'POST': {
                'summary': 'Confirm or deny item depletion',
                'description': 'User responds to depletion prediction - confirms (item is finished) or denies (item still exists)',
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['confirmation_id', 'response'],
                        'properties': {
                            'confirmation_id': {
                                'type': 'string',
                                'example': 'abc123def456',
                                'description': 'Confirmation ID from pending confirmations'
                            },
                            'response': {
                                'type': 'string',
                                'enum': ['confirmed', 'denied'],
                                'example': 'confirmed',
                                'description': 'confirmed = item is finished, denied = item still exists'
                            },
                            'actual_quantity_remaining': {
                                'type': 'number',
                                'example': 0.5,
                                'description': 'Optional - remaining quantity if response is denied'
                            }
                        }
                    }
                }],
                'tags': ['Consumption Prediction'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': 'Response processed - item removed/kept based on confirmation'
                    },
                    '400': {
                        'description': 'Invalid response type'
                    },
                    '403': {
                        'description': 'Unauthorized'
                    },
                    '404': {
                        'description': 'Confirmation not found'
                    }
                }
            }
        },
        
        '/api/consumption/confirmations/count': {
            'GET': {
                'summary': 'Get count of pending confirmations',
                'description': 'Returns number of items awaiting user confirmation (for badge display)',
                'parameters': [
                    {
                        'name': 'kitchen_id',
                        'in': 'query',
                        'required': True,
                        'type': 'string',
                        'description': 'Kitchen ID'
                    }
                ],
                'tags': ['Consumption Prediction'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': 'Returns count of pending confirmations'
                    }
                }
            }
        },
        
        '/api/consumption/usage/history': {
            'GET': {
                'summary': 'Get partial usage history',
                'description': 'Returns events when items were used but not fully depleted (e.g., recipes using partial quantities)',
                'parameters': [
                    {
                        'name': 'kitchen_id',
                        'in': 'query',
                        'required': True,
                        'type': 'string',
                        'description': 'Kitchen ID'
                    },
                    {
                        'name': 'item_name',
                        'in': 'query',
                        'required': False,
                        'type': 'string',
                        'description': 'Filter by specific item'
                    },
                    {
                        'name': 'limit',
                        'in': 'query',
                        'required': False,
                        'type': 'integer',
                        'default': 50,
                        'description': 'Maximum number of events (max 200)'
                    },
                    {
                        'name': 'days',
                        'in': 'query',
                        'required': False,
                        'type': 'integer',
                        'description': 'Only show events from last N days'
                    }
                ],
                'tags': ['Consumption Prediction'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {
                        'description': 'Returns list of partial usage events with analytics'
                    }
                }
            }
        },
        # ─── Smart Kitchen Setup ──────────────────────────────────────────────────
        '/api/kitchen/setup/scan': {
            'POST': {
                'summary': 'Smart Kitchen Setup - Scan Images',
                'description': (
                    'Scan 1-5 kitchen area photos with AI (GPT-4o Vision) to detect food items. '
                    'Returns auto_confirmed (confidence >= 70%) and needs_review lists. '
                    'Expiry dates are resolved from the existing baseline database, not from AI.\n\n'
                    'Image field naming options:\n'
                    '  Option A (named areas): image_fridge, image_freezer, image_pantry, image_spices, image_miscellaneous\n'
                    '  Option B (indexed):     image_0 .. image_4  (+ optional area_0 .. area_4)\n'
                    '  Option C (single):      image               (+ optional area field)\n\n'
                    'Also requires kitchen_id as a form field.'
                ),
                'consumes': ['multipart/form-data'],
                'parameters': [
                    {'name': 'kitchen_id',         'in': 'formData', 'required': True,  'type': 'integer', 'description': 'Kitchen ID'},
                    {'name': 'image_fridge',        'in': 'formData', 'required': False, 'type': 'file',    'description': 'Photo of fridge interior'},
                    {'name': 'image_freezer',       'in': 'formData', 'required': False, 'type': 'file',    'description': 'Photo of freezer interior'},
                    {'name': 'image_pantry',        'in': 'formData', 'required': False, 'type': 'file',    'description': 'Photo of pantry / dry storage'},
                    {'name': 'image_spices',        'in': 'formData', 'required': False, 'type': 'file',    'description': 'Photo of spices / seasonings shelf'},
                    {'name': 'image_miscellaneous', 'in': 'formData', 'required': False, 'type': 'file',    'description': 'Photo of countertop or miscellaneous area'},
                ],
                'tags': ['Smart Kitchen Setup'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {'description': 'Returns session_id, auto_confirmed[], needs_review[]'},
                    '400': {'description': 'Missing kitchen_id or no images provided'},
                    '403': {'description': 'Only host or co-host can scan'},
                    '401': {'description': 'Unauthorized'},
                }
            }
        },
        '/api/kitchen/setup/edit': {
            'PUT': {
                'summary': 'Smart Kitchen Setup - Edit Detected Items',
                'description': (
                    'After scanning, the user reviews the AI-detected list and edits it. '
                    'Call this endpoint with the updated list to save changes back to the session.\n\n'
                    'The user can:\n'
                    '  - Edit name, quantity, unit, recommended_storage, expiry_date\n'
                    '  - Remove items (simply omit them from the list)\n'
                    '  - Add new items manually\n\n'
                    'Expiry is auto-resolved from baselines for any item missing expiry_date.'
                ),
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['session_id', 'items'],
                        'properties': {
                            'session_id': {'type': 'string', 'example': 'a1b2c3d4e5f6...'},
                            'items': {
                                'type': 'array',
                                'items': {
                                    'type': 'object',
                                    'required': ['name'],
                                    'properties': {
                                        'name':                 {'type': 'string',  'example': 'whole milk'},
                                        'quantity':             {'type': 'number',  'example': 2},
                                        'unit':                 {'type': 'string',  'example': 'litre', 'description': 'kg | grams | litre | mL | pounds | ounces | count'},
                                        'recommended_storage':  {'type': 'string',  'example': 'fridge', 'description': 'fridge | freezer | pantry | cabinet | counter'},
                                        'expiry_date':          {'type': 'string',  'example': '7 days', 'description': 'Optional - auto-calculated from baselines if omitted'},
                                        'brand':                {'type': 'string',  'example': 'Heinz',  'description': 'Optional brand name'},
                                        'area':                 {'type': 'string',  'example': 'fridge', 'description': 'Kitchen area this item came from'},
                                        'temp_id':              {'type': 'string',  'example': 'abc123', 'description': 'Keep the original temp_id to maintain item identity'},
                                    }
                                }
                            }
                        }
                    }
                }],
                'tags': ['Smart Kitchen Setup'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {'description': 'Updated items saved to session'},
                    '400': {'description': 'Missing session_id or invalid body'},
                    '403': {'description': 'Only host or co-host can edit'},
                    '404': {'description': 'Session not found'},
                    '409': {'description': 'Session already confirmed'},
                }
            }
        },
        '/api/kitchen/setup/confirm': {
            'POST': {
                'summary': 'Smart Kitchen Setup - Confirm and Populate Inventory',
                'description': (
                    'Finalises the setup by adding all confirmed items to the kitchen inventory.\n\n'
                    'Uses the session\'s current item list (as saved by /edit).\n'
                    'Optionally accepts an inline "items" list to override the session list.\n\n'
                    'Items are merged with existing inventory (quantities summed for duplicates).\n'
                    'Thumbnails generated via DALL-E. Expiry always resolved from baselines.\n'
                    'Only host or co-host can call this.'
                ),
                'parameters': [{
                    'name': 'body',
                    'in': 'body',
                    'required': True,
                    'schema': {
                        'type': 'object',
                        'required': ['session_id'],
                        'properties': {
                            'session_id': {'type': 'string', 'example': 'a1b2c3d4e5f6...'},
                            'items': {
                                'type': 'array',
                                'description': 'Optional override list. If omitted, uses the session\'s saved item list.',
                                'items': {
                                    'type': 'object',
                                    'required': ['name'],
                                    'properties': {
                                        'name':                {'type': 'string', 'example': 'whole milk'},
                                        'quantity':            {'type': 'number', 'example': 2},
                                        'unit':                {'type': 'string', 'example': 'litre'},
                                        'recommended_storage': {'type': 'string', 'example': 'fridge'},
                                        'expiry_date':         {'type': 'string', 'example': '7 days'},
                                    }
                                }
                            }
                        }
                    }
                }],
                'tags': ['Smart Kitchen Setup'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {'description': 'Kitchen inventory populated successfully'},
                    '400': {'description': 'Missing session_id or no items to confirm'},
                    '403': {'description': 'Only host or co-host can confirm'},
                    '404': {'description': 'Session not found'},
                    '409': {'description': 'Session already confirmed'},
                }
            }
        },
        '/api/kitchen/setup/history': {
            'GET': {
                'summary': 'Smart Kitchen Setup - Scan Session History',
                'description': (
                    'Returns paginated list of all setup scan sessions for a kitchen.\n'
                    'Used for the "Re-scan My Kitchen" feature in Profile Settings.\n'
                    'Any kitchen member can view the history.'
                ),
                'parameters': [
                    {'name': 'kitchen_id', 'in': 'query', 'required': True,  'type': 'integer', 'description': 'Kitchen ID'},
                    {'name': 'page',       'in': 'query', 'required': False, 'type': 'integer', 'description': 'Page number (default 0, page size = 10)'},
                ],
                'tags': ['Smart Kitchen Setup'],
                'security': [{'Bearer': []}],
                'responses': {
                    '200': {'description': 'Returns paginated list of scan sessions'},
                    '400': {'description': 'Missing kitchen_id'},
                    '403': {'description': 'Not a kitchen member'},
                    '404': {'description': 'Kitchen not found'},
                }
            }
        },
    }

    # Auto-discover all routes
    for rule in app.url_map.iter_rules():
        if rule.endpoint not in ['static', 'swagger_json', 'swagger_ui.show', 'swagger_ui.static']:
            path = str(rule)
            methods = [m for m in rule.methods if m not in ['HEAD', 'OPTIONS']]
            
            if path not in swagger_spec["paths"]:
                swagger_spec["paths"][path] = {}
            
            for method in methods:
                # Check if we have predefined parameters for this endpoint
                if path in endpoint_params and method in endpoint_params[path]:
                    swagger_spec["paths"][path][method.lower()] = {
                        "summary": endpoint_params[path][method].get('summary', f"{method} {path}"),
                        "description": endpoint_params[path][method].get('description', f"Endpoint: {rule.endpoint}"),
                        "produces": ["application/json"],
                        "parameters": endpoint_params[path][method].get('parameters', []),
                        "tags": endpoint_params[path][method].get('tags', ['default']),
                        "responses": {
                            "200": {"description": "Success"},
                            "400": {"description": "Bad Request"},
                            "401": {"description": "Unauthorized"},
                            "403": {"description": "Forbidden"},
                            "404": {"description": "Not Found"}
                        }
                    }
                    
                    # Add security if specified
                    if 'security' in endpoint_params[path][method]:
                        swagger_spec["paths"][path][method.lower()]["security"] = endpoint_params[path][method]['security']
                    
                    # Add consumes if specified (for file uploads)
                    if 'consumes' in endpoint_params[path][method]:
                        swagger_spec["paths"][path][method.lower()]["consumes"] = endpoint_params[path][method]['consumes']
                else:
                    # Default endpoint without parameters
                    swagger_spec["paths"][path][method.lower()] = {
                        "summary": f"{method} {path}",
                        "description": f"Endpoint: {rule.endpoint}",
                        "produces": ["application/json"],
                        "responses": {
                            "200": {"description": "Success"},
                            "400": {"description": "Bad Request"},
                            "401": {"description": "Unauthorized"},
                            "404": {"description": "Not Found"}
                        },
                        "tags": ['default']
                    }
    
    return jsonify(swagger_spec)

# END OF ADDED LINES

@app.route('/test', methods=['GET'])
def test_route():
    return {"message": "API is up and running"}, 200

print("\n" + "="*60)
print("🚀 Initializing Consumption Prediction System...")
print("="*60)

# ============================================
# ✅ CONDITIONAL SCHEDULER - Respects ENABLE_SCHEDULER secret
# ============================================
ENABLE_SCHEDULER = os.environ.get('ENABLE_SCHEDULER', 'false').lower() == 'true'
IS_REPLIT = os.environ.get('REPL_ID') is not None

if ENABLE_SCHEDULER and not IS_REPLIT:
    # Scenario: Running locally with ENABLE_SCHEDULER=true
    print("⏰ Scheduler ENABLED (running locally)")
    
    consumption_scheduler = ConsumptionScheduler()
    consumption_scheduler.start_daily_checks(hour=2, minute=0)
    
    # Ensure scheduler stops when app shuts down
    def shutdown_scheduler():
        consumption_scheduler.stop()
    atexit.register(shutdown_scheduler)
    
elif IS_REPLIT:
    # Scenario: Running on Replit (production)
    print("⚠️  Scheduler DISABLED (Replit environment detected)")
    print("💡 Use manual trigger endpoint: POST /api/consumption/check_now")
    consumption_scheduler = None
    
else:
    # Scenario: Running locally without ENABLE_SCHEDULER set
    print("⚠️  Scheduler DISABLED (set ENABLE_SCHEDULER=true to enable)")
    print("💡 Use manual trigger endpoint: POST /api/consumption/check_now")
    consumption_scheduler = None
# ============================================

# Populate baseline data (check first to avoid duplicate key errors)
from db_connection import get_session
from models import ConsumptionBaseline

session = get_session()
try:
    baseline_count = session.query(ConsumptionBaseline).count()
    
    if baseline_count == 0:
        print("📊 Populating baseline consumption data...")
        from utils.consumption_baselines import populate_baselines_to_db
        populate_baselines_to_db()
    else:
        print(f"✅ Baselines already populated ({baseline_count} records)")
        
except Exception as e:
    print(f"⚠️ Warning: Could not check/populate baselines: {str(e)}")
finally:
    session.close()

print("="*60)
if consumption_scheduler:
    print("✅ Consumption Prediction System Ready (with scheduler)!")
else:
    print("✅ Consumption Prediction System Ready (manual mode)!")
print("="*60 + "\n")



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)