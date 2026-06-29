# Brevo Invite Email Setup

The assessment platform sends candidate invite links through Brevo Transactional Email.

Do not use Brevo Marketing Campaigns for assessment invites. Each candidate invite contains a unique secure token, so the backend must send one transactional email per candidate assignment.

## Environment Variables

Set these in `core-assessment-platform-service/.env`:

```env
BREVO_BASE_URL=https://api.brevo.com/v3
BREVO_API_KEY=your_brevo_transactional_api_key
BREVO_SENDER_EMAIL=verified_sender@example.com
BREVO_SENDER_NAME=CAP Assessments
APP_BASE_URL=http://localhost:5173
```

`APP_BASE_URL` must be the frontend URL candidates can open. In production this should be the deployed frontend domain.

## Brevo Dashboard Steps

1. Create or log in to your Brevo account.
2. Go to `SMTP & API`.
3. Open the `API Keys` tab.
4. Create a new API key for this project.
5. Copy the key into `BREVO_API_KEY` in the local `.env` file.
6. Go to `Senders, Domains & Dedicated IPs`.
7. Add and verify the sender email address you want candidates to see.
8. Put that same email into `BREVO_SENDER_EMAIL`.
9. If using a custom domain, complete Brevo domain authentication by adding the DNS records Brevo gives you.
10. Restart the core assessment platform service after editing `.env`.

## How Invites Are Sent

1. Recruiter creates an assessment.
2. Recruiter creates a test slot.
3. Recruiter imports candidates into that test slot.
4. Recruiter clicks `Send Invites`.
5. The API schedules a background task.
6. The background task generates a fresh invite token for each candidate.
7. The backend sends one transactional email per candidate through `POST /smtp/email`.
8. Candidate email status becomes `sent` or `failed`.

## Verify Delivery

After sending invites:

1. Open the test detail page.
2. Go to `Candidates & Batch`.
3. Check each candidate's invite status.
4. In Brevo, check `Transactional` email logs for accepted, delivered, bounced, or rejected messages.

If all candidates show `failed`, check:

1. `BREVO_API_KEY` is present and correct.
2. `BREVO_SENDER_EMAIL` is verified in Brevo.
3. Brevo transactional sending is enabled for the account.
4. The core service was restarted after `.env` changes.
5. `APP_BASE_URL` points to the frontend URL candidates can access.
