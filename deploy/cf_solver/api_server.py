import json
import os
import sys
import time
import uuid
import asyncio
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import JSONResponse
from loguru import logger
from camoufox import DefaultAddons
from camoufox.async_api import AsyncCamoufox
import uvicorn

# Kompatibilitas Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


class ClearanceAPIServer:
    """
    Solver gabungan:
      GET /turnstile   → Cloudflare Turnstile token
      GET /clearance   → cf_clearance cookie (bypass Cloudflare WAF)
      GET /aws-token   → aws-waf-token cookie (bypass AWS WAF)
    """

    HTML_TEMPLATE = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Boterdrop Solver</title>
        <script src="https://challenges.cloudflare.com/turnstile/v0/api.js?onload=onloadTurnstileCallback" async="" defer=""></script>
    </head>
    <body>
        <!-- cf turnstile -->
        <p id="ip-display"></p>
    </body>
    </html>
    """

    def __init__(self, headless: bool, thread: int, page_count: int,
                 proxy_support: bool, proxy_file: str = "proxies.txt",
                 cleanup_interval_minutes: int = 10):
        self.app = FastAPI()
        self.headless = headless
        self.thread_count = thread
        self.page_count = page_count
        self.proxy_support = proxy_support
        self.proxy_file = proxy_file
        self.cleanup_interval_minutes = cleanup_interval_minutes
        self.page_pool = asyncio.Queue()
        self.browser_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
        ]
        self.camoufox = None
        self.browser = None
        self.results = {}
        self.contexts = []  # Track semua context agar bisa di-restart dengan aman
        self.proxies = []
        self._proxy_index = 0
        self.max_task_num = self.thread_count * self.page_count

        self.app.on_event("startup")(self._startup)
        self.app.on_event("shutdown")(self._shutdown)
        self.app.get("/turnstile")(self.process_turnstile)
        self.app.get("/clearance")(self.process_clearance)
        self.app.get("/result")(self.get_result)
        self.app.get("/aws-token")(self.process_aws_token)
        self.app.get("/recaptchaV3")(self.process_recaptcha)
        self.app.post("/recaptchaV3")(self.process_recaptcha)

    # ──────────────────────────────────────────────
    #  PROXY
    # ──────────────────────────────────────────────

    def _load_proxies(self):
        if not self.proxy_support:
            return
        if not os.path.isfile(self.proxy_file):
            logger.warning(f"proxy_support aktif tapi file '{self.proxy_file}' tidak ditemukan.")
            return
        with open(self.proxy_file) as f:
            lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        self.proxies = lines
        logger.info(f"Memuat {len(self.proxies)} proxy dari '{self.proxy_file}'")

    def _next_proxy(self):
        if not self.proxies:
            return None
        proxy = self.proxies[self._proxy_index % len(self.proxies)]
        self._proxy_index += 1
        return proxy

    async def _create_context_with_proxy(self, proxy: str = None):
        if not proxy:
            return await self.browser.new_context()
        from urllib.parse import urlparse
        parsed = urlparse(proxy)
        if not parsed.scheme or not parsed.hostname:
            logger.warning(f"Format proxy tidak valid: {proxy}")
            return await self.browser.new_context()
        server = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
        if parsed.username and parsed.password:
            return await self.browser.new_context(
                proxy={"server": server, "username": parsed.username, "password": parsed.password}
            )
        return await self.browser.new_context(proxy={"server": server})

    # ──────────────────────────────────────────────
    #  BROWSER LIFECYCLE
    # ──────────────────────────────────────────────

    async def _startup(self):
        logger.info("Inisialisasi browser...")
        try:
            await self._initialize_browser()
        except Exception as e:
            logger.error(f"Inisialisasi gagal: {e}")
            raise

    async def _shutdown(self):
        logger.info("Menutup browser...")
        try:
            await self.browser.close()
        except Exception as e:
            logger.warning(f"Error saat menutup browser: {e}")
        logger.success("Browser berhasil ditutup")

    async def _initialize_browser(self):
        self._load_proxies()
        self.camoufox = AsyncCamoufox(
            headless=self.headless,
            exclude_addons=[DefaultAddons.UBO],
            args=self.browser_args
        )
        self.browser = await self.camoufox.start()
        await self._build_page_pool()
        logger.success(f"Pool siap: {self.page_pool.qsize()} halaman")
        asyncio.create_task(self._cleanup_results())
        asyncio.create_task(self._periodic_cleanup(self.cleanup_interval_minutes))

    async def _build_page_pool(self):
        """Buat/rebuild semua context dan page ke dalam pool."""
        self.contexts = []
        self._proxy_index = 0
        for _ in range(self.thread_count):
            proxy = self._next_proxy() if self.proxy_support else None
            context = await self._create_context_with_proxy(proxy)
            self.contexts.append(context)
            for _ in range(self.page_count):
                page = await context.new_page()
                await self.page_pool.put((page, context))

    async def _cleanup_results(self):
        """Bersihkan hasil (success/error) yang sudah > 10 menit belum diambil.
        Task yang masih berstatus 'process' TIDAK dihapus — cukup ditandai timeout
        jika sudah melewati 300 detik, agar client tetap mendapat respons yang benar.
        """
        while True:
            await asyncio.sleep(300)  # Cek setiap 5 menit
            now = time.time()
            to_delete = []
            to_timeout = []
            for tid, res in list(self.results.items()):
                if not isinstance(res, dict):
                    continue
                age = now - res.get("start_time", now)
                status = res.get("status", "")
                if status == "process":
                    # Jika task sudah terlalu lama dalam status process, tandai error
                    # agar client tidak menunggu selamanya — tapi JANGAN hapus dulu
                    if age > 300:
                        to_timeout.append(tid)
                else:
                    # Hapus hasil success/error yang sudah > 10 menit belum diambil
                    if age > 600:
                        to_delete.append(tid)
            for tid in to_timeout:
                if self.results.get(tid, {}).get("status") == "process":
                    start_t = self.results[tid].get("start_time", now)
                    self.results[tid] = {
                        "status": "error",
                        "elapsed_time": round(now - start_t, 3),
                        "value": "timeout",
                        "message": "Tugas timeout: tidak selesai dalam 300 detik",
                        "start_time": start_t,
                    }
            if to_timeout:
                logger.warning(f"[Cleanup] {len(to_timeout)} task ditandai timeout (process > 300s)")
            for tid in to_delete:
                self.results.pop(tid, None)
            if to_delete:
                logger.info(f"[Cleanup] Menghapus {len(to_delete)} hasil kedaluwarsa (> 10 menit) dari memori")

    async def _periodic_cleanup(self, interval_minutes: int = 10):
        """
        Periodic cleanup PAKSA yang membebaskan RAM:
        - Berjalan setiap interval_minutes menit (bisa diatur di config.json)
        - Tidak menunggu semua worker selesai — langsung paksa cleanup
        - Tunggu page yang sedang dipakai (max 60 detik), lalu full restart
        """
        DRAIN_TIMEOUT = 60  # Waktu tunggu max untuk page yang sedang dipakai (detik)

        while True:
            await asyncio.sleep(interval_minutes * 60)
            logger.info(f"[Cleanup] Memulai FORCED cleanup (interval: {interval_minutes} menit)...")

            # Fase 1: Drain semua page dari pool secara non-blocking
            collected = []
            try:
                while True:
                    item = self.page_pool.get_nowait()
                    collected.append(item)
            except asyncio.QueueEmpty:
                pass

            busy_count = self.max_task_num - len(collected)

            if busy_count > 0:
                # Ada page yang sedang dipakai, tunggu mereka selesai (max DRAIN_TIMEOUT)
                logger.info(f"[Cleanup] Menunggu {busy_count} page yang sedang dipakai (max {DRAIN_TIMEOUT}s)...")
                deadline = time.time() + DRAIN_TIMEOUT
                while len(collected) < self.max_task_num and time.time() < deadline:
                    try:
                        remaining = deadline - time.time()
                        if remaining <= 0:
                            break
                        item = await asyncio.wait_for(
                            self.page_pool.get(), timeout=remaining
                        )
                        collected.append(item)
                    except asyncio.TimeoutError:
                        break

                still_busy = self.max_task_num - len(collected)
                if still_busy > 0:
                    logger.warning(f"[Cleanup] {still_busy} page masih dipakai setelah timeout, paksa restart tanpa mereka")

            logger.info(f"[Cleanup] Full context restart dimulai ({len(collected)}/{self.max_task_num} page terkumpul)...")

            # ── KRITIS: Invalidasi context SEBELUM close ──
            # Simpan referensi lama, lalu kosongkan self.contexts SEGERA
            # Agar worker yang selesai saat close TIDAK mengembalikan page mati ke pool
            old_contexts = list(self.contexts)
            self.contexts = []

            # Fase 2: Tutup semua page yang berhasil dikumpulkan
            for page, _ in collected:
                try:
                    await page.close()
                except Exception:
                    pass

            # Fase 3: Tutup semua context lama (ini yang bebaskan RAM Firefox)
            for context in old_contexts:
                try:
                    await context.close()
                except Exception:
                    pass

            # Fase 3.5: Buang dan TUTUP page mati yang masuk pool selama proses close
            # (dari worker yang selesai SEBELUM self.contexts dikosongkan di atas)
            stale = []
            try:
                while True:
                    stale.append(self.page_pool.get_nowait())
            except asyncio.QueueEmpty:
                pass
            if stale:
                logger.info(f"[Cleanup] Menutup {len(stale)} stale page dari pool")
                for stale_page, _ in stale:
                    try:
                        await stale_page.close()
                    except Exception:
                        pass

            # Fase 4: Recreate semua context dan page baru
            try:
                await self._build_page_pool()
                logger.success(f"[Cleanup] Full context restart selesai, {self.page_pool.qsize()} halaman siap")
            except Exception as e:
                logger.error(f"[Cleanup] Gagal rebuild pool: {e}, mencoba restart browser...")
                try:
                    try:
                        await self.browser.close()
                    except Exception:
                        pass
                    self.browser = await self.camoufox.start()
                    await self._build_page_pool()
                    logger.success(f"[Cleanup] Browser restart berhasil, {self.page_pool.qsize()} halaman siap")
                except Exception as e2:
                    logger.error(f"[Cleanup] FATAL: Gagal restart browser: {e2}")

    # ──────────────────────────────────────────────
    #  TURNSTILE SOLVER
    # ──────────────────────────────────────────────

    async def _save_debug_on_fail(self, page, task_id: str, round_num: int, url: str):
        """Simpan screenshot + HTML + info halaman ke debug_logs/ saat gagal."""
        try:
            debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_logs")
            os.makedirs(debug_dir, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            prefix = os.path.join(debug_dir, f"{ts}_{task_id[:8]}_r{round_num}")

            # Screenshot
            try:
                await page.screenshot(path=f"{prefix}.png", full_page=True)
            except Exception as e:
                logger.debug(f"[Debug] Gagal screenshot: {e}")

            # Info halaman
            info = {}
            try:
                info["title"] = await page.title()
            except Exception:
                info["title"] = "N/A"
            try:
                info["url"] = page.url
            except Exception:
                info["url"] = "N/A"
            try:
                info["turnstile_widget_exists"] = await page.locator("//div[@class='cf-turnstile']").count() > 0
            except Exception:
                info["turnstile_widget_exists"] = "N/A"
            try:
                info["cf_response_value"] = await page.input_value("[name=cf-turnstile-response]", timeout=500)
            except Exception:
                info["cf_response_value"] = "not found"
            try:
                info["js_errors"] = await page.evaluate(
                    "() => window.__debugErrors || []"
                )
            except Exception:
                info["js_errors"] = []
            try:
                info["html_snippet"] = await page.inner_html("body")
            except Exception:
                info["html_snippet"] = "N/A"

            info["task_id"] = task_id
            info["target_url"] = url
            info["round"] = round_num
            info["timestamp"] = ts

            with open(f"{prefix}.json", "w", encoding="utf-8") as f:
                json.dump(info, f, indent=2, ensure_ascii=False)

            logger.info(f"[Debug] Disimpan: {prefix}.png + .json")
        except Exception as e:
            logger.warning(f"[Debug] Gagal simpan debug: {e}")

    async def _solve_turnstile(self, task_id: str, url: str, sitekey: str,
                                action: str = None, cdata: str = None, proxy: str = None):
        start_time = time.time()
        if proxy:
            # 指定代理：建独立代理上下文（不复用全局 page_pool 的直连 context，用完关闭）
            logger.info(f"[Turnstile] Menggunakan proxy eksplisit: {proxy} — {task_id}")
            try:
                context = await self._create_context_with_proxy(proxy)
            except Exception as e:
                self.results[task_id] = {"status": "error", "elapsed_time": 0,
                                         "value": "captcha_fail"}
                logger.error(f"[Turnstile] Gagal buat context proxy {proxy}: {e} — {task_id}")
                return
            page = await context.new_page()
        else:
            page, context = await self.page_pool.get()
        try:
            url_with_slash = url if url.endswith("/") else url + "/"
            turnstile_div = (
                f'<div class="cf-turnstile" style="background:white;" data-sitekey="{sitekey}"'
                + (f' data-action="{action}"' if action else "")
                + (f' data-cdata="{cdata}"' if cdata else "")
                + "></div>"
            )
            page_data = self.HTML_TEMPLATE.replace("<!-- cf turnstile -->", turnstile_div)

            MAX_ROUNDS = 2
            for round_num in range(1, MAX_ROUNDS + 1):
                if round_num > 1:
                    logger.info(f"[Turnstile] Putaran {round_num}: reload halaman — {task_id}")
                    if proxy is None and self.proxy_support and self.proxies:
                        proxy = self._next_proxy()
                        try:
                            new_context = await self._create_context_with_proxy(proxy)
                            new_page = await new_context.new_page()
                            try:
                                await page.close()
                            except Exception:
                                pass
                            try:
                                await context.close()
                            except Exception:
                                pass
                            page, context = new_page, new_context
                            logger.info(f"[Turnstile] Proxy diganti: {proxy} — {task_id}")
                        except Exception as e:
                            logger.warning(f"[Turnstile] Gagal ganti proxy: {e}, tetap pakai context lama")

                # Pasang error listener JS untuk debug
                try:
                    await page.evaluate("() => { window.__debugErrors = []; window.onerror = (m,s,l,c,e) => { window.__debugErrors.push({msg:m,src:s,line:l,col:c}); }; }")
                except Exception:
                    pass

                try:
                    await page.unroute_all()
                except Exception:
                    pass
                await page.route(url_with_slash, lambda route: route.fulfill(body=page_data, status=200))
                await page.goto(url_with_slash)
                await page.eval_on_selector("//div[@class='cf-turnstile']", "el => el.style.width = '70px'")

                solved = False
                for attempt in range(80):  # 80 × 0.3s = ~24 detik timeout
                    try:
                        value = await page.input_value("[name=cf-turnstile-response]", timeout=400)
                        if value == "":
                            await page.locator("//div[@class='cf-turnstile']").click(timeout=400)
                            await asyncio.sleep(0.3)
                        else:
                            elapsed = round(time.time() - start_time, 3)
                            self.results[task_id] = {"status": "success", "elapsed_time": elapsed, "value": value}
                            logger.info(f"[Turnstile] Sukses (putaran {round_num}) — {task_id} ({elapsed}s)")
                            solved = True
                            return
                    except Exception as e:
                        logger.debug(f"[Turnstile] Putaran {round_num} percobaan {attempt + 1} gagal: {e}")

                if not solved:
                    logger.warning(f"[Turnstile] Putaran {round_num} gagal 30x — {task_id}, {'retry...' if round_num < MAX_ROUNDS else 'menyerah'}")
                    # Simpan debug info di setiap putaran yang gagal
                    await self._save_debug_on_fail(page, task_id, round_num, url_with_slash)

            elapsed = round(time.time() - start_time, 3)
            self.results[task_id] = {"status": "error", "elapsed_time": elapsed, "value": "captcha_fail"}
            logger.warning(f"[Turnstile] Gagal setelah {MAX_ROUNDS} putaran — {task_id}")
        except Exception as e:
            elapsed = round(time.time() - start_time, 3)
            self.results[task_id] = {"status": "error", "elapsed_time": elapsed, "value": "captcha_fail"}
            logger.error(f"[Turnstile] Exception — {task_id}: {e}")
        finally:
            try:
                await page.unroute_all()
            except Exception:
                pass
            if proxy:
                # 独立代理上下文：用完直接关闭（不归还全局池）
                try:
                    await context.close()
                except Exception:
                    pass
                logger.info(f"[Turnstile] Proxy context ditutup — {task_id}")
            elif context in self.contexts:
                await self.page_pool.put((page, context))
            else:
                logger.info(f"[Turnstile] Page dibuang (context sudah di-restart oleh cleanup) — {task_id}")


    # ──────────────────────────────────────────────
    #  CF_CLEARANCE SOLVER
    # ──────────────────────────────────────────────

    async def _solve_clearance(self, task_id: str, url: str, timeout: int = 30):
        """
        Navigasikan browser ke URL target, tunggu Cloudflare challenge selesai,
        lalu ambil cookie cf_clearance dan User-Agent.
        """
        start_time = time.time()
        page, context = await self.page_pool.get()
        try:
            user_agent = await page.evaluate("navigator.userAgent")

            logger.info(f"[Clearance] Navigasi ke {url} — {task_id}")
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)

            # Tunggu Cloudflare challenge selesai
            # Indikator: judul halaman bukan "Just a moment..." dan ada cookie CF
            deadline = time.time() + timeout
            cf_clearance = None
            cf_cookie_names = ["cf_clearance", "__cf_bm", "_cfuvid", "cf_chl_rc", "cf_chl_prog"]
            while time.time() < deadline:
                title = await page.title()
                cookies = await context.cookies()
                # 检测多种 CF cookie
                cf_cookie = None
                for name in cf_cookie_names:
                    cf_cookie = next((c for c in cookies if c["name"] == name), None)
                    if cf_cookie:
                        break

                # 如果页面标题不是 "Just a moment" 且有 CF cookie，认为已通过
                if cf_cookie and "just a moment" not in title.lower():
                    cf_clearance = cf_cookie["value"]
                    break

                # 如果页面标题已经是正常页面（如 "ChatGPT"），也认为已通过
                if "just a moment" not in title.lower() and "checking" not in title.lower() and "verify" not in title.lower():
                    # 收集所有 cookie
                    all_cookies = await context.cookies()
                    cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in all_cookies)
                    self.results[task_id] = {
                        "status": "success",
                        "elapsed_time": round(time.time() - start_time, 3),
                        "cf_clearance": cf_clearance or "",
                        "user_agent": user_agent,
                        "cookies": cookie_header,
                    }
                    logger.success(f"[Clearance] Sukses (page title OK) — {task_id}")
                    return

                await asyncio.sleep(1)

            elapsed = round(time.time() - start_time, 3)

            if cf_clearance:
                # Kumpulkan semua cookies dari domain
                all_cookies = await context.cookies()
                cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in all_cookies)
                self.results[task_id] = {
                    "status": "success",
                    "elapsed_time": elapsed,
                    "cf_clearance": cf_clearance,
                    "user_agent": user_agent,
                    "cookies": cookie_header,
                }
                logger.success(f"[Clearance] Sukses — {task_id} ({elapsed}s)")
            else:
                title = await page.title()
                self.results[task_id] = {
                    "status": "error",
                    "elapsed_time": elapsed,
                    "value": "clearance_fail",
                    "message": f"cf_clearance tidak ditemukan setelah {timeout}s. Judul halaman: '{title}'",
                }
                logger.warning(f"[Clearance] Gagal — {task_id}")

        except Exception as e:
            elapsed = round(time.time() - start_time, 3)
            self.results[task_id] = {"status": "error", "elapsed_time": elapsed, "value": str(e)}
            logger.error(f"[Clearance] Exception — {task_id}: {e}")
        finally:
            # Reset halaman & bersihkan cookies agar tidak membawa state lama
            try:
                await context.clear_cookies()
            except Exception:
                pass
            try:
                await page.goto("about:blank")
            except Exception:
                pass
            # Hanya kembalikan ke pool jika context masih valid (belum di-restart cleanup)
            if context in self.contexts:
                await self.page_pool.put((page, context))
            else:
                logger.info(f"[Clearance] Page dibuang (context sudah di-restart oleh cleanup) — {task_id}")

    # ──────────────────────────────────────────────
    #  AWS WAF TOKEN SOLVER
    # ──────────────────────────────────────────────

    # ── Judul/pesan yang dikeluarkan CloudFront saat IP di-block ──
    _CLOUDFRONT_BLOCK_TITLES = [
        "error: the request could not be satisfied",
        "403 forbidden",
        "access denied",
        "request blocked",
    ]

    def _is_cloudfront_blocked(self, title: str) -> bool:
        t = title.lower().strip()
        return any(kw in t for kw in self._CLOUDFRONT_BLOCK_TITLES)

    async def _solve_aws_token(self, task_id: str, url: str, timeout: int = 30):
        """
        Navigasi browser ke URL target, tunggu aws-waf-token cookie muncul,
        lalu return cookies + user-agent.
        Jika IP diblok CloudFront, otomatis retry dengan proxy (jika tersedia).
        """
        start_time = time.time()
        page, context = await self.page_pool.get()
        _temp_context = None  # context sementara untuk retry proxy

        async def _navigate_and_poll(p, ctx, attempt_label: str):
            """Navigasi, poll cookies, kembalikan (waf_cookie, title, final_url, status, poll_count)."""
            response_status = None
            final_url = url
            try:
                remaining_timeout = max(5, int(timeout - (time.time() - start_time))) * 1000
                resp = await p.goto(url, wait_until="domcontentloaded", timeout=remaining_timeout)
                response_status = resp.status if resp else None
                final_url = p.url
                logger.debug(f"[AWS-Token][{attempt_label}] HTTP {response_status} | URL: {final_url}")
            except Exception as nav_err:
                logger.debug(f"[AWS-Token][{attempt_label}] goto() error: {nav_err}")

            try:
                title_now = await p.title()
                logger.debug(f"[AWS-Token][{attempt_label}] Judul: '{title_now}'")
                if self._is_cloudfront_blocked(title_now):
                    logger.warning(f"[AWS-Token][{attempt_label}] 🚫 CLOUDFRONT BLOCK TERDETEKSI: '{title_now}'")
                    return None, title_now, final_url, response_status, 0, True
            except Exception:
                title_now = ""

            # Poll
            deadline_poll = time.time() + max(1, timeout - (time.time() - start_time))
            waf_cookie = None
            poll_count = 0
            while time.time() < deadline_poll:
                poll_count += 1
                cookies = await ctx.cookies()
                cookie_names = [c["name"] for c in cookies]
                logger.debug(f"[AWS-Token][{attempt_label}] Poll #{poll_count} | Cookies: {cookie_names}")

                waf_cookie = next((c for c in cookies if c["name"] == "aws-waf-token"), None)
                if waf_cookie:
                    logger.debug(f"[AWS-Token][{attempt_label}] [OK] aws-waf-token ditemukan di poll #{poll_count}")
                    break

                # Cek judul tiap 5 detik (bisa jadi halaman di-redirect ke block page)
                if poll_count % 5 == 0:
                    try:
                        cur_title = await p.title()
                        cur_url = p.url
                        logger.debug(f"[AWS-Token][{attempt_label}] [5s] Judul: '{cur_title}' | URL: {cur_url}")
                        if self._is_cloudfront_blocked(cur_title):
                            logger.warning(f"[AWS-Token][{attempt_label}] 🚫 Block terdeteksi saat polling: '{cur_title}'")
                            return None, cur_title, cur_url, response_status, poll_count, True
                    except Exception:
                        pass

                await asyncio.sleep(1)

            try:
                final_title = await p.title()
            except Exception:
                final_title = title_now

            return waf_cookie, final_title, final_url, response_status, poll_count, False

        try:
            logger.info(f"[AWS-Token] Navigasi ke {url} — {task_id}")
            logger.debug(f"[AWS-Token] Timeout: {timeout}s | proxy_support: {self.proxy_support} | proxies: {len(self.proxies)}")

            # ── Attempt 1: tanpa proxy (dari pool) ──
            waf_cookie, title, final_url, http_status, polls, was_blocked = await _navigate_and_poll(page, context, "no-proxy")

            # ── Jika diblok CloudFront, coba ulang dengan proxy ──
            if was_blocked or (not waf_cookie):
                if was_blocked:
                    logger.warning(f"[AWS-Token] IP VPS diblok CloudFront. Mencoba proxy... ({len(self.proxies)} tersedia)")

                if self.proxies:
                    proxy_str = self._next_proxy()
                    logger.info(f"[AWS-Token] Retry dengan proxy: {proxy_str}")
                    try:
                        _temp_context = await self._create_context_with_proxy(proxy_str)
                        proxy_page = await _temp_context.new_page()
                        try:
                            w2, t2, u2, s2, p2, b2 = await _navigate_and_poll(proxy_page, _temp_context, f"proxy:{proxy_str}")
                            if w2:
                                waf_cookie, title, final_url, http_status, polls = w2, t2, u2, s2, p2
                                logger.info(f"[AWS-Token] [OK] Proxy berhasil bypass CloudFront block")
                            else:
                                logger.warning(f"[AWS-Token] Proxy juga gagal. Judul: '{t2}' | blocked: {b2}")
                        finally:
                            try:
                                await proxy_page.close()
                            except Exception:
                                pass
                    except Exception as proxy_err:
                        logger.error(f"[AWS-Token] Gagal buat context proxy: {proxy_err}")
                        logger.debug(f"[AWS-Token] Proxy error detail: {type(proxy_err).__name__}: {proxy_err}")
                else:
                    if was_blocked:
                        logger.error(
                            "[AWS-Token] 🚫 IP VPS diblok CloudFront dan tidak ada proxy tersedia!\n"
                            "         → Aktifkan proxy_support=true di config.json dan isi proxies.txt"
                        )

            elapsed = round(time.time() - start_time, 3)

            if waf_cookie:
                # Ambil cookies dari context yang sukses
                try:
                    all_cookies = await context.cookies() if not _temp_context else await _temp_context.cookies()
                except Exception:
                    all_cookies = []
                cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in all_cookies)
                try:
                    user_agent = await page.evaluate("navigator.userAgent")
                except Exception:
                    user_agent = "unknown"
                logger.debug(f"[AWS-Token] User-Agent: {user_agent}")
                self.results[task_id] = {
                    "status": "success",
                    "elapsed_time": elapsed,
                    "aws_waf_token": waf_cookie["value"],
                    "cookies": cookie_header,
                    "user_agent": user_agent,
                }
                logger.success(f"[AWS-Token] Sukses — {task_id} ({elapsed}s)")
            else:
                # ── Diagnosis lengkap saat gagal ──
                try:
                    fail_title = title
                    fail_url = final_url
                    cookie_dump = {}
                    try:
                        remaining_cookies = await context.cookies()
                        cookie_dump = {c["name"]: c["value"][:40] for c in remaining_cookies}
                    except Exception:
                        pass

                    logger.warning(f"[AWS-Token] Gagal — {task_id} | Judul: '{fail_title}' | URL: {fail_url}")
                    logger.debug(f"[AWS-Token] Total polls: {polls} | elapsed: {elapsed}s | HTTP: {http_status}")
                    logger.debug(f"[AWS-Token] Cookies saat gagal: {cookie_dump}")

                    # Screenshot
                    try:
                        debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debug_logs")
                        os.makedirs(debug_dir, exist_ok=True)
                        ts = time.strftime("%Y%m%d_%H%M%S")
                        shot_path = os.path.join(debug_dir, f"{ts}_{task_id[:8]}_aws_fail.png")
                        await page.screenshot(path=shot_path, full_page=True)
                        logger.debug(f"[AWS-Token] Screenshot: {shot_path}")
                    except Exception as ss_err:
                        logger.debug(f"[AWS-Token] Gagal screenshot: {ss_err}")

                    block_note = " (IP diblok CloudFront — gunakan proxy!)" if was_blocked else ""
                    self.results[task_id] = {
                        "status": "error",
                        "elapsed_time": elapsed,
                        "value": "waf_fail",
                        "message": (
                            f"aws-waf-token tidak ditemukan setelah {elapsed}s "
                            f"({polls} polls). HTTP {http_status}. "
                            f"Judul: '{fail_title}'{block_note}"
                        ),
                    }
                except Exception as diag_err:
                    logger.debug(f"[AWS-Token] Gagal diagnosis: {diag_err}")
                    self.results[task_id] = {
                        "status": "error",
                        "elapsed_time": elapsed,
                        "value": "waf_fail",
                        "message": f"aws-waf-token tidak ditemukan setelah {timeout}s",
                    }

        except Exception as e:
            elapsed = round(time.time() - start_time, 3)
            self.results[task_id] = {"status": "error", "elapsed_time": elapsed, "value": str(e)}
            logger.error(f"[AWS-Token] Exception — {task_id}: {e}")
            logger.debug(f"[AWS-Token] {type(e).__name__}: {e}")
        finally:
            # Tutup context proxy sementara jika ada
            if _temp_context is not None:
                try:
                    await _temp_context.close()
                except Exception:
                    pass
            try:
                await context.clear_cookies()
            except Exception:
                pass
            try:
                await page.goto("about:blank")
            except Exception:
                pass
            if context in self.contexts:
                await self.page_pool.put((page, context))
            else:
                logger.info(f"[AWS-Token] Page dibuang (context sudah di-restart) — {task_id}")


    # ──────────────────────────────────────────────
    #  RECAPTCHA V3 SOLVER
    # ──────────────────────────────────────────────

    async def _solve_recaptcha(self, task_id: str, url: str, sitekey: str, action: str):
        start_time = time.time()
        browser = None
        playwright = None
        try:
            from playwright.async_api import async_playwright
            playwright = await async_playwright().start()
            
            # Setup proxy jika proxy_support aktif
            proxy_args = None
            if self.proxy_support and self.proxies:
                proxy_str = self._next_proxy()
                if proxy_str:
                    from urllib.parse import urlparse
                    parsed = urlparse(proxy_str)
                    if parsed.scheme and parsed.hostname:
                        server = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"
                        if parsed.username and parsed.password:
                            proxy_args = {"server": server, "username": parsed.username, "password": parsed.password}
                        else:
                            proxy_args = {"server": server}

            logger.info(f"[reCAPTCHA] Menyiapkan browser Chromium — {task_id}")
            browser = await playwright.chromium.launch(
                headless=self.headless,
                args=self.browser_args + ["--disable-gpu", "--disable-dev-shm-usage"]
            )
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 720},
                proxy=proxy_args
            )
            page = await context.new_page()

            # Intersepsi request (blokir gambar, media, font)
            async def block_resources(route):
                req_type = route.request.resource_type
                if req_type in ["image", "media", "font"]:
                    try:
                        await route.abort()
                    except Exception:
                        pass
                else:
                    try:
                        await route.continue_()
                    except Exception:
                        pass

            await page.route("**/*", block_resources)

            logger.info(f"[reCAPTCHA] Membuka URL: {url} — {task_id}")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            logger.info(f"[reCAPTCHA] Memeriksa keberadaan script reCAPTCHA di halaman — {task_id}")
            
            has_recaptcha = False
            try:
                await page.wait_for_function("""() => {
                    return typeof grecaptcha !== 'undefined' && typeof grecaptcha.execute === 'function';
                }""", timeout=15000)
                has_recaptcha = True
            except Exception:
                pass

            if not has_recaptcha:
                logger.info(f"[reCAPTCHA] Script tidak terdeteksi, menyuntikkan script api.js secara manual — {task_id}")
                inject_js = """(key) => {
                    return new Promise((res, rej) => {
                        const s = document.createElement('script');
                        s.src = 'https://www.google.com/recaptcha/api.js?render=' + key;
                        s.onload = () => {
                            const i = setInterval(() => {
                                if (typeof grecaptcha !== 'undefined' && typeof grecaptcha.execute === 'function') {
                                    clearInterval(i);
                                    res(true);
                                }
                            }, 100);
                            setTimeout(() => { clearInterval(i); rej(new Error("Timeout menyuntikkan script Google reCAPTCHA")); }, 10000);
                        };
                        s.onerror = () => rej(new Error("Gagal memuat script Google reCAPTCHA"));
                        document.head.appendChild(s);
                    });
                }"""
                await page.evaluate(inject_js, sitekey)
                logger.info(f"[reCAPTCHA] Script berhasil disuntikkan secara manual — {task_id}")
            else:
                logger.info(f"[reCAPTCHA] Script sudah terdeteksi di halaman — {task_id}")

            logger.info(f"[reCAPTCHA] Mengeksekusi grecaptcha.execute (Action: '{action}') — {task_id}")
            solve_js = """([key, act]) => {
                return new Promise((res, rej) => {
                    grecaptcha.ready(() => {
                        grecaptcha.execute(key, { action: act })
                            .then(res)
                            .catch(err => rej(new Error(err.message || "Gagal mendapatkan token")));
                    });
                });
            }"""
            token = await page.evaluate(solve_js, [sitekey, action])

            elapsed = round(time.time() - start_time, 3)
            self.results[task_id] = {"status": "success", "elapsed_time": elapsed, "value": token}
            logger.success(f"[reCAPTCHA] Sukses memecahkan — {task_id} ({elapsed}s)")

        except Exception as e:
            elapsed = round(time.time() - start_time, 3)
            self.results[task_id] = {
                "status": "error",
                "elapsed_time": elapsed,
                "value": "captcha_fail",
                "message": f"Gagal menyelesaikan reCAPTCHA: {str(e)}"
            }
            logger.error(f"[reCAPTCHA] Exception — {task_id}: {e}")
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            if playwright:
                try:
                    await playwright.stop()
                except Exception:
                    pass


    # ──────────────────────────────────────────────
    #  ENDPOINTS
    # ──────────────────────────────────────────────

    async def process_turnstile(self, url: str = Query(...), sitekey: str = Query(...),
                                 action: str = Query(None), cdata: str = Query(None),
                                 proxy: str = Query(None)):
        if not url or not sitekey:
            raise HTTPException(status_code=400, detail={"status": "error", "error": "Parameter 'url' dan 'sitekey' wajib diisi"})

        # 解除硬性 429 拦截：允许请求进入 asyncio 排队池等待可用页面，避免直接丢弃
        task_id = str(uuid.uuid4())
        self.results[task_id] = {"status": "process", "message": "solving turnstile", "start_time": time.time()}
        try:
            asyncio.create_task(self._solve_turnstile(task_id, url, sitekey, action, cdata, proxy))
            return JSONResponse(content={"task_id": task_id, "status": "accepted"}, status_code=202)
        except Exception as e:
            self.results.pop(task_id, None)
            return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

    async def process_clearance(
        self,
        url: str = Query(..., description="URL target yang dilindungi Cloudflare"),
        timeout: int = Query(30, description="Waktu tunggu maksimal dalam detik (default: 30)"),
    ):
        """
        Endpoint untuk mendapatkan cf_clearance cookie.

        Response sukses berisi:
        - cf_clearance : nilai cookie cf_clearance
        - user_agent   : User-Agent yang HARUS dipakai bersama cookie ini
        - cookies      : seluruh cookie domain dalam format header (opsional, untuk kemudahan)
        """
        if not url:
            raise HTTPException(status_code=400, detail={"status": "error", "error": "Parameter 'url' wajib diisi"})

        if self.page_pool.qsize() == 0:
            return JSONResponse(content={"status": "error", "error": "Server penuh, coba lagi nanti"}, status_code=429)

        task_id = str(uuid.uuid4())
        self.results[task_id] = {"status": "process", "message": "solving clearance", "start_time": time.time()}
        try:
            asyncio.create_task(self._solve_clearance(task_id, url, timeout))
            return JSONResponse(content={"task_id": task_id, "status": "accepted"}, status_code=202)
        except Exception as e:
            self.results.pop(task_id, None)
            return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

    async def process_aws_token(
        self,
        url: str = Query(..., description="URL target (e.g. https://vala-wallet.cc/waitlist)"),
        timeout: int = Query(30, description="Waktu tunggu maksimal dalam detik"),
    ):
        """
        Endpoint untuk mendapatkan aws-waf-token cookie.
        Response sukses berisi: aws_waf_token, cookies, user_agent
        """
        if not url:
            raise HTTPException(status_code=400, detail={"status": "error", "error": "Parameter 'url' wajib diisi"})

        if self.page_pool.qsize() == 0:
            return JSONResponse(content={"status": "error", "error": "Server penuh, coba lagi nanti"}, status_code=429)

        task_id = str(uuid.uuid4())
        self.results[task_id] = {"status": "process", "message": "fetching aws-waf-token", "start_time": time.time()}
        try:
            asyncio.create_task(self._solve_aws_token(task_id, url, timeout))
            return JSONResponse(content={"task_id": task_id, "status": "accepted"}, status_code=202)
        except Exception as e:
            self.results.pop(task_id, None)
            return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

    async def process_recaptcha(
        self,
        url: str = Query(..., description="URL target / Domain yang menggunakan reCAPTCHA v3"),
        sitekey: str = Query(..., description="siteKey untuk Google reCAPTCHA v3"),
        action: str = Query("submit", description="Action name untuk reCAPTCHA v3 (default: submit)")
    ):
        """
        Endpoint untuk memecahkan Google reCAPTCHA v3.
        Menerima parameter url, sitekey, dan action (opsional).
        """
        if not url or not sitekey:
            raise HTTPException(status_code=400, detail={"status": "error", "error": "Parameter 'url' dan 'sitekey' wajib diisi"})

        task_id = str(uuid.uuid4())
        self.results[task_id] = {"status": "process", "message": "solving recaptcha v3", "start_time": time.time()}
        try:
            asyncio.create_task(self._solve_recaptcha(task_id, url, sitekey, action))
            return JSONResponse(content={"task_id": task_id, "status": "accepted"}, status_code=202)
        except Exception as e:
            self.results.pop(task_id, None)
            return JSONResponse(content={"status": "error", "message": str(e)}, status_code=500)

    async def get_result(self, task_id: str = Query(..., alias="id")):
        if not task_id:
            return JSONResponse(content={"status": "error", "message": "Parameter id wajib diisi"}, status_code=400)
        if task_id not in self.results:
            return JSONResponse(content={"status": "error", "message": "task_id tidak valid atau sudah expired"}, status_code=404)

        result = self.results[task_id]

        if result.get("status") == "process":
            start_time = result.get("start_time", time.time())
            if time.time() - start_time > 300:
                self.results[task_id] = {
                    "status": "error",
                    "elapsed_time": round(time.time() - start_time, 3),
                    "value": "timeout",
                    "message": "Tugas timeout"
                }
                result = self.results[task_id]
            else:
                return JSONResponse(content=result, status_code=202)

        result = self.results.pop(task_id)
        if result.get("status") == "success":
            status_code = 200
        elif result.get("value") == "timeout":
            status_code = 408
        else:
            status_code = 422
        return JSONResponse(content=result, status_code=status_code)


def create_app(headless, thread, page_count, proxy_support, proxy_file="proxies.txt",
               cleanup_interval_minutes=10) -> FastAPI:
    server = ClearanceAPIServer(headless=headless, thread=thread, page_count=page_count,
                                proxy_support=proxy_support, proxy_file=proxy_file,
                                cleanup_interval_minutes=cleanup_interval_minutes)
    return server.app


# ──────────────────────────────────────────────
#  BANNER
# ──────────────────────────────────────────────
def _print_banner():
    banner = r"""
  ____        _                _
 | __ )  ___ | |_ ___ _ __ __| |_ __ ___  _ __
 |  _ \ / _ \| __/ _ \ '__/ _` | '__/ _ \| '_ \
 | |_) | (_) | ||  __/ | | (_| | | | (_) | |_) |
 |____/ \___/ \__\___|_|  \__,_|_|  \___/| .__/
  ____        _                          |_|
 / ___|  ___ | |_   _____ _ __
 \___ \ / _ \| \ \ / / _ \ '__|
  ___) | (_) | |\ V /  __/ |    v1.0.5
 |____/ \___/|_| \_/ \___|_|
"""
    print("\033[95m" + banner + "\033[0m")
    print("  \033[90m github.com/najibyahya/Boterdrop-Solver\033[0m")
    print()

# ──────────────────────────────────────────────
#  AUTO INSTALL
# ──────────────────────────────────────────────
def _auto_install():
    import subprocess
    PACKAGES = ["fastapi==0.95.2", "uvicorn", "camoufox[fetch]", "loguru", "psutil"]
    print("\n" + "═" * 52)
    print("  [*]  Memeriksa dependensi yang dibutuhkan...")
    print("═" * 52)
    for pkg in PACKAGES:
        try:
            pkg_import = pkg.split("==")[0].split("[")[0]
            __import__(pkg_import)
            print(f"  [OK]  {pkg} sudah terpasang")
        except ImportError:
            print(f"  [PKG]  Menginstall {pkg}...")
            installed = False
            for extra in [[], ["--break-system-packages"]]:
                try:
                    subprocess.check_call(
                        [sys.executable, "-m", "pip", "install", pkg] + extra,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    installed = True
                    break
                except subprocess.CalledProcessError:
                    continue
            print(f"  {'[OK]' if installed else '[WARN] Gagal install'}  {pkg}")

    import shutil
    if not _camoufox_data_exists():
        print("  [NET]  Mengunduh data browser Camoufox...")
        subprocess.check_call([sys.executable, "-m", "camoufox", "fetch"])
        print("  [OK]  Camoufox berhasil diunduh")
    print("═" * 52 + "\n")


def _camoufox_data_exists():
    # Linux/macOS 旧路径
    d1 = os.path.join(os.path.expanduser("~"), ".camoufox")
    d2 = os.path.join(os.path.expanduser("~"), ".cache", "camoufox")
    if (os.path.isdir(d1) and bool(os.listdir(d1))) or (os.path.isdir(d2) and bool(os.listdir(d2))):
        return True
    # Windows: camoufox 实际安装到 user_cache_dir -> %LOCALAPPDATA%\camoufox\camoufox\Cache
    try:
        from camoufox.pkgman import INSTALL_DIR
        browsers_dir = INSTALL_DIR / "browsers"
        return browsers_dir.is_dir() and bool(list(browsers_dir.iterdir()))
    except Exception:
        return False


def _check_xvfb(headless: bool):
    if sys.platform == "win32" or headless:
        return
    import shutil, subprocess
    if os.environ.get("DISPLAY", ""):
        print("  [OK]  DISPLAY terdeteksi, GUI dapat berjalan")
        return
    print("═" * 52)
    print("  [WARN]   headless=false di VPS tanpa DISPLAY terdeteksi")
    if not shutil.which("xvfb-run"):
        print("  [PKG]  Menginstall Xvfb...")
        try:
            subprocess.check_call(["apt-get", "install", "-y", "xvfb"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("  [OK]  Xvfb berhasil diinstall")
        except Exception:
            print("  [FAIL]  Gagal. Jalankan manual: sudo apt-get install -y xvfb")
    print()
    print("  [ALERT]  Jalankan dengan:")
    print("       xvfb-run -a python3 cf_clearance_server.py")
    print()
    print("  [INFO]   Atau ubah headless=true di config.json")
    print("═" * 52)
    sys.exit(1)


# ──────────────────────────────────────────────
#  CONFIG
# ──────────────────────────────────────────────
CONFIG_PATH = "config.json"
CONFIG_DEFAULTS = {
    "headless":      True,
    "thread":        2,
    "page_count":    1,
    "proxy_support": False,
    "proxy_file":    "proxies.txt",
    "host":          "127.0.0.1",
    "port":          8001,   # port berbeda dari api_server.py agar bisa jalan bersamaan
    "debug":         False,
    "cleanup_interval_minutes": 10,  # interval cleanup paksa (menit)
}


def _load_config() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            return {**CONFIG_DEFAULTS, **json.load(f)}
    except FileNotFoundError:
        print(f"  [WARN]  {CONFIG_PATH} tidak ditemukan, menggunakan nilai default\n")
        return dict(CONFIG_DEFAULTS)
    except json.JSONDecodeError as e:
        print(f"  [FAIL]  Format {CONFIG_PATH} tidak valid: {e}\n")
        return dict(CONFIG_DEFAULTS)


def _save_config(cfg: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=4)
    print(f"\n  [SAVE]  Config disimpan ke {CONFIG_PATH}")


def _parse_value(key, raw, current):
    raw = raw.strip()
    if not raw:
        return current
    if isinstance(current, bool):
        return raw.lower() in ("true", "1", "y", "yes")
    if isinstance(current, int):
        try:
            return int(raw)
        except ValueError:
            return current
    return raw


def _show_config_summary(cfg: dict):
    print("═" * 52)
    print("  ⚙️   KONFIGURASI AKTIF")
    print("═" * 52)
    labels = {
        "headless":      ("Mode Headless",                    "bool"),
        "thread":        ("Jumlah instance browser",          "int"),
        "page_count":    ("Halaman per instance",             "int"),
        "proxy_support": ("Dukungan proxy",                   "bool"),
        "host":          ("Host server",                      "str"),
        "port":          ("Port server",                      "int"),
        "debug":         ("Mode Debug",                       "bool"),
        "cleanup_interval_minutes": ("Interval cleanup paksa (menit)", "int"),
    }
    for i, (key, (label, _)) in enumerate(labels.items(), 1):
        print(f"  [{i}] {label:<38} : {cfg.get(key)}")
    print("═" * 52)


def _interactive_config(cfg: dict) -> dict:
    _show_config_summary(cfg)
    print()
    ans = input("  [>]  Lanjutkan? [Enter/Y = ya  |  N = ubah] : ").strip().lower()
    if ans not in ("n", "no", "tidak"):
        return cfg

    field_order = ["headless", "thread", "page_count", "proxy_support", "host", "port", "debug", "cleanup_interval_minutes"]
    labels = {
        "headless":      "Mode Headless (true/false)",
        "thread":        "Jumlah thread",
        "page_count":    "Halaman per instance",
        "proxy_support": "Dukungan proxy (true/false)",
        "host":          "Host server",
        "port":          "Port server",
        "debug":         "Mode Debug (true/false)",
        "cleanup_interval_minutes": "Interval cleanup paksa (menit)",
    }
    print("\n  [EDIT]   Tekan Enter untuk mempertahankan nilai saat ini")
    print("─" * 52)
    new_cfg = dict(cfg)
    for key in field_order:
        raw = input(f"  {labels[key]} [{cfg[key]}] : ")
        new_cfg[key] = _parse_value(key, raw, cfg[key])

    print()
    _show_config_summary(new_cfg)
    if input("\n  [SAVE]  Simpan? [Y/Enter = ya  |  N = tidak] : ").strip().lower() not in ("n", "no"):
        _save_config(new_cfg)
    return new_cfg


def _check_port(cfg: dict) -> dict:
    import socket
    while True:
        port = cfg.get("port", 8001)
        host = cfg.get("host", "0.0.0.0")
        bind = "127.0.0.1" if host == "0.0.0.0" else host
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            in_use = s.connect_ex((bind, port)) == 0
        if not in_use:
            print(f"  [OK]  Port {port} tersedia")
            print("═" * 52 + "\n")
            break
        print(f"  [FAIL]  Port {port} sudah digunakan!")
        try:
            new_port = int(input(f"  [RETRY]  Port pengganti : ").strip())
            cfg = dict(cfg)
            cfg["port"] = new_port
            if input(f"  [SAVE]  Simpan port {new_port}? [Y/Enter] : ").strip().lower() not in ("n", "no"):
                _save_config(cfg)
        except ValueError:
            print("  [WARN]  Input tidak valid")
    return cfg


def _check_system(cfg: dict):
    import psutil
    cpu_count = os.cpu_count() or 1
    cpu_usage = psutil.cpu_percent(interval=1)
    ram = psutil.virtual_memory()
    ram_total = ram.total / 1024**3
    ram_free = ram.available / 1024**3
    ram_pct = ram.percent
    thread = cfg.get("thread", 2)
    page_count = cfg.get("page_count", 1)
    total = thread * page_count
    est_ram = total * 0.3
    print("═" * 52)
    print("  [PC]  INFO SISTEM")
    print("═" * 52)
    print(f"  [CPU]  CPU  : {cpu_count} core | terpakai {cpu_usage:.1f}%")
    print(f"  [RAM]  RAM  : {ram_total:.1f} GB | bebas {ram_free:.1f} GB ({ram_pct:.1f}%)")
    print(f"  [CFG]  Config: {thread} thread × {page_count} halaman = {total} slot")
    print(f"  [STAT]  Est. RAM browser: ±{est_ram:.1f} GB")
    print("─" * 52)
    issues = []
    if thread > cpu_count:
        issues.append(f"  [WARN]  thread ({thread}) > core CPU ({cpu_count})")
    if est_ram > ram_free * 0.85:
        issues.append(f"  [WARN]  Est. RAM ({est_ram:.1f} GB) mendekati RAM bebas ({ram_free:.1f} GB)")
    if cpu_usage > 80:
        issues.append(f"  [WARN]  CPU tinggi ({cpu_usage:.1f}%)")
    if issues:
        print("  [FAIL]  Peringatan:")
        for i in issues:
            print(i)
    else:
        print("  [OK]  Config sesuai dengan resource sistem")
    print("═" * 52 + "\n")


# ──────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────
if __name__ == "__main__":
    _print_banner()
    _auto_install()
    config = _load_config()
    config = _interactive_config(config)
    _check_xvfb(config.get("headless", True))

    print()
    print("═" * 52)
    print("  [CHECK]  CEK PORT & SUMBER DAYA SISTEM")
    print("═" * 52)
    log_level = "DEBUG" if config.get("debug", False) else "INFO"
    logger.remove()
    logger.add(sys.stderr, level=log_level)
    logger.info(f"Level log: {log_level}")

    _check_system(config)
    config = _check_port(config)

    print("═" * 52)
    print("  [GO]  Memulai Boterdrop Solver...")
    print("═" * 52 + "\n")

    app = create_app(
        headless=config["headless"],
        thread=config["thread"],
        page_count=config["page_count"],
        proxy_support=config["proxy_support"],
        proxy_file=config.get("proxy_file", "proxies.txt"),
        cleanup_interval_minutes=config.get("cleanup_interval_minutes", 10),
    )
    uvicorn.run(app, host=config["host"], port=config["port"])
