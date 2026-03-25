#!/usr/bin/env python3
"""
Sociamonials API Client
Based on: https://github.com/turrbo/reverse-engineered-apis/tree/master/apis/marketing/sociamonials

Reverse-engineered client for posting to X/Twitter (and other platforms) via
Sociamonials. Authentication uses session-based cookies (PHPSESSID).

Key discovery: The post creation form (#f1) has 230+ fields. The AJAX publish
endpoint requires ALL of them via jQuery's $('#f1').serialize(). This client
loads the dashboard, parses all default form values, overrides the ones we
need, and submits the full payload.

Endpoints (discovered 2026-03-25):
  - Publish Now:  AJAX POST to /accounts/post_to_social_ajax.php
  - Queue/Schedule/Draft: Form POST to /accounts/social_media.php
  - Read posts:   POST to /accounts/grid_data.php
  - Heartbeat:    POST to /accounts/get_heartbit.php
"""

import os
import re
import sys
import json
import time
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlencode, quote
import requests
from bs4 import BeautifulSoup


class SociamonialAPI:
    """
    Client for creating and managing social media posts via Sociamonials.com.
    """

    TWITTER_ACCOUNT_ID = '17019'
    LINKEDIN_ACCOUNT_ID = '14029_0_0'
    PINTEREST_ACCOUNT_ID = '9313'

    def __init__(self, username: str = None, password: str = None,
                 base_url: str = "https://www.sociamonials.com"):
        self.username = username or os.getenv('SOCIAMONIALS_USERNAME', '')
        self.password = password or os.getenv('SOCIAMONIALS_PASSWORD', '')
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/javascript, */*; q=0.01',
            'Accept-Language': 'en-US,en;q=0.9',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': f'{self.base_url}/accounts/social_media.php'
        })
        self.user_id: Optional[str] = None
        self.user_hash: Optional[str] = None
        self.is_authenticated = False
        self._form_defaults: Optional[List[Tuple[str, str]]] = None

    # ---- Authentication ----

    def login(self) -> Dict[str, Any]:
        """Authenticate with Sociamonials via /password.php."""
        if not self.username or not self.password:
            raise ValueError("Credentials required. Set SOCIAMONIALS_USERNAME and SOCIAMONIALS_PASSWORD.")

        self.session.get(f"{self.base_url}/login.php")

        response = self.session.post(
            f"{self.base_url}/password.php",
            data={
                'username': self.username,
                'password': self.password,
                'remember': '1'
            },
            allow_redirects=True
        )

        try:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                result = result[0]

            if isinstance(result, dict):
                if result.get('res_status') == 'success' and result.get('login_status') == '1':
                    self.user_id = result.get('user_id')
                    self.user_hash = result.get('user_hash')
                    self.is_authenticated = True
                    return result
                else:
                    raise ValueError(f"Login failed: {result.get('error_msg', 'Unknown error')}")
            else:
                raise ValueError(f"Unexpected response format: {type(result)}")
        except json.JSONDecodeError:
            if 'PHPSESSID' in self.session.cookies:
                dash = self.session.get(f"{self.base_url}/accounts/social_media.php")
                if dash.status_code == 200:
                    self.is_authenticated = True
                    return {'status': 'success'}
            raise ValueError("Login failed: Invalid response")

    def _ensure_authenticated(self):
        if not self.is_authenticated:
            raise RuntimeError("Not authenticated. Call login() first.")

    def extend_session(self) -> Dict[str, Any]:
        """Send heartbeat to keep session alive."""
        self._ensure_authenticated()
        response = self.session.post(
            f"{self.base_url}/accounts/get_heartbit.php",
            data={'extend_session': '1'}
        )
        response.raise_for_status()
        try:
            return response.json()
        except json.JSONDecodeError:
            return {'status': 'ok', 'text': response.text}

    # ---- Post Reading ----

    def get_posts(self, page_name: str = 'pending_posts', status: int = 3,
                  search_type: str = 'message', start: int = 0,
                  length: int = 10, search_value: str = '') -> Dict[str, Any]:
        """Get posts from Sociamonials (queue, sent, drafts)."""
        self._ensure_authenticated()

        params = {
            'pageName': page_name,
            'status': status,
            'search_type': search_type,
            'sm_timeformat_id': '1'
        }

        dt_params = {
            'draw': '1',
            'start': start,
            'length': length,
            'search[value]': search_value,
            'search[regex]': 'false'
        }

        for i in range(8):
            dt_params[f'columns[{i}][data]'] = str(i)
            dt_params[f'columns[{i}][name]'] = ''
            dt_params[f'columns[{i}][searchable]'] = 'true'
            dt_params[f'columns[{i}][orderable]'] = 'true' if i == 7 else 'false'
            dt_params[f'columns[{i}][search][value]'] = ''
            dt_params[f'columns[{i}][search][regex]'] = 'false'

        dt_params['order[0][column]'] = '7'
        dt_params['order[0][dir]'] = 'desc'

        url = f"{self.base_url}/accounts/grid_data.php?{urlencode(params)}"
        response = self.session.post(url, data=dt_params)
        response.raise_for_status()

        try:
            return response.json()
        except json.JSONDecodeError:
            return {'draw': 1, 'recordsTotal': 0, 'recordsFiltered': 0, 'data': []}

    def get_queued_posts(self, start: int = 0, length: int = 10) -> Dict[str, Any]:
        return self.get_posts(page_name='pending_posts', status=3, start=start, length=length)

    def get_sent_posts(self, start: int = 0, length: int = 10) -> Dict[str, Any]:
        return self.get_posts(page_name='published_posts', status=1, start=start, length=length)

    def get_draft_posts(self, start: int = 0, length: int = 10) -> Dict[str, Any]:
        return self.get_posts(page_name='draft_posts', status=2, start=start, length=length)

    # ---- Dashboard Form Parsing ----

    def _load_form_defaults(self) -> List[Tuple[str, str]]:
        """
        Load the dashboard page and parse all form field defaults from #f1.
        Returns a list of (name, value) tuples, preserving order and duplicates.

        This replicates what jQuery's $('#f1').serialize() produces.
        jQuery.serialize() includes:
          - input[type=text/hidden/password], textarea, select (with current value)
          - input[type=checkbox/radio] ONLY if checked
          - Skips file inputs, buttons (submit/button/reset), disabled elements
        """
        self._ensure_authenticated()
        response = self.session.get(f"{self.base_url}/accounts/social_media.php")
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        form = soup.find('form', id='f1')
        if not form:
            raise RuntimeError("Could not find form #f1 on dashboard")

        fields = []
        for el in form.find_all(['input', 'textarea', 'select']):
            name = el.get('name', '')
            if not name:
                continue

            # Skip disabled elements (jQuery serialize skips them)
            if el.get('disabled') is not None:
                continue

            tag = el.name  # HTML tag name

            if tag == 'input':
                input_type = (el.get('type', 'text') or 'text').lower()

                # Skip file inputs and buttons
                if input_type in ('file', 'submit', 'button', 'reset', 'image'):
                    continue

                if input_type in ('checkbox', 'radio'):
                    # Only include if checked
                    if el.get('checked') is not None:
                        fields.append((name, el.get('value', 'on')))
                else:
                    fields.append((name, el.get('value', '')))

            elif tag == 'textarea':
                fields.append((name, el.string or ''))

            elif tag == 'select':
                # Get selected option value
                selected = el.find('option', selected=True)
                if selected:
                    fields.append((name, selected.get('value', selected.string or '')))
                else:
                    first = el.find('option')
                    if first:
                        fields.append((name, first.get('value', first.string or '')))
                    else:
                        fields.append((name, ''))

        return fields

    def _get_form_data(self, message: str, account_ids: List[str],
                       schedule_type: str = '1', publish_status: str = '1',
                       schedule_date: str = '', schedule_time_val: str = '') -> List[Tuple[str, str]]:
        """
        Get the full form data by loading defaults then overriding our values.
        Returns list of (name, value) tuples ready for serialization.
        """
        if self._form_defaults is None:
            self._form_defaults = self._load_form_defaults()

        # Start with all defaults
        fields = list(self._form_defaults)

        # Build override map
        tw_ids = [a for a in account_ids if a == self.TWITTER_ACCOUNT_ID]
        ln_ids = [a for a in account_ids if a == self.LINKEDIN_ACCOUNT_ID]
        pi_ids = [a for a in account_ids if a == self.PINTEREST_ACCOUNT_ID]

        msg_len = len(message)
        word_count = len(message.split())
        tw_remaining = 280 - msg_len

        overrides = {
            'message': message,
            'schedule_type': schedule_type,
            'publish_status': publish_status,
            'tw_selected_ids': ','.join(tw_ids),
            'ln_selected_ids': ','.join(ln_ids),
            'pi_selected_ids': ','.join(pi_ids),
            'in_selected_ids': '',
            'blsk_selected_ids': '',
            'thrd_selected_ids': '',
            'gmb_default_selected_ids': '',
            'tiktok_selected_ids': '',
            'yt_selected_ids': '',
            'fb_selected_ids': '',
            'tw_msg_count': str(msg_len),
            'wordcount': str(word_count),
            'total_length': str(msg_len),
            'remaining_length': str(tw_remaining),
            'publish_socialmedia': 'add',
            'edit_tw_message': message,
            'edit_fb_message': message,
            'edit_ln_message': message,
            'edit_in_message': message,
            'edit_pi_message': message,
            'edit_blsk_message': message,
            'edit_thrd_message': message,
            'edit_gmb_message': message,
            'edit_tiktok_message': message,
            'edit_yt_message': message,
            'upload_yt_title': message,
            'sm_tiktok_title_text': message,
            'sm_pin_title_text': message,
        }

        if schedule_date:
            overrides['publish_date'] = schedule_date
        if schedule_time_val:
            overrides['end_hours'] = schedule_time_val

        # Apply overrides: replace first occurrence of each field, or append if missing
        overridden = set()
        result = []

        for name, value in fields:
            if name in overrides and name not in overridden:
                result.append((name, overrides[name]))
                overridden.add(name)
            else:
                result.append((name, value))

        # Remove all select_accounts[] entries from defaults
        result = [(n, v) for n, v in result if n != 'select_accounts[]']

        # Add our account selections
        for aid in account_ids:
            result.append(('select_accounts[]', aid))

        # Add any overrides that weren't in the defaults
        for name, value in overrides.items():
            if name not in overridden:
                result.append((name, value))

        return result

    # ---- Post Creation ----

    def publish_now(self, message: str, account_ids: List[str] = None,
                    media_path: str = None) -> Dict[str, Any]:
        """
        Publish a post immediately via AJAX POST to post_to_social_ajax.php.

        Flow: schedule_type=1, publish_status=1
        AJAX: sm_ajax_publish_type=1&{serialized_form}
        Response: JSON array [{postid, network}]
        """
        self._ensure_authenticated()

        if account_ids is None:
            account_ids = [self.TWITTER_ACCOUNT_ID]

        form_fields = self._get_form_data(
            message=message,
            account_ids=account_ids,
            schedule_type='1',
            publish_status='1'
        )

        url = f"{self.base_url}/accounts/post_to_social_ajax.php"

        if media_path and os.path.exists(media_path):
            flat_data = [('sm_ajax_publish_type', '1')] + form_fields
            files = {
                'asset_image_social_network[]': (
                    os.path.basename(media_path),
                    open(media_path, 'rb'),
                    self._guess_mimetype(media_path)
                )
            }
            response = self.session.post(url, data=flat_data, files=files)
            files['asset_image_social_network[]'][1].close()
        else:
            # Build URL-encoded string like jQuery serialize
            parts = ['sm_ajax_publish_type=1']
            for name, value in form_fields:
                encoded_name = quote(name, safe='[]')
                encoded_value = quote(str(value), safe='')
                parts.append(f"{encoded_name}={encoded_value}")

            payload = '&'.join(parts)

            response = self.session.post(
                url,
                data=payload,
                headers={
                    **dict(self.session.headers),
                    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8'
                }
            )

        response.raise_for_status()

        try:
            result = response.json()
            if isinstance(result, list):
                return {
                    'status': 'success',
                    'posts': result,
                    'raw_response': result
                }
            return result
        except json.JSONDecodeError:
            return {'status': 'unknown', 'raw_response': response.text[:500]}

    def add_to_queue(self, message: str, account_ids: List[str] = None,
                     media_path: str = None) -> Dict[str, Any]:
        """
        Add a post to the publishing queue.
        Queue flow: schedule_type=5, publish_status=0
        """
        return self._form_post(
            message=message,
            account_ids=account_ids or [self.TWITTER_ACCOUNT_ID],
            schedule_type='5',
            publish_status='0',
            media_path=media_path
        )

    def schedule_post(self, message: str, schedule_date: str, schedule_time: str,
                      account_ids: List[str] = None,
                      media_path: str = None) -> Dict[str, Any]:
        """
        Schedule a post for a specific date/time.
        Schedule flow: schedule_type=2, publish_status=0
        """
        return self._form_post(
            message=message,
            account_ids=account_ids or [self.TWITTER_ACCOUNT_ID],
            schedule_type='2',
            publish_status='0',
            schedule_date=schedule_date,
            schedule_time_val=schedule_time,
            media_path=media_path
        )

    def save_draft(self, message: str, account_ids: List[str] = None,
                   media_path: str = None) -> Dict[str, Any]:
        """
        Save a post as draft.
        Draft flow: schedule_type=1, publish_status=0
        """
        return self._form_post(
            message=message,
            account_ids=account_ids or [self.TWITTER_ACCOUNT_ID],
            schedule_type='1',
            publish_status='0',
            media_path=media_path
        )

    def _form_post(self, message: str, account_ids: List[str],
                   schedule_type: str, publish_status: str,
                   schedule_date: str = '', schedule_time_val: str = '',
                   media_path: str = None) -> Dict[str, Any]:
        """
        Submit via standard form POST to /accounts/social_media.php.
        Used for queue, schedule, and draft flows.
        """
        self._ensure_authenticated()

        form_fields = self._get_form_data(
            message=message,
            account_ids=account_ids,
            schedule_type=schedule_type,
            publish_status=publish_status,
            schedule_date=schedule_date,
            schedule_time_val=schedule_time_val
        )

        url = f"{self.base_url}/accounts/social_media.php"

        files = None
        if media_path and os.path.exists(media_path):
            files = {
                'asset_image_social_network[]': (
                    os.path.basename(media_path),
                    open(media_path, 'rb'),
                    self._guess_mimetype(media_path)
                )
            }

        headers = dict(self.session.headers)
        headers.pop('X-Requested-With', None)
        headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'

        response = self.session.post(url, data=form_fields, files=files, headers=headers)

        if files:
            files['asset_image_social_network[]'][1].close()

        response.raise_for_status()

        if response.status_code == 200 and 'social_media.php' in response.url:
            return {
                'status': 'success',
                'message': f'Post submitted (schedule_type={schedule_type})',
                'redirect_url': response.url
            }

        try:
            return response.json()
        except (json.JSONDecodeError, ValueError):
            return {
                'status': 'submitted',
                'http_status': response.status_code,
                'raw_response': response.text[:500]
            }

    # ---- Convenience methods ----

    def post_to_twitter(self, message: str, schedule_time: str = None,
                        media_path: str = None) -> Dict[str, Any]:
        """
        Post to X/Twitter specifically.

        Args:
            message: Tweet text (max 280 chars)
            schedule_time: Optional ISO datetime for scheduling (e.g., '2026-03-25T10:00:00')
            media_path: Optional path to image/video
        """
        if len(message) > 280:
            raise ValueError(f"Tweet exceeds 280 chars ({len(message)} chars)")

        account_ids = [self.TWITTER_ACCOUNT_ID]

        if schedule_time:
            from datetime import datetime
            dt = datetime.fromisoformat(schedule_time)
            date_str = dt.strftime('%m/%d/%Y')
            time_str = dt.strftime('%I:%M %p')
            return self.schedule_post(
                message=message,
                schedule_date=date_str,
                schedule_time=time_str,
                account_ids=account_ids,
                media_path=media_path
            )
        else:
            return self.publish_now(
                message=message,
                account_ids=account_ids,
                media_path=media_path
            )

    @staticmethod
    def _guess_mimetype(path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        mimetypes = {
            '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png', '.gif': 'image/gif',
            '.webp': 'image/webp', '.mp4': 'video/mp4',
            '.mov': 'video/quicktime', '.avi': 'video/x-msvideo',
        }
        return mimetypes.get(ext, 'application/octet-stream')

    # ---- Utility ----

    def logout(self) -> bool:
        """Log out from Sociamonials."""
        if not self.is_authenticated:
            return True
        try:
            self.session.get(f"{self.base_url}/logout.php")
            self.is_authenticated = False
            self.user_id = None
            self.user_hash = None
            return True
        except Exception:
            return False


if __name__ == '__main__':
    username = os.getenv('SOCIAMONIALS_USERNAME')
    password = os.getenv('SOCIAMONIALS_PASSWORD')

    if not username or not password:
        print("Set SOCIAMONIALS_USERNAME and SOCIAMONIALS_PASSWORD environment variables")
        sys.exit(1)

    client = SociamonialAPI(username=username, password=password)
    result = client.login()
    print(f"Logged in. User ID: {client.user_id}")

    queued = client.get_queued_posts(length=3)
    print(f"Queued posts: {queued.get('recordsTotal', 0)}")

    sent = client.get_sent_posts(length=3)
    print(f"Sent posts: {sent.get('recordsTotal', 0)}")

    client.logout()
    print("Done.")
