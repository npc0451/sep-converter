"""Small, shared SEP-only downloader used by both output formats."""
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import threading
import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests

ORIGIN = 'https://plato.stanford.edu'
USER_AGENT = 'SEPConverter/1.0 (personal reading; respects robots.txt)'
_lock = threading.RLock()
_last = -float('inf')
_cooldown = 0.0
_interval = 5.0
_robot = None
_blocked = False


def validate_url(url):
    parts, origin = urlsplit(url), urlsplit(ORIGIN)
    if parts.scheme not in ('http', 'https') or parts.netloc.lower() != origin.netloc or parts.username or parts.password:
        raise ValueError('Only Stanford SEP URLs are supported: ' + url)
    return parts._replace(scheme=origin.scheme, fragment='').geturl()


def _retry_after(value):
    try:
        return max(30, float(value))
    except (TypeError, ValueError):
        try:
            return max(30, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 30


def _request(url, timeout):
    global _last, _cooldown, _blocked
    if _blocked:
        raise RuntimeError('SEP returned 403; restart the converter after checking access.')
    delay = max(_last + _interval, _cooldown) - time.monotonic()
    if delay > 0:
        time.sleep(delay)
    _last = time.monotonic()
    response = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=timeout, allow_redirects=False)
    if response.status_code == 429:
        _cooldown = time.monotonic() + _retry_after(response.headers.get('Retry-After'))
    if response.status_code == 403:
        _blocked = True
    return response


def fetch(url, timeout=60):
    global _robot, _interval
    url = validate_url(url)
    with _lock:
        if _robot is None:
            response = _request(ORIGIN + '/robots.txt', timeout)
            response.raise_for_status()
            if response.is_redirect:
                raise RuntimeError('robots.txt redirected; cannot verify access rules.')
            text = response.text
            robot = RobotFileParser()
            robot.parse(text.splitlines())
            # SEP's delay can occur before the first User-agent group.
            preamble = text.lower().split('user-agent:', 1)[0]
            for line in preamble.splitlines():
                if line.strip().startswith('crawl-delay:'):
                    _interval = max(_interval, float(line.split(':', 1)[1].split('#')[0]))
            _interval = max(_interval, robot.crawl_delay(USER_AGENT) or 0)
            _robot = robot
        for _ in range(6):
            if not _robot.can_fetch(USER_AGENT, url):
                raise RuntimeError('robots.txt does not permit this resource: ' + url)
            response = _request(url, timeout)
            response.raise_for_status()
            if not response.is_redirect:
                return response
            location = response.headers.get('Location')
            if not location:
                raise RuntimeError('Redirect has no Location header')
            url = validate_url(urljoin(url, location))
        raise RuntimeError('Too many redirects')
