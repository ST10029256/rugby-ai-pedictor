# How to Create a Test License Key

## Where License Keys Are Stored

License keys are stored in **Firebase Firestore** in the `subscriptions` collection.

Each document has this structure:
```json
{
  "license_key": "XXXX-XXXX-XXXX-XXXX",
  "email": "test@rugbyai.com",
  "subscription_type": "lifetime",
  "created_at": "2024-01-01T00:00:00Z",
  "expires_at": "2124-01-01T00:00:00Z",  // 100 years = unlimited
  "used": false,
  "reusable": true,  // Can be used multiple times
  "active": true,
  "notes": "Test license key with unlimited access"
}
```

## Method 1: Using Firebase Console (Easiest)

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select your project: `rugby-ai-61fd0`
3. Navigate to **Firestore Database**
4. Click on the `subscriptions` collection
5. Click **Add document**
6. Add these fields:
   - `license_key` (string): `TEST-UNLIMITED-KEY-2024` (or generate your own)
   - `email` (string): `test@rugbyai.com`
   - `subscription_type` (string): `lifetime`
   - `expires_at` (timestamp): Set to a date 100 years in the future (e.g., 2124-01-01)
   - `used` (boolean): `false`
   - `reusable` (boolean): `true`
   - `active` (boolean): `true`
   - `created_at` (timestamp): Current date/time
7. Save the document

## Method 2: Using Python Script

**⚠️ IMPORTANT: Make sure your credentials file is for `rugby-ai-61fd0` project!**

Run the script:
```bash
python scripts/create_test_license_key.py --email test@rugbyai.com
```

**If you get a warning about wrong project:**
1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Select project: `rugby-ai-61fd0`
3. Go to Project Settings → Service Accounts
4. Click "Generate New Private Key"
5. Save the JSON file
6. Set environment variable:
   ```powershell
   $env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\rugby-ai-61fd0-credentials.json"
   ```
7. Run the script again

This will:
- Generate a secure random license key
- Create a Firestore document with unlimited access in `rugby-ai-61fd0`
- Print the license key for you to use

## Method 3: Using Firebase CLI

```bash
firebase firestore:set subscriptions/test-key-001 \
  '{"license_key":"TEST-UNLIMITED-KEY-2024","email":"test@rugbyai.com","subscription_type":"lifetime","expires_at":"2124-01-01T00:00:00Z","used":false,"reusable":true,"active":true}'
```

## Test License Key Format

The license key should be in format: `XXXX-XXXX-XXXX-XXXX`

Example test keys you can use:
- `TEST-UNLIMITED-KEY-2024`
- `DEMO-LIFETIME-ACCESS-2024`
- `DEV-TEST-KEY-UNLIMITED`

## Important Notes

1. **CORS Issue**: The current CORS error needs to be fixed. The `verify_license_key` function is a callable function, which should handle CORS automatically, but there might be a configuration issue.

2. **Firebase Callable Functions**: These should automatically handle CORS, but if you're still getting errors, we might need to create an HTTP endpoint version.

3. **Testing**: Once you create the key in Firestore, try using it in the login widget. The key will be verified against the Firestore database.

## Quick Test Key

For immediate testing, you can manually add this to Firestore:

**License Key**: `TEST-UNLIMITED-KEY-2024`
**Email**: `test@rugbyai.com`
**Expires**: 2124-01-01 (100 years from now)
**Reusable**: `true`
**Active**: `true`

