"""
Canyon (usecanyon.com) API Client
==================================
Reverse-engineered client for the Canyon career platform API.

Canyon is a job search platform that helps users:
- Track job applications on a Kanban board
- Build and manage resumes
- Generate cover letters with AI
- Prep for interviews with AI mock interviews
- Search 600k+ job listings
- Score and analyze resumes

Architecture:
- Frontend: Next.js (app.usecanyon.com)
- Auth: NextAuth.js with Google OAuth and credentials
- API: Rails GraphQL API (api.usecanyon.com/graphql)
- WebSocket: Action Cable (wss://api.usecanyon.com/cable)
- File Upload: REST endpoint (api.usecanyon.com/upload)

Authentication:
- The API uses Bearer token authentication
- Token is obtained via the authSignIn or authSignUp GraphQL mutations
- Token must be passed as: Authorization: Bearer <token>
- For WebSocket subscriptions: wss://api.usecanyon.com/cable?token=<token>

HOW TO EXTRACT YOUR AUTH TOKEN FROM THE BROWSER:
-------------------------------------------------
Option 1 - From DevTools Network tab:
  1. Open https://app.usecanyon.com and sign in
  2. Open Chrome DevTools (F12) -> Network tab
  3. Filter by "graphql"
  4. Click any GraphQL request
  5. In the Request Headers, copy the value of "authorization"
     It will look like: "Bearer eyJhbGciOi..."
  6. Remove the "Bearer " prefix - that's your token

Option 2 - From DevTools Console:
  1. Sign in to https://app.usecanyon.com
  2. Open Chrome DevTools (F12) -> Console tab
  3. Run: (await (await fetch('/api/auth/session')).json()).token
  4. This returns your current session token

Option 3 - Programmatic (credentials auth):
  1. Use the authenticate_with_credentials() method below
  2. This calls the authSignIn GraphQL mutation directly
  3. Returns { token, user } - store the token for future requests

Google OAuth Flow Details:
  - OAuth Client ID: 134277461262-t6trpdctf81ckqm3aevtg6882l4kcd93.apps.googleusercontent.com
  - Redirect URI: https://app.usecanyon.com/api/auth/callback/google
  - Scopes: openid email profile
  - Provider: NextAuth.js with Google OAuth 2.0
  - After OAuth completes, the Canyon backend issues its own JWT token
"""

import os
import json
import mimetypes
from pathlib import Path
from typing import Optional, Any

try:
    import requests
except ImportError:
    raise ImportError("Please install: pip install requests")


# === API Configuration ===

GRAPHQL_URL = "https://api.usecanyon.com/graphql"
UPLOAD_URL = "https://api.usecanyon.com/upload"
NEXTAUTH_SESSION_URL = "https://app.usecanyon.com/api/auth/session"
WEBSOCKET_URL = "wss://api.usecanyon.com/cable"

# Google OAuth parameters (for documentation)
GOOGLE_OAUTH_CLIENT_ID = "134277461262-t6trpdctf81ckqm3aevtg6882l4kcd93.apps.googleusercontent.com"
GOOGLE_OAUTH_REDIRECT_URI = "https://app.usecanyon.com/api/auth/callback/google"
GOOGLE_OAUTH_SCOPES = "openid email profile"


class CanyonAPIError(Exception):
    """Raised when Canyon API returns an error."""
    def __init__(self, message: str, errors: Optional[list] = None):
        super().__init__(message)
        self.errors = errors or []


class CanyonClient:
    """
    Canyon (usecanyon.com) API client.

    Usage:
        # Option 1: Credentials authentication
        client = CanyonClient()
        client.authenticate_with_credentials("email@example.com", "password")

        # Option 2: Pre-obtained Bearer token
        client = CanyonClient(token="your_bearer_token_here")

        # Then use the API
        user = client.get_user()
        jobs = client.get_users_jobs()
        resumes = client.get_resumes()
    """

    def __init__(self, token: Optional[str] = None):
        """
        Initialize the Canyon client.

        Args:
            token: Bearer token for authentication. Can also be set via
                   CANYON_TOKEN environment variable.
        """
        self.token = token or os.environ.get("CANYON_TOKEN")
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (compatible; CanyonClient/1.0)",
            "Origin": "https://app.usecanyon.com",
            "Referer": "https://app.usecanyon.com/",
        })
        if self.token:
            self._set_auth_header()

    def _set_auth_header(self):
        """Set the Authorization header with the Bearer token."""
        self.session.headers["Authorization"] = f"Bearer {self.token}"

    def _graphql(self, query: str, variables: Optional[dict] = None) -> dict:
        """
        Execute a GraphQL query or mutation.

        Args:
            query: The GraphQL query/mutation string
            variables: Optional variables dict

        Returns:
            The 'data' field of the GraphQL response

        Raises:
            CanyonAPIError: If GraphQL returns errors
        """
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        response = self.session.post(GRAPHQL_URL, json=payload)
        response.raise_for_status()
        result = response.json()

        if "errors" in result:
            messages = [e.get("message", str(e)) for e in result["errors"]]
            raise CanyonAPIError(
                f"GraphQL errors: {'; '.join(messages)}",
                errors=result["errors"]
            )

        return result.get("data", {})

    # =========================================================================
    # Authentication
    # =========================================================================

    def authenticate_with_credentials(self, email: str, password: str) -> dict:
        """
        Authenticate using email and password.

        Canyon supports both Google OAuth and native credentials.
        This method uses the GraphQL authSignIn mutation for direct
        credential-based authentication.

        Args:
            email: User's email address
            password: User's password

        Returns:
            dict with keys: token, user (Users object), isNewUser

        Raises:
            CanyonAPIError: If credentials are invalid
        """
        query = """
        mutation AuthSignIn($email: String!, $password: String!) {
          authSignIn(email: $email, password: $password) {
            token
            isNewUser
            user {
              id
              email
              firstName
              lastName
              role
              plan
              hasSubscription
              hasCompletedOnboarding
            }
          }
        }
        """
        data = self._graphql(query, {"email": email, "password": password})
        result = data["authSignIn"]
        self.token = result["token"]
        self._set_auth_header()
        return result

    def sign_up(
        self,
        email: str,
        password: Optional[str] = None,
        first_name: str = "",
        last_name: str = "",
        utm_source: Optional[str] = None,
    ) -> dict:
        """
        Create a new account.

        Args:
            email: User's email address
            password: Password (required for credential-based signup)
            first_name: User's first name
            last_name: User's last name
            utm_source: Optional UTM source for analytics

        Returns:
            dict with keys: token, user, isNewUser
        """
        query = """
        mutation AuthSignUp(
          $email: String!,
          $firstName: String,
          $lastName: String,
          $utmSource: String
        ) {
          authSignUp(
            email: $email,
            firstName: $firstName,
            lastName: $lastName,
            utmSource: $utmSource
          ) {
            token
            isNewUser
            user {
              id
              email
              firstName
              lastName
            }
          }
        }
        """
        data = self._graphql(query, {
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "utmSource": utm_source,
        })
        result = data["authSignUp"]
        self.token = result["token"]
        self._set_auth_header()
        return result

    def request_password_reset(self, email: str) -> str:
        """
        Request a password reset email.

        Args:
            email: The email address to send the reset link to

        Returns:
            Success message string
        """
        query = """
        mutation ForgotPassword($email: String!) {
          authPasswordResetRequest(email: $email)
        }
        """
        data = self._graphql(query, {"email": email})
        return data["authPasswordResetRequest"]

    def reset_password(self, reset_token: str, new_password: str) -> str:
        """
        Reset password using a reset token from email.

        Args:
            reset_token: Token from the password reset email
            new_password: New password to set

        Returns:
            Success message string
        """
        query = """
        mutation ResetPassword($resetPasswordToken: String!, $newPassword: String!) {
          authResetPassword(resetPasswordToken: $resetPasswordToken, newPassword: $newPassword)
        }
        """
        data = self._graphql(query, {
            "resetPasswordToken": reset_token,
            "newPassword": new_password,
        })
        return data["authResetPassword"]

    # =========================================================================
    # User Profile
    # =========================================================================

    def get_user(self) -> dict:
        """
        Get the current authenticated user's profile.

        Returns:
            Users object with profile fields
        """
        query = """
        query GetCurrentUser {
          user {
            id
            email
            firstName
            lastName
            role
            plan
            hasSubscription
            hasCompletedOnboarding
            hasCompletedResumeTour
            targetJobTitle
            jobExperienceLevel
            location
            latestCity
            latestState
            linkedinUrl
            phoneNumber
            website
            profilePictureUrl
            createdAt
            lastActiveAt
            numJobs
            numClients
            tokenCoverLetter
            tokenInterview
            tokenOptimizeResume
            tokenProfessionalSummary
            tokenJobMatch
            tokenSalaryInsights
            tokenLearnSkills
            writingStyleEnum
            verified
          }
        }
        """
        data = self._graphql(query)
        return data["user"]

    def update_user(self, attributes: dict) -> dict:
        """
        Update the current user's profile.

        Args:
            attributes: Dict of fields to update. Can include:
                - firstName, lastName, email
                - targetJobTitle, jobExperienceLevel
                - location, linkedinUrl, phoneNumber, website
                - enableJobNotifications, enableJobRecommendationsNotifications

        Returns:
            Updated Users object
        """
        query = """
        mutation UpdateUser($attributes: UsersInputObject!) {
          updateUser(attributes: $attributes) {
            id
            email
            firstName
            lastName
            targetJobTitle
            location
            linkedinUrl
            phoneNumber
            website
          }
        }
        """
        data = self._graphql(query, {"attributes": attributes})
        return data["updateUser"]

    def upload_profile_picture(self, file_path: str) -> dict:
        """
        Upload a profile picture.

        Args:
            file_path: Path to the image file

        Returns:
            Updated Users object with profilePictureUrl
        """
        signed_id = self._upload_file(file_path)
        query = """
        mutation UserUploadProfilePicture($uploadSignedId: String!) {
          userUploadProfilePicture(uploadSignedId: $uploadSignedId) {
            id
            profilePictureUrl
          }
        }
        """
        data = self._graphql(query, {"uploadSignedId": signed_id})
        return data["userUploadProfilePicture"]

    # =========================================================================
    # Job Applications (UsersJobs)
    # =========================================================================

    def get_users_jobs(
        self,
        users_job_ids: Optional[list] = None,
        archived: bool = False,
        search_term: Optional[str] = None,
    ) -> list:
        """
        Get job applications tracked by the user.

        Args:
            users_job_ids: Optional list of specific job IDs to fetch
            archived: If True, return archived applications
            search_term: Optional search term to filter jobs

        Returns:
            List of UsersJobs objects
        """
        query = """
        query GetUsersJobs($usersJobIds: [ID!], $archived: Boolean, $searchTerm: String) {
          usersJobs(usersJobIds: $usersJobIds, archived: $archived, searchTerm: $searchTerm) {
            id
            position
            companyName
            status
            url
            location
            isRemote
            salaryMin
            salaryMax
            payPeriod
            notes
            jobDetails
            companyDomain
            appliedAt
            interviewedAt
            offerAt
            rejectedAt
            archived
            interviewStep
            rejectedStage
            matchLevel
            createdAt
            updatedAt
            resume {
              id
              name
            }
            coverLetter {
              id
              body
            }
          }
        }
        """
        data = self._graphql(query, {
            "usersJobIds": users_job_ids,
            "archived": archived,
            "searchTerm": search_term,
        })
        return data.get("usersJobs") or []

    def get_paginated_users_jobs(
        self,
        archived: bool = False,
        search_term: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        sort_by: Optional[str] = None,
        sort_by_direction: Optional[str] = None,
    ) -> dict:
        """
        Get paginated job applications.

        Args:
            archived: If True, return archived applications
            search_term: Optional search filter
            page: Page number (1-based)
            per_page: Results per page
            sort_by: Field to sort by
            sort_by_direction: "ASC" or "DESC"

        Returns:
            dict with 'data' (list of UsersJobs) and 'pagination' info
        """
        query = """
        query PaginatedUsersJobs(
          $archived: Boolean,
          $searchTerm: String,
          $page: Int,
          $perPage: Int,
          $sortBy: SortByDirectionEnum,
          $sortByDirection: SortByDirectionEnum
        ) {
          paginatedUsersJobs(
            archived: $archived,
            searchTerm: $searchTerm,
            page: $page,
            perPage: $perPage,
            sortBy: $sortBy,
            sortByDirection: $sortByDirection
          ) {
            data {
              id
              position
              companyName
              status
              url
              location
              isRemote
              salaryMin
              salaryMax
              createdAt
              updatedAt
              archived
            }
            pagination {
              page
              pageSize
              totalCount
              totalPages
            }
          }
        }
        """
        data = self._graphql(query, {
            "archived": archived,
            "searchTerm": search_term,
            "page": page,
            "perPage": per_page,
            "sortBy": sort_by,
            "sortByDirection": sort_by_direction,
        })
        return data.get("paginatedUsersJobs") or {}

    def create_users_job(
        self,
        position: str,
        company_name: str,
        status: str = "wishlist",
        url: Optional[str] = None,
        location: Optional[str] = None,
        is_remote: bool = False,
        salary_min: Optional[int] = None,
        salary_max: Optional[int] = None,
        notes: Optional[str] = None,
        job_details: Optional[str] = None,
        resume_id: Optional[str] = None,
    ) -> dict:
        """
        Create a new job application entry.

        Args:
            position: Job title/position
            company_name: Company name
            status: Application status - one of:
                "wishlist", "applied", "interviewing", "offer", "rejected", "archived"
            url: Job posting URL
            location: Job location
            is_remote: Whether the job is remote
            salary_min: Minimum salary
            salary_max: Maximum salary
            notes: Personal notes about the job
            job_details: Job description
            resume_id: ID of the resume to associate

        Returns:
            Created UsersJobs object
        """
        query = """
        mutation CreateUsersJob(
          $position: String!,
          $companyName: String!,
          $status: UsersJobsStatusEnum,
          $url: String,
          $location: String,
          $isRemote: Boolean,
          $salaryMin: Int,
          $salaryMax: Int,
          $notes: String,
          $jobDetails: String,
          $resumeId: ID
        ) {
          createUsersJob(
            position: $position,
            companyName: $companyName,
            status: $status,
            url: $url,
            location: $location,
            isRemote: $isRemote,
            salaryMin: $salaryMin,
            salaryMax: $salaryMax,
            notes: $notes,
            jobDetails: $jobDetails,
            resumeId: $resumeId
          ) {
            id
            position
            companyName
            status
            url
            location
            isRemote
            salaryMin
            salaryMax
            notes
            createdAt
          }
        }
        """
        data = self._graphql(query, {
            "position": position,
            "companyName": company_name,
            "status": status,
            "url": url,
            "location": location,
            "isRemote": is_remote,
            "salaryMin": salary_min,
            "salaryMax": salary_max,
            "notes": notes,
            "jobDetails": job_details,
            "resumeId": resume_id,
        })
        return data["createUsersJob"]

    def update_users_job(self, job_id: str, **kwargs) -> dict:
        """
        Update a job application.

        Args:
            job_id: ID of the UsersJob to update
            **kwargs: Fields to update. Supported fields:
                - status: UsersJobsStatusEnum (wishlist/applied/interviewing/offer/rejected)
                - position, companyName, url, notes, jobDetails
                - location, isRemote, salaryMin, salaryMax, payPeriod
                - archived (bool)
                - interviewStep, rejectedStage
                - resumeId
                - appliedAt, interviewedAt (ISO8601DateTime strings)

        Returns:
            Updated UsersJobs object
        """
        query = """
        mutation UpdateUsersJob(
          $id: ID!,
          $status: UsersJobsStatusEnum,
          $position: String,
          $companyName: String,
          $url: String,
          $notes: String,
          $jobDetails: String,
          $location: String,
          $isRemote: Boolean,
          $salaryMin: Int,
          $salaryMax: Int,
          $archived: Boolean,
          $interviewStep: UsersJobsInterviewStepEnum,
          $rejectedStage: UsersJobsRejectedStageEnum,
          $resumeId: ID,
          $appliedAt: ISO8601DateTime,
          $interviewedAt: ISO8601DateTime
        ) {
          updateUsersJob(
            id: $id,
            status: $status,
            position: $position,
            companyName: $companyName,
            url: $url,
            notes: $notes,
            jobDetails: $jobDetails,
            location: $location,
            isRemote: $isRemote,
            salaryMin: $salaryMin,
            salaryMax: $salaryMax,
            archived: $archived,
            interviewStep: $interviewStep,
            rejectedStage: $rejectedStage,
            resumeId: $resumeId,
            appliedAt: $appliedAt,
            interviewedAt: $interviewedAt
          ) {
            id
            position
            companyName
            status
            archived
            updatedAt
          }
        }
        """
        variables = {"id": job_id}
        variables.update(kwargs)
        data = self._graphql(query, variables)
        return data["updateUsersJob"]

    def archive_users_job(self, job_id: str) -> dict:
        """Archive a job application."""
        return self.update_users_job(job_id, archived=True)

    def find_users_job_by_url(self, url: str) -> Optional[dict]:
        """
        Find a tracked job application by its URL.

        Args:
            url: Job posting URL

        Returns:
            UsersJobs object or None if not found
        """
        query = """
        query FindUsersJobByUrl($url: String!) {
          findUsersJobByUrl(url: $url) {
            id
            position
            companyName
            status
            url
            createdAt
          }
        }
        """
        try:
            data = self._graphql(query, {"url": url})
            return data.get("findUsersJobByUrl")
        except CanyonAPIError:
            return None

    def export_users_jobs_to_csv(self) -> str:
        """
        Export all job applications to CSV.

        Returns:
            CSV content as a string
        """
        query = """
        mutation ExportUsersJobToCsv {
          exportUsersJobToCsv
        }
        """
        data = self._graphql(query)
        return data["exportUsersJobToCsv"]

    # =========================================================================
    # Job Listings (Browse/Search Jobs)
    # =========================================================================

    def search_job_listings(
        self,
        search_term: Optional[str] = None,
        page: int = 1,
        per_page: int = 20,
        attributes: Optional[dict] = None,
        sort_by: Optional[str] = None,
        sort_by_direction: str = "DESC",
    ) -> dict:
        """
        Search the Canyon job listings database (600k+ jobs).

        Args:
            search_term: Job title, keywords, or company name
            page: Page number (1-based)
            per_page: Results per page (max ~50)
            attributes: Filter attributes dict. Can include:
                - location: str
                - isRemote: bool
                - employmentType: "full_time", "part_time", "intern", etc.
                - experienceLevel: "entry", "mid", "senior", "director", etc.
                - salaryMin, salaryMax: int
                - datePosted: "last_24_hours", "last_week", "last_month"
            sort_by: Field to sort by
            sort_by_direction: "ASC" or "DESC"

        Returns:
            dict with 'data' (list of JobListings) and 'pagination' info
        """
        query = """
        query SearchJobListings(
          $searchTerm: String,
          $page: Int,
          $perPage: Int,
          $attributes: JobListingsFilterInputObject,
          $sortBy: JobListingsSortEnum,
          $sortByDirection: SortByDirectionEnum
        ) {
          paginatedJobListings(
            searchTerm: $searchTerm,
            page: $page,
            perPage: $perPage,
            attributes: $attributes,
            sortBy: $sortBy,
            sortByDirection: $sortByDirection
          ) {
            data {
              id
              position
              companyName
              companyDomain
              companyLogoUrl
              location
              isRemote
              salaryMin
              salaryMax
              salaryCurrency
              payPeriod
              employmentType
              experienceLevelString
              datePosted
              externalApplyUrl
              url
              aiRequirementsSummary
              aiCoreResponsibilities
              expired
              createdAt
            }
            pagination {
              page
              pageSize
              totalCount
              totalPages
            }
          }
        }
        """
        data = self._graphql(query, {
            "searchTerm": search_term,
            "page": page,
            "perPage": per_page,
            "attributes": attributes,
            "sortBy": sort_by,
            "sortByDirection": sort_by_direction,
        })
        return data.get("paginatedJobListings") or {}

    def get_job_listing(self, job_listing_id: str) -> dict:
        """
        Get a specific job listing by ID.

        Args:
            job_listing_id: The job listing ID

        Returns:
            JobListings object with full details
        """
        query = """
        query GetJobListing($jobListingId: ID!) {
          jobListing(jobListingId: $jobListingId) {
            id
            position
            companyName
            companyDomain
            companyLogoUrl
            companyDescription
            companyIndustry
            companyNumEmployees
            companyLinkedinUrl
            location
            isRemote
            salaryMin
            salaryMax
            salaryCurrency
            payPeriod
            employmentType
            experienceLevelString
            datePosted
            externalApplyUrl
            url
            jobDetails
            aiRequirementsSummary
            aiCoreResponsibilities
            aiWorkArrangement
            hiringManagerName
            hiringManagerEmail
            visaSponsorship
            expired
            createdAt
          }
        }
        """
        data = self._graphql(query, {"jobListingId": job_listing_id})
        return data["jobListing"]

    def bookmark_job(self, job_listing_id: str, status: str = "wishlist") -> dict:
        """
        Bookmark a job listing to track it.

        Args:
            job_listing_id: The job listing ID to bookmark
            status: Initial status (default: "wishlist")

        Returns:
            Created UsersJobs object
        """
        query = """
        mutation BookmarkJob($jobListingId: ID!, $status: String) {
          bookmarkJob(jobListingId: $jobListingId, status: $status) {
            id
            position
            companyName
            status
            createdAt
          }
        }
        """
        data = self._graphql(query, {
            "jobListingId": job_listing_id,
            "status": status,
        })
        return data["bookmarkJob"]

    def mark_job_as_applied(self, job_listing_id: str) -> dict:
        """
        Mark a job listing as applied.

        Args:
            job_listing_id: The job listing ID

        Returns:
            Updated UsersJobs object
        """
        query = """
        mutation MarkJobListingAsApplied($jobListingId: ID!) {
          markJobListingAsApplied(jobListingId: $jobListingId) {
            id
            position
            companyName
            status
            appliedAt
          }
        }
        """
        data = self._graphql(query, {"jobListingId": job_listing_id})
        return data["markJobListingAsApplied"]

    def check_if_applied_to_job(self, job_listing_id: str) -> Optional[dict]:
        """
        Check if the user has already applied to a specific job listing.

        Args:
            job_listing_id: The job listing ID

        Returns:
            UsersJobs object if applied, None otherwise
        """
        query = """
        query HasAddedJobListing($jobListingId: ID!) {
          hasAddedJobListing(jobListingId: $jobListingId) {
            id
            position
            companyName
            status
            appliedAt
          }
        }
        """
        data = self._graphql(query, {"jobListingId": job_listing_id})
        return data.get("hasAddedJobListing")

    # =========================================================================
    # Resumes
    # =========================================================================

    def get_resumes(
        self,
        resume_ids: Optional[list] = None,
        archived: bool = False,
        search_term: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list:
        """
        Get user's resumes.

        Args:
            resume_ids: Optional list of specific resume IDs
            archived: If True, return archived resumes
            search_term: Optional search filter
            limit: Max number of results

        Returns:
            List of Resumes objects
        """
        query = """
        query GetResumes(
          $resumeIds: [ID!],
          $archived: Boolean,
          $searchTerm: String,
          $limit: Int
        ) {
          resumes(
            resumeIds: $resumeIds,
            archived: $archived,
            searchTerm: $searchTerm,
            limit: $limit
          ) {
            id
            name
            nameSlug
            targetTitle
            firstName
            lastName
            email
            location
            template
            templateColorEnum
            isPublic
            publicId
            archived
            aiGenerated
            documentType
            documentUrl
            mostRecentJobTitle
            mostRecentEmployer
            professionalSummary
            createdAt
            updatedAt
          }
        }
        """
        data = self._graphql(query, {
            "resumeIds": resume_ids,
            "archived": archived,
            "searchTerm": search_term,
            "limit": limit,
        })
        return data.get("resumes") or []

    def get_resume(self, resume_id: str) -> dict:
        """
        Get a specific resume with all details.

        Args:
            resume_id: The resume ID

        Returns:
            Full Resumes object including work experiences, education, etc.
        """
        query = """
        query GetResume($resumeId: ID!) {
          resumes(resumeIds: [$resumeId]) {
            id
            name
            nameSlug
            targetTitle
            firstName
            lastName
            email
            phoneNumber
            location
            website
            linkedinUrl
            professionalSummary
            template
            templateColorEnum
            isPublic
            publicId
            archived
            documentType
            documentUrl
            createdAt
            updatedAt
            workExperiences {
              id
              company
              location
              isRemote
              positions {
                id
                title
                startDate
                endDate
                currentlyWorking
                achievements
              }
            }
            educations {
              id
              school
              degree
              fieldOfStudy
              startDate
              endDate
              currentlyStudying
              gpa
            }
            groupedSkills {
              id
              category
              skills
            }
            certifications {
              id
              name
              organization
              issueDate
              expirationDate
              credentialId
              credentialUrl
            }
            projects {
              id
              title
              description
              url
              startDate
              endDate
            }
            preferences {
              template
              fontFamily
              fontSize
              lineHeight
              horizontalMargin
              verticalMargin
              templateColor
              dateFormat
              pageSize
            }
          }
        }
        """
        data = self._graphql(query, {"resumeId": resume_id})
        resumes = data.get("resumes") or []
        return resumes[0] if resumes else {}

    def create_resume(self, name: str) -> dict:
        """
        Create a new blank resume.

        Args:
            name: Name for the resume

        Returns:
            Created Resumes object
        """
        query = """
        mutation CreateResume($name: String!) {
          createResume(name: $name) {
            id
            name
            createdAt
          }
        }
        """
        data = self._graphql(query, {"name": name})
        return data["createResume"]

    def create_resume_from_linkedin(self, linkedin_profile_url: str) -> dict:
        """
        Create a resume by importing a LinkedIn profile.

        Args:
            linkedin_profile_url: Full LinkedIn profile URL

        Returns:
            Created Resumes object
        """
        query = """
        mutation CreateResumeFromLinkedin($linkedinProfileUrl: String!) {
          createResumeFromLinkedinUrl(linkedinProfileUrl: $linkedinProfileUrl) {
            id
            name
            firstName
            lastName
            createdAt
          }
        }
        """
        data = self._graphql(query, {"linkedinProfileUrl": linkedin_profile_url})
        return data["createResumeFromLinkedinUrl"]

    def update_resume(self, resume_id: str, attributes: dict) -> dict:
        """
        Update a resume's content.

        Args:
            resume_id: The resume ID
            attributes: ResumesInputObject with fields to update. Can include:
                - name, targetTitle, firstName, lastName
                - email, phoneNumber, location, website, linkedinUrl
                - professionalSummary
                - workExperiences: list of work experience objects
                - educations: list of education objects
                - groupedSkills: list of skill group objects
                - certifications, projects, involvements, courseworks

        Returns:
            Updated Resumes object
        """
        query = """
        mutation UpdateResume($id: ID!, $attributes: ResumesInputObject!) {
          updateResume(id: $id, attributes: $attributes) {
            id
            name
            updatedAt
          }
        }
        """
        data = self._graphql(query, {"id": resume_id, "attributes": attributes})
        return data["updateResume"]

    def duplicate_resume(self, resume_id: str) -> dict:
        """
        Duplicate an existing resume.

        Args:
            resume_id: The resume ID to duplicate

        Returns:
            New Resumes object (the duplicate)
        """
        query = """
        mutation DuplicateResume($id: ID!) {
          duplicateResume(id: $id) {
            id
            name
            createdAt
          }
        }
        """
        data = self._graphql(query, {"id": resume_id})
        return data["duplicateResume"]

    def archive_resume(self, resume_id: str) -> dict:
        """
        Archive a resume.

        Args:
            resume_id: The resume ID to archive

        Returns:
            Updated Resumes object
        """
        query = """
        mutation ArchiveResume($id: ID!, $archived: Boolean!) {
          updateArchivedResume(id: $id, archived: $archived) {
            id
            archived
          }
        }
        """
        data = self._graphql(query, {"id": resume_id, "archived": True})
        return data["updateArchivedResume"]

    def upload_resume(
        self,
        file_path: str,
        name: Optional[str] = None,
        resume_id: Optional[str] = None,
    ) -> dict:
        """
        Upload a resume document (PDF, DOCX, etc.).

        This first uploads the file to get a signed_id, then calls
        the uploadResume mutation to associate it with Canyon.

        Args:
            file_path: Path to the resume file
            name: Optional name for the resume
            resume_id: Optional ID of existing resume to update

        Returns:
            Resumes object
        """
        signed_id = self._upload_file(file_path)
        query = """
        mutation UploadResume($uploadSignedId: String!, $name: String, $id: ID) {
          uploadResume(uploadSignedId: $uploadSignedId, name: $name, id: $id) {
            id
            name
            documentType
            documentUrl
            createdAt
          }
        }
        """
        data = self._graphql(query, {
            "uploadSignedId": signed_id,
            "name": name or Path(file_path).stem,
            "id": resume_id,
        })
        return data["uploadResume"]

    def score_resume(self, resume_id: str) -> dict:
        """
        Get an AI score for a resume.

        Args:
            resume_id: The resume ID to score

        Returns:
            ResumesScoreType with score breakdown
        """
        query = """
        mutation ScoreResume($id: ID!) {
          scoreResume(id: $id) {
            score
            fields {
              type
              score
              tags {
                name
                score
              }
            }
          }
        }
        """
        data = self._graphql(query, {"id": resume_id})
        return data["scoreResume"]

    def get_resume_score(self, resume_id: str) -> Optional[dict]:
        """
        Get the cached resume score.

        Args:
            resume_id: The resume ID

        Returns:
            ResumesScoreType or None
        """
        query = """
        query GetResumeScore($id: ID!) {
          resumeScore(id: $id) {
            score
            fields {
              type
              score
            }
          }
        }
        """
        data = self._graphql(query, {"id": resume_id})
        return data.get("resumeScore")

    def download_resume_pdf(self, resume_id: str) -> str:
        """
        Generate and get the PDF download URL for a resume.

        Args:
            resume_id: The resume ID

        Returns:
            URL string to download the PDF
        """
        query = """
        mutation DownloadPdfResume($id: ID!) {
          downloadPdfResume(id: $id) {
            id
            name
          }
        }
        """
        # Get the PDF blob URL
        blob_query = """
        query GetResumePdfBlob($resumeId: ID!) {
          resumesPdfBlob(resumeId: $resumeId)
        }
        """
        data = self._graphql(blob_query, {"resumeId": resume_id})
        return data.get("resumesPdfBlob", "")

    def generate_professional_summary(
        self,
        resume_id: str,
        keywords: Optional[list] = None,
        custom_prompt: Optional[str] = None,
        use_existing: bool = True,
    ) -> str:
        """
        Generate a professional summary for a resume using AI.

        Args:
            resume_id: The resume ID
            keywords: Optional list of keywords to include
            custom_prompt: Optional custom instructions for the AI
            use_existing: Whether to use existing experience in the resume

        Returns:
            Generated summary text
        """
        query = """
        mutation GenerateProfessionalSummary(
          $id: ID!,
          $useExisting: Boolean,
          $keywords: [String!],
          $customPrompt: String
        ) {
          generateProfessionalSummary(
            id: $id,
            useExisting: $useExisting,
            keywords: $keywords,
            customPrompt: $customPrompt
          )
        }
        """
        data = self._graphql(query, {
            "id": resume_id,
            "useExisting": use_existing,
            "keywords": keywords,
            "customPrompt": custom_prompt,
        })
        return data["generateProfessionalSummary"]

    def tailor_resume_for_job(
        self,
        resume_id: str,
        users_job_id: Optional[str] = None,
        job_listing_id: Optional[str] = None,
        job_title: Optional[str] = None,
        keywords: Optional[list] = None,
        skills: Optional[list] = None,
    ) -> dict:
        """
        Tailor/optimize a resume for a specific job using AI.

        Args:
            resume_id: The resume ID to optimize
            users_job_id: Optional UsersJob ID to optimize for
            job_listing_id: Optional JobListing ID to optimize for
            job_title: Optional job title context
            keywords: Keywords to include
            skills: Skills to incorporate

        Returns:
            Updated Resumes object
        """
        query = """
        mutation OptimizeResumeForJob(
          $resumeId: ID!,
          $usersJobId: ID,
          $jobListingId: ID,
          $jobTitle: String,
          $keywords: [String!],
          $skills: [String!]
        ) {
          optimizeResumeForJobV2(
            resumeId: $resumeId,
            usersJobId: $usersJobId,
            jobListingId: $jobListingId,
            jobTitle: $jobTitle,
            keywords: $keywords,
            skills: $skills
          ) {
            id
            name
            updatedAt
          }
        }
        """
        data = self._graphql(query, {
            "resumeId": resume_id,
            "usersJobId": users_job_id,
            "jobListingId": job_listing_id,
            "jobTitle": job_title,
            "keywords": keywords,
            "skills": skills,
        })
        return data["optimizeResumeForJobV2"]

    def share_resume_publicly(self, resume_id: str, is_public: bool = True) -> dict:
        """
        Make a resume publicly shareable.

        Args:
            resume_id: The resume ID
            is_public: Whether to make it public (True) or private (False)

        Returns:
            Updated Resumes object with publicId
        """
        query = """
        mutation UpdatePublicResume($id: ID!, $isPublic: Boolean!) {
          updatePublicResume(id: $id, isPublic: $isPublic) {
            id
            isPublic
            publicId
          }
        }
        """
        data = self._graphql(query, {"id": resume_id, "isPublic": is_public})
        return data["updatePublicResume"]

    # =========================================================================
    # Cover Letters
    # =========================================================================

    def get_cover_letters(
        self,
        cover_letter_ids: Optional[list] = None,
        archived: bool = False,
        search_term: Optional[str] = None,
    ) -> list:
        """
        Get user's cover letters.

        Args:
            cover_letter_ids: Optional list of specific cover letter IDs
            archived: If True, return archived cover letters
            search_term: Optional search filter

        Returns:
            List of UsersJobsCoverLetterType objects
        """
        query = """
        query GetCoverLetters(
          $coverLetterIds: [ID!],
          $archived: Boolean,
          $searchTerm: String
        ) {
          coverLetters(
            coverLetterIds: $coverLetterIds,
            archived: $archived,
            searchTerm: $searchTerm
          ) {
            id
            body
            archived
            createdAt
            updatedAt
          }
        }
        """
        data = self._graphql(query, {
            "coverLetterIds": cover_letter_ids,
            "archived": archived,
            "searchTerm": search_term,
        })
        return data.get("coverLetters") or []

    def generate_cover_letter(
        self,
        users_job_id: str,
        resume_id: str,
        tone: str = "professional",
        length: str = "medium",
        custom_prompt: Optional[str] = None,
    ) -> dict:
        """
        Generate a cover letter using AI.

        Args:
            users_job_id: The UsersJob ID to generate a cover letter for
            resume_id: The resume ID to base the cover letter on
            tone: Cover letter tone - one of:
                "professional", "confident", "friendly", "formal"
            length: Cover letter length - one of:
                "short", "medium", "long"
            custom_prompt: Optional custom instructions for the AI

        Returns:
            UsersJobsCoverLetterType with generated body
        """
        query = """
        mutation GenerateCoverLetter(
          $usersJobId: ID!,
          $resumeId: ID!,
          $coverLetterTone: CoverLetterToneEnum,
          $coverLetterLength: CoverLetterLengthEnum,
          $customPrompt: String
        ) {
          generateCoverLetter(
            usersJobId: $usersJobId,
            resumeId: $resumeId,
            coverLetterTone: $coverLetterTone,
            coverLetterLength: $coverLetterLength,
            customPrompt: $customPrompt
          ) {
            id
            body
            createdAt
          }
        }
        """
        data = self._graphql(query, {
            "usersJobId": users_job_id,
            "resumeId": resume_id,
            "coverLetterTone": tone,
            "coverLetterLength": length,
            "customPrompt": custom_prompt,
        })
        return data["generateCoverLetter"]

    def upsert_cover_letter(self, users_job_id: str, attributes: dict) -> dict:
        """
        Create or update a cover letter for a job application.

        Args:
            users_job_id: The UsersJob ID
            attributes: Cover letter attributes dict with 'body' field

        Returns:
            UsersJobsCoverLetterType object
        """
        query = """
        mutation UpsertCoverLetter(
          $usersJobId: ID!,
          $attributes: UsersJobsCoverLetterInputObject!
        ) {
          coverLetterUpsert(usersJobId: $usersJobId, attributes: $attributes) {
            id
            body
            updatedAt
          }
        }
        """
        data = self._graphql(query, {
            "usersJobId": users_job_id,
            "attributes": attributes,
        })
        return data["coverLetterUpsert"]

    # =========================================================================
    # Interview Prep
    # =========================================================================

    def get_interviews(self, interview_ids: Optional[list] = None) -> list:
        """
        Get mock interviews.

        Args:
            interview_ids: Optional list of specific interview IDs

        Returns:
            List of Interview objects
        """
        query = """
        query GetInterviews($interviewIds: [ID!]) {
          interviews(interviewIds: $interviewIds) {
            id
            jobTitle
            interviewType
            status
            createdAt
            updatedAt
          }
        }
        """
        data = self._graphql(query, {"interviewIds": interview_ids})
        return data.get("interviews") or []

    def start_mock_interview(
        self,
        job_title: str,
        interview_type: str = "behavioral",
        job_description: Optional[str] = None,
        users_job_id: Optional[str] = None,
        resume_id: Optional[str] = None,
    ) -> dict:
        """
        Start a new AI mock interview session.

        Args:
            job_title: The job title to practice for
            interview_type: Type of interview - one of:
                "behavioral", "technical", "case", "general"
            job_description: Optional job description context
            users_job_id: Optional UsersJob ID for context
            resume_id: Optional resume ID to use

        Returns:
            Interview object with initial questions
        """
        query = """
        mutation StartMockInterview(
          $jobTitle: String!,
          $interviewType: InterviewsTypeEnum!,
          $jobDescription: String,
          $usersJobId: ID,
          $resumeId: ID
        ) {
          interviewStartMock(
            jobTitle: $jobTitle,
            interviewType: $interviewType,
            jobDescription: $jobDescription,
            usersJobId: $usersJobId,
            resumeId: $resumeId
          ) {
            id
            jobTitle
            interviewType
            status
            messages {
              id
              role
              content
              createdAt
            }
            createdAt
          }
        }
        """
        data = self._graphql(query, {
            "jobTitle": job_title,
            "interviewType": interview_type,
            "jobDescription": job_description,
            "usersJobId": users_job_id,
            "resumeId": resume_id,
        })
        return data["interviewStartMock"]

    def send_interview_message(
        self, interview_id: str, message: str
    ) -> dict:
        """
        Send a message in an ongoing mock interview.

        Args:
            interview_id: The Interview ID
            message: Your answer/response

        Returns:
            Updated Interview object with new messages
        """
        query = """
        mutation InterviewAddMessage($message: String!, $interviewId: ID!) {
          interviewAddMessage(message: $message, interviewId: $interviewId) {
            id
            messages {
              id
              role
              content
              createdAt
            }
            status
          }
        }
        """
        data = self._graphql(query, {
            "message": message,
            "interviewId": interview_id,
        })
        return data["interviewAddMessage"]

    # =========================================================================
    # AI Features
    # =========================================================================

    def check_job_fit(
        self,
        resume_id: str,
        position: Optional[str] = None,
        job_description: Optional[str] = None,
        users_job_id: Optional[str] = None,
        job_listing_id: Optional[str] = None,
    ) -> dict:
        """
        Check how well a resume fits a job using AI.

        Args:
            resume_id: The resume ID to check
            position: Job position/title
            job_description: Job description text
            users_job_id: Optional UsersJob ID
            job_listing_id: Optional JobListing ID

        Returns:
            AmIAGoodFit object with fit analysis
        """
        query = """
        mutation CheckJobFit(
          $resumeId: ID!,
          $position: String,
          $jobDescription: String,
          $usersJobId: ID,
          $jobListingId: ID
        ) {
          amIAGoodFit(
            resumeId: $resumeId,
            position: $position,
            jobDescription: $jobDescription,
            usersJobId: $usersJobId,
            jobListingId: $jobListingId
          ) {
            matchScore
            summary
            strengths
            gaps
            recommendations
          }
        }
        """
        data = self._graphql(query, {
            "resumeId": resume_id,
            "position": position,
            "jobDescription": job_description,
            "usersJobId": users_job_id,
            "jobListingId": job_listing_id,
        })
        return data["amIAGoodFit"]

    def get_salary_insights(self, users_job_id: str) -> str:
        """
        Get salary insights for a job application using AI.

        Args:
            users_job_id: The UsersJob ID

        Returns:
            Salary insights as text
        """
        query = """
        mutation GetSalaryInsights($usersJobId: ID!) {
          salaryInsights(usersJobId: $usersJobId)
        }
        """
        data = self._graphql(query, {"usersJobId": users_job_id})
        return data["salaryInsights"]

    def get_match_score(self, users_job_id: str, resume_id: str) -> dict:
        """
        Get the match score between a resume and a job.

        Args:
            users_job_id: The UsersJob ID
            resume_id: The resume ID

        Returns:
            UsersJobsMatch object with score
        """
        query = """
        mutation GetMatchScore($usersJobId: ID!, $resumeId: ID!) {
          matchScore(usersJobId: $usersJobId, resumeId: $resumeId) {
            score
            matchLevel
          }
        }
        """
        data = self._graphql(query, {
            "usersJobId": users_job_id,
            "resumeId": resume_id,
        })
        return data["matchScore"]

    def get_company_info(self, users_job_id: str) -> dict:
        """
        Get AI-powered company information for a job.

        Args:
            users_job_id: The UsersJob ID

        Returns:
            CompanyLatestInfo object with company data
        """
        query = """
        query GetLatestCompanyInfo($usersJobId: ID!) {
          getLatestCompanyInfo(usersJobId: $usersJobId) {
            name
            description
            industry
            numEmployees
            revenue
            founded
            headquarters
            website
            stockTicker
            competitors {
              name
              description
            }
            sources {
              url
              title
            }
          }
        }
        """
        data = self._graphql(query, {"usersJobId": users_job_id})
        return data.get("getLatestCompanyInfo") or {}

    def generate_job_achievement(
        self,
        work_position_id: str,
        index: int,
        keywords: Optional[list] = None,
        custom_prompt: Optional[str] = None,
    ) -> str:
        """
        Generate an AI-enhanced resume bullet point.

        Args:
            work_position_id: ID of the work position to generate for
            index: Index of the achievement to generate/enhance
            keywords: Keywords to incorporate
            custom_prompt: Custom instructions for the AI

        Returns:
            Generated achievement text
        """
        query = """
        mutation GenerateOneJobAchievement(
          $workPositionId: ID!,
          $index: Int!,
          $keywords: [String!],
          $customPrompt: String
        ) {
          generateOneJobAchievement(
            workPositionId: $workPositionId,
            index: $index,
            keywords: $keywords,
            customPrompt: $customPrompt
          )
        }
        """
        data = self._graphql(query, {
            "workPositionId": work_position_id,
            "index": index,
            "keywords": keywords,
            "customPrompt": custom_prompt,
        })
        return data["generateOneJobAchievement"]

    def fill_job_application_form(
        self,
        html_string: str,
        resume_id: str,
        extra_data_source: Optional[str] = None,
    ) -> str:
        """
        Auto-fill a job application form using resume data (v2).

        Args:
            html_string: HTML of the job application form
            resume_id: Resume ID to use for filling
            extra_data_source: Additional data source

        Returns:
            JSON string with field mappings
        """
        query = """
        mutation FillJobApplicationForm(
          $htmlString: String!,
          $resumeId: ID!,
          $extraDataSource: String
        ) {
          jobsFormFieldsMappingV2(
            htmlString: $htmlString,
            resumeId: $resumeId,
            extraDataSource: $extraDataSource
          )
        }
        """
        data = self._graphql(query, {
            "htmlString": html_string,
            "resumeId": resume_id,
            "extraDataSource": extra_data_source,
        })
        return data["jobsFormFieldsMappingV2"]

    # =========================================================================
    # Headshots (AI-generated headshots)
    # =========================================================================

    def get_headshots(self) -> list:
        """
        Get all headshot requests.

        Returns:
            List of HeadshotRequest objects
        """
        query = """
        query GetHeadshots {
          headshotRequests {
            id
            status
            attire
            background
            createdAt
            updatedAt
          }
        }
        """
        data = self._graphql(query)
        return data.get("headshotRequests") or []

    def create_headshot_request(
        self,
        file_path: str,
        attire: str = "business_casual",
        background: str = "office",
    ) -> dict:
        """
        Request an AI-generated professional headshot.

        Args:
            file_path: Path to the source photo
            attire: Clothing style - e.g., "business_casual", "business_formal"
            background: Background style - e.g., "office", "outdoor", "studio"

        Returns:
            HeadshotRequest object
        """
        signed_id = self._upload_file(file_path)
        query = """
        mutation CreateHeadshotRequest(
          $uploadSignedId: String!,
          $attire: HeadshotRequestsAttireEnum!,
          $background: HeadshotRequestsBackgroundEnum!
        ) {
          createHeadshotRequest(
            uploadSignedId: $uploadSignedId,
            attire: $attire,
            background: $background
          ) {
            id
            status
            attire
            background
            createdAt
          }
        }
        """
        data = self._graphql(query, {
            "uploadSignedId": signed_id,
            "attire": attire,
            "background": background,
        })
        return data["createHeadshotRequest"]

    # =========================================================================
    # Billing / Subscriptions
    # =========================================================================

    def get_billing_portal_url(self) -> str:
        """
        Get the URL for the Stripe billing portal.

        Returns:
            URL string to the billing portal
        """
        query = """
        mutation GetBillingPortalUrl {
          billingPortalUrl
        }
        """
        data = self._graphql(query)
        return data["billingPortalUrl"]

    def create_subscription_session(
        self,
        plan: str,
        coupon: Optional[str] = None,
        is_onboarding: bool = False,
    ) -> str:
        """
        Create a Stripe checkout session for subscribing.

        Args:
            plan: Subscription plan name (e.g., "gold", "silver")
            coupon: Optional coupon code
            is_onboarding: Whether this is during the onboarding flow

        Returns:
            Stripe checkout session URL/ID
        """
        query = """
        mutation CreateSubscriptionSession(
          $plan: SubscriptionPlanEnum!,
          $coupon: String,
          $isOnboarding: Boolean
        ) {
          subscriptionsSessionCreate(
            plan: $plan,
            coupon: $coupon,
            isOnboarding: $isOnboarding
          )
        }
        """
        data = self._graphql(query, {
            "plan": plan,
            "coupon": coupon,
            "isOnboarding": is_onboarding,
        })
        return data["subscriptionsSessionCreate"]

    def redeem_promo_code(self, promo_code: str) -> dict:
        """
        Redeem a lifetime deal promo code.

        Args:
            promo_code: The promo code to redeem

        Returns:
            Updated Users object
        """
        query = """
        mutation RedeemPromoCode($promoCode: String!) {
          subscriptionsRedeemLtdPromoCode(promoCode: $promoCode) {
            id
            plan
            hasSubscription
          }
        }
        """
        data = self._graphql(query, {"promoCode": promo_code})
        return data["subscriptionsRedeemLtdPromoCode"]

    # =========================================================================
    # File Upload (REST endpoint)
    # =========================================================================

    def _upload_file(self, file_path: str) -> str:
        """
        Upload a file to Canyon's storage.

        This uses the REST endpoint POST /upload with multipart form data.
        The response contains a signed_id that can be used in GraphQL mutations.

        Args:
            file_path: Path to the file to upload

        Returns:
            signed_id string for use in GraphQL mutations
        """
        if not self.token:
            raise CanyonAPIError("Authentication required. Call authenticate_with_credentials() first.")

        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        content_type, _ = mimetypes.guess_type(str(file_path))
        if not content_type:
            content_type = "application/octet-stream"

        with open(file_path, "rb") as f:
            # Use a separate session without Content-Type header for multipart
            headers = {"Authorization": f"Bearer {self.token}"}
            files = {"file": (file_path.name, f, content_type)}
            response = requests.post(
                UPLOAD_URL,
                headers=headers,
                files=files,
            )
            response.raise_for_status()
            result = response.json()
            return result["signed_id"]

    # =========================================================================
    # GraphQL Introspection (for development)
    # =========================================================================

    def introspect(self) -> dict:
        """
        Get the full GraphQL schema via introspection.

        Returns:
            GraphQL schema dict
        """
        query = """
        {
          __schema {
            types {
              name
              kind
              fields {
                name
                type { name kind ofType { name kind } }
              }
            }
          }
        }
        """
        return self._graphql(query)

    def execute(self, query: str, variables: Optional[dict] = None) -> dict:
        """
        Execute a raw GraphQL query or mutation.

        Args:
            query: GraphQL query/mutation string
            variables: Optional variables dict

        Returns:
            The 'data' field of the GraphQL response
        """
        return self._graphql(query, variables)


# =============================================================================
# Main - Example usage
# =============================================================================

if __name__ == "__main__":
    import os

    # Read credentials from environment variables
    token = os.environ.get("CANYON_TOKEN")
    email = os.environ.get("CANYON_EMAIL")
    password = os.environ.get("CANYON_PASSWORD")

    print("Canyon API Client - Test Run")
    print("=" * 40)

    # Initialize client
    client = CanyonClient(token=token)

    # Attempt authentication if no token provided
    if not client.token and email and password:
        print(f"Authenticating with credentials: {email}")
        try:
            result = client.authenticate_with_credentials(email, password)
            print(f"Authenticated as: {result['user']['email']}")
            print(f"Token: {result['token'][:20]}...")
        except CanyonAPIError as e:
            print(f"Authentication failed: {e}")
            exit(1)
    elif client.token:
        print(f"Using provided token: {client.token[:20]}...")
    else:
        print("\nNo credentials provided. Running unauthenticated tests...\n")
        print("To authenticate, set environment variables:")
        print("  CANYON_TOKEN=<your_bearer_token>")
        print("  or")
        print("  CANYON_EMAIL=<email> CANYON_PASSWORD=<password>")
        print()

    # Test 1: Search job listings (works without auth for public data)
    print("\n--- Test: Search Job Listings ---")
    try:
        results = client.search_job_listings(
            search_term="software engineer",
            per_page=3,
        )
        jobs = results.get("data", [])
        print(f"Found {results.get('pagination', {}).get('totalCount', 0)} jobs")
        for job in jobs[:3]:
            salary = ""
            if job.get("salaryMin"):
                salary = f" | ${job['salaryMin']:,}-${job.get('salaryMax', 0):,}"
            print(f"  - {job['position']} @ {job['companyName']} ({job.get('location', 'N/A')}){salary}")
    except Exception as e:
        print(f"Error: {e}")

    # Test 2: Get resume example categories (no auth required)
    print("\n--- Test: Get Resume Example Categories ---")
    try:
        resume = client.execute("""
        query {
          resumeExampleCategories
        }
        """)
        categories = resume.get("resumeExampleCategories", [])
        print(f"Resume example categories ({len(categories or [])}): {(categories or [])[:5]}")
    except Exception as e:
        print(f"Error: {e}")

    # Test authenticated endpoints only if we have a token
    if client.token:
        print("\n--- Test: Get Current User ---")
        try:
            user = client.get_user()
            print(f"User: {user.get('firstName')} {user.get('lastName')} ({user.get('email')})")
            print(f"Plan: {user.get('plan')}, Role: {user.get('role')}")
        except CanyonAPIError as e:
            print(f"Error: {e}")

        print("\n--- Test: Get Resumes ---")
        try:
            resumes = client.get_resumes()
            print(f"Found {len(resumes)} resumes")
            for r in resumes[:3]:
                print(f"  - {r.get('name')} (updated: {r.get('updatedAt', 'N/A')[:10]})")
        except CanyonAPIError as e:
            print(f"Error: {e}")

        print("\n--- Test: Get Job Applications ---")
        try:
            jobs = client.get_users_jobs()
            print(f"Found {len(jobs)} tracked job applications")
            for j in jobs[:3]:
                print(f"  - {j.get('position')} @ {j.get('companyName')} [{j.get('status')}]")
        except CanyonAPIError as e:
            print(f"Error: {e}")

    print("\nDone!")
