# License Key Authentication Setup Guide

## Overview

This system implements a license key-based authentication where users receive a unique key via email when they purchase a subscription. The key is used to login and access the Rugby AI Predictor.

## Architecture

### Backend (Firebase Cloud Functions)

1. **`verify_license_key`** - Verifies a license key and returns authentication status
2. **`generate_license_key`** - Generates a new license key (called when subscription is purchased)

### Frontend (React)

1. **`LoginWidget`** - Login component that accepts license keys
2. **`App.js`** - Main app with authentication protection

### Firestore Structure

```
subscriptions/
  {subscription_id}/
    - license_key: "XXXX-XXXX-XXXX-XXXX"
    - email: "user@example.com"
    - subscription_type: "monthly" | "yearly"
    - created_at: Timestamp
    - expires_at: Timestamp
    - used: boolean
    - reusable: boolean (allows multiple logins)
    - active: boolean
    - last_used: Timestamp
```

## Setup Steps

### 1. Deploy Cloud Functions

```bash
cd rugby-ai-predictor
firebase deploy --only functions
```

### 2. Set Up Email Sending

You have several options for sending license keys via email:

#### Option A: Gmail API (Recommended for Gmail)

1. **Enable Gmail API** in Google Cloud Console
2. **Create OAuth 2.0 credentials**
3. **Install dependencies**:
   ```bash
   pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
   ```
4. **Add email sending code** to `generate_license_key` function:

```python
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import base64
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

def send_license_key_email(email, license_key, expires_at):
    """Send license key via Gmail API"""
    # Load credentials from environment or service account
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    service = build('gmail', 'v1', credentials=creds)
    
    message = MIMEMultipart()
    message['to'] = email
    message['subject'] = 'Your Rugby AI Predictor License Key'
    
    expires_date = datetime.fromtimestamp(expires_at).strftime('%B %d, %Y')
    body = f"""
    Thank you for your subscription!
    
    Your license key is: {license_key}
    
    This key expires on: {expires_date}
    
    Use this key to login at: https://your-app-url.com
    
    If you have any questions, please contact support.
    """
    
    message.attach(MIMEText(body, 'plain'))
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
    
    send_message = service.users().messages().send(
        userId='me',
        body={'raw': raw_message}
    ).execute()
    
    return send_message
```

#### Option B: SendGrid (Easier Setup)

1. **Sign up for SendGrid** (free tier available)
2. **Get API key** from SendGrid dashboard
3. **Install SendGrid**:
   ```bash
   pip install sendgrid
   ```
4. **Add to requirements.txt**:
   ```
   sendgrid>=6.9.0
   ```
5. **Add email sending code**:

```python
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

def send_license_key_email(email, license_key, expires_at):
    """Send license key via SendGrid"""
    sg = SendGridAPIClient(os.getenv('SENDGRID_API_KEY'))
    
    expires_date = datetime.fromtimestamp(expires_at).strftime('%B %d, %Y')
    
    message = Mail(
        from_email='noreply@yourdomain.com',
        to_emails=email,
        subject='Your Rugby AI Predictor License Key',
        html_content=f"""
        <h2>Thank you for your subscription!</h2>
        <p>Your license key is: <strong>{license_key}</strong></p>
        <p>This key expires on: {expires_date}</p>
        <p>Use this key to login at: <a href="https://your-app-url.com">https://your-app-url.com</a></p>
        """
    )
    
    response = sg.send(message)
    return response
```

#### Option C: Firebase Extensions

Use the "Trigger Email" Firebase Extension:
1. Install from Firebase Console → Extensions
2. Configure to send emails on Firestore document creation
3. No code changes needed!

### 3. Integrate with Payment System

When a subscription is purchased, call `generate_license_key`:

#### Example: Stripe Webhook

```python
@https_fn.on_request()
def stripe_webhook(req):
    """Handle Stripe payment webhook"""
    import stripe
    stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
    
    payload = req.get_json()
    event = stripe.Event.construct_from(payload, stripe.api_key)
    
    if event.type == 'checkout.session.completed':
        session = event.data.object
        email = session.customer_details.email
        
        # Generate license key
        from main import generate_license_key
        result = generate_license_key({
            'email': email,
            'subscription_type': 'monthly',  # or get from Stripe
            'duration_days': 30
        })
        
        # Email will be sent automatically if configured
        return {'status': 'success', 'license_key': result['license_key']}
```

#### Example: Manual Generation (for testing)

```python
# Call from Python script or admin panel
from firebase_functions import https_fn
from main import generate_license_key

# This would be called via HTTP or admin interface
result = generate_license_key({
    'email': 'user@example.com',
    'subscription_type': 'monthly',
    'duration_days': 30
})

print(f"License key: {result['license_key']}")
```

### 4. Test the System

1. **Generate a test license key**:
   ```python
   # In Firebase Functions or local script
   result = generate_license_key({
       'email': 'test@example.com',
       'subscription_type': 'monthly',
       'duration_days': 30
   })
   ```

2. **Test login**:
   - Open your app
   - Enter the generated license key
   - Should authenticate successfully

3. **Test expiration**:
   - Create a key with `duration_days: 0` (expired)
   - Try to login - should fail

## Security Considerations

1. **Secure `generate_license_key` endpoint**:
   - Add admin authentication
   - Only allow from payment webhooks
   - Rate limit the endpoint

2. **License Key Format**:
   - Currently: `XXXX-XXXX-XXXX-XXXX` (16 characters)
   - Consider adding checksum for validation
   - Store hashed versions in database (optional)

3. **Rate Limiting**:
   - Add rate limiting to `verify_license_key`
   - Prevent brute force attacks

4. **HTTPS Only**:
   - Ensure all communication is over HTTPS
   - License keys should never be sent over HTTP

## Usage

### For Users

1. Purchase subscription
2. Receive license key via email
3. Enter key on login page
4. Access granted!

### For Developers

**Generate a license key manually**:
```python
# Call the Cloud Function
import requests

response = requests.post(
    'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/generate_license_key',
    json={
        'email': 'user@example.com',
        'subscription_type': 'monthly',
        'duration_days': 30
    },
    headers={'Authorization': 'Bearer YOUR_ADMIN_TOKEN'}
)
```

**Verify a license key**:
```python
response = requests.post(
    'https://us-central1-rugby-ai-61fd0.cloudfunctions.net/verify_license_key',
    json={'license_key': 'XXXX-XXXX-XXXX-XXXX'}
)
```

## Troubleshooting

1. **"Invalid license key"**:
   - Check Firestore for the key
   - Verify key format (uppercase, no spaces)
   - Check if expired

2. **Email not sending**:
   - Check email service credentials
   - Verify email service is enabled
   - Check Cloud Functions logs

3. **Authentication not persisting**:
   - Check localStorage in browser
   - Verify expiration check logic
   - Check browser console for errors

## Next Steps

1. ✅ Implement email sending (choose one option above)
2. ✅ Integrate with payment provider (Stripe, PayPal, etc.)
3. ✅ Add admin panel for manual key generation
4. ✅ Add subscription renewal logic
5. ✅ Add usage analytics/tracking

