import asyncio, threading, aiohttp
from typing import Optional

class HttpClient:
    def __init__(self, app,  on_http_read_callback, log):
        self.app = app
        self.log = log
        self.on_http_read_callback = on_http_read_callback
        self.running = False
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._session: Optional[aiohttp.ClientSession] = None



    # === loop & session ===
    def _start_loop(self):
        if self.loop: return
        self.loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=lambda: (asyncio.set_event_loop(self.loop), self.loop.run_forever()),
            daemon=True
        )
        self._loop_thread.start()

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # === public api ===

    def connect(self, base_url: str, interval: int = 1):
        self.base_url = base_url.rstrip('/')
        self.interval = interval
        self.endpoints = {
            'drive': f'{self.base_url}/drive/stat',
            'mntr': f'{self.base_url}/mntr/stat',
            'dashboard': f'{self.base_url}/stat',
        }
        self.faultEndpoint = f'{self.base_url}/evt/lst'

    def start_continuous_read(self, interval: int | None = None) -> None:
        if interval is not None:
            self.interval = interval
        if self.running:
            self.log('⚠️ HTTP polling already running.')
            return
        self.running = True
        self._start_loop()
        asyncio.run_coroutine_threadsafe(self._poll_loop(), self.loop)

    def stop_continuous_read(self) -> None:
        if not self.running:
            self.log('⚠️ HTTP polling is not running.')
            return
        self.running = False
        fut = asyncio.run_coroutine_threadsafe(self._close(), self.loop)
        fut.result(timeout=3)
        self.log('⏹️ Async HTTP polling stopped.')

    async def read_fault_history(self) -> dict | None:
        session = await self._ensure_session()
        return await self._fetch(session, self.faultEndpoint)

    def read_fault_history_sync(self) -> dict | None:
        self._start_loop()
        fut = asyncio.run_coroutine_threadsafe(self.read_fault_history(), self.loop)
        return fut.result(timeout=5)

    async def _poll_loop(self) -> None:
        session = await self._ensure_session()
        while self.running:
            combined = {}
            for _, url in self.endpoints.items():
                data = await self._fetch(session, url)
                if isinstance(data, dict):
                    combined.update(data)
            if combined:
                self.on_http_read_callback(combined)
            await asyncio.sleep(self.interval)


    async def _fetch(self, session: aiohttp.ClientSession, url: str) -> dict | None:
        try:
            async with session.get(url, timeout=3) as response:
                if response.status == 200:
                    return await response.json()
                self.log(f'⚠️ HTTP {response.status} {url}')
        except Exception as e:
            self.log(f'❌ HTTP exception {url}: {e}')
        return None
