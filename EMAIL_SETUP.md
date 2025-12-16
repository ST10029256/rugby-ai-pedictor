# Email Setup for License Key Delivery

This guide explains how to configure email sending for license key delivery after subscription purchases.

## Current Status

The subscription system is fully functional and will:
- ✅ Generate unique license keys
- ✅ Save to Firestore with correct expiration dates
- ✅ Send license key via email (when configured)
- ⚠️ License key is NOT displayed on the website - only sent via email

## Email Service Options

### Option 1: Gmail SMTP (Easiest - Recommended for Quick Setup)

**Pros:** Free, uses your existing Gmail account, no external services needed

**Setup Steps:**

1. **Enable 2-Factor Authentication on Gmail**
   - Go to your Google Account settings
   - Enable 2-Step Verification

2. **Generate App Password**
   - Go to https://myaccount.google.com/apppasswords
   - Select "Mail" and your device
   - Click "Generate"
   - Copy the 16-character app password (you'll only see it once!)

3. **Set Environment Variables in Firebase Functions**
   ```bash
   cd rugby-ai-predictor
   firebase functions:config:set gmail.user="your-email@gmail.com"
   firebase functions:config:set gmail.app_password="your-16-char-app-password"
   ```

4. **Deploy Functions**
   ```bash
   firebase deploy --only functions:generate_license_key_with_email
   ```

**Note:** Gmail has a daily sending limit (500 emails/day for free accounts). For higher volume, use SendGrid.

### Option 2: SendGrid (Recommended for Production)

**Pros:** Easy setup, reliable, good free tier (100 emails/day)

**Setup Steps:**

1. **Create SendGrid Account**
   - Go to https://sendgrid.com
   - Sign up for free account
   - Verify your email

2. **Create API Key**
   - Go to Settings → API Keys
   - Click "Create API Key"
   - Name it "Rugby AI License Keys"
   - Give "Full Access" permissions
   - Copy the API key (you'll only see it once!)

3. **Verify Sender Email**
   - Go to Settings → Sender Authentication
   - Verify a single sender email (e.g., noreply@rugbyai.com)
   - Or set up domain authentication for better deliverability

4. **Install SendGrid SDK**
   ```bash
   pip install sendgrid
   ```

5. **Update Firebase Function**
   - In `rugby-ai-predictor/main.py`, find `send_license_key_email()`
   - Uncomment the SendGrid code block
   - Set environment variable:
     ```bash
     firebase functions:config:set sendgrid.api_key="YOUR_SENDGRID_API_KEY"
     ```
   - Update the `from_email` to your verified sender

6. **Deploy**
   ```bash
   cd rugby-ai-predictor
   firebase deploy --only functions:generate_license_key_with_email
   ```

### Option 2: Gmail API

**Pros:** Free, uses your existing Gmail account

**Setup Steps:**

1. **Enable Gmail API**
   - Go to Google Cloud Console
   - Enable Gmail API for your project
   - Create OAuth 2.0 credentials
   - Download credentials JSON

2. **Install Dependencies**
   ```bash
   pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
   ```

3. **Set Up OAuth**
   - Follow Gmail API OAuth setup guide
   - Store refresh token securely in Firebase Functions config

4. **Update Function**
   - Implement Gmail API sending in `send_license_key_email()`
   - See Gmail API documentation for code examples

### Option 4: AWS SES (Simple Email Service)

**Pros:** Very cheap, high deliverability, good for high volume

**Setup Steps:**

1. **Set Up AWS SES**
   - Create AWS account
   - Go to SES console
   - Verify your email or domain
   - Request production access (if needed)

2. **Install Boto3**
   ```bash
   pip install boto3
   ```

3. **Configure AWS Credentials**
   - Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in Firebase Functions config
   - Or use IAM role if running on AWS

4. **Update Function**
   - Implement SES sending in `send_license_key_email()`

### Option 5: Mailgun

**Pros:** Good free tier, easy API

**Setup Steps:**

1. **Create Mailgun Account**
   - Go to https://mailgun.com
   - Verify your domain or use sandbox domain for testing

2. **Get API Key**
   - Copy API key from dashboard

3. **Install Mailgun SDK**
   ```bash
   pip install mailgun
   ```

4. **Update Function**
   - Implement Mailgun sending

## Testing Email Sending

Currently, the function logs email content to the console. To test:

1. **Test Subscription Flow**
   - Go to `subscribe.html`
   - Select a plan
   - Enter test email
   - Complete purchase
   - Check Firebase Functions logs for email content

2. **Verify License Key**
   - Check Firestore `subscriptions` collection
   - Verify license key was created with correct expiration
   - Test login with the generated key

## Email Template

The email includes:
- Welcome message with user's name
- License key in highlighted box
- Subscription details (plan, duration, expiration)
- Activation instructions
- Support contact information

## Production Checklist

Before going live:

- [ ] Set up email service (SendGrid recommended)
- [ ] Verify sender email/domain
- [ ] Test email delivery
- [ ] Update email template with your branding
- [ ] Set up email monitoring/alerts
- [ ] Configure SPF/DKIM records (for domain authentication)
- [ ] Test with real email addresses
- [ ] Set up email bounce handling
- [ ] Configure unsubscribe links (if required by law)

## Security Notes

- Never commit API keys to git
- Use Firebase Functions config for secrets
- Rotate API keys regularly
- Monitor for unusual activity
- Set up rate limiting on subscription endpoint

## Support

If you need help setting up email:
1. Check the email service's documentation
2. Review Firebase Functions logs
3. Test with a simple email first
4. Verify sender authentication is complete

## Current Implementation

The function `generate_license_key_with_email` in `main.py`:
- Generates secure license keys
- Saves to Firestore with all metadata
- Calls `send_license_key_email()` for email delivery
- Returns license key to frontend for immediate display

The frontend (`subscribe.html`) displays the license key immediately, so users can start using it even if email is delayed.

