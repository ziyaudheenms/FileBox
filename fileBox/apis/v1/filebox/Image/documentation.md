# FileBox API Documentation

## Table of Contents
1. [Authentication](#authentication)
2. [File/Folder Management](#filefolder-management)
3. [Storage Management](#storage-management)
4. [Permission Management](#permission-management)
5. [Share Link Management](#share-link-management)
6. [Test Endpoint](#test-endpoint)
7. [Authentication Endpoints](#authentication-endpoints)
8. [Common Status Codes](#common-status-codes)

---

## Authentication

All endpoints (except test) require Clerk JWT authentication via the `Authorization` header.

**Rate Limiting**: Tier-based rates (FREE: 10/m, PRO: 25/m, ADVANCED: 50/m) + Token Bucket algorithm (100/m, burst: 200)

---

## File/Folder Management

### 1. Upload Image
**Endpoint**: `POST /api/v1/Create/Image/`

**Description**: Upload a single image file directly (non-chunked)

**Request**:
```
Content-Type: multipart/form-data
- image: File
- folderID: UUID (optional) - Parent folder ID
```

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Image Added to Queue Successfully, Upload Started",
  "data": "file_instance_pk"
}
```

**Error Responses**:
- `4001`: User not authenticated
- `5000+`: Various upload errors

---

### 2. Create Folder
**Endpoint**: `POST /api/v1/Create/Folder/`

**Description**: Create a new folder

**Request**:
```json
{
  "name": "Folder Name",
  "folderID": "parent_folder_uuid"
}
```

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Folder Created Successfully",
  "data": "folder_pk"
}
```

---

### 3. Upload Image in Chunks
**Endpoint**: `POST /api/v1/Create/Image/Chunk/`

**Description**: Upload a chunk of an image file (for large files)

**Request**:
```json
{
  "chunk": "binary_data",
  "chunkIndex": 0,
  "totalChunks": 5,
  "fileId": "unique_file_id",
  "fileName": "image.jpg"
}
```

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Started Uploading the chunks",
  "data": ""
}
```

---

### 4. Join Chunks
**Endpoint**: `POST /api/v1/Create/Image/Chunk/Join/`

**Description**: Merge uploaded chunks into a single file and initiate upload

**Request**:
```json
{
  "fileId": "unique_file_id",
  "fileName": "image.jpg",
  "fileSize": 1024000,
  "fileExtenstion": ".jpg",
  "folderID": "parent_folder_uuid"
}
```

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Image Queued Successfully",
  "data": "file_instance_pk"
}
```

---

### 5. Get All Files/Folders
**Endpoint**: `GET /api/v1/fileFolders`

**Description**: Fetch paginated list of files/folders for a user (with optional parent folder filter)

**Query Parameters**:
- `parentFolderID`: UUID (optional) - Filter by parent folder
- `cursor`: string (optional) - Pagination cursor

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Folder Created Successfully",
  "data": [],
  "next": "cursor_token",
  "previous": "cursor_token"
}
```

**Error Responses**:
- `4001`: User not authenticated
- `5002`: No files/folders found

---

### 6. Delete File/Folder
**Endpoint**: `DELETE /api/v1/delete/FolderFile/`

**Description**: Permanently delete a file or folder

**Query Parameters**:
- `fileFolderID`: UUID - ID of file/folder to delete

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Folder/File Deleted Successfully",
  "data": ""
}
```

---

### 7. Toggle Trash Status
**Endpoint**: `GET /api/v1/trash/FolderFile/`

**Description**: Move file/folder to trash or restore from trash

**Query Parameters**:
- `fileFolderID`: UUID - ID of file/folder
- `parentFolderID`: UUID (optional) - Parent folder ID

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Folder/File Updated Successfully",
  "data": ""
}
```

---

### 8. Get Trash Files/Folders
**Endpoint**: `GET /api/v1/fileFolders/Trash`

**Description**: Fetch paginated list of trashed items

**Query Parameters**:
- `cursor`: string (optional) - Pagination cursor

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Folder Created Successfully",
  "data": []
}
```

---

### 9. Toggle Favorite Status
**Endpoint**: `GET /api/v1/favorite/FolderFile/`

**Description**: Mark/unmark file or folder as favorite

**Query Parameters**:
- `fileFolderID`: UUID - ID of file/folder

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Folder/File Updated Successfully",
  "data": ""
}
```

---

### 10. Get Favorite Files/Folders
**Endpoint**: `GET /api/v1/fileFolders/Favorite`

**Description**: Fetch paginated list of favorite items

**Query Parameters**:
- `cursor`: string (optional) - Pagination cursor

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Folder Updated Successfully",
  "data": []
}
```

---

### 11. Get Single Image/File Details
**Endpoint**: `GET /api/v1/fileFolders/Image`

**Description**: Fetch details of a specific file/image

**Query Parameters**:
- `imageFileID`: UUID - ID of the file

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Image Fetched Successfully",
  "data": {}
}
```

---

## Storage Management

### 12. Get Storage Details
**Endpoint**: `GET /api/v1/storage/status/`

**Description**: Fetch user's storage usage and limits

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Storage Details Fetched Successfully",
  "data": {
    "total_storage_limit": "5 GB",
    "used_storage": "2.5 GB",
    "total_image_storage": "1 GB",
    "total_document_storage": "1.5 GB",
    "total_other_storage": "0 KB"
  }
}
```

---

## Permission Management

### 13. Search Users for Permission
**Endpoint**: `POST /api/v1/permission/getUser`

**Description**: Find users by email prefix for permission assignment

**Request**:
```json
{
  "userToFind": "user@example"
}
```

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Users with email that starts with user@example",
  "data": [
    {
      "id": "user_id",
      "username": "john_doe",
      "email": "user@example.com",
      "profile": "profile_image_url"
    }
  ]
}
```

---

### 14. Assign Permissions to Users
**Endpoint**: `POST /api/v1/permission/grandUsers`

**Description**: Grant file/folder access permissions to users

**Query Parameters**:
- `fileFolderID`: UUID - ID of file/folder to share

**Request**:
```json
{
  "usersToGrandPermission": [
    {
      "email": "user@example.com",
      "permission": "VIEW"
    }
  ]
}
```

**Permission Types**: `VIEW`, `EDIT`, `ADMIN`

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Successfully Updated the permissions..",
  "data": ""
}
```

**Error Responses**:
- `5002`: Invalid permission type or user not found
- `5003`: User has no rights to modify permissions

---

### 15. Get Users with Permissions
**Endpoint**: `GET /api/v1/permission/Users`

**Description**: Fetch all users who have access to a file/folder

**Query Parameters**:
- `fileFolderID`: UUID - ID of file/folder

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Successfully Fetched The Data",
  "data": [
    {
      "id": "permission_id",
      "username": "john_doe",
      "email": "john@example.com",
      "profile": "profile_image_url",
      "permission": "EDIT"
    }
  ]
}
```

---

## Share Link Management

### 16. Generate Share Link
**Endpoint**: `POST /api/v1/get/sharableLink`

**Description**: Create a shareable link for a file/folder

**Query Parameters**:
- `fileFolderID`: UUID - ID of file/folder to share
- `type`: string - Type: 'image', 'documents', 'others', or 'folder'

**Request (PRO/ADVANCED users)**:
```json
{
  "access_type": "PUBLIC",
  "password": "optional_password",
  "max_count": 100,
  "expires_at": "2025-12-31T23:59:59Z"
}
```

**Request (FREE users)**:
```json
{
  "access_type": "PUBLIC"
}
```

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Successfully Generated The URL",
  "data": {
    "sharable_link": "sharable/image/uuid-string"
  }
}
```

---
// ...existing code...

### 17. Access Shared File/Folder
**Endpoint**: `POST /api/v1/get/sharedFileFolder`

**Description**: Access and retrieve details of a shared file/folder with comprehensive access control

**Authentication**: Requires Clerk JWT authentication

**Query Parameters**:
- `sharableUUID`: UUID (required) - Sharable link UUID

**Request Body** (optional, only required for password-protected private links):
```json
{
  "password": "password_string"
}
```

**Access Control Logic**:
1. **Owner**: Full access, bypass all checks (is_active, is_expired, count_limited)
2. **PUBLIC Links**: Anyone with the link can access
3. **PRIVATE Links**: 
   - If user has explicit permission: Grant access with permission details
   - Else if password-protected: Validate password, then grant access
   - Else: Deny access

**User Type Access Behavior**:

| User Type | Bypasses Expiry/Limit? | Increments Count? | Requires Password? |
|-----------|------------------------|-------------------|--------------------|
| Author (Owner) | ✅ Yes | ❌ No | ❌ No |
| Public User | ❌ No | ✅ Yes | ❌ No |
| Invited (Private) | ❌ No | ✅ Yes | ❌ No |
| Password Guest | ❌ No | ✅ Yes | ✅ Yes |

**Response** (200 - Success):
```json
{
  "status_code": 5000,
  "message": "Successfully fetched resource",
  "data": {
    "id": "file_folder_uuid",
    "name": "File/Folder Name",
    "type": "image|document|folder",
    "size": 1024000,
    "created_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-01-15T10:30:00Z",
    "is_favorite": false,
    "is_trash": false,
    "permission_data": {
      "permission_type": "VIEW|EDIT|ADMIN",
      "permission_granded_at": "2025-01-15T10:30:00Z"
    }
  }
}
```

**Note**: `permission_data` is only included in response if user has explicit permission on a PRIVATE link

**Error Responses**:

| Status Code | Message | Condition |
|-------------|---------|-----------|
| 4001 | User not authenticated | User is not signed in with Clerk JWT |
| 4001 | User Record Not Found | Authenticated user doesn't exist in database |
| 4002 | Forbidden ! You Have No Access. | User lacks access to PRIVATE link (no permission, no password provided/invalid) |
| 5002 | FileFolder Instance Not Found. | Link is inactive (for non-owners) |
| 5004 | Link is_expired, it cant be used.... | Link has expired (for non-owners) |
| 5006 | The No Of Times The Link Should Use Crossed The Limit. | Access count limit exceeded (for non-owners) |
| 5008 | Wrong Password , Try Again Later! | Password provided doesn't match link password hash |

**Behavior Details**:

- **Access Count Tracking**: Incremented on each access by non-owner users (Public User, Invited, Password Guest)
- **Owner Bypass**: File owners skip all link validation checks (expiry, limits) and don't increment access count
- **Select Related Optimization**: Uses SQL JOIN to fetch ShareLink and FileFolder in single query
- **Permission Data**: Only returned when user has explicit permission on PRIVATE links
- **Database Efficiency**: Uses `.first()` for permission checks, avoiding unnecessary DB hits
- **Password Protection**: Only required for Password Guest user type on PRIVATE links

// ...existing code...
---

## Test Endpoint

### 18. Test Function
**Endpoint**: `GET /api/v1/test/`

**Description**: Simple test endpoint (rate limited: 1/m per IP)

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Hello world",
  "data": ""
}
```

---

## Authentication Endpoints

### 19. Create Clerk User
**Endpoint**: `POST /api/v1/auth/createUser/`

**Description**: Sync a new Clerk user to the database

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Clerk User synced successfully",
  "data": ""
}
```

---

### 20. Update Clerk User
**Endpoint**: `POST /api/v1/auth/updateUser/`

**Description**: Update user profile information

**Response** (200):
```json
{
  "status_code": 5000,
  "message": "Clerk User updated successfully",
  "data": ""
}
```

---

## Common Status Codes

| Code | Meaning |
|------|---------|
| 5000 | Success |
| 5001-5009 | Various business logic errors |
| 4001 | Unauthenticated user |
| 4002 | Forbidden/No access |
| 4004 | Chunks folder not found |

---

## Additional Notes

- All timestamps are in ISO 8601 format
- Cache keys use Redis (version 1 for storage, version 2 for file listings)
- File uploads are processed asynchronously via Celery
- WebSocket updates available at `ws/files/?token=<clerk_jwt>`
- Rate limiting applies per user based on subscription tier
- Pagination uses cursor-based approach for better performance