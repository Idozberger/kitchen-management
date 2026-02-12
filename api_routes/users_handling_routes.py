from flask import Blueprint, request, jsonify, current_app
import os, bcrypt
from werkzeug.utils import secure_filename
from datetime import datetime, timezone
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity, get_jwt
from flask_mail import Message
import uuid
import traceback

# PostgreSQL imports
from db_connection import get_session
from models import User

# Create a Blueprint object
users_handling_blueprint = Blueprint('users_handling_blueprint', __name__)


@users_handling_blueprint.route('/api/register_user', methods=['POST'])
def register_user_r():
    """Register a new user"""
    session = get_session()
    try:
        # Get the request data
        data = request.json
        first_name = data.get('first_name', None)
        last_name = data.get('last_name', None)
        email = data.get('email', None)
        password = data.get('password', None)
        verified = 0

        if not first_name or not last_name or not email or not password:
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Check if the email already exists
        existing_user = session.query(User).filter(User.email == email).first()
        if existing_user:
            return jsonify({'error': 'User already exists'}), 400

        # Hash the password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        # Get the current date and time for the 'created_at' field
        created_at = datetime.now(timezone.utc)

        verification_code = str(uuid.uuid4()).replace('-', '')[:5]
        
        # Create the user object
        user = User(
            first_name=first_name,
            last_name=last_name,
            email=email,
            password=hashed_password.decode('utf-8'),  # Store as string
            verified=verified,
            verification_code=verification_code,
            created_at=created_at
        )

        # Insert the new user
        session.add(user)
        session.commit()
        
        # Refresh to get the ID
        session.refresh(user)

        # Respond with the created user's id
        return jsonify({
            'message': 'User created successfully',
            '_id': str(user.id)  # Return as string for compatibility
        }), 201

    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@users_handling_blueprint.route('/api/verify_user', methods=['POST'])
def verify_user():
    """Verify user email with verification code"""
    session = get_session()
    try:
        # Get the request data
        data = request.json
        print("incoming_data: ", data)
        email = data.get('email')
        verification_code = data.get('verification_code')

        if not email or email.strip() == '':
            return jsonify({'error': 'invalid email'}), 400

        if not verification_code or not verification_code.strip() or len(verification_code) != 5:
            return jsonify({'error': 'Invalid Code...'}), 400

        # Find the user by email
        user = session.query(User).filter(User.email == email).first()

        # Check if the user exists
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Check if the user is already verified
        if user.verified == 1:
            return jsonify({'message': 'User already verified'}), 400

        # Check if the verification code matches
        if user.verification_code != verification_code:
            return jsonify({'error': 'Invalid verification code'}), 400

        # Update the user's 'verified' status to 1
        user.verified = 1
        session.commit()

        # Generate access token
        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={
                'user_id': str(user.id),
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email': user.email
            }
        )

        return jsonify({
            'message': 'User verified successfully',
            'access_token': access_token
        }), 200

    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


def send_email_verification(email, code):
    """
    Send verification code via email using SendGrid API.
    Works for both local and production environments.
    """
    import os
    import traceback
    
    try:
        # Get SendGrid API key from environment
        sendgrid_api_key = os.environ.get('SENDGRID_API_KEY')
        
        if not sendgrid_api_key:
            raise ValueError("SENDGRID_API_KEY environment variable is not set")
        
        # âœ… Use SendGrid API for all environments
        print(f"ðŸ“§ Using SendGrid API to send email to {email}")
        
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
        
        # ✅ Get verified sender email from environment
        # Must be verified in SendGrid account
        sender_email = os.environ.get('SENDGRID_SENDER_EMAIL', 'princemaya26@gmail.com')
        
        message = Mail(
            from_email=(sender_email, "Kitchen Guardian"),
            to_emails=email,
            subject='Your Kitchen Guardian Verification Code',
            html_content=f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif; background-color: #f5f5f5;">
    <table role="presentation" style="width: 100%; border-collapse: collapse;">
        <tr>
            <td style="padding: 40px 20px;">
                <table role="presentation" style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    <!-- Header -->
                    <tr>
                        <td style="padding: 40px 40px 20px 40px; text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 8px 8px 0 0;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 28px; font-weight: 600;">Kitchen Guardian</h1>
                        </td>
                    </tr>
                    
                    <!-- Body -->
                    <tr>
                        <td style="padding: 40px;">
                            <h2 style="margin: 0 0 20px 0; color: #333333; font-size: 22px; font-weight: 600;">Verify Your Email</h2>
                            <p style="margin: 0 0 30px 0; color: #666666; font-size: 16px; line-height: 1.5;">
                                Thank you for signing up! Please use the verification code below to complete your registration:
                            </p>
                            
                            <!-- Verification Code Box -->
                            <table role="presentation" style="width: 100%; margin: 0 0 30px 0;">
                                <tr>
                                    <td style="background-color: #f8f9fa; border: 2px dashed #667eea; border-radius: 8px; padding: 25px; text-align: center;">
                                        <div style="font-size: 36px; font-weight: 700; color: #667eea; letter-spacing: 8px; font-family: 'Courier New', monospace;">
                                            {code}
                                        </div>
                                    </td>
                                </tr>
                            </table>
                            
                            <p style="margin: 0 0 10px 0; color: #999999; font-size: 14px; line-height: 1.5;">
                                This code will expire in 10 minutes.
                            </p>
                            <p style="margin: 0; color: #999999; font-size: 14px; line-height: 1.5;">
                                If you didn't request this code, please ignore this email.
                            </p>
                        </td>
                    </tr>
                    
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 30px 40px; background-color: #f8f9fa; border-radius: 0 0 8px 8px; border-top: 1px solid #e9ecef;">
                            <p style="margin: 0 0 10px 0; color: #666666; font-size: 14px; text-align: center;">
                                Kitchen Guardian - Smart Kitchen Management
                            </p>
                            <p style="margin: 0; color: #999999; font-size: 12px; text-align: center;">
                                This is an automated message, please do not reply.
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
            """
        )
        
        # ✅ CRITICAL: Add plain text version for spam prevention
        # Emails without plain text are more likely to be marked as spam
        message.plain_text_content = f"""
Kitchen Guardian - Email Verification

Your verification code is: {code}

This code will expire in 10 minutes.

If you didn't request this code, please ignore this email.

---
Kitchen Guardian - Smart Kitchen Management
This is an automated message, please do not reply.
        """
        
        sg = SendGridAPIClient(sendgrid_api_key)
        response = sg.send(message)
        print(f"âœ… Email sent via SendGrid. Status: {response.status_code}")
        return True
            
    except Exception as e:
        print(f"âŒ Error sending email: {str(e)}")
        traceback.print_exc()
        return False


@users_handling_blueprint.route('/api/send_verification_code', methods=['POST'])
def send_verification_code():
    """Generate and send verification code"""
    session = get_session()
    try:
        # Get the request data
        data = request.json
        email = data.get('email')

        if not email or email.strip() == "":
            return jsonify({'error': 'Invalid email'}), 400
        
        # Find the user by email
        user = session.query(User).filter(User.email == email).first()

        # Check if the user exists
        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Check if the user is already verified
        if user.verified == 1:
            return jsonify({'message': 'User already verified'}), 400

        # Generate a new 5-character verification code using UUID
        verification_code = str(uuid.uuid4()).replace('-', '')[:5]

        # Update the user's verification code in the database
        user.verification_code = verification_code
        session.commit()

        # Send the verification code to the user's email
        email_sent = send_email_verification(email, verification_code)
        if not email_sent:
            return jsonify({'error': 'could not send verification code'}), 422

        return jsonify({'message': 'Verification code sent successfully'}), 200

    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@users_handling_blueprint.route('/api/forgot_password', methods=['POST'])
def forgot_password():
    """Request a password reset code"""
    session = get_session()
    try:
        data = request.json
        email = data.get('email')

        if not email or email.strip() == '':
            return jsonify({'error': 'Invalid email'}), 400

        # Find the user
        user = session.query(User).filter(User.email == email).first()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Generate a reset code (5-character string)
        reset_code = str(uuid.uuid4()).replace('-', '')[:5]

        # Store reset_code in user's record
        user.reset_code = reset_code
        session.commit()

        # Send reset code via email
        if send_email_verification(email, reset_code):
            return jsonify({'message': 'Password reset code sent successfully'}), 200
        else:
            return jsonify({'error': 'Failed to send reset code'}), 500

    except Exception as e:
        session.rollback()
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500
    finally:
        session.close()


@users_handling_blueprint.route('/api/reset_password', methods=['POST'])
def reset_password():
    """Verify reset code and reset password"""
    session = get_session()
    try:
        data = request.json
        email = data.get('email')
        reset_code = data.get('reset_code')
        new_password = data.get('new_password')

        if not email or email.strip() == '':
            return jsonify({'error': 'Invalid email'}), 400

        if not reset_code or reset_code.strip() == '' or len(reset_code) != 5:
            return jsonify({'error': 'Invalid reset code'}), 400

        if not new_password or len(new_password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400

        # Find user
        user = session.query(User).filter(User.email == email).first()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Check if reset_code matches
        if not user.reset_code or user.reset_code != reset_code:
            return jsonify({'error': 'Incorrect reset code'}), 400

        # Hash the new password
        hashed_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())

        # Update password and remove reset_code
        user.password = hashed_password.decode('utf-8')
        user.reset_code = None
        session.commit()

        return jsonify({'message': 'Password reset successfully'}), 200

    except Exception as e:
        session.rollback()
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500
    finally:
        session.close()


@users_handling_blueprint.route('/api/change_password', methods=['POST'])
@jwt_required()
def change_password():
    """Change password for authenticated user"""
    session = get_session()
    try:
        data = request.json
        new_password = data.get('new_password')
        current_password = data.get('current_password')

        if not current_password or not new_password:
            return jsonify({'error': 'Current and new password are required'}), 400

        if len(new_password) < 6:
            return jsonify({'error': 'New password must be at least 6 characters'}), 400

        # Get the current user email from JWT claims
        user_identity = get_jwt()
        email = user_identity['email']
        
        # Find the user
        user = session.query(User).filter(User.email == email).first()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        # Verify the current password
        if not bcrypt.checkpw(current_password.encode('utf-8'), user.password.encode('utf-8')):
            return jsonify({'error': 'Incorrect current password'}), 400

        # Hash the new password
        hashed_new_password = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())

        # Update the password in the database
        user.password = hashed_new_password.decode('utf-8')
        session.commit()

        return jsonify({'message': 'Password changed successfully'}), 200

    except Exception as e:
        session.rollback()
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500
    finally:
        session.close()


@users_handling_blueprint.route('/api/login', methods=['POST'])
def login_user_r():
    """Login user and return JWT token"""
    session = get_session()
    try:
        # Get the request data
        data = request.json
        email = data.get('email')
        password = data.get('password')

        # Find the user by email
        user = session.query(User).filter(User.email == email).first()

        if not user:
            return jsonify({'error': 'Invalid email or password'}), 401

        # Check if the password matches
        if not bcrypt.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
            return jsonify({'error': 'Invalid email or password'}), 401

        # Check if the user is verified
        if user.verified != 1:
            return jsonify({'error': 'User not verified'}), 403

        # Generate access token using create_access_token
        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={
                'user_id': str(user.id),
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email': user.email
            }
        )

        # Respond with the token
        return jsonify({'access_token': access_token}), 200

    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@users_handling_blueprint.route('/api/protected', methods=['GET'])
@jwt_required()
def protected_r():
    """Protected route example"""
    # Get the JWT identity (i.e., the user's information)
    current_user = get_jwt_identity()

    # Return a protected resource
    return jsonify({'message': 'Access granted!', 'user': current_user}), 200


@users_handling_blueprint.route('/api/check_identity', methods=['GET'])
@jwt_required()
def check_identity_r():
    """Check if user is logged in"""
    # Get the JWT identity (i.e., the user's information)
    current_user = get_jwt_identity()

    # Return the user's identity to indicate they are logged in
    return jsonify({
        'message': 'User is logged in and authorized.',
        'user': current_user
    }), 200


@users_handling_blueprint.route('/api/get_user_profile', methods=['GET'])
@jwt_required()
def get_user_profile():
    """Get current user's profile including avatar"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_email = user_identity['email']
        
        user = session.query(User).filter(User.email == user_email).first()
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        return jsonify({
            'user_id': str(user.id),
            'first_name': user.first_name,
            'last_name': user.last_name,
            'email': user.email,
            'avatar': user.avatar or '',
            'verified': user.verified,
            'created_at': user.created_at.isoformat() if user.created_at else ''
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@users_handling_blueprint.route('/api/get_all_users', methods=['GET'])
@jwt_required()
def get_all_users():
    """Get all users (admin endpoint)"""
    session = get_session()
    try:
        # Fetch all users from the database
        users = session.query(User).all()

        # Prepare user data by excluding sensitive information
        users_data = []
        for user in users:
            users_data.append({
                '_id': str(user.id),
                'first_name': user.first_name or '',
                'last_name': user.last_name or '',
                'email': user.email or '',
                'verified': user.verified or 0,
                'created_at': user.created_at.isoformat() if user.created_at else ''
            })

        return jsonify({
            'message': 'Users fetched successfully',
            'users': users_data,
            'total': len(users_data)
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        session.close()


@users_handling_blueprint.route('/api/edit_user', methods=['POST'])
@jwt_required()
def edit_user():
    """Edit user profile (name, avatar)"""
    session = get_session()
    try:
        user_identity = get_jwt()
        user_email = user_identity['email']
        
        # Get request data
        data = request.json
        first_name = data.get('first_name', '').strip()
        last_name = data.get('last_name', '').strip()
        avatar = data.get('avatar', '').strip()  # Base64 encoded image
        
        # Validation
        if not first_name and not last_name and not avatar:
            return jsonify({'error': 'At least one field (first_name, last_name, or avatar) is required'}), 400
        
        # Find the user
        user = session.query(User).filter(User.email == user_email).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Update fields
        if first_name:
            user.first_name = first_name
        if last_name:
            user.last_name = last_name
        if avatar:
            user.avatar = avatar
        
        session.commit()
        
        # Refresh to get updated data
        session.refresh(user)
        
        # Generate new access token with updated information
        access_token = create_access_token(
            identity=str(user.id),
            additional_claims={
                'user_id': str(user.id),
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email': user.email
            }
        )
        
        return jsonify({
            'message': 'User profile updated successfully',
            'access_token': access_token,
            'user': {
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email': user.email,
                'avatar': user.avatar or ''
            }
        }), 200
        
    except Exception as e:
        session.rollback()
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
    finally:
        session.close()