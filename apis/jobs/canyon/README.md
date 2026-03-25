# Canyon (usecanyon.com) - Reverse Engineered API Documentation

## What is Canyon?

Canyon is a modern career platform (SaaS) that helps job seekers:
- **Track job applications** on a Kanban-style board (Wishlist → Applied → Interviewing → Offer/Rejected)
- **Build and manage resumes** with multiple templates and AI-powered writing assistance
- **Generate cover letters** using AI tailored to specific job descriptions
- **Prep for interviews** with AI mock interview simulations
- **Search 600k+ job listings** with filters for location, salary, remote work, etc.
- **Score and analyze resumes** against job descriptions
- **Generate professional headshots** using AI (upload a photo → get professional headshots)
- **Auto-fill job applications** using resume data

The platform is targeted at individual job seekers and career advisors/coaches who manage multiple clients.

---

## Architecture

| Component | Technology | URL |
|-----------|-----------|-----|
| Frontend | Next.js (App Router) | https://app.usecanyon.com |
| Landing Page | Next.js | https://www.usecanyon.com |
| GraphQL API | Rails + GraphQL-Ruby | https://api.usecanyon.com/graphql |
| WebSocket | Rails Action Cable | wss://api.usecanyon.com/cable |
| File Upload | REST (Rails) | https://api.usecanyon.com/upload |
| Auth | NextAuth.js | https://app.usecanyon.com/api/auth/* |
| Analytics | PostHog (relayed) | https://app.usecanyon.com/analytics-relay/* |
| Error Tracking | Rollbar | https://app.usecanyon.com/rb |
| Monitoring | Vercel Speed Insights | https://app.usecanyon.com/_vercel/speed-insights/* |

---

## Authentication

### Overview

Canyon uses **NextAuth.js** with two authentication methods:
1. **Google OAuth** (primary) - "Continue with Google" button
2. **Native Credentials** - Email + Password

After successful authentication, Canyon's Rails backend issues a **custom Bearer JWT token** that must be included in all API requests.

### Auth Token Flow

```
Browser                  NextAuth (Vercel)       Canyon Rails API
  |                           |                       |
  |-- POST /api/auth/signin -->|                       |
  |     (email, password)     |                       |
  |                           |-- authSignIn mutation->|
  |                           |    (email, password)  |
  |                           |<-- { token, user } ---|
  |<-- session cookie --------|                       |
  |                           |                       |
  |-- POST /graphql ----------|---------------------->|
  |     Authorization: Bearer {token}                 |
  |<-- GraphQL response ------|----------------------<|
```

The token from `AuthResponse.token` is:
- A custom server-generated ID (stored as an `ID` scalar, not a JWT)
- Used as `Authorization: Bearer <token>` header for all GraphQL requests
- Used as `?token=<token>` query parameter for WebSocket connections

### Auth Providers (NextAuth)

From `https://app.usecanyon.com/api/auth/providers`:

```json
{
  "signin": {
    "id": "signin",
    "type": "credentials",
    "signinUrl": "https://app.usecanyon.com/api/auth/signin/signin",
    "callbackUrl": "https://app.usecanyon.com/api/auth/callback/signin"
  },
  "signup": {
    "id": "signup",
    "type": "credentials",
    "signinUrl": "https://app.usecanyon.com/api/auth/signin/signup",
    "callbackUrl": "https://app.usecanyon.com/api/auth/callback/signup"
  },
  "google": {
    "id": "google",
    "type": "oauth",
    "signinUrl": "https://app.usecanyon.com/api/auth/signin/google",
    "callbackUrl": "https://app.usecanyon.com/api/auth/callback/google"
  }
}
```

### Google OAuth Parameters

```
Authorization URL: https://accounts.google.com/v3/signin/identifier
Client ID:         134277461262-t6trpdctf81ckqm3aevtg6882l4kcd93.apps.googleusercontent.com
Redirect URI:      https://app.usecanyon.com/api/auth/callback/google
Scopes:            openid email profile
Response Type:     code
PKCE:              Yes (code_challenge_method=S256)
```

---

## How to Extract Your Auth Token

### Method 1: DevTools Network Tab (Recommended)

1. Open https://app.usecanyon.com and sign in
2. Open Chrome/Firefox DevTools (F12) → **Network** tab
3. Filter by "graphql" in the search box
4. Click any GraphQL request to `api.usecanyon.com/graphql`
5. In the **Request Headers** section, find the `authorization` header
6. Copy the value — it looks like: `Bearer eyJhbGciOi...` or `Bearer abc123def456...`
7. Remove the `Bearer ` prefix — the remaining string is your token

### Method 2: DevTools Console

1. Sign in to https://app.usecanyon.com
2. Open DevTools (F12) → **Console** tab
3. Run this command:
   ```javascript
   (await (await fetch('/api/auth/session')).json()).token
   ```
4. The output is your token

### Method 3: Programmatic (credentials-based accounts)

```python
from usecanyon_client import CanyonClient

client = CanyonClient()
result = client.authenticate_with_credentials("your@email.com", "yourpassword")
token = result["token"]
print(f"Token: {token}")
```

---

## API Endpoints

### GraphQL Endpoint

```
POST https://api.usecanyon.com/graphql
Content-Type: application/json
Authorization: Bearer <token>

Body: { "query": "...", "variables": {...} }
```

The GraphQL API supports full introspection (no introspection blocking detected).

### File Upload Endpoint

```
POST https://api.usecanyon.com/upload
Authorization: Bearer <token>
Content-Type: multipart/form-data

Form field: file=<binary file data>

Response: { "signed_id": "eyJfcm..." }
```

The `signed_id` returned is then passed to GraphQL mutations like `uploadResume`, `uploadResumeWebsocket`, `createHeadshotRequest`, and `userUploadProfilePicture`.

### WebSocket Endpoint

```
wss://api.usecanyon.com/cable?token=<token>
```

Used for real-time subscriptions (resume roasting, Glassdoor results, OCR, etc.).

### NextAuth Endpoints

```
GET  https://app.usecanyon.com/api/auth/session       - Get current session
GET  https://app.usecanyon.com/api/auth/csrf           - Get CSRF token
GET  https://app.usecanyon.com/api/auth/providers      - List auth providers
POST https://app.usecanyon.com/api/auth/signin/signin  - Sign in with credentials
POST https://app.usecanyon.com/api/auth/signin/signup  - Sign up with credentials
GET  https://app.usecanyon.com/api/auth/signin/google  - Initiate Google OAuth
GET  https://app.usecanyon.com/api/auth/callback/google - Google OAuth callback
```

---

## GraphQL Schema Overview

### Query Operations (49 total)

| Query | Description |
|-------|-------------|
| `user()` | Get current authenticated user |
| `usersJobs(usersJobIds, archived, searchTerm)` | Get tracked job applications |
| `paginatedUsersJobs(page, perPage, ...)` | Paginated job applications |
| `resumes(resumeIds, archived, searchTerm, limit)` | Get resumes |
| `coverLetters(coverLetterIds, archived, searchTerm)` | Get cover letters |
| `interviews(interviewIds)` | Get mock interview sessions |
| `paginatedJobListings(searchTerm, page, perPage, attributes)` | Search job listings (600k+) |
| `jobListing(jobListingId)` | Get a specific job listing |
| `hasAddedJobListing(jobListingId)` | Check if user applied to a job |
| `resumeScore(id)` | Get resume score |
| `headshotRequests(headshotRequestIds)` | Get AI headshot requests |
| `jobSearchPreference()` | Get user's job search preferences |
| `advisors(...)` | Get advisors (for advisory org accounts) |
| `clients(...)` | Get clients (for advisory org accounts) |
| `clientGroups(...)` | Get client groups |
| `paginatedResumeExamples(...)` | Browse resume examples |
| `resumeExampleCategories()` | Get resume example categories (17 categories) |
| `publicResume(publicId)` | Get a publicly shared resume |
| `getLatestCompanyInfo(usersJobId)` | AI-powered company research |
| `getAboutCompanyInfo(usersJobId)` | Get company about info |
| `getGlassdoorResults(usersJobId)` | Get Glassdoor data for a company |
| `networkingPeopleFromUsersJob(usersJobId)` | Find networking contacts |
| `getLinkedinConnectionsUrl(usersJobId)` | Get LinkedIn connections URL |
| `similarProfilesFromUsersJob(usersJobId)` | Find similar LinkedIn profiles |
| `findUsersJobByUrl(url)` | Find job app by URL |
| `findUsersJobByInfo(companyName, position, ...)` | Find job app by details |
| `locationsTypeahead(location)` | Location search typeahead |
| `usersJobsDateRange(fromDate, toDate)` | Job application analytics over time |
| `writingSamples()` | Get writing samples |
| `savedFilters()` | Get saved job search filters |

### Mutation Operations (90 total)

**Auth:**
- `authSignIn(email, password)` → `AuthResponse { token, user, isNewUser }`
- `authSignUp(email, firstName, lastName, ...)` → `AuthResponse`
- `authProviderAuthenticate(provider, data, ...)` → `AuthResponse` (for Google OAuth)
- `authPasswordResetRequest(email)` → String
- `authResetPassword(resetPasswordToken, newPassword)` → String

**User Management:**
- `updateUser(attributes)` → Users
- `userUploadProfilePicture(uploadSignedId)` → Users
- `userEmailVerify(emailVerificationCode, password, ...)` → AuthResponse
- `userStoreLocation(city, state)` → Users
- `userUpdateWritingStyle(writingStyleEnum)` → Users
- `userUpsertJobSearchPreference(attributes)` → JobSearchPreference
- `updateAdvisoryOrganization(name, uploadSignedId)` → Users

**Job Applications (UsersJobs):**
- `createUsersJob(position, companyName, status, ...)` → UsersJobs
- `updateUsersJob(id, status, position, ...)` → UsersJobs
- `addContactToUsersJob(id, contact)` → UsersJobs
- `generateCompanyDomain(id)` → UsersJobs
- `exportUsersJobToCsv()` → String (CSV content)
- `shareJobWithClients(usersJobId, userIds, ...)` → UsersJobs

**Job Listings:**
- `bookmarkJob(jobListingId, status)` → UsersJobs
- `unbookmarkJob(jobListingId)` → UsersJobs
- `markJobListingAsApplied(jobListingId)` → UsersJobs
- `createSearchFilter(name, searchFilters)` → JobListingSavedSearch
- `updateSearchFilter(id, searchFilters)` → JobListingSavedSearch

**Resumes:**
- `createResume(name)` → Resumes
- `createResumeFromLinkedinUrl(linkedinProfileUrl)` → Resumes
- `updateResume(id, attributes)` → Resumes
- `duplicateResume(id)` → Resumes
- `updateArchivedResume(id, archived)` → Resumes
- `uploadResume(uploadSignedId, name, id)` → Resumes
- `uploadResumeWebsocket(uploadSignedId, name, id)` → String
- `downloadPdfResume(id)` → Resumes
- `scoreResume(id)` → ResumesScoreType
- `updatePublicResume(id, isPublic)` → Resumes
- `updateTemplateResume(id, template, templateColorEnum)` → Resumes
- `updateResumePreferences(id, attributes)` → Resumes
- `requestResumeReview(id, notes)` → String
- `roastResume(uploadSignedId, token, roleType, toneLevel, jobTitle)` → String
- `analyzeResume(id)` → ResumesResumeRelevanceAnalysis (via subscription)
- `fixFromRelevanceAnalysis(id, summary, achievementsToUpdate, ...)` → Resumes
- `optimizeResumeForJob(resumeId, usersJobId, keywords, skills)` → Resumes
- `optimizeResumeForJobV2(resumeId, usersJobId, jobListingId, ...)` → Resumes
- `updatePdfBlob(id, pdfBlob)` → Resumes
- `duplicateResumeFromResumeExample(id)` → Resumes
- `previewResume(attributes, template)` → String (HTML)
- `previewAuthResume(id, template)` → String (HTML)

**Cover Letters:**
- `generateCoverLetter(usersJobId, resumeId, coverLetterTone, coverLetterLength, customPrompt)` → UsersJobsCoverLetterType
- `coverLetterUpsert(usersJobId, attributes)` → UsersJobsCoverLetterType
- `updateArchivedCoverLetter(coverLetterId, archived)` → UsersJobsCoverLetterType
- `coverLetterBodyPrefillApplication(usersJobId, resumeId)` → String

**AI Features:**
- `generateProfessionalSummary(id, useExisting, keywords, customPrompt)` → String
- `generateOneJobAchievement(workPositionId, index, keywords, customPrompt)` → String
- `generateJobAchievement(workPositionId, indices, keywords)` → streaming
- `generateJobAchievementFromString(achievementStrings, keywords, customPrompt)` → streaming
- `amIAGoodFit(resumeId, position, jobDescription, usersJobId, jobListingId)` → AmIAGoodFit
- `matchScore(usersJobId, resumeId)` → UsersJobsMatch
- `salaryInsights(usersJobId)` → String
- `generateMessageForContact(messageType, contactRelationship, ...)` → SimilarProfilesMessage
- `generateDraftEmailForSimilarProfile(resumeId, usersJobId, ...)` → SimilarProfilesMessage
- `jobsFormFieldsMapping(htmlString, resumeId, ...)` → form mappings
- `jobsFormFieldsMappingV2(htmlString, resumeId, ...)` → String (JSON)
- `fetchJobKeywords(usersJobId, jobListingId, jobTitle)` → streaming
- `fetchMissingSkillsOfJobResume(usersJobId, jobListingId, resumeId)` → streaming
- `learnSkills(usersJobId)` → CachedStreamingType
- `sampleInterviewQuestions(usersJobId)` → CachedStreamingType
- `questionPrefillApplication(resumeId, question)` → String
- `fakeJob(companyName, datePosted)` / `fakeJobMutation(...)` → FakeJobInfo

**Interview:**
- `interviewStartMock(jobTitle, interviewType, jobDescription, ...)` → Interview
- `interviewAddMessage(message, interviewId)` → Interview

**Headshots:**
- `createHeadshotRequest(uploadSignedId, attire, background)` → HeadshotRequest

**Billing:**
- `subscriptionsSessionCreate(plan, coupon, isOnboarding)` → String (Stripe session URL)
- `subscriptionsSessionFetch(sessionId)` → String
- `billingPortalUrl()` → String
- `subscriptionsRedeemLtdPromoCode(promoCode)` → Users
- `subscriptionsRequestResumeSuccess(id, sessionId, notes)` → String

**Advisory (B2B features):**
- `inviteAdvisor(email, role)` → Users
- `inviteClient(email)` → Users
- `assignClientToAdvisor(clientIds, advisorId)` → String
- `createClientGroup(name)` → ClientGroup
- `editClientGroup(clientGroupId, name, userIds)` → ClientGroup
- `addUsersToClientGroup(userIds, clientGroupId)` → ClientGroup

### Subscription Operations (6 total)

Used via WebSocket (`wss://api.usecanyon.com/cable?token=<token>`):

| Subscription | Description |
|-------------|-------------|
| `roast()` | Stream resume roast feedback |
| `glassdoor()` | Stream Glassdoor results |
| `ocrResume()` | Stream OCR resume processing |
| `learnSkills()` | Stream skill learning content |
| `sampleInterviewQuestions()` | Stream interview questions |
| `formFieldsMapping()` | Stream form field mappings |

---

## Key Types

### AuthResponse
```graphql
type AuthResponse {
  token: ID
  user: Users
  isNewUser: Boolean
}
```

### Users (partial)
```graphql
type Users {
  id: ID
  email: String
  firstName: String
  lastName: String
  role: UsersRoleEnum         # user | advisor | admin
  plan: SubscriptionPlanEnum  # free | silver | gold | ltdGold etc.
  hasSubscription: Boolean
  targetJobTitle: String
  jobExperienceLevel: JobListingExperienceLevelEnum
  profilePictureUrl: String
  # ... 60+ more fields
}
```

### UsersJobs (job application)
```graphql
type UsersJobs {
  id: ID
  position: String
  companyName: String
  status: UsersJobsStatusEnum   # wishlist | applied | interviewing | offer | rejected
  url: String
  location: String
  isRemote: Boolean
  salaryMin: Int
  salaryMax: Int
  payPeriod: UsersJobsPayPeriodEnum
  notes: String
  jobDetails: String
  archived: Boolean
  interviewStep: UsersJobsInterviewStepEnum
  rejectedStage: UsersJobsRejectedStageEnum
  matchLevel: UsersJobsMatchEnum
  resume: Resumes
  coverLetter: UsersJobsCoverLetterType
  contacts: [Contacts]
  appliedAt: ISO8601DateTime
  interviewedAt: ISO8601DateTime
  createdAt: ISO8601DateTime
  updatedAt: ISO8601DateTime
}
```

### Pagination
```graphql
type Pagination {
  page: Int!
  pageSize: Int!
  totalCount: Int!
  totalPages: Int!
}
```

---

## Usage Examples

### Installation

```bash
pip install requests
```

### Basic Usage

```python
from usecanyon_client import CanyonClient

# Option 1: Use a pre-obtained token
client = CanyonClient(token="your_bearer_token_here")

# Option 2: Authenticate with credentials
client = CanyonClient()
client.authenticate_with_credentials("you@example.com", "yourpassword")

# Option 3: Use environment variables
# CANYON_TOKEN=your_token python script.py
# CANYON_EMAIL=you@example.com CANYON_PASSWORD=pass python script.py
```

### Search Job Listings

```python
from usecanyon_client import CanyonClient

client = CanyonClient()  # No auth required for job search

results = client.search_job_listings(
    search_term="product manager",
    per_page=20,
    attributes={
        "isRemote": True,
        "salaryMin": 120000,
    }
)

print(f"Total jobs: {results['pagination']['totalCount']}")
for job in results['data']:
    print(f"  {job['position']} @ {job['companyName']} - {job['location']}")
```

### Track a Job Application

```python
from usecanyon_client import CanyonClient

client = CanyonClient(token="your_token")

# Add a job to track
job = client.create_users_job(
    position="Senior Software Engineer",
    company_name="Stripe",
    status="applied",
    url="https://stripe.com/jobs/listing/123",
    location="San Francisco, CA",
    is_remote=True,
    salary_min=180000,
    salary_max=250000,
    notes="Applied via referral from John",
)
print(f"Created job ID: {job['id']}")

# Update status as you progress
client.update_users_job(job['id'], status="interviewing")

# Export all jobs to CSV
csv_data = client.export_users_jobs_to_csv()
with open("job_applications.csv", "w") as f:
    f.write(csv_data)
```

### Generate a Cover Letter

```python
from usecanyon_client import CanyonClient

client = CanyonClient(token="your_token")

# Get a resume and job
resumes = client.get_resumes()
jobs = client.get_users_jobs()

# Generate cover letter
cover_letter = client.generate_cover_letter(
    users_job_id=jobs[0]['id'],
    resume_id=resumes[0]['id'],
    tone="professional",
    length="medium",
    custom_prompt="Focus on my Python and data engineering experience",
)
print(cover_letter['body'])
```

### Score a Resume

```python
from usecanyon_client import CanyonClient

client = CanyonClient(token="your_token")

resumes = client.get_resumes()
score = client.score_resume(resumes[0]['id'])
print(f"Overall score: {score['score']}")
for field in score.get('fields', []):
    print(f"  {field['type']}: {field['score']}")
```

### Start a Mock Interview

```python
from usecanyon_client import CanyonClient

client = CanyonClient(token="your_token")

# Start an interview session
interview = client.start_mock_interview(
    job_title="Product Manager",
    interview_type="behavioral",
    job_description="We're looking for a PM to lead our growth team...",
)
print(f"Interview started: {interview['id']}")
# Print the first question
for msg in interview['messages']:
    if msg['role'] == 'assistant':
        print(f"Interviewer: {msg['content']}")
        break

# Send your answer
response = client.send_interview_message(
    interview_id=interview['id'],
    message="In my previous role at XYZ, I led a team that increased..."
)
# Get next question
for msg in reversed(response['messages']):
    if msg['role'] == 'assistant':
        print(f"Interviewer: {msg['content']}")
        break
```

### Upload a Resume File

```python
from usecanyon_client import CanyonClient

client = CanyonClient(token="your_token")

# Upload a PDF or DOCX resume
resume = client.upload_resume(
    file_path="my_resume.pdf",
    name="My Main Resume 2024"
)
print(f"Uploaded resume: {resume['id']} - {resume['name']}")
```

### Raw GraphQL Query

```python
from usecanyon_client import CanyonClient

client = CanyonClient(token="your_token")

# Execute any GraphQL query directly
result = client.execute("""
query {
  user {
    id
    email
    firstName
    tokenCoverLetter
    tokenInterview
    tokenOptimizeResume
  }
}
""")
print(result)
```

---

## Enums

### UsersJobsStatusEnum
- `wishlist` - Job saved to wishlist (not yet applied)
- `applied` - Application submitted
- `interviewing` - In the interview process
- `offer` - Received an offer
- `rejected` - Application rejected

### CoverLetterToneEnum
- `professional`
- `confident`
- `friendly`
- `formal`

### CoverLetterLengthEnum
- `short`
- `medium`
- `long`

### ResumesTemplateEnum
Various resume templates available in the Canyon resume builder.

### UsersJobsInterviewStepEnum
- `phone_screen`
- `technical`
- `behavioral`
- `panel`
- `final`
- `offer`

### SubscriptionPlanEnum
- `free`
- `silver`
- `gold`
- Various LTD (Lifetime Deal) plans

---

## Notes

1. **CSRF**: The NextAuth endpoints require CSRF tokens for credential-based sign-in via the NextAuth flow. However, the GraphQL `authSignIn` mutation can be called directly without CSRF.

2. **Rate Limiting**: No rate limiting was observed during testing, but be respectful and avoid excessive requests.

3. **Public Endpoints**: The following work without authentication:
   - `paginatedJobListings` query
   - `resumeExampleCategories` query
   - `resumeExamples` query
   - `publicResume` query (for shared resumes)
   - `resumeUnauthenticated` query
   - `createResumeUnauthenticated` mutation

4. **File Uploads**: The `POST /upload` endpoint uses multipart form data with a `file` field. It returns `{ "signed_id": "..." }` which is a Rails ActiveStorage signed blob ID.

5. **WebSocket**: The Action Cable WebSocket endpoint requires the token as a query parameter: `wss://api.usecanyon.com/cable?token=<token>`. The `actioncable` npm package or equivalent is needed to interact with subscriptions.

6. **Advisory Features**: The `advisors`, `clients`, `clientGroups`, and related mutations are only available to users with `role: advisor` or `role: admin` on advisory organization accounts.

7. **AI Token Usage**: Many AI features consume "tokens" (not JWT tokens, but Canyon's internal credits):
   - `tokenCoverLetter`: Cover letter generation
   - `tokenInterview`: Mock interviews
   - `tokenOptimizeResume`: Resume optimization
   - `tokenProfessionalSummary`: Professional summary generation
   - `tokenJobMatch`: Job match scoring
   - `tokenSalaryInsights`: Salary insights
   - Free users have limited credits; paid plans have more.
