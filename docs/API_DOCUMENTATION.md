# SCHEME SAATHI API Documentation

Base URL: `http://localhost:8000`
Versioned API prefix: `/api/v1`
Interactive docs after startup: `/docs` and `/redoc`

## Health
- `GET /health`

## Auth
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/anonymous`

## Profile
- `GET /api/v1/profile`
- `PUT /api/v1/profile`

## Chat
- `POST /api/v1/chat`

## Schemes
- `GET /api/v1/schemes/search?q=farmer&state=central`
- `GET /api/v1/schemes/{scheme_id}`

## Recommendations
- `GET /api/v1/recommendations`

## Eligibility
- `POST /api/v1/eligibility/check`

## Voice
- `POST /api/v1/voice/query`
  - multipart form fields: `audio` or `text`, optional `language`

## Notifications
- `POST /api/v1/notifications`

## Admin
Send header `X-Admin-Key: hackathon-admin-key` unless changed in `.env`.
- `POST /api/v1/admin/upload-dataset`
- `POST /api/v1/admin/rebuild-embeddings`
- `POST /api/v1/admin/reindex`
- `GET /api/v1/admin/dataset-stats`

## Example Chat Request
```json
{
  "message": "I am a farmer in Bihar looking for income support schemes",
  "language": "en",
  "state": "bihar"
}
```

## Example Eligibility Request
```json
{
  "scheme_id": "pm-kisan",
  "profile": {
    "name": "Ravi",
    "state": "bihar",
    "age": 32,
    "gender": "male",
    "occupation": "farmer",
    "income": 120000,
    "caste": "obc",
    "disability": false,
    "preferred_language": "hi"
  }
}
```
