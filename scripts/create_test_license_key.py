#!/usr/bin/env python3
"""
Create a test license key with unlimited access
This script creates a license key that never expires and can be reused
"""

import os
import sys
import string
import secrets
from datetime import datetime, timedelta

# Add project root to path
script_dir = os.path.dirname(__file__)
project_root = os.path.abspath(os.path.join(script_dir, os.pardir))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from firebase_admin import firestore, initialize_app, credentials
    from firebase_admin.exceptions import FirebaseError
except ImportError:
    print("❌ Firebase Admin SDK not installed. Install with: pip install firebase-admin")
    sys.exit(1)

def get_firestore_client():
    """Initialize Firebase Admin and return Firestore client for rugby-ai-61fd0 project"""
    # Explicitly use rugby-ai-61fd0 project
    project_id = 'rugby-ai-61fd0'
    
    # Check credentials file project if it exists
    cred_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if cred_path and os.path.exists(cred_path):
        try:
            import json
            with open(cred_path, 'r') as f:
                cred_data = json.load(f)
                cred_project = cred_data.get('project_id', 'unknown')
                if cred_project != project_id:
                    print(f"⚠️  WARNING: Your credentials file is for project '{cred_project}', not '{project_id}'")
                    print(f"⚠️  This script needs credentials for project: {project_id}")
                    print(f"⚠️  The key may be saved to the wrong project!")
                    print(f"💡 Solution: Download credentials for '{project_id}' from Firebase Console")
                    print(f"💡 Then set: $env:GOOGLE_APPLICATION_CREDENTIALS='path/to/rugby-ai-61fd0-credentials.json'")
                    response = input(f"\n❓ Continue anyway? (y/n): ")
                    if response.lower() != 'y':
                        print("❌ Aborted. Please use correct credentials file.")
                        sys.exit(1)
        except Exception:
            pass  # Couldn't read credentials file, continue anyway
    
    try:
        # Check if already initialized and delete if wrong project
        from firebase_admin import _apps, delete_app
        if len(_apps) > 0:
            app = _apps[0]
            # Try to delete existing app to force reinitialization with correct project
            try:
                delete_app(app)
                print(f"🔄 Deleted existing Firebase connection to reinitialize for {project_id}")
            except Exception:
                pass  # Couldn't delete, might already be correct
        
        # Try with credentials if available
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            # Explicitly set project_id to override credentials file project
            initialize_app(credential=cred, options={'projectId': project_id})
            print(f"✅ Initialized Firebase with credentials, targeting project: {project_id}")
        else:
            # Use default credentials but specify project
            print(f"⚠️  No credentials file found. Using default credentials.")
            print(f"📝 Targeting project: {project_id}")
            initialize_app(options={'projectId': project_id})
            print(f"✅ Initialized Firebase with default credentials for project: {project_id}")
    except ValueError:
        # Already initialized - that's okay, but warn user
        print(f"⚠️  Firebase already initialized. Using existing connection.")
        print(f"⚠️  If this is wrong project, restart Python or set correct GOOGLE_APPLICATION_CREDENTIALS")
    except Exception as init_error:
        print(f"❌ Failed to initialize Firebase: {init_error}")
        print(f"💡 Set GOOGLE_APPLICATION_CREDENTIALS environment variable to credentials for {project_id}")
        sys.exit(1)
    
    # Get Firestore client
    client = firestore.client()
    print(f"✅ Connected to Firestore")
    print(f"📋 IMPORTANT: After running, verify in Firebase Console that the key is in project: {project_id}")
    return client

def generate_license_key():
    """Generate a secure license key in format XXXX-XXXX-XXXX-XXXX"""
    alphabet = string.ascii_uppercase + string.digits
    key_parts = []
    for _ in range(4):
        part = ''.join(secrets.choice(alphabet) for _ in range(4))
        key_parts.append(part)
    return '-'.join(key_parts)

def create_unlimited_license_key(email: str = "test@rugbyai.com"):
    """Create a license key with unlimited access (never expires)"""
    db = get_firestore_client()
    
    # Verify we're connected to the right project by checking if subscriptions collection exists
    # (This is a sanity check - we'll proceed anyway)
    print(f"📝 Creating license key in 'subscriptions' collection...")
    
    # Generate license key
    license_key = generate_license_key()
    
    # Set expiration to 100 years from now (effectively unlimited)
    expires_at = datetime.utcnow() + timedelta(days=36500)  # 100 years
    
    # Create subscription data
    subscription_data = {
        'license_key': license_key,
        'email': email,
        'subscription_type': 'lifetime',  # Special type for unlimited
        'created_at': firestore.SERVER_TIMESTAMP,
        'expires_at': expires_at,
        'used': False,
        'reusable': True,  # Can be used multiple times
        'active': True,
        'notes': 'Test license key with unlimited access - created for testing in rugby-ai-61fd0'
    }
    
    try:
        # Add to Firestore subscriptions collection
        print(f"💾 Saving to Firestore 'subscriptions' collection in project: rugby-ai-61fd0")
        doc_ref = db.collection('subscriptions').add(subscription_data)
        subscription_id = doc_ref[1].id
        
        print("✅ Successfully created unlimited access license key!")
        print("\n" + "="*60)
        print("LICENSE KEY DETAILS")
        print("="*60)
        print(f"License Key: {license_key}")
        print(f"Email: {email}")
        print(f"Subscription Type: lifetime (unlimited)")
        print(f"Expires At: {expires_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"Reusable: Yes (can be used multiple times)")
        print(f"Active: Yes")
        print(f"Subscription ID: {subscription_id}")
        print("="*60)
        print("\n💡 You can now use this license key to login:")
        print(f"   {license_key}")
        print("\n📝 Copy the license key above and use it in the login widget.")
        
        return {
            'license_key': license_key,
            'subscription_id': subscription_id,
            'email': email,
            'expires_at': expires_at
        }
        
    except Exception as e:
        print(f"❌ Error creating license key: {str(e)}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Create a test license key with unlimited access')
    parser.add_argument('--email', type=str, default='test@rugbyai.com',
                       help='Email address for the license key (default: test@rugbyai.com)')
    
    args = parser.parse_args()
    
    print("🔑 Creating unlimited access test license key...")
    print(f"📧 Email: {args.email}")
    print()
    
    result = create_unlimited_license_key(args.email)
    
    if result:
        print("\n✅ Done! License key is ready to use.")
    else:
        print("\n❌ Failed to create license key.")
        sys.exit(1)

