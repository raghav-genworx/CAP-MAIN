# Firebase Auth And PostgreSQL Roles

The core platform service uses Firebase only for identity verification. Platform
authorization data is stored in PostgreSQL. The API does not store passwords or
login sessions.

## Request Flow

1. The frontend signs in through the Firebase web SDK.
2. Firebase returns an ID token to the browser.
3. The frontend calls protected API routes with
   `Authorization: Bearer <firebase-id-token>`.
4. The API verifies the token audience, signature, expiry, issuer, and Firebase
   UID.
5. The API reads `user_roles.uid = <firebase_uid>` from PostgreSQL.
6. The request continues only when the role is active and authorized.

## Role Table

PostgreSQL table: `user_roles`

Primary key: Firebase UID

```json
{
  "uid": "firebase-user-id",
  "email": "recruiter@example.com",
  "role": "recruiter",
  "is_active": true,
  "created_at": "2026-06-17T00:00:00Z",
  "updated_at": "2026-06-17T00:00:00Z"
}
```

Only `recruiter` is supported now, but the enum and service boundary are ready
for more roles later.
