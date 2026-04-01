# Home Cloud Server API Documentation

## Overview

This document describes the REST API endpoints available in Home Cloud Server. All API endpoints (except health check) require authentication.

**Base URL:** `/`

**Authentication:** HTTP Basic Authentication (Base64 encoded `username:password`)

---

## Authentication

All API requests must include an `Authorization` header with Basic Auth credentials:

```
Authorization: Basic <base64(username:password)>
```

Example:
```bash
curl -u username:password http://localhost:5000/api/user/info
```

---

## Response Format

All API responses are returned in JSON format.

**Success Response:**
```json
{
  "success": true,
  "data": { ... }
}
```

**Error Response:**
```json
{
  "error": "Error message",
  "code": 400
}
```

---

## User API Endpoints

### Get User Information

**Endpoint:** `GET /api/user/info`

**Authentication:** Required

**Description:** Returns information about the authenticated user.

**Response:**
```json
{
  "id": 1,
  "username": "john_doe",
  "email": "john@example.com",
  "role": "user",
  "storage_quota": 10737418240,
  "storage_used": 2147483648,
  "storage_percent": 20.0,
  "created_at": "2024-01-15 10:30:00",
  "last_login": "2024-03-20 14:45:00"
}
```

---

## File API Endpoints

### List Files and Folders

**Endpoint:** `GET /api/files`

**Authentication:** Required

**Description:** Lists files and folders in a directory.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| folder_id | integer | No | Folder ID to list (omit for root folder) |

**Response:**
```json
{
  "folder": {
    "id": 1,
    "name": "root",
    "parent_id": null,
    "created_at": "2024-01-15 10:30:00"
  },
  "files": [
    {
      "id": 1,
      "filename": "abc123_document.pdf",
      "original_filename": "document.pdf",
      "size": 1048576,
      "file_type": "document",
      "folder_id": 1,
      "created_at": "2024-03-20 14:45:00"
    }
  ],
  "subfolders": [
    {
      "id": 2,
      "name": "Documents",
      "parent_id": 1,
      "created_at": "2024-03-20 14:45:00"
    }
  ]
}
```

### Create Folder

**Endpoint:** `POST /api/folders/create`

**Authentication:** Required

**Description:** Creates a new folder.

**Request Body:**
```json
{
  "name": "New Folder",
  "parent_id": 1
}
```

**Response:**
```json
{
  "success": true,
  "folder": {
    "id": 3,
    "name": "New Folder",
    "parent_id": 1,
    "created_at": "2024-03-20 15:00:00"
  }
}
```

### Upload File

**Endpoint:** `POST /api/files/upload`

**Authentication:** Required

**Description:** Uploads a file to the specified folder.

**Request:**
- Content-Type: `multipart/form-data`

**Form Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| file | file | Yes | File to upload |
| folder_id | integer | No | Destination folder ID (omit for root) |

**Response:**
```json
{
  "success": true,
  "file": {
    "id": 2,
    "filename": "xyz789_image.jpg",
    "original_filename": "image.jpg",
    "size": 2097152,
    "file_type": "image",
    "folder_id": 1,
    "created_at": "2024-03-20 15:05:00"
  }
}
```

**Error Codes:**
- `400` - Invalid file, file too large, or not enough storage space
- `404` - Folder not found

---

## Admin API Endpoints

All admin endpoints require the authenticated user to have `admin` role.

### List All Users

**Endpoint:** `GET /api/admin/users`

**Authentication:** Required (Admin only)

**Description:** Returns a list of all users in the system.

**Response:**
```json
{
  "users": [
    {
      "id": 1,
      "username": "admin",
      "email": "admin@example.com",
      "role": "admin",
      "storage_quota": 107374182400,
      "storage_used": 5368709120,
      "storage_percent": 5.0,
      "created_at": "2024-01-15 10:30:00",
      "last_login": "2024-03-20 14:45:00"
    }
  ]
}
```

### Get System Statistics

**Endpoint:** `GET /api/admin/system/stats`

**Authentication:** Required (Admin only)

**Description:** Returns real-time system statistics.

**Response:**
```json
{
  "cpu": {
    "percent": 15.5
  },
  "memory": {
    "total": 16777216000,
    "available": 12582912000,
    "used": 4194304000,
    "percent": 25.0
  },
  "disk": {
    "total": 1099511627776,
    "used": 549755813888,
    "free": 549755813888,
    "percent": 50.0
  },
  "network": {
    "bytes_sent": 1048576000,
    "bytes_recv": 2097152000,
    "packets_sent": 500000,
    "packets_recv": 750000
  },
  "timestamp": "2024-03-20 15:10:00"
}
```

### Get Metrics History

**Endpoint:** `GET /api/admin/metrics/history`

**Authentication:** Required (Admin only)

**Description:** Returns historical system metrics.

**Query Parameters:**
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| hours | integer | No | 24 | Number of hours to retrieve |

**Response:**
```json
{
  "metrics": [
    {
      "id": 1,
      "cpu_usage": 12.5,
      "memory_usage": 30.0,
      "disk_usage": 45.0,
      "network_rx": 104857600,
      "network_tx": 52428800,
      "active_connections": 5,
      "timestamp": "2024-03-20 14:00:00"
    }
  ]
}
```

---

## Web Routes (HTML Interface)

The following routes serve HTML pages and require session-based authentication (via browser).

### Authentication Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/auth/login` | GET/POST | User login page |
| `/auth/logout` | GET | Logout user |
| `/auth/register` | GET/POST | User registration |

### File Management Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/files` | GET | File browser (root folder) |
| `/files?folder_id={id}` | GET | File browser (specific folder) |
| `/files/upload` | POST | Upload files |
| `/files/download/{id}` | GET | Download a file |
| `/files/search?query={q}` | GET | Search files and folders |
| `/files/trash` | GET | View trash bin |
| `/files/history` | GET | View transfer history |

### File Operations

| Route | Method | Description |
|-------|--------|-------------|
| `/files/delete/{id}` | POST | Move file to trash |
| `/files/restore/{id}` | POST | Restore file from trash |
| `/files/rename/{id}` | POST | Rename file |
| `/files/delete_folder/{id}` | POST | Delete folder |
| `/files/restore_folder/{id}` | POST | Restore folder from trash |
| `/files/rename_folder/{id}` | POST | Rename folder |
| `/files/empty_trash` | POST | Empty trash permanently |

### Batch Operations

| Route | Method | Description |
|-------|--------|-------------|
| `/files/batch_delete` | POST | Delete multiple items |
| `/files/batch_restore` | POST | Restore multiple items |
| `/files/batch_move` | POST | Move multiple items |
| `/files/download_folder/{id}` | GET | Download folder as ZIP |

### Folder Operations

| Route | Method | Description |
|-------|--------|-------------|
| `/folders/create` | POST | Create new folder |

### Admin Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/admin/dashboard` | GET | Admin dashboard |
| `/admin/users` | GET | User management |
| `/admin/settings` | GET/POST | System settings |
| `/admin/activities` | GET | Activity logs |

---

## Error Codes

| Code | Description |
|------|-------------|
| `400` | Bad Request - Invalid input data |
| `401` | Unauthorized - Authentication required or invalid credentials |
| `403` | Forbidden - Insufficient privileges |
| `404` | Not Found - Resource does not exist |
| `409` | Conflict - Resource already exists |
| `500` | Internal Server Error |

---

## Rate Limits

The following rate limits apply to API requests:

- **Search queries:** Maximum 100 characters
- **Batch operations:** Maximum 50 items per request

---

## Security Features

The API implements the following security measures:

1. **Authentication:** HTTP Basic Auth required for all API endpoints
2. **CSRF Protection:** Web routes protected with CSRF tokens
3. **Security Headers:**
   - `X-Frame-Options: DENY` - Prevents clickjacking
   - `X-Content-Type-Options: nosniff` - Prevents MIME sniffing
   - `X-XSS-Protection: 1; mode=block` - XSS protection
   - `Referrer-Policy: strict-origin-when-cross-origin`
4. **Input Validation:** File names validated to prevent path traversal
5. **Size Limits:** Search queries and batch operations limited

---

## Changelog

### Version 1.0.0 (2024-03-20)
- Initial API documentation
- Documented all user, file, and admin endpoints
- Added security information

---

**Note:** This API is subject to change. Please check for updates regularly.
