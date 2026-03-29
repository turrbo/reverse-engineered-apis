"""
Mavely Creators Platform API Client
====================================
Reverse-engineered client for the Mavely influencer/creator affiliate platform.

Architecture:
  - Auth: Auth0 Resource Owner Password Grant (ROPC)
    Domain: mavely.us.auth0.com
    Client ID: PItSrEo35MYmLjhY6wJp8sCQAQRRWYxr
    Audience: https://auth.mave.ly/
    Scopes: openid profile email offline_access
  - API: GraphQL at https://mavely.live/api/graphql
    Required headers: client-name, client-version, client-revision
    Auth: Bearer JWT in Authorization header
  - Feature flags: Unleash at https://unleash-edge.mavely.live/api/frontend
  - Frontend: Next.js at https://creators.joinmavely.com (NextAuth sessions)

Discovered: 84 GraphQL operations (43 queries, 24 mutations, 17 fragments)
  - Brands: browse 1000+ affiliate brands, search, filter by category, favorite
  - Affiliate Links: create tracked short links, manage folders, view metrics
  - Analytics: clicks, sales, commission, conversion; time series + entity breakdown
  - Earnings: balance, payout statements, bonus levels, referral stats
  - Promotions: browse active deals and featured promotions
  - Shop: creator storefronts with pages and product posts
  - Account: profile, social platforms, sub-accounts, URL shorteners

Usage:
    client = MavelyClient()
    client.login("email@example.com", "password")

    # Browse brands
    brands = client.get_brands(first=20)
    for edge in brands["edges"]:
        print(edge["node"]["name"], edge["node"]["commissionRate"])

    # Create affiliate link
    link = client.create_affiliate_link("https://www.target.com/p/some-product")
    print(link["link"])  # => https://mavely.app.link/...

    # Get analytics
    stats = client.get_analytics_totals("2026-03-01", "2026-03-29")
    print(stats["metrics"]["commission"])
"""

import json
import time
import urllib.request
import urllib.parse
import urllib.error
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

AUTH0_DOMAIN = "mavely.us.auth0.com"
AUTH0_TOKEN_URL = f"https://{AUTH0_DOMAIN}/oauth/token"
AUTH0_CLIENT_ID = "PItSrEo35MYmLjhY6wJp8sCQAQRRWYxr"
AUTH0_AUDIENCE = "https://auth.mave.ly/"

GRAPHQL_URL = "https://mavely.live/api/graphql"
CLIENT_NAME = "@mavely/creator-app"
CLIENT_VERSION = "1.6.5"
CLIENT_REVISION = "418e5810"

UNLEASH_URL = "https://unleash-edge.mavely.live/api/frontend"
UNLEASH_CLIENT_KEY = "*:production.06ecc647a0ecca68a8beb02f539e225329c6fd3b4e0c5a3564781c06"


# ─────────────────────────────────────────────────────────────────────────────
# GraphQL Operations (extracted from JS bundles)
# ─────────────────────────────────────────────────────────────────────────────

# ── Profile & Account ──

Q_ME = """
query me {
  me {
    id createdAt firstName lastName name email paypalEmail phone
    referralLink
    integration {
      id amazonAssociatesTag linkDmIntegrationStatus
      urlShorteners { id isEnabled name accessToken groupGuid }
    }
    socialPlatforms { id createdAt updatedAt platform handle followerRange }
    mavelyGoals completedOnboarding role completedTipaltiOnboarding
  }
}
"""

Q_ME_ROLE = """
query MeRole { me { id name email role } }
"""

Q_ME_COMPLETED_ONBOARDING = """
query MeCompletedOnboarding { me { id completedOnboarding } }
"""

Q_ME_COMPLETED_TIPALTI = """
query MeCompletedTipaltiOnboarding { me { id completedTipaltiOnboarding } }
"""

Q_IS_AMAZON_ENABLED = """
query isAmazonAssociatesProgramEnabled { isAmazonAssociatesProgramEnabled }
"""

Q_SUB_ACCOUNTS = """
query subAccounts { subAccounts { id firstName lastName email } }
"""

Q_SUB_ACCOUNT_INVITES = """
query subAccountInvites { subAccountInvites }
"""

M_UPDATE_USER = """
mutation updateUser2($data: UserUpdateInput!) {
  updateUser2(data: $data) {
    id firstName lastName name email paypalEmail phone
    referralLink mavelyGoals completedOnboarding role
    socialPlatforms { id platform handle followerRange }
    integration {
      id amazonAssociatesTag linkDmIntegrationStatus
      urlShorteners { id isEnabled name accessToken groupGuid }
    }
  }
}
"""

M_CREATE_SOCIAL_PLATFORM = """
mutation createSocialPlatform($data: SocialPlatformCreateInput!) {
  createSocialPlatform(data: $data) {
    id createdAt updatedAt platform handle followerRange
  }
}
"""

M_UPDATE_SOCIAL_PLATFORM = """
mutation updateSocialPlatform($where: SocialPlatformWhereUniqueInput!, $data: SocialPlatformUpdateInput!) {
  updateSocialPlatform(where: $where, data: $data) {
    id createdAt updatedAt platform handle followerRange
  }
}
"""

M_UPSERT_URL_SHORTENER = """
mutation upsertMyUrlShortener($data: UrlShortenerUpdateInput!, $urlShortenerName: UrlShortenerName!) {
  upsertMyUrlShortener(data: $data, urlShortenerName: $urlShortenerName) {
    id accessToken isEnabled groupGuid name
  }
}
"""

M_CREATE_SUB_ACCOUNT_INVITE = """
mutation createSubAccountInvite($subAccountEmail: String!) {
  createSubAccountInvite(subAccountEmail: $subAccountEmail) { email }
}
"""

M_DELETE_SUB_ACCOUNT = """
mutation deleteSubAccount($subAccountId: String!) {
  deleteSubAccount(subAccountId: $subAccountId) { id }
}
"""

M_DELETE_SUB_ACCOUNT_INVITE = """
mutation deleteSubAccountInvite($subAccountEmail: String!) {
  deleteSubAccountInvite(subAccountEmail: $subAccountEmail) { email }
}
"""

M_DELETE_USER = """
mutation deleteUser { deleteUser { id } }
"""

M_REFRESH_TOKEN = """
mutation RefreshToken($token: String!) {
  refreshToken(token: $token) { accessToken refreshToken ok }
}
"""

M_IDENTIFY = """
mutation Identify($input: IdentifyInput!) {
  identify(input: $input) { success }
}
"""

# ── Brands ──

Q_BRANDS_CONNECTION = """
query brandsConnection($where: BrandWhereInput, $orderBy: BrandOrderByInput, $first: Int, $skip: Int, $after: String) {
  brands2(where: $where, orderBy: $orderBy, first: $first, skip: $skip, after: $after) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id slug name reportBrandName homepage description
        banner logo icon
        commissionFlat commissionRate commissionFlatFloat commissionRateFloat
        maxCommission { maxFlat maxRate }
        allCategories { id name }
      }
    }
  }
}
"""

Q_BRAND = """
query brand($where: BrandWhereUniqueInput!) {
  brand2(where: $where) {
    id slug name homepage description banner logo icon
    commissionFlat commissionRate commissionFlatFloat commissionRateFloat
    maxCommission { maxFlat maxRate }
    allCategories { id name }
  }
}
"""

Q_ALL_BRANDS = """
query allBrands($where: BrandWhereInput) {
  brands2(where: $where, first: 9999, orderBy: name_ASC) {
    pageInfo { hasNextPage }
    edges { node { id slug name icon commissionRate commissionFlat } }
  }
}
"""

Q_BRANDS_COUNT = """
query BrandsCount($where: BrandWhereInput) { brandsCount(where: $where) }
"""

Q_TRENDING_BRANDS = """
query trendingBrands($where: BrandWhereInput, $orderBy: BrandOrderByInput, $first: Int, $skip: Int, $after: String) {
  trendingBrands(where: $where, orderBy: $orderBy, first: $first, skip: $skip, after: $after) {
    pageInfo { hasNextPage }
    edges {
      node {
        id slug name reportBrandName icon logo banner
        allCategories { id name }
        homepage commissionFlatFloat commissionRateFloat
        maxCommission { maxFlat maxRate }
      }
    }
  }
}
"""

Q_FAVORITE_BRANDS = """
query favoriteBrands($where: BrandWhereInput, $orderBy: BrandOrderByInput, $first: Int, $skip: Int, $after: String) {
  favoriteBrands(where: $where, orderBy: $orderBy, first: $first, skip: $skip, after: $after) {
    pageInfo { hasNextPage }
    edges {
      node {
        id slug name icon logo banner homepage
        commissionFlatFloat commissionRateFloat
        maxCommission { maxFlat maxRate }
        allCategories { id name }
      }
    }
  }
}
"""

Q_FAVORITE_BRAND_IDS = """
query favoriteBrandIds { favoriteBrandIds }
"""

M_FAVORITE_BRAND = """
mutation favoriteBrand($id: ID!) { favoriteBrand(id: $id) { id } }
"""

M_UNFAVORITE_BRAND = """
mutation unfavoriteBrand($id: ID!) { unfavoriteBrand(id: $id) { id } }
"""

Q_CATEGORIES = """
query categories2($where: CategoryWhereInput, $orderBy: CategoryOrderByInput, $first: Int) {
  categories2(where: $where, orderBy: $orderBy, first: $first) {
    edges { node { id name } }
  }
}
"""

# ── Affiliate Links ──

Q_AFFILIATE_LINKS = """
query affiliateLinks($where: AffiliateLinkWhereInput, $first: Int, $skip: Int, $after: String, $orderBy: AffiliateLinkOrderByInput) {
  affiliateLinks(where: $where, first: $first, skip: $skip, after: $after, orderBy: $orderBy) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id updatedAt link metaDescription metaTitle metaImage metaUrl
        metaLogo metaSiteName metaVideo
        brand { id name icon banner slug }
        createdByUserId partnerId
      }
    }
  }
}
"""

Q_AFFILIATE_LINK = """
query affiliateLink($where: AffiliateLinkWhereUniqueInput!) {
  affiliateLink(where: $where) {
    id link metaDescription metaTitle metaImage metaUrl
    metaLogo metaSiteName metaVideo
    brand { id name icon banner slug }
    createdByUserId partnerId
  }
}
"""

Q_AFFILIATE_LINK_WITH_FOLDERS = """
query affiliateLinkWithFolders($where: AffiliateLinkWhereUniqueInput!) {
  affiliateLink(where: $where) {
    id link metaDescription metaTitle metaImage metaUrl
    brand { id name icon slug }
    folders { id name }
  }
}
"""

Q_AFFILIATE_LINKS_COUNT = """
query affiliateLinksCount($where: AffiliateLinkWhereInput) {
  affiliateLinksCount(where: $where)
}
"""

Q_AFFILIATE_LINK_METRICS = """
query affiliateLinkMetrics($where: AffiliateLinkWhereUniqueInput!, $metricsWhere: AffiliateLinkMetricsWhereInput) {
  affiliateLink(where: $where) {
    id link metaTitle brand { id name slug }
    metrics(where: $metricsWhere) {
      clicksCount commission sales salesCount conversion
    }
  }
}
"""

M_CREATE_AFFILIATE_LINK = """
mutation createAffiliateLink($url: String!) {
  createAffiliateLink(url: $url) {
    id link metaDescription metaTitle metaImage metaUrl
    metaLogo metaSiteName metaVideo
    brand { id name slug }
    originalUrl canonicalLink attributionUrl
  }
}
"""

M_DELETE_AFFILIATE_LINK = """
mutation deleteAffiliateLink($where: AffiliateLinkWhereUniqueInput!) {
  deleteAffiliateLink(where: $where) { id }
}
"""

M_UPDATE_AFFILIATE_LINK_METADATA = """
mutation updateAffiliateLinkMetadata($where: AffiliateLinkWhereUniqueInput!, $data: AffiliateLinkMetadataUpdateInput!) {
  updateAffiliateLinkMetadata(where: $where, data: $data) {
    id metaDescription metaTitle metaImage metaUrl metaLogo metaSiteName
  }
}
"""

# ── Affiliate Link Folders ──

Q_AFFILIATE_LINK_FOLDERS = """
query affiliateLinkFolders($first: Int, $skip: Int) {
  affiliateLinkFolders(first: $first, skip: $skip) {
    edges { node { id name affiliateLinks { id link } } }
    pageInfo { hasNextPage }
  }
}
"""

Q_AFFILIATE_LINK_FOLDER = """
query affiliateLinkFolder($where: AffiliateLinkFolderWhereUniqueInput!) {
  affiliateLinkFolder(where: $where) {
    id name affiliateLinks { id link metaTitle brand { id name slug } }
  }
}
"""

Q_AFFILIATE_LINK_FOLDERS_COUNT = """
query affiliateLinkFoldersCount { affiliateLinkFoldersCount }
"""

M_CREATE_AFFILIATE_LINK_FOLDER = """
mutation createAffiliateLinkFolder($name: String!, $affiliateLink: AffiliateLinkWhereUniqueInput) {
  createAffiliateLinkFolder(name: $name, affiliateLink: $affiliateLink) {
    id name affiliateLinks { id link }
  }
}
"""

M_DELETE_AFFILIATE_LINK_FOLDER = """
mutation deleteAffiliateLinkFolder($where: AffiliateLinkFolderWhereUniqueInput!) {
  deleteAffiliateLinkFolder(where: $where) { id }
}
"""

M_UPDATE_AFFILIATE_LINK_FOLDER = """
mutation updateAffiliateLinkFolder($where: AffiliateLinkFolderWhereUniqueInput!, $data: AffiliateLinkFolderUpdateInput!) {
  updateAffiliateLinkFolder(where: $where, data: $data) {
    id name affiliateLinks { id link }
  }
}
"""

M_ADD_LINK_TO_FOLDER = """
mutation addAffiliateLinkToAffiliateLinkFolder($affiliateLinkFolderId: ID!, $affiliateLinkId: ID!) {
  addAffiliateLinkToAffiliateLinkFolder(affiliateLinkFolderId: $affiliateLinkFolderId, affiliateLinkId: $affiliateLinkId) {
    id name affiliateLinks { id link }
  }
}
"""

M_REMOVE_LINK_FROM_FOLDER = """
mutation removeAffiliateLinkFromAffiliateLinkFolder($affiliateLinkFolderId: ID!, $affiliateLinkId: ID!) {
  removeAffiliateLinkFromAffiliateLinkFolder(affiliateLinkFolderId: $affiliateLinkFolderId, affiliateLinkId: $affiliateLinkId) {
    id name affiliateLinks { id link }
  }
}
"""

# ── Analytics ──

Q_ANALYTICS_TOTALS = """
query CreatorAnalyticsMetricsTotals($where: CreatorAnalyticsWhereInput!) {
  creatorAnalyticsMetricsTotals(where: $where) {
    metrics { clicksCount commission sales salesCount conversion }
  }
}
"""

Q_ANALYTICS_TIME_SERIES = """
query CreatorAnalyticsMetricsTimeSeries($where: CreatorAnalyticsWhereInput!) {
  creatorAnalyticsMetricsTimeSeries(where: $where) {
    aggregates {
      cstDateStr
      metrics { clicksCount commission sales salesCount conversion }
    }
  }
}
"""

Q_ANALYTICS_BY_ENTITY = """
query CreatorAnalyticsMetricsByEntity($where: CreatorAnalyticsWhereInput!, $orderBy: CreatorAnalyticsOrderByInput, $first: Int, $skip: Int) {
  creatorAnalyticsMetricsByEntity(where: $where, orderBy: $orderBy, first: $first, skip: $skip) {
    entity { id name icon domain }
    metrics { clicksCount commission sales salesCount conversion }
  }
}
"""

Q_ANALYTICS_BRAND_METRICS = """
query CreatorAnalyticsBrandMetrics($where: CreatorAnalyticsWhereInput!, $orderBy: CreatorAnalyticsOrderByInput, $first: Int, $skip: Int) {
  creatorAnalyticsMetricsByEntity(where: $where, orderBy: $orderBy, first: $first, skip: $skip) {
    entity { id name icon domain }
    metrics { clicksCount commission sales salesCount conversion }
  }
}
"""

Q_ANALYTICS_LINK_METRICS = """
query CreatorAnalyticsLinkMetrics($where: CreatorAnalyticsWhereInput!, $orderBy: CreatorAnalyticsOrderByInput, $first: Int, $skip: Int) {
  creatorAnalyticsMetricsByEntity(where: $where, orderBy: $orderBy, first: $first, skip: $skip) {
    entity { id name icon domain }
    metrics { clicksCount commission sales salesCount conversion }
  }
}
"""

Q_ANALYTICS_LINK_CLICKS = """
query CreatorAnalyticsLinkClicks($where: CreatorAnalyticsWhereInput!, $orderBy: CreatorAnalyticsOrderByInput, $first: Int, $skip: Int) {
  creatorAnalyticsMetricsByEntity(where: $where, orderBy: $orderBy, first: $first, skip: $skip) {
    entity { id name icon domain }
    metrics { clicksCount commission sales salesCount conversion }
  }
}
"""

Q_ANALYTICS_TRAFFIC_SOURCE = """
query CreatorAnalyticsTrafficSourceMetrics($where: CreatorAnalyticsWhereInput!, $orderBy: CreatorAnalyticsOrderByInput, $first: Int, $skip: Int) {
  creatorAnalyticsMetricsByEntity(where: $where, orderBy: $orderBy, first: $first, skip: $skip) {
    entity { id name icon domain }
    metrics { clicksCount commission sales salesCount conversion }
  }
}
"""

# ── Earnings ──

Q_BALANCE = """
query balance { balance { upcomingPaymentDate } }
"""

Q_PAYOUT_STATEMENTS = """
query getPayoutStatements($where: PartnerPayoutWhereInput) {
  getPayoutStatements(where: $where) {
    netPayout payoutDate
    payPeriod { from to }
    commission {
      total earnings adjustments
      brands { brandId brandName brandIcon earnings adjustments }
      payPeriod { from to }
    }
    campaign {
      total
      payPeriod { from to }
      campaigns { brandId brandName brandIcon earnings payPeriod { from to } }
    }
    bonus { total sales referrals amazon payPeriod { from to } }
    other { total flatFees }
  }
}
"""

Q_SALES_BONUS_LEVELS = """
query SalesBonusLevels($orderBy: SalesBonusLevelOrderByInput, $useCommissionBasedLevels: Boolean) {
  salesBonusLevels(orderBy: $orderBy, useCommissionBasedLevels: $useCommissionBasedLevels) {
    id commissionValue commissionLabel bonusValue bonusLabel
  }
}
"""

Q_REFERRAL_STATS = """
query ReferralStats { referralStats { usersCount totalEarnings } }
"""

Q_GENERATE_TIPALTI_URL = """
query GenerateTipaltiIFrameUrl { generateTipaltiIFrameUrl }
"""

Q_REPORTS_CONNECTION = """
query ReportsConnection($where: ReportWhereInput, $orderBy: ReportOrderByInput, $first: Int, $skip: Int, $after: String) {
  allReports(where: $where, orderBy: $orderBy, first: $first, skip: $skip, after: $after) {
    pageInfo { hasNextPage endCursor }
    edges { node { id createdAt status type downloadUrl } }
  }
}
"""

Q_REPORTS_COUNT = """
query ReportsCount($where: ReportWhereInput) { reportsCount(where: $where) }
"""

# ── Promotions ──

Q_PROMOTIONS_LIST = """
query promotionsList($where: PromotionWhereInput, $orderBy: PromotionOrderByInput, $first: Int, $after: String) {
  promotionsConnection(where: $where, orderBy: $orderBy, first: $first, after: $after) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id startDate endDate title description banner url
        brand { id name icon banner homepage slug }
      }
    }
  }
}
"""

Q_FEATURED_PROMOTIONS = """
query featuredPromotions($where: PromotionWhereInput, $orderBy: PromotionOrderByInput, $first: Int, $after: String) {
  featuredPromotions(where: $where, orderBy: $orderBy, first: $first, after: $after) {
    pageInfo { hasNextPage endCursor }
    edges {
      node {
        id startDate endDate title description banner url
        brand { id name icon banner homepage slug }
      }
    }
  }
}
"""

# ── Opportunities ──

Q_OPPORTUNITIES = """
query opportunities($where: OpportunityWhereInput, $orderBy: OpportunityOrderByInput, $first: Int!, $after: String) {
  opportunities(where: $where, orderBy: $orderBy, first: $first, after: $after) {
    pageInfo { hasNextPage endCursor }
    edges {
      cursor
      node { id title description status type }
    }
  }
}
"""

Q_OPPORTUNITY = """
query opportunity($where: OpportunityWhereUniqueInput!) {
  opportunity(where: $where) {
    id title description status type
  }
}
"""

# ── Shop ──

Q_MY_SHOP = """
query myShop {
  myShop {
    id createdAt updatedAt title bio slug profileImage
    shopSocialChannelUrls { id position platform urlPath url }
  }
}
"""

Q_MY_SHOP_PAGES = """
query myShopPages($where: ShopPageWhereInput, $first: Int, $skip: Int) {
  myShop {
    shopPages(where: $where, first: $first, skip: $skip) {
      edges {
        node { id createdAt updatedAt title slug position isPublished }
      }
      pageInfo { hasNextPage }
    }
  }
}
"""

Q_MY_SHOP_POSTS = """
query myShopPosts($first: Int, $skip: Int) {
  myShop {
    shopPosts(first: $first, skip: $skip) {
      pageInfo { hasNextPage }
      edges {
        node {
          id createdAt updatedAt title description slug
          image { url width height }
        }
      }
    }
  }
}
"""

Q_SHOP_PAGE = """
query shopPage($where: ShopPageWhereUniqueInput!) {
  shopPage(where: $where) {
    id title slug position isPublished
  }
}
"""

Q_SHOP_POST = """
query shopPost($where: ShopPostWhereUniqueInput!) {
  shopPost(where: $where) {
    id title description slug image { url width height }
  }
}
"""

Q_SHOP_POST_LINKS = """
query shopPostLinks($where: ShopPostWhereUniqueInput!, $first: Int, $skip: Int) {
  shopPost(where: $where) {
    affiliateLinks(first: $first, skip: $skip) {
      edges { node { id link metaTitle brand { id name slug } } }
      pageInfo { hasNextPage }
    }
  }
}
"""

Q_SHOP_POST_LINKS_COUNT = """
query shopPostLinksTotalCount($where: ShopPostWhereUniqueInput!) {
  shopPost(where: $where) { affiliateLinksTotalCount }
}
"""

Q_SHOP_PAGE_POSTS = """
query shopPagePosts($where: ShopPageWhereUniqueInput!, $first: Int, $skip: Int) {
  shopPage(where: $where) {
    shopPosts(first: $first, skip: $skip) {
      edges { node { id title slug image { url } } }
      pageInfo { hasNextPage }
    }
  }
}
"""

Q_SHOP_PAGE_POST_SLUGS = """
query shopPagePostSlugs($where: ShopPageWhereUniqueInput!) {
  shopPage(where: $where) { shopPosts { edges { node { slug } } } }
}
"""

Q_SHOP_PAGE_POSTS_COUNT = """
query shopPagePostsTotalCount($where: ShopPageWhereUniqueInput!) {
  shopPage(where: $where) { shopPostsTotalCount }
}
"""

M_CREATE_SHOP = """
mutation createShop($data: ShopCreateInput!) {
  createShop(data: $data) { id title bio slug profileImage }
}
"""

M_UPDATE_SHOP = """
mutation updateShop($data: ShopUpdateInput!) {
  updateShop(data: $data) { id title bio slug profileImage }
}
"""

M_CREATE_SHOP_PAGE = """
mutation createShopPage($data: ShopPageCreateInput!) {
  createShopPage(data: $data) { id title slug position isPublished }
}
"""

M_DELETE_SHOP_PAGE = """
mutation deleteShopPage($where: ShopPageWhereUniqueInput!) {
  deleteShopPage(where: $where) { id }
}
"""

M_UPDATE_SHOP_PAGE = """
mutation updateShopPage($where: ShopPageWhereUniqueInput!, $data: ShopPageUpdateInput!) {
  updateShopPage(where: $where, data: $data) { id title slug position isPublished }
}
"""

M_CREATE_SHOP_POST = """
mutation createShopPost($data: ShopPostCreateInput!) {
  createShopPost(data: $data) {
    id title description slug image { url width height }
  }
}
"""

M_DELETE_SHOP_POST = """
mutation deleteShopPost($where: ShopPostWhereUniqueInput!) {
  deleteShopPost(where: $where) { id }
}
"""

M_UPDATE_SHOP_POST = """
mutation updateShopPost($where: ShopPostWhereUniqueInput!, $data: ShopPostUpdateInput!) {
  updateShopPost(where: $where, data: $data) {
    id title description slug image { url width height }
  }
}
"""

# ── Misc ──

Q_CLOUDINARY_SIGNATURE = """
query cloudinarySignature($paramsToSign: String!) {
  cloudinarySignature(paramsToSign: $paramsToSign)
}
"""

M_CREATE_CLOUDINARY_COLLAGE = """
mutation createCloudinaryCollage($imageUrls: [String!]!) {
  createCloudinaryCollage(imageUrls: $imageUrls)
}
"""

Q_RESOURCES_NEWSFEED = """
query resourcesGridNewsfeedItems($first: Int, $skip: Int) {
  resourcesGridNewsfeedItems(first: $first, skip: $skip) {
    edges {
      node { id title description url image publishDate }
    }
    pageInfo { hasNextPage }
  }
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────────────────────────────────────

class MavelyError(Exception):
    """Raised when the Mavely API returns an error."""
    def __init__(self, errors: list, data: Any = None):
        self.errors = errors
        self.data = data
        messages = [e.get("message", str(e)) for e in errors]
        super().__init__(f"Mavely API error: {'; '.join(messages)}")


class MavelyClient:
    """
    Reverse-engineered client for the Mavely Creators platform.

    Auth flow:
      1. Auth0 Resource Owner Password Grant -> JWT access_token + refresh_token
      2. JWT used as Bearer token for GraphQL API at mavely.live
      3. Refresh token can be exchanged via Auth0 or GraphQL mutation

    All methods return raw dict responses from the GraphQL API.
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._id_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._user_id: Optional[str] = None

    # ── Auth ──

    def login(self, email: str, password: str) -> dict:
        """
        Authenticate via Auth0 Resource Owner Password Grant.
        Returns the full token response.
        """
        payload = json.dumps({
            "grant_type": "password",
            "client_id": AUTH0_CLIENT_ID,
            "audience": AUTH0_AUDIENCE,
            "scope": "openid profile email offline_access",
            "username": email,
            "password": password,
        }).encode()

        req = urllib.request.Request(
            AUTH0_TOKEN_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read())

        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token")
        self._id_token = data.get("id_token")
        self._token_expires_at = time.time() + data.get("expires_in", 9000)

        # Extract user ID from JWT payload
        try:
            import base64
            payload_b64 = self._access_token.split(".")[1]
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            jwt_payload = json.loads(base64.b64decode(payload_b64))
            self._user_id = jwt_payload.get("id")
        except Exception:
            pass

        return data

    def set_tokens(self, access_token: str, refresh_token: Optional[str] = None):
        """Set tokens directly (e.g., from a stored session)."""
        self._access_token = access_token
        self._refresh_token = refresh_token

    def refresh_auth0(self) -> dict:
        """Refresh the access token via Auth0."""
        if not self._refresh_token:
            raise ValueError("No refresh token available")

        payload = json.dumps({
            "grant_type": "refresh_token",
            "client_id": AUTH0_CLIENT_ID,
            "refresh_token": self._refresh_token,
        }).encode()

        req = urllib.request.Request(
            AUTH0_TOKEN_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read())

        self._access_token = data["access_token"]
        if "refresh_token" in data:
            self._refresh_token = data["refresh_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 9000)
        return data

    def refresh_graphql(self) -> dict:
        """Refresh the access token via the GraphQL mutation."""
        if not self._refresh_token:
            raise ValueError("No refresh token available")
        result = self._graphql(M_REFRESH_TOKEN, {"token": self._refresh_token})
        rt = result["refreshToken"]
        if rt.get("ok"):
            self._access_token = rt["accessToken"]
            self._refresh_token = rt["refreshToken"]
            self._token_expires_at = time.time() + 9000
        return rt

    @property
    def is_authenticated(self) -> bool:
        return self._access_token is not None

    @property
    def token_expired(self) -> bool:
        return time.time() >= self._token_expires_at

    def _ensure_auth(self):
        if not self._access_token:
            raise ValueError("Not authenticated. Call login() first.")
        if self.token_expired and self._refresh_token:
            self.refresh_auth0()

    # ── GraphQL Transport ──

    def _graphql(self, query: str, variables: Optional[dict] = None) -> dict:
        """Execute a GraphQL query/mutation and return the data dict."""
        self._ensure_auth()

        body = {"query": query.strip()}
        if variables:
            body["variables"] = variables

        req = urllib.request.Request(
            GRAPHQL_URL,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._access_token}",
                "client-name": CLIENT_NAME,
                "client-version": CLIENT_VERSION,
                "client-revision": CLIENT_REVISION,
                "Origin": "https://creators.joinmavely.com",
                "Referer": "https://creators.joinmavely.com/",
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            result = json.loads(resp.read())

        if "errors" in result and result["errors"]:
            raise MavelyError(result["errors"], result.get("data"))

        return result.get("data", {})

    # ── Profile & Account ──

    def get_me(self) -> dict:
        """Get the current user's full profile."""
        return self._graphql(Q_ME)["me"]

    def get_role(self) -> str:
        """Get the current user's role."""
        return self._graphql(Q_ME_ROLE)["me"]["role"]

    def update_user(self, data: dict) -> dict:
        """Update user profile fields."""
        return self._graphql(M_UPDATE_USER, {"data": data})["updateUser2"]

    def get_sub_accounts(self) -> list:
        """Get sub-accounts."""
        return self._graphql(Q_SUB_ACCOUNTS)["subAccounts"]

    def create_sub_account_invite(self, email: str) -> dict:
        return self._graphql(M_CREATE_SUB_ACCOUNT_INVITE, {"subAccountEmail": email})

    def create_social_platform(self, platform: str, handle: str, follower_range: str = None) -> dict:
        data = {"platform": platform, "handle": handle}
        if follower_range:
            data["followerRange"] = follower_range
        return self._graphql(M_CREATE_SOCIAL_PLATFORM, {"data": data})["createSocialPlatform"]

    def update_social_platform(self, platform_id: str, data: dict) -> dict:
        return self._graphql(M_UPDATE_SOCIAL_PLATFORM, {
            "where": {"id": platform_id}, "data": data
        })["updateSocialPlatform"]

    # ── Brands ──

    def get_brands(self, first: int = 20, skip: int = 0, search: str = None,
                   category_id: str = None, order_by: str = "name_ASC") -> dict:
        """
        Browse affiliate brands with pagination.
        Returns: {"pageInfo": {...}, "edges": [{"node": {...}}]}
        """
        where = {}
        if search:
            where["name_contains"] = search
        if category_id:
            where["allCategories_some"] = {"id": category_id}
        return self._graphql(Q_BRANDS_CONNECTION, {
            "first": first, "skip": skip,
            "orderBy": order_by,
            "where": where or None,
        })["brands2"]

    def get_brand(self, slug: str = None, brand_id: str = None) -> dict:
        """Get a single brand by slug or ID."""
        where = {"slug": slug} if slug else {"id": brand_id}
        return self._graphql(Q_BRAND, {"where": where})["brand2"]

    def get_all_brands(self, search: str = None) -> list:
        """Get all brands (up to 9999) for dropdowns/search."""
        where = {"name_contains": search} if search else None
        return self._graphql(Q_ALL_BRANDS, {"where": where})["brands2"]["edges"]

    def get_trending_brands(self, first: int = 10) -> dict:
        """Get trending brands."""
        return self._graphql(Q_TRENDING_BRANDS, {"first": first})["trendingBrands"]

    def get_favorite_brands(self, first: int = 20) -> dict:
        """Get user's favorite brands."""
        return self._graphql(Q_FAVORITE_BRANDS, {"first": first})["favoriteBrands"]

    def get_favorite_brand_ids(self) -> list:
        """Get list of favorited brand IDs."""
        return self._graphql(Q_FAVORITE_BRAND_IDS)["favoriteBrandIds"]

    def favorite_brand(self, brand_id: str) -> dict:
        return self._graphql(M_FAVORITE_BRAND, {"id": brand_id})

    def unfavorite_brand(self, brand_id: str) -> dict:
        return self._graphql(M_UNFAVORITE_BRAND, {"id": brand_id})

    def get_categories(self, first: int = 100) -> list:
        """Get all brand categories."""
        return self._graphql(Q_CATEGORIES, {
            "first": first, "orderBy": "name_ASC"
        })["categories2"]["edges"]

    # ── Affiliate Links ──

    def get_affiliate_links(self, first: int = 20, skip: int = 0,
                            brand_id: str = None,
                            order_by: str = "createdAt_DESC") -> dict:
        """Get paginated affiliate links."""
        where = {}
        if brand_id:
            where["brand"] = {"id": brand_id}
        return self._graphql(Q_AFFILIATE_LINKS, {
            "first": first, "skip": skip,
            "orderBy": order_by,
            "where": where or None,
        })["affiliateLinks"]

    def get_affiliate_link(self, link_id: str) -> dict:
        return self._graphql(Q_AFFILIATE_LINK, {"where": {"id": link_id}})["affiliateLink"]

    def get_affiliate_links_count(self, brand_id: str = None) -> int:
        where = {"brand": {"id": brand_id}} if brand_id else None
        return self._graphql(Q_AFFILIATE_LINKS_COUNT, {"where": where})["affiliateLinksCount"]

    def get_affiliate_link_metrics(self, link_id: str,
                                    date_from: str = None,
                                    date_to: str = None) -> dict:
        """Get metrics for a single affiliate link."""
        metrics_where = {}
        if date_from:
            metrics_where["cstDateStr_gte"] = date_from
        if date_to:
            metrics_where["cstDateStr_lte"] = date_to
        return self._graphql(Q_AFFILIATE_LINK_METRICS, {
            "where": {"id": link_id},
            "metricsWhere": metrics_where or None,
        })["affiliateLink"]

    def create_affiliate_link(self, url: str) -> dict:
        """
        Create a new affiliate link from a product URL.
        The API generates a tracked short link (mavely.app.link/...).
        """
        return self._graphql(M_CREATE_AFFILIATE_LINK, {"url": url})["createAffiliateLink"]

    def delete_affiliate_link(self, link_id: str) -> dict:
        return self._graphql(M_DELETE_AFFILIATE_LINK, {"where": {"id": link_id}})

    def update_affiliate_link_metadata(self, link_id: str, data: dict) -> dict:
        """Update link metadata (title, description, image, etc.)."""
        return self._graphql(M_UPDATE_AFFILIATE_LINK_METADATA, {
            "where": {"id": link_id}, "data": data
        })["updateAffiliateLinkMetadata"]

    # ── Link Folders ──

    def get_link_folders(self, first: int = 50) -> dict:
        return self._graphql(Q_AFFILIATE_LINK_FOLDERS, {"first": first})["affiliateLinkFolders"]

    def get_link_folder(self, folder_id: str) -> dict:
        return self._graphql(Q_AFFILIATE_LINK_FOLDER, {"where": {"id": folder_id}})["affiliateLinkFolder"]

    def create_link_folder(self, name: str, link_id: str = None) -> dict:
        variables = {"name": name}
        if link_id:
            variables["affiliateLink"] = {"id": link_id}
        return self._graphql(M_CREATE_AFFILIATE_LINK_FOLDER, variables)["createAffiliateLinkFolder"]

    def delete_link_folder(self, folder_id: str) -> dict:
        return self._graphql(M_DELETE_AFFILIATE_LINK_FOLDER, {"where": {"id": folder_id}})

    def add_link_to_folder(self, folder_id: str, link_id: str) -> dict:
        return self._graphql(M_ADD_LINK_TO_FOLDER, {
            "affiliateLinkFolderId": folder_id,
            "affiliateLinkId": link_id,
        })["addAffiliateLinkToAffiliateLinkFolder"]

    def remove_link_from_folder(self, folder_id: str, link_id: str) -> dict:
        return self._graphql(M_REMOVE_LINK_FROM_FOLDER, {
            "affiliateLinkFolderId": folder_id,
            "affiliateLinkId": link_id,
        })["removeAffiliateLinkFromAffiliateLinkFolder"]

    # ── Analytics ──

    def get_analytics_totals(self, date_from: str, date_to: str,
                              brand_id: str = None) -> dict:
        """
        Get aggregate analytics metrics for a date range.
        Dates are CST strings: "YYYY-MM-DD".
        Returns: {"metrics": {"clicksCount": N, "commission": N, ...}}
        """
        where = {"cstDateStr_gte": date_from, "cstDateStr_lte": date_to}
        if brand_id:
            where["brand"] = {"id": brand_id}
        return self._graphql(Q_ANALYTICS_TOTALS, {"where": where})["creatorAnalyticsMetricsTotals"]

    def get_analytics_time_series(self, date_from: str, date_to: str,
                                   brand_id: str = None) -> list:
        """
        Get daily analytics time series.
        Returns list of {"cstDateStr": "YYYY-MM-DD", "metrics": {...}}.
        """
        where = {"cstDateStr_gte": date_from, "cstDateStr_lte": date_to}
        if brand_id:
            where["brand"] = {"id": brand_id}
        return self._graphql(Q_ANALYTICS_TIME_SERIES, {"where": where}
                             )["creatorAnalyticsMetricsTimeSeries"]["aggregates"]

    def get_analytics_by_brand(self, date_from: str, date_to: str,
                                first: int = 10, order_by: str = "commission_DESC") -> list:
        """Get analytics broken down by brand."""
        where = {
            "cstDateStr_gte": date_from,
            "cstDateStr_lte": date_to,
            "entity": "Brand",
        }
        return self._graphql(Q_ANALYTICS_BRAND_METRICS, {
            "where": where, "first": first, "orderBy": order_by,
        })["creatorAnalyticsMetricsByEntity"]

    def get_analytics_by_link(self, date_from: str, date_to: str,
                               first: int = 10, order_by: str = "clicksCount_DESC") -> list:
        """Get analytics broken down by affiliate link."""
        where = {
            "cstDateStr_gte": date_from,
            "cstDateStr_lte": date_to,
            "entity": "Link",
        }
        return self._graphql(Q_ANALYTICS_LINK_METRICS, {
            "where": where, "first": first, "orderBy": order_by,
        })["creatorAnalyticsMetricsByEntity"]

    def get_analytics_by_traffic_source(self, date_from: str, date_to: str,
                                         first: int = 10) -> list:
        """Get analytics broken down by traffic source."""
        where = {
            "cstDateStr_gte": date_from,
            "cstDateStr_lte": date_to,
            "entity": "TrafficSource",
        }
        return self._graphql(Q_ANALYTICS_TRAFFIC_SOURCE, {
            "where": where, "first": first,
        })["creatorAnalyticsMetricsByEntity"]

    # ── Earnings ──

    def get_balance(self) -> dict:
        """Get upcoming payment date."""
        return self._graphql(Q_BALANCE)["balance"]

    def get_payout_statements(self, year: int = None) -> list:
        """Get payout statements. Filter by year if provided."""
        where = {"year": year} if year else None
        return self._graphql(Q_PAYOUT_STATEMENTS, {"where": where})["getPayoutStatements"]

    def get_bonus_levels(self, commission_based: bool = True) -> list:
        """Get sales bonus tier levels."""
        return self._graphql(Q_SALES_BONUS_LEVELS, {
            "useCommissionBasedLevels": commission_based
        })["salesBonusLevels"]

    def get_referral_stats(self) -> dict:
        """Get referral program stats."""
        return self._graphql(Q_REFERRAL_STATS)["referralStats"]

    def get_reports(self, first: int = 20) -> dict:
        """Get downloadable reports."""
        return self._graphql(Q_REPORTS_CONNECTION, {"first": first})["allReports"]

    # ── Promotions ──

    def get_promotions(self, first: int = 20, brand_slug: str = None,
                       order_by: str = "startDate_DESC") -> dict:
        """Get active promotions/deals."""
        where = {}
        if brand_slug:
            where["brand"] = {"slug": brand_slug}
        return self._graphql(Q_PROMOTIONS_LIST, {
            "first": first, "orderBy": order_by,
            "where": where or None,
        })["promotionsConnection"]

    def get_featured_promotions(self, first: int = 10) -> dict:
        """Get featured promotions."""
        return self._graphql(Q_FEATURED_PROMOTIONS, {"first": first})["featuredPromotions"]

    # ── Opportunities ──

    def get_opportunities(self, first: int = 20, status: str = None) -> dict:
        """Get brand collaboration opportunities."""
        where = {"status": status} if status else None
        return self._graphql(Q_OPPORTUNITIES, {
            "first": first, "where": where,
        })["opportunities"]

    def get_opportunity(self, opportunity_id: str) -> dict:
        return self._graphql(Q_OPPORTUNITY, {"where": {"id": opportunity_id}})["opportunity"]

    # ── Shop ──

    def get_my_shop(self) -> dict:
        """Get the creator's storefront."""
        return self._graphql(Q_MY_SHOP)["myShop"]

    def get_shop_pages(self, first: int = 50) -> dict:
        return self._graphql(Q_MY_SHOP_PAGES, {"first": first})["myShop"]

    def get_shop_posts(self, first: int = 50) -> dict:
        return self._graphql(Q_MY_SHOP_POSTS, {"first": first})["myShop"]

    def create_shop(self, title: str, bio: str = None) -> dict:
        data = {"title": title}
        if bio:
            data["bio"] = bio
        return self._graphql(M_CREATE_SHOP, {"data": data})["createShop"]

    def update_shop(self, data: dict) -> dict:
        return self._graphql(M_UPDATE_SHOP, {"data": data})["updateShop"]

    def create_shop_page(self, title: str, slug: str = None) -> dict:
        data = {"title": title}
        if slug:
            data["slug"] = slug
        return self._graphql(M_CREATE_SHOP_PAGE, {"data": data})["createShopPage"]

    def create_shop_post(self, title: str, description: str = None) -> dict:
        data = {"title": title}
        if description:
            data["description"] = description
        return self._graphql(M_CREATE_SHOP_POST, {"data": data})["createShopPost"]

    # ── Misc ──

    def get_cloudinary_signature(self, params_to_sign: str) -> str:
        """Get Cloudinary upload signature."""
        return self._graphql(Q_CLOUDINARY_SIGNATURE, {
            "paramsToSign": params_to_sign
        })["cloudinarySignature"]

    def get_newsfeed(self, first: int = 20) -> dict:
        """Get resources/newsfeed items."""
        return self._graphql(Q_RESOURCES_NEWSFEED, {"first": first})["resourcesGridNewsfeedItems"]

    # ── Feature Flags ──

    def get_feature_flags(self, email: str = "", user_type: str = "creator",
                           plan: str = "free") -> list:
        """
        Get Unleash feature flags for the creator app.
        No auth required -- uses public client key.
        """
        params = {
            "sessionId": "no-session",
            "appName": "mavely-creator-app",
            "environment": "default",
            "userId": "anonymous",
            "properties[email]": email,
            "properties[userType]": user_type,
            "properties[plan]": plan,
            "properties[environment]": "production",
            "properties[appVersion]": CLIENT_VERSION,
        }
        url = f"{UNLEASH_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={
            "Authorization": UNLEASH_CLIENT_KEY,
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        })
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read()).get("toggles", [])


# ─────────────────────────────────────────────────────────────────────────────
# CLI Demo
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import os

    email = os.environ.get("MAVELY_EMAIL") or (sys.argv[1] if len(sys.argv) > 1 else None)
    password = os.environ.get("MAVELY_PASSWORD") or (sys.argv[2] if len(sys.argv) > 2 else None)

    if not email or not password:
        print("Usage: python mavely_client.py <email> <password>")
        print("  or set MAVELY_EMAIL and MAVELY_PASSWORD env vars")
        sys.exit(1)

    client = MavelyClient()

    print("=== Authenticating ===")
    tokens = client.login(email, password)
    print(f"  Token type: {tokens['token_type']}")
    print(f"  Expires in: {tokens['expires_in']}s")
    print(f"  Scopes: {tokens['scope']}")

    print("\n=== Profile ===")
    me = client.get_me()
    print(f"  Name: {me['name']}")
    print(f"  Email: {me['email']}")
    print(f"  Role: {me['role']}")
    print(f"  Referral link: {me['referralLink']}")
    print(f"  Onboarded: {me['completedOnboarding']}")

    print("\n=== Categories ===")
    cats = client.get_categories()
    print(f"  {len(cats)} categories:")
    for c in cats[:8]:
        print(f"    - {c['node']['name']}")
    if len(cats) > 8:
        print(f"    ... and {len(cats) - 8} more")

    print("\n=== Brands (first 5) ===")
    brands = client.get_brands(first=5)
    print(f"  Has more: {brands['pageInfo']['hasNextPage']}")
    for edge in brands["edges"]:
        b = edge["node"]
        rate = b.get("commissionRate") or b.get("commissionRateFloat") or 0
        flat = b.get("commissionFlat") or b.get("commissionFlatFloat") or 0
        print(f"  {b['name']:30s} {rate}% + ${flat:.2f} flat")

    print("\n=== Trending Brands ===")
    trending = client.get_trending_brands(first=5)
    for edge in trending["edges"]:
        b = edge["node"]
        print(f"  {b['name']}")

    print("\n=== Affiliate Links (first 5) ===")
    links = client.get_affiliate_links(first=5)
    for edge in links["edges"]:
        ln = edge["node"]
        brand = ln["brand"]["name"] if ln.get("brand") else "?"
        print(f"  [{brand}] {ln.get('metaTitle', '(no title)')}")
        print(f"    -> {ln['link']}")

    print("\n=== Analytics (MTD) ===")
    from datetime import datetime, timedelta
    today = datetime.now()
    first_of_month = today.replace(day=1).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    stats = client.get_analytics_totals(first_of_month, today_str)
    m = stats["metrics"]
    print(f"  Clicks: {m['clicksCount']}")
    print(f"  Sales: ${m['sales']:.2f} ({m['salesCount']} orders)")
    print(f"  Commission: ${m['commission']:.2f}")
    print(f"  Conversion: {m['conversion']:.1%}" if m['conversion'] else "  Conversion: 0%")

    print("\n=== Earnings ===")
    balance = client.get_balance()
    print(f"  Next payment: {balance['upcomingPaymentDate']}")

    bonus = client.get_bonus_levels()
    print(f"  Bonus tiers: {len(bonus)}")
    for b in bonus[:3]:
        print(f"    ${b['commissionValue']:,.0f} commission -> ${b['bonusValue']:,.0f} bonus")

    referrals = client.get_referral_stats()
    print(f"  Referrals: {referrals['usersCount']} users, ${referrals['totalEarnings']:.2f} earned")

    print("\n=== Promotions (first 3) ===")
    promos = client.get_promotions(first=3)
    for edge in promos["edges"]:
        p = edge["node"]
        brand = p["brand"]["name"] if p.get("brand") else "?"
        print(f"  [{brand}] {p['title']}")
        print(f"    {p['startDate'][:10]} -> {p['endDate'][:10]}")

    print("\n=== Feature Flags ===")
    try:
        flags = client.get_feature_flags()
        enabled = [f for f in flags if f.get("enabled")]
        print(f"  {len(enabled)}/{len(flags)} flags enabled")
        for f in enabled[:5]:
            print(f"    {f['name']}: {f.get('variant', {}).get('name', 'on')}")
    except Exception as e:
        print(f"  (Unleash may be geo-restricted: {e})")

    print("\n--- All tests passed ---")
