# Security Fixes for Home-Cloud-Server

This PR addresses several critical security vulnerabilities in the Home-Cloud-Server application.

## Summary of Changes

### 1. Path Traversal Vulnerability (HIGH SEVERITY)
**Location:** `app/routes/files.py` - `normalize_item_name()` function

**Problem:** The original implementation only checked for `/` and `\` characters, but could be bypassed using:
- Null bytes (`\x00`)
- Unicode normalization attacks
- Relative path sequences (e.g., `..%2f`, `%2e%2e`)
- Windows reserved names (e.g., `CON`, `PRN`, `AUX`)

**Fix:** Enhanced `normalize_item_name()` function with:
- Null byte detection
- Unicode NFC normalization to prevent homograph attacks
- Comprehensive path traversal pattern detection
- Windows drive letter pattern rejection
- Windows reserved name filtering

### 2. Missing CSRF Protection (HIGH SEVERITY)
**Location:** All POST endpoints in web routes

**Problem:** The application had no CSRF protection, allowing attackers to perform actions on behalf of authenticated users through malicious websites.

**Fix:** 
- Added `Flask-WTF` dependency
- Initialized CSRF protection in `app/__init__.py`
- Exempted API routes (which use Basic Auth) from CSRF checks in `app/routes/api.py`

### 3. Broken Password Reset (CRITICAL SEVERITY)
**Location:** `app/routes/auth.py` - `forgot_password()` and `reset_password()`

**Problem:** 
- Password reset tokens were not stored or validated
- Any token was accepted, allowing anyone to reset any user's password
- No expiration check on reset links

**Fix:**
- Added `reset_token` and `reset_token_expires` fields to User model
- Implemented `generate_reset_token()`, `verify_reset_token()`, and `clear_reset_token()` methods
- Modified `forgot_password()` to store tokens in the database with 1-hour expiration
- Modified `reset_password()` to validate tokens against the database
- Added password strength validation (minimum 8 characters)

### 4. Race Condition in File Upload (MEDIUM SEVERITY)
**Location:** `app/routes/files.py` - `upload_file()` function

**Problem:** The file existence check and file creation were not atomic, allowing concurrent uploads to overwrite each other or create duplicate entries.

**Fix:**
- Created `generate_unique_filename()` function that uses database row locking (`with_for_update()`)
- Replaced simple existence check with atomic filename generation
- Limited retry attempts to prevent infinite loops

### 5. Path Traversal in API Upload (HIGH SEVERITY)
**Location:** `app/routes/api.py` - `api_upload_file()` function

**Problem:** API file upload did not validate filenames, allowing path traversal attacks.

**Fix:** Added filename validation using the enhanced `normalize_item_name()` function before processing uploads.

## Files Modified

1. `requirements.txt` - Added Flask-WTF dependency
2. `app/__init__.py` - Initialized CSRF protection
3. `app/models/user.py` - Added password reset token fields and methods
4. `app/routes/auth.py` - Fixed password reset functionality
5. `app/routes/files.py` - Fixed path traversal and race condition vulnerabilities
6. `app/routes/api.py` - Added CSRF exemption and filename validation

## Testing Recommendations

1. **Path Traversal:** Try uploading files with names like `../../../etc/passwd`, `file\x00.txt`, `..%2fetc%2fpasswd`
2. **CSRF Protection:** Verify that POST requests without CSRF tokens are rejected (except API endpoints)
3. **Password Reset:** Test that expired tokens are rejected and valid tokens work correctly
4. **Race Condition:** Attempt concurrent uploads with the same filename

## Backwards Compatibility

- Database migration required: New columns `reset_token` and `reset_token_expires` in `users` table
- CSRF tokens are automatically added to forms using Flask-WTF
- API clients using Basic Auth are unaffected

## Credits

These vulnerabilities were discovered and fixed as part of a security audit of the Home-Cloud-Server project.