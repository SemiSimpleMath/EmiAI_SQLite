# Google OAuth Implementation Guide

## Overview
This document describes the complete Google OAuth integration for Gmail, Google Calendar, and Google Tasks. The system now uses OAuth 2.0 instead of IMAP for email access, providing better security and access to additional Google services.

## What Was Implemented

### 1. Backend OAuth Routes (`app/routes/google_oauth.py`)
- **`/api/oauth/google/status`** - Check if OAuth credentials are configured
- **`/api/oauth/google/start`** - Start OAuth flow, returns authorization URL
- **`/oauth/google/callback`** - Handle OAuth callback after user authenticates
- **`/api/oauth/google/revoke`** - Disconnect Google account

### 2. Setup Wizard Integration
**File: `app/templates/setup_wizard.html`**
- Removed old IMAP email fields
- Added "Authenticate with Google" button in Step 6
- Shows OAuth status (connected/pending/error)

**File: `app/static/js/setup_wizard.js`**
- Added OAuth button handler
- Opens OAuth flow in popup window
- Checks OAuth status on page load
- Displays success message after authentication

### 3. Features Settings Page Integration
**File: `app/static/js/features_settings.js`**
- Automatically adds "Connect Google Account" button to disabled Google features
- Detects when OAuth credentials are missing
- Redirects to OAuth flow when clicked
- Shows success message and reloads after authentication

**File: `app/static/css/setup_wizard.css`**
- Added styling for OAuth connect button with Google colors
- Hover effects and transitions

### 4. Email Tool Migration to Gmail API
**New File: `app/assistant/lib/core_tools/email_tool/utils/gmail_api_client.py`**
- Complete Gmail API client using OAuth2
- Methods:
  - `search_emails()` - Search using Gmail query syntax
  - `fetch_full_email()` - Fetch full email content
  - `send_email()` - Send emails via Gmail API
  - `mark_as_read()` - Mark emails as read
  - `build_query()` - Convert parameters to Gmail query

**Updated Files:**
- `app/assistant/lib/core_tools/email_tool/email_tool.py` - No longer requires IMAP credentials
- `app/assistant/lib/core_tools/email_tool/utils/email_utils.py` - Uses Gmail API instead of IMAP

### 5. Feature Dependency Checking
**File: `app/assistant/user_settings_manager/user_settings.py`**
- Added `has_google_oauth_credentials()` method
- Updated feature dependencies to include `requires_oauth`
- Auto-disables features when OAuth credentials are missing
- Shows clear error messages about missing OAuth

**File: `app/routes/user_settings.py`**
- `/api/settings/features` endpoint auto-disables features without credentials
- Prevents enabling features that can't run

## How It Works

### First-Time Setup Flow
1. User runs `setup.py` wizard
2. In Step 6, user clicks "Authenticate with Google"
3. OAuth popup opens with Google's consent screen
4. User logs in and grants permissions
5. Callback saves `token.pickle` with refresh token
6. Setup wizard shows success message

### Features Settings Flow
1. User opens Features Settings page
2. If Google features (email/calendar/tasks) are disabled due to missing OAuth:
   - Feature card is grayed out
   - Shows "Missing Google OAuth credentials" message
   - Displays "Connect Google Account" button
3. User clicks connect button
4. Redirected to Google OAuth consent
5. After authentication, redirected back with success message
6. Page reloads, features are now available

### Runtime Email Fetching
1. Agent/scheduler calls `EmailTool.execute()`
2. EmailTool initializes `EmailUtils` (no IMAP credentials needed)
3. EmailUtils creates `GmailAPIClient`
4. GmailAPIClient loads `token.pickle` from `app/assistant/lib/core_tools/credentials/`
5. If token is expired, automatically refreshes using refresh token
6. Fetches emails via Gmail API
7. Returns processed emails to agent

## File Locations

### OAuth Credentials
```
app/assistant/lib/core_tools/credentials/
├── credentials.json    # OAuth client ID/secret (from Google Cloud Console)
└── token.pickle        # User's OAuth token (generated after first auth)
```

### Key Files Modified
```
Backend:
- app/routes/google_oauth.py (NEW)
- app/routes/setup.py
- app/routes/__init__.py
- app/create_app.py
- app/routes/user_settings.py
- app/assistant/user_settings_manager/user_settings.py

Frontend:
- app/templates/setup_wizard.html
- app/static/js/setup_wizard.js
- app/static/js/features_settings.js
- app/static/css/setup_wizard.css

Email Tool:
- app/assistant/lib/core_tools/email_tool/utils/gmail_api_client.py (NEW)
- app/assistant/lib/core_tools/email_tool/email_tool.py
- app/assistant/lib/core_tools/email_tool/utils/email_utils.py
```

## OAuth Scopes

The following scopes are requested from Google:

```python
SCOPES = [
    'https://www.googleapis.com/auth/calendar',           # Calendar access
    'https://www.googleapis.com/auth/gmail.readonly',     # Read emails
    'https://www.googleapis.com/auth/gmail.send',         # Send emails
    'https://www.googleapis.com/auth/tasks'               # Tasks access
]
```

## Security Notes

1. **Client Secret Distribution**: The `credentials.json` (containing client ID and secret) is bundled with the app. This is standard for desktop applications - Google's OAuth flow for desktop apps is designed for this scenario.

2. **User Tokens**: Each user authenticates with their own Google account. The `token.pickle` contains their personal refresh token and is stored locally.

3. **Test Users**: During development (before app verification), add test users in Google Cloud Console:
   - Go to OAuth consent screen
   - Add test users (email addresses)
   - These users can authenticate without app verification

4. **Token Refresh**: Tokens are automatically refreshed when expired. No user interaction needed.

## Testing Checklist

### Setup Wizard
- [ ] Can click "Authenticate with Google" button
- [ ] OAuth popup opens correctly
- [ ] After authentication, returns to wizard with success message
- [ ] `token.pickle` is created in credentials folder

### Features Settings
- [ ] Google features show as unavailable without OAuth
- [ ] "Connect Google Account" button appears on disabled features
- [ ] Clicking button redirects to OAuth flow
- [ ] After authentication, features become available
- [ ] Feature toggles can be enabled after OAuth

### Email Functionality
- [ ] Email tool can fetch emails via Gmail API
- [ ] No IMAP credentials required
- [ ] Emails are processed and stored correctly
- [ ] Token auto-refreshes when expired

### Error Handling
- [ ] Clear error if `credentials.json` is missing
- [ ] Clear error if OAuth fails
- [ ] Features auto-disable if token is revoked
- [ ] Helpful messages guide user to authenticate

## Future Enhancements

1. **OAuth Status Dashboard**: Add a dedicated page showing:
   - Connected Google account email
   - Granted scopes
   - Token expiration date
   - Button to disconnect/reconnect

2. **Scope Management**: Allow users to see and manage individual scopes

3. **Multi-Account Support**: Support multiple Google accounts (currently single-user per installation)

4. **Token Health Monitoring**: Background task to check token validity and notify user if re-authentication needed

## Troubleshooting

### "OAuth credentials not found" error
- Ensure `credentials.json` exists in `app/assistant/lib/core_tools/credentials/`
- Download from Google Cloud Console if missing

### OAuth popup blocked
- Allow popups for your domain
- Or use full-page redirect (modify `handleGoogleOAuth` to use `window.location.href` instead of `window.open`)

### "Access blocked" during OAuth
- Add your email as a test user in Google Cloud Console
- Or publish the app (requires verification for public use)

### Token expired and won't refresh
- Delete `token.pickle`
- Re-authenticate through setup wizard or features settings

## Removed Legacy Code

The following IMAP-related code is now **deprecated** but kept for reference:
- `app/assistant/lib/core_tools/email_tool/utils/imap_client.py`
- Environment variables: `EMAIL_ADDR`, `EMAIL_PASSWORD`, `EMAIL_IMAP_URL`

These can be safely removed in a future cleanup, but are left in place to avoid breaking anything that might still reference them.

## Conclusion

The OAuth integration provides a modern, secure way to access Google services. Users authenticate once, and the app maintains access through refresh tokens. Features automatically disable when credentials are missing, providing clear feedback and easy paths to resolve issues.

