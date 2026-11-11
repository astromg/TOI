"""NATS link between TOI and the guider service (ocabox-tcs ``guiding_svc.guider``), feeding :class:`GuiderTab`.

- Discovery: ``svc.status.guiding_svc.guider.>`` (last per subject, then new) -> ``details.metrics.guider`` of
  each service, by ``telescope_id``; the subjects of the pipeline come from there, nothing is hard-coded.
- The guider of the shown telescope: ``….pipeline.<pipe>.state`` (``PipelineState``), ``….events``,
  ``….journal`` and ``frame.thumbnail.ready``; the JPEG is fetched over HTTP from the thumbnail server
  (``toi.guider_thumbs_url`` + the path below ``toi.guider_thumbs_root``), only while the tab is visible and never
  more than one at a time (the latest wins).
- Commands: :meth:`GuiderLink.rpc` - core-NATS request to ``<rpc_root>.<cmd>``.
Interface: knowledge base, "Guider service - NATS interface".
"""

import asyncio
import datetime
import logging
import time
import urllib.request

from serverish.messenger import get_journalreader, get_reader, request

logger = logging.getLogger(__name__)

STATUS_SUBJECT = "svc.status.guiding_svc.guider.>"
THUMBS_URL = "http://192.168.7.45:8090/thumbs"         # thumbnail_svc.server na services01
THUMBS_ROOT = "/storage/poweruser/thumbs/guider"        # jego katalog /thumbs
RPC_TIMEOUT = 5         # s
JOURNAL_HISTORY = datetime.timedelta(minutes=15)    # dziennik po przelaczeniu: z ostatnich 15 min
HTTP_TIMEOUT = 5        # s
# zdarzenia, ktore idzie pokazac w dzienniku (reszta i tak ma swoja linie w journalu serwisu)
SHOWN_EVENTS = {"mode_changed": "info", "safety_demote": "warning", "acquired_lost": "warning",
                "reticle_refined": "info"}


class GuiderLink:
    def __init__(self, toi, tab):
        self.toi = toi
        self.tab = tab
        cfg = toi.local_cfg.get("toi", {}) if isinstance(toi.local_cfg, dict) else {}
        self.thumbs_url = str(cfg.get("guider_thumbs_url", THUMBS_URL)).rstrip("/")
        self.thumbs_root = str(cfg.get("guider_thumbs_root", THUMBS_ROOT)).rstrip("/")
        self.guiders = {}           # tel -> info (details.metrics.guider + status)
        self.tel = None             # teleskop pokazywany w zakladce
        self.followed = None        # (tel, subjects) - czytniki dzialaja dla tego
        self.tasks = []
        self.thumb_path = None      # najnowsza klatka do pobrania
        self.thumb_busy = False
        tab.link = self
        tab.rpc = self.rpc

    # --- discovery ---

    async def discovery_reader(self):
        try:
            r = get_reader(STATUS_SUBJECT, deliver_policy="last_per_subject")
            async for data, meta in r:
                try:
                    guider = data["details"]["metrics"]["guider"]
                    tel = guider["telescope_id"]
                    info = dict(guider)
                    info["status"] = data.get("status")
                    info["status_time"] = time.time()
                    info["runtime"] = data["details"].get("guider_runtime") or {}
                    self.guiders[tel] = info
                    self.tab.set_guiders(self.guiders)
                    self.follow(self.tel)       # nowe subjecty / guider sie pojawil
                except Exception as e:      # jedna zla wiadomosc nie konczy czytnika
                    logger.warning(f"GuiderLink: bad guider status skipped: {e!r}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"GuiderLink: discovery reader stopped: {e!r}")

    def pipeline(self, tel=None):
        info = self.guiders.get(self.tel if tel is None else tel) or {}
        pipes = info.get("pipelines") or []
        return pipes[0] if pipes else None

    # --- czytniki guidera pokazywanego teleskopu ---

    def follow(self, tel):
        """Read the guider of ``tel`` (None or no guider - nothing); restarts the readers when it changes."""
        self.tel = tel
        info = self.guiders.get(tel)
        pipe = self.pipeline(tel)
        key = None
        if info and pipe:
            key = (tel, tuple(sorted((pipe.get("subjects") or {}).items())), info.get("subjects", {}).get(
                "thumbnail_ready"))
        if key == self.followed:
            return
        for task in self.tasks:
            task.cancel()
        self.tasks = []
        self.followed = key
        self.thumb_path = None
        if key is None:
            return
        subjects = pipe["subjects"]
        coros = [self.state_reader(subjects["state"]), self.journal_reader(subjects["journal"]),
                 self.events_reader(subjects["events"])]
        if info.get("subjects", {}).get("thumbnail_ready"):
            coros.append(self.thumbnail_reader(info["subjects"]["thumbnail_ready"]))
        self.tasks = [asyncio.ensure_future(c) for c in coros]

    async def _read(self, name, reader, handle):
        try:
            async for data, meta in reader:
                try:
                    handle(data, meta)
                except Exception as e:      # jedna zla wiadomosc nie konczy czytnika
                    logger.warning(f"GuiderLink {name}: bad message skipped: {e!r}")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"GuiderLink {name} reader stopped: {e!r}")

    async def state_reader(self, subject):
        await self._read("state", get_reader(subject, deliver_policy="last"),
                         lambda data, meta: self.tab.show_state(data))

    async def journal_reader(self, subject):
        def handle(data, meta):
            level = getattr(data, "level", 20) or 20
            name = "error" if level >= 40 else "warning" if level >= 30 else "info"
            self.tab.add_journal(str(getattr(data, "message", data)), name, getattr(data, "timestamp", None))
        start = datetime.datetime.now(datetime.timezone.utc) - JOURNAL_HISTORY
        await self._read("journal", get_journalreader(subject, deliver_policy="by_start_time", opt_start_time=start),
                         handle)

    async def events_reader(self, subject):
        def handle(data, meta):
            event = data.get("event")
            if event in SHOWN_EVENTS:
                payload = data.get("payload") or {}
                if event == "mode_changed":
                    text = f"mode {payload.get('from')} → {payload.get('to')}"
                else:
                    text = f"{event} {payload or ''}"
                self.tab.add_journal(text, SHOWN_EVENTS[event], data.get("ts"))
        await self._read("events", get_reader(subject, deliver_policy="new"), handle)

    async def thumbnail_reader(self, subject):
        def handle(data, meta):
            self.thumb_path = (data.get("path"), data.get("dimensions"))
            if not self.thumb_busy:
                asyncio.ensure_future(self.fetch_thumbnails())
        await self._read("thumbnail", get_reader(subject, deliver_policy="last"), handle)

    def thumb_url(self, path):
        if path.startswith(self.thumbs_root + "/"):
            return self.thumbs_url + path[len(self.thumbs_root):]
        return None

    async def fetch_thumbnails(self):
        """Fetch the newest announced frame; frames that come in meanwhile are skipped (only the newest counts)."""
        self.thumb_busy = True
        try:
            while self.thumb_path:
                path, dims = self.thumb_path
                self.thumb_path = None
                if not self.tab.isVisible():        # nikt nie patrzy - nie ciagniemy ~0.4 MB co klatke
                    continue
                url = self.thumb_url(path or "")
                if url is None:
                    logger.warning(f"GuiderLink: thumbnail {path} outside {self.thumbs_root}")
                    continue
                try:
                    data = await asyncio.to_thread(self._get, url)
                except Exception as e:      # siec, 404 (plik zrotowany) - nastepna klatka
                    logger.info(f"GuiderLink: thumbnail {url}: {e!r}")
                    await asyncio.sleep(1)
                    continue
                self.tab.show_frame(data, dims)
        finally:
            self.thumb_busy = False

    @staticmethod
    def _get(url):
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as resp:
            return resp.read()

    # --- komendy ---

    async def rpc(self, cmd, data):
        """Command ``cmd`` to the pipeline of the shown guider -> reply data ``{status, result | error, detail}``."""
        pipe = self.pipeline()
        if pipe is None:
            raise RuntimeError("no guider")
        subject = f"{pipe['subjects']['rpc_root']}.{cmd}"
        resp, meta = await request(subject, data=data, timeout=RPC_TIMEOUT)
        return resp or {}
