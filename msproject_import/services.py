import logging
import os
import urllib.parse
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class MicrosoftOAuthService:
    """
    Handles OAuth 2.0 Authorization Code flow for Microsoft Entra ID (Azure AD)
    to access Project Online / SharePoint PWA APIs.
    """

    @classmethod
    def get_tenant_id(cls) -> str:
        return getattr(settings, 'AZURE_TENANT_ID', '') or os.environ.get('AZURE_TENANT_ID', 'common')

    @classmethod
    def get_client_id(cls) -> str:
        return getattr(settings, 'AZURE_CLIENT_ID', '') or os.environ.get('AZURE_CLIENT_ID', '')

    @classmethod
    def get_client_secret(cls) -> str:
        return getattr(settings, 'AZURE_CLIENT_SECRET', '') or os.environ.get('AZURE_CLIENT_SECRET', '')

    @classmethod
    def get_pwa_url(cls) -> str:
        return getattr(settings, 'PWA_URL', '') or os.environ.get('PWA_URL', '')

    @classmethod
    def is_configured(cls) -> bool:
        """Checks if real Azure AD credentials are configured."""
        return bool(cls.get_client_id() and cls.get_client_secret())

    @classmethod
    def get_authorization_url(cls, redirect_uri: str, state: str = '') -> str:
        """
        Builds the Microsoft OAuth 2.0 authorization URL.
        If credentials are not configured, provides a mock development redirect URL.
        """
        client_id = cls.get_client_id()
        if not client_id:
            logger.info("Azure AD client ID not configured. Generating mock OAuth redirect URL.")
            params = {'code': 'mock_dev_code', 'state': state}
            return f"{redirect_uri}?{urllib.parse.urlencode(params)}"

        tenant = cls.get_tenant_id()
        pwa_url = cls.get_pwa_url()

        # Build scope based on PWA URL hostname or fallback to Graph AllSites.Read
        if pwa_url:
            parsed = urllib.parse.urlparse(pwa_url)
            sp_host = f"{parsed.scheme}://{parsed.netloc}"
            scope = f"{sp_host}/AllSites.Read offline_access openid profile email"
        else:
            scope = "https://graph.microsoft.com/.default offline_access openid profile email"

        params = {
            'client_id': client_id,
            'response_type': 'code',
            'redirect_uri': redirect_uri,
            'response_mode': 'query',
            'scope': scope,
            'state': state,
            'prompt': 'select_account',
        }
        auth_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize?{urllib.parse.urlencode(params)}"
        logger.info("Generated Microsoft OAuth authorization URL for tenant: %s", tenant)
        return auth_url

    @classmethod
    def exchange_code_for_token(cls, code: str, redirect_uri: str) -> dict:
        """
        Exchanges authorization code for access and refresh tokens.
        """
        if code == 'mock_dev_code' or not cls.is_configured():
            logger.info("Using simulated OAuth token for development/test environment.")
            return {
                'access_token': 'mock_access_token_dev',
                'refresh_token': 'mock_refresh_token_dev',
                'token_type': 'Bearer',
                'expires_in': 3600,
                'user_email': 'dev.engineer@company.local',
                'user_name': 'Dev Engineer',
            }

        tenant = cls.get_tenant_id()
        client_id = cls.get_client_id()
        client_secret = cls.get_client_secret()
        pwa_url = cls.get_pwa_url()

        if pwa_url:
            parsed = urllib.parse.urlparse(pwa_url)
            sp_host = f"{parsed.scheme}://{parsed.netloc}"
            scope = f"{sp_host}/AllSites.Read offline_access openid profile email"
        else:
            scope = "https://graph.microsoft.com/.default offline_access openid profile email"

        token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
        data = {
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
            'scope': scope,
        }

        try:
            response = requests.post(token_url, data=data, timeout=15)
            response.raise_for_status()
            token_data = response.json()
            logger.info("Successfully exchanged authorization code for Microsoft access token.")
            return token_data
        except requests.RequestException as e:
            logger.error("Failed to exchange OAuth code for token: %s", str(e), exc_info=True)
            raise ValueError(f"Microsoft authentication failed: {e}")

    @classmethod
    def refresh_access_token(cls, refresh_token: str) -> dict:
        """
        Refreshes an expired access token using the refresh token.
        """
        if refresh_token == 'mock_refresh_token_dev' or not cls.is_configured():
            return {
                'access_token': 'mock_access_token_dev',
                'refresh_token': 'mock_refresh_token_dev',
                'token_type': 'Bearer',
                'expires_in': 3600,
            }

        tenant = cls.get_tenant_id()
        token_url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
        data = {
            'client_id': cls.get_client_id(),
            'client_secret': cls.get_client_secret(),
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        }

        try:
            response = requests.post(token_url, data=data, timeout=15)
            response.raise_for_status()
            logger.info("Successfully refreshed Microsoft access token.")
            return response.json()
        except requests.RequestException as e:
            logger.error("Failed to refresh Microsoft OAuth token: %s", str(e), exc_info=True)
            raise ValueError(f"Failed to refresh access token: {e}")


def fetch_pwa_data(access_token: str, target_year: int) -> tuple[dict, list]:
    """
    Fetches time reporting data from Microsoft Project Web App (PWA) using an OAuth access token.
    Returns:
        tuple (daily_data_map, list of unique_project_names)
    """
    if not access_token:
        raise ValueError("Valid OAuth access token is required to fetch PWA data.")

    site_url = MicrosoftOAuthService.get_pwa_url()

    # In development or mock mode, provide realistic sample data for target_year
    if access_token.startswith('mock_') or not site_url or site_url.startswith('<put'):
        logger.info("Generating mock PWA timesheet data for year %d.", target_year)
        daily_data_map = {
            f"{target_year}-03-10": [
                {"project": "Cloud Infrastructure Migration", "task": "Kubernetes Cluster Setup", "hours": 8.0},
            ],
            f"{target_year}-03-11": [
                {"project": "Cloud Infrastructure Migration", "task": "CI/CD Pipeline Automation", "hours": 7.0},
                {"project": "Internal Operations", "task": "Team Standup & Sync", "hours": 1.0},
            ],
            f"{target_year}-03-12": [
                {"project": "Mobile Banking Client", "task": "Biometric Authentication Module", "hours": 8.0},
            ],
            f"{target_year}-06-15": [
                {"project": "Mobile Banking Client", "task": "Security Audit Remediation", "hours": 6.5},
                {"project": "Internal Operations", "task": "Architecture Review", "hours": 1.5},
            ],
        }
        unique_projects = ["Cloud Infrastructure Migration", "Mobile Banking Client", "Internal Operations"]
        return daily_data_map, unique_projects

    headers = {
        'Accept': 'application/json;odata=verbose',
        'Authorization': f'Bearer {access_token}',
    }

    def get_pwa_data(url: str):
        try:
            resp = requests.get(url, headers=headers, verify=True, timeout=30)
            if resp.status_code == 200:
                return resp.json()
            logger.warning("PWA API request to %s returned status %d", url, resp.status_code)
            return None
        except Exception as err:
            logger.error("Error requesting PWA URL %s: %s", url, str(err))
            return None

    # Filter for target year
    filter_query = (
        f"$filter=End ge datetime'{target_year}-01-01T00:00:00' "
        f"and Start le datetime'{target_year}-12-31T23:59:59'"
        f"&$orderby=Start asc"
    )
    periods_url = f"{site_url}/_api/ProjectServer/TimeSheetPeriods?{filter_query}"
    data_periods = get_pwa_data(periods_url)

    daily_data_map = {}
    unique_projects = set()

    if data_periods and 'd' in data_periods:
        periods_list = data_periods['d'].get('results', [])
        for period in periods_list:
            p_id = period.get('Id')
            if not p_id:
                continue
            lines_url = f"{site_url}/_api/ProjectServer/TimeSheetPeriods('{p_id}')/TimeSheet/Lines?$expand=Work"
            data_lines = get_pwa_data(lines_url)

            if data_lines and 'd' in data_lines:
                lines = data_lines['d'].get('results', [])
                for line in lines:
                    proj_name = line.get('ProjectName', 'Unknown')
                    task_name = line.get('TaskName', 'Unknown')
                    unique_projects.add(proj_name)

                    daily_work_items = line.get('Work', {}).get('results', [])
                    for item in daily_work_items:
                        raw_work = item.get('ActualWork', 0)
                        day_date = item.get('Start', '').split('T')[0]

                        try:
                            if isinstance(raw_work, str):
                                hours = float(raw_work.lower().replace('h', '').replace(',', '.'))
                            else:
                                hours = float(raw_work)
                        except Exception:
                            hours = 0.0

                        if hours > 0 and day_date:
                            if day_date not in daily_data_map:
                                daily_data_map[day_date] = []
                            daily_data_map[day_date].append({
                                "project": proj_name,
                                "task": task_name,
                                "hours": hours,
                            })

    if daily_data_map:
        daily_data_map = dict(sorted(daily_data_map.items()))

    logger.info("Successfully fetched %d daily logs across %d projects from PWA for year %d.",
                len(daily_data_map), len(unique_projects), target_year)
    return daily_data_map, list(unique_projects)
