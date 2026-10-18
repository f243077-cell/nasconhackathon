"""Selenium Grid 4 fixtures (spec 6.2).

The browsers run in the grid's node containers, so they reach the API by its compose service name, not
localhost. Override with env vars when the grid runs on another laptop:
  GRID_URL  default http://localhost:4444   (the hub, as seen from the test runner)
  APP_URL   default http://api:8080         (the API, as seen from the browser nodes)
"""
import os

import pytest
from selenium import webdriver

GRID_URL = os.environ.get("GRID_URL", "http://localhost:4444")
APP_URL = os.environ.get("APP_URL", "http://api:8080").rstrip("/")

_OPTIONS = {"chrome": webdriver.ChromeOptions, "firefox": webdriver.FirefoxOptions}


@pytest.fixture
def driver(request):
    """A remote browser from the grid. Tests pick the browser with indirect parametrize, so a run of the
    suite uses both node types."""
    name = getattr(request, "param", "chrome")
    opts = _OPTIONS[name]()
    if name == "chrome":
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
    drv = webdriver.Remote(command_executor=GRID_URL, options=opts)
    drv.set_window_size(1280, 900)
    yield drv
    drv.quit()


@pytest.fixture
def app_url():
    return APP_URL
