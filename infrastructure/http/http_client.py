import asyncio
import threading
import aiohttp


class HttpClient:
    """
    Asynchronous HTTP client that polls configured endpoints and forwards a combined payload.
    """

    def __init__(self, app, base_url: str, interval: int = 5):
        """
        Initialize HttpClient.

        :param app: Application instance for logging and sending signals
        :param base_url: Base URL for HTTP API
        :param interval: Polling interval in seconds
        """
        self.app = app
        self.base_url = base_url.rstrip('/')
        self.interval = interval
        self.running = False
        self.loop = None

        # Configure the endpoints to poll
        self.endpoints = {
            'drive': f'{self.base_url}/drive/stat',
            'mntr': f'{self.base_url}/mntr/stat',
            'dashboard': f'{self.base_url}/stat'
        }

    def start_continuous_read(self, interval: int = None) -> None:
        """
        Start asynchronous polling of HTTP endpoints.

        :param interval: Optional override interval in seconds
        """
        if interval is not None:
            self.interval = interval

        if self.running:
            self.app._log('⚠️ HTTP polling already running.')
            return

        self.running = True
        # Create and start an asyncio loop in a new thread
        self.loop = asyncio.new_event_loop()
        thread = threading.Thread(target=self._run_loop, daemon=True)
        thread.start()
        self.app._log(f'🔁 Async HTTP polling started with interval {self.interval}s.')

    def stop_continuous_read(self) -> None:
        """
        Stop the asynchronous polling loop.
        """
        if not self.running:
            self.app._log('⚠️ HTTP polling is not running.')
            return

        self.running = False
        self.app._log('⏹️ Async HTTP polling stopped.')

    def _run_loop(self) -> None:
        """
        Internal method to set up and run the asyncio event loop.
        """
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._poll_loop())
        self.loop.close()

    async def _poll_loop(self) -> None:
        """
        Coroutine that polls all endpoints and sends a single combined payload.
        """
        async with aiohttp.ClientSession() as session:
            while self.running:
                combined_data = {}
                for name, url in self.endpoints.items():
                    data = await self._fetch(session, url)
                    if data is not None:
                        combined_data[name] = data
                if combined_data:
                    self._send_signal(combined_data)
                await asyncio.sleep(self.interval)

    async def _fetch(self, session: aiohttp.ClientSession, url: str) -> dict:
        """
        Perform an asynchronous GET request and return JSON response.

        :param session: aiohttp ClientSession
        :param url: Full URL to fetch
        :return: Parsed JSON data or None on error
        """
        try:
            async with session.get(url, timeout=3) as response:
                if response.status == 200:
                    return await response.json()
                self.app._log(f'⚠️ HTTP error {response.status} reading {url}')
        except Exception as e:
            self.app._log(f'❌ Async HTTP exception for {url}: {e}')
        return None

    def _send_signal(self, payload: dict) -> None:
        """
        Send a combined payload via the application's MQTT client.

        :param payload: Dictionary containing data from all endpoints
        """
        try:
            device_serial = self.app.serial_var.get().strip()
            gateway_id = self.app.gateway_cfg.get('gatewayId')
            organization_id = self.app.gateway_cfg.get('organizationId')

            topic_info = {
                'gateway_id': gateway_id,
                'organization_id': organization_id,
                'serial_number': device_serial
            }

            # Delegate to the application's gateway
            self.app.gateway.send_signal(topic_info, payload)
            self.app._log(f'📤 HTTP combined payload sent for serial {device_serial}')
        except Exception as e:
            self.app._log(f'❌ Error sending HTTP signal: {e}')
