# Quick Email Setup Guide

## Current Status: ❌ Emails are NOT being sent

The license key is generated and saved, but **emails are not sent** until you configure an email service.

**Once configured, emails will be sent FROM your Gmail address TO the recipient**, just like a normal email!

## ✅ Enable Email Sending (5 minutes)

### Step 1: Get Gmail App Password

**EASIEST WAY - Direct Link:**
1. Go directly to App Passwords: https://myaccount.google.com/apppasswords
   - This will take you straight to the App passwords page

**OR Alternative Method:**
1. Go to your Google Account: https://myaccount.google.com/
2. Click **Security** in the left menu
3. Under "How you sign in to Google", find **2-Step Verification** and click on it
   - ✅ You already have this ON - that's perfect!
4. On the 2-Step Verification page, look for **App passwords** link
   - If you don't see it, try the direct link above: https://myaccount.google.com/apppasswords
5. You might be asked to sign in again for security
6. On the App passwords page, you'll see:
   - **Select app**: Choose "Mail" (or "Other (Custom name)")
   - **Select device**: Choose "Other (Custom name)" and type "Firebase Functions"
7. Click **Generate** (or "Create")
8. **Copy the 16-character password** (you'll only see it once!)
   - It looks like: `abcd efgh ijkl mnop`
   - **Important:** Remove all spaces when you use it (should be 16 characters with no spaces)
   - Example: `abcdefghijklmnop` (no spaces)

### Step 2: Set Firebase Secrets

Open PowerShell or Terminal in the `rugby-ai-predictor` folder and run:

```bash
cd rugby-ai-predictor

# Set your Gmail address (it will prompt you to enter it)
firebase functions:secrets:set GMAIL_USER

# Set your app password (it will prompt you - paste the 16-character password)
firebase functions:secrets:set GMAIL_APP_PASSWORD
```

When prompted:
- For `GMAIL_USER`: Enter your Gmail address (e.g., `your-email@gmail.com`)
- For `GMAIL_APP_PASSWORD`: Paste the 16-character app password (remove spaces if any)

**Important:** 
- Remove spaces from the app password! It should be 16 characters with no spaces
- The secrets are encrypted and stored securely by Firebase

### Step 3: Deploy

```bash
firebase deploy --only functions:generate_license_key_with_email
```

### Step 5: Test

1. Go to `subscribe.html`
2. Complete a test purchase with your own email address
3. Check your email inbox - you should receive the license key email
4. The email will appear to be sent **FROM your Gmail address** (the one you configured)
5. Check Firebase Functions logs to confirm email was sent

## Verify It's Working

After deploying, check Firebase Functions logs:
```bash
firebase functions:log --only generate_license_key_with_email
```

You should see: `"Email sent successfully to user@example.com"`

If you see warnings, the email service isn't configured yet.

## Troubleshooting

**"EMAIL NOT SENT - No email service configured"**
- Gmail credentials not set in Firebase Functions config
- Run Step 2 again

**"SMTP email sending failed"**
- Check that 2-Step Verification is enabled
- Verify app password is correct (no spaces, 16 characters)
- Make sure you're using an App Password, not your regular Gmail password

**Email goes to spam**
- This is normal for new senders
- Ask users to check spam folder
- Consider using SendGrid for better deliverability

## Alternative: Use SendGrid (Better for Production)

See `EMAIL_SETUP.md` for SendGrid setup (recommended for production with better deliverability).

