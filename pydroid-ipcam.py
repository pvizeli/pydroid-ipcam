"""PyDroidIpCam api for android ipcam."""
import asyncio
import logging
import xml.etree.ElementTree as ET

import aiohttp
import async_timeout
import yarl

_LOGGER = logging.getLogger(__name__)

CONTENT_XML = 'xml'
CONTENT_JSON = 'json'

ALLOWED_ORIENTATIONS = [
    'landscape', 'upsidedown', 'portrait', 'upsidedown_portrait'
]


class IPWebcam(object):
    """The Android device running IP Webcam."""

    def __init__(self, loop, websession, host, port, username=None,
                 password=None, timeout=10):
        """Initialize the data oject."""
        self.loop = loop
        self.websession = websession
        self.status_data = None
        self.sensor_data = None
        self._host = host
        self._port = port
        self._auth = None
        self._timeout = None

        if username and password:
            self._auth = aiohttp.BasicAuth(username, password=password)

    @property
    def base_url(self):
        """Return the base url for endpoints."""
        return "http://{}:{}".format(self._host, self._port)

    @property
    def mjpeg_url(self):
        """Return mjpeg url."""
        return "{}/video".format(self.base_url)

    @property
    def image_url(self):
        """Return snapshot image url."""
        return "{}/photo.jpg".format(self.base_url)

    @asyncio.coroutine
    def _request(self, path, content=CONTENT_XML):
        """Make the actual request and return the parsed response."""
        url = '{}{}'.format(self.base_url, path)

        response = None
        data = None
        try:
            with async_timeout.timeout(self._timeout, loop=self.loop):
                response = yield from self.websession.get(url, auth=auth)

                if response.status == 200:
                    if content == CONTENT_XML:
                        data = yield from response.text()
                    elif content == CONTENT_JSON:
                        data = yield from response.json()

        except (asyncio.TimeoutError, aiohttp.errors.ClientError,
                aiohttp.errors.ClientDisconnectedError) as error:
            _LOGGER.error('Failed to communicate with IP Webcam: %s', error)
            return

        finally:
            if response is not None:
                yield from response.release()

        try:
            if CONTENT_XML == 'xml':
                return ET.fromstring(data)
            else:
                return data
        except (ET.ParseError, TypeError, AttributeError):
            _LOGGER.error("Received invalid response: %s", data)
            return

    @asyncio.coroutine
    def update(self):
        """Fetch the latest data from IP Webcam."""
        self.status_data = yield from self._request(
            '/status.json', content=CONTENT_JSON)

        self.sensor_data = yield from self._request(
            '/sensors.json', content=CONTENT_JSON)

    @property
    def enabled_sensors(self):
        """Return the enabled sensors."""
        return list(self.sensor_data.keys())

    @property
    def current_settings(self):
        """Return a dictionary of the current settings."""
        settings = {}
        if self.status_data is not None:
            for (key, val) in self.status_data.get('curvals', {}).items():
                try:
                    val = float(val)
                except ValueError:
                    val = val

                if val == 'on' or val == 'off':
                    val = (val == 'on')

                settings[key] = val
            return settings

    def change_setting(self, key, val):
        """Change a setting.

        Return a coroutine.
        """
        if isinstance(val, bool):
            payload = 'on' if val else 'off'
        else:
            payload = val
        return self._request('/settings/{}?set={}'.format(key, payload))

    def torch(self, activate=True):
        """Enable/disable the torch.

        Return a coroutine.
        """
        path = '/enabletorch' if activate else '/disabletorch'
        return self._request(path)

    def focus(self, activate=True):
        """Enable/disable camera focus.

        Return a coroutine.
        """
        path = '/focus' if activate else '/nofocus'
        return self._request(path)

    def record(self, record=True, tag=None):
        """Enable/disable recording.

        Return a coroutine.
        """
        path = '/startvideo?force=1' if record else '/stopvideo?force=1'
        if record and tag is not None:
            path = '/startvideo?force=1&tag={}'.format(quote(tag))
        return self._request(path, content=CONTENT_JSON)

    def set_front_facing_camera(self, activate=True):
        """Enable/disable the front-facing camera.

        Return a coroutine.
        """
        return self.change_setting('ffc', activate)

    def set_night_vision(self, activate=True):
        """Enable/disable night vision.

        Return a coroutine.
        """
        return self.change_setting('night_vision', activate)

    def set_overlay(self, activate=True):
        """Enable/disable the video overlay.

        Return a coroutine.
        """
        return self.change_setting('overlay', activate)

    def set_gps_active(self, activate=True):
        """Enable/disable GPS.

        Return a coroutine.
        """
        return self.change_setting('gps_active', activate)

    def set_quality(self, quality=100):
        """Set the video quality.

        Return a coroutine.
        """
        return self.change_setting('quality', quality)

    def set_orientation(self, orientation: str='landscape'):
        """Set the video orientation.

        Return a coroutine.
        """
        if orientation not in ALLOWED_ORIENTATIONS:
            _LOGGER.debug('%s is not a valid orientation', orientation)
            return False
        return self.change_setting('orientation', orientation)

    def set_zoom(self, zoom: int):
        """Set the zoom level.

        Return a coroutine.
        """
        return self._request('/settings/ptz?zoom={}'.format(zoom))
