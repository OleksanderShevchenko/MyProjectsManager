import os

import requests
from office365.runtime.auth.user_credential import UserCredential
from office365.sharepoint.client_context import ClientContext
from office365.runtime.http.request_options import RequestOptions


def fetch_pwa_data(email: str, password: str, target_year: int):
    """
    This function is using as service layer of the application -
     it responsible for fetching PWA data for a user per selected year
    """
    # get PWA url from settings
    site_url = os.getenv('PWA_URL')
    if not site_url:
        raise ValueError("PWA_URL is not set in environment variables.")

    # Authorize user connection with email and password
    try:
        ctx = ClientContext(site_url).with_credentials(UserCredential(email, password))
        ctx.web.get().execute_query()
    except Exception as e:
        raise ValueError(f"Authentication failed: {e}")

    def get_pwa_data(url):
        """
        This internal function proceed fetching time reports form PWA
        """
        try:
            request = RequestOptions(url)
            ctx.authentication_context.authenticate_request(request)
            headers = request.headers
            headers['Accept'] = 'application/json;odata=verbose'
            response = requests.get(url, headers=headers, verify=True)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception:
            return None

    # create filter for entire year
    filter_query = (
        f"$filter=End ge datetime'{target_year}-01-01T00:00:00' "
        f"and Start le datetime'{target_year}-12-31T23:59:59'"
        f"&$orderby=Start asc"
    )
    # create url for time periods
    periods_url = f"{site_url}/_api/ProjectServer/TimeSheetPeriods?{filter_query}"
    # fetch periods of the year
    data_periods = get_pwa_data(periods_url)
    # dictionary for daily data: key = "YYYY-MM-DD", value = [list of tasks]
    daily_data_map = {}
    unique_projects = set()

    if data_periods and 'd' in data_periods:
        periods_list = data_periods['d']['results']
        # for each period (week) fetch data
        for period in periods_list:
            p_id = period['Id']
            lines_url = f"{site_url}/_api/ProjectServer/TimeSheetPeriods('{p_id}')/TimeSheet/Lines?$expand=Work"
            data_lines = get_pwa_data(lines_url)

            if data_lines and 'd' in data_lines:
                lines = data_lines['d']['results']

                for line in lines:
                    proj_name = line.get('ProjectName', 'Unknown')
                    task_name = line.get('TaskName', 'Unknown')

                    unique_projects.add(proj_name)  # We collect unique projects

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

                        if hours > 0:
                            if day_date not in daily_data_map:
                                daily_data_map[day_date] = []

                            daily_data_map[day_date].append({
                                "project": proj_name,
                                "task": task_name,
                                "hours": hours
                            })
    if daily_data_map:
        # sort by date
        daily_data_map = dict(sorted(daily_data_map.items()))

    return daily_data_map, list(unique_projects)
