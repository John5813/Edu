"""Sayt akkauntlari API: Google bilan kirish, profil (ism, til), Telegram va Google ni ulash.

Google bilan kirish — standart "authorization code" oqimi, hammasi serverda:
  /auth/google/start  → Google (state cookie bilan)  → /auth/google/callback → sessiya cookie → /app
Parol saqlanmaydi. Kimlik faqat Google `sub` bo'yicha; email faqat ko'rsatish uchun (tasdiqlangan bo'lishi shart).
`state` imzolangan cookie bilan solishtiriladi (CSRF), yo'naltirish manzili qat'iy (ochiq redirect yo'q).
"""
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Dict, Optional
from urllib.parse import urlencode

import aiohttp
from aiohttp import web

import config
import webapp
from database import web_accounts, web_store
from database.database import Database

log = logging.getLogger(__name__)

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
STATE_COOKIE = "edu_oauth"
STATE_TTL = 10 * 60
CALLBACK_PATH = "/api/v1/auth/google/callback"


def google_enabled() -> bool:
    return bool(config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET)


def redirect_uri() -> str:
    return webapp.public_url(CALLBACK_PATH)


# ───────────────────────────────────────────────────────────── imzolangan state

def _key() -> bytes:
    return hashlib.sha256(("edu-oauth|" + (config.BOT_TOKEN or "")).encode()).digest()


def _seal(payload: Dict) -> str:
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return body + "." + hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()


def _open(value: str) -> Optional[Dict]:
    try:
        body, sig = (value or "").rsplit(".", 1)
        if not hmac.compare_digest(sig, hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()):
            return None
        payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except Exception:
        return None
    return payload if isinstance(payload, dict) and payload.get("t", 0) >= time.time() else None


# ───────────────────────────────────────────────────────────────────── Google

async def google_exchange(code: str, uri: str) -> Dict:
    """Kodni Google'da almashtirib, foydalanuvchi ma'lumotini oladi: {sub, email, email_verified, name, locale}."""
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(GOOGLE_TOKEN, data={
                "code": code, "client_id": config.GOOGLE_CLIENT_ID, "client_secret": config.GOOGLE_CLIENT_SECRET,
                "redirect_uri": uri, "grant_type": "authorization_code"}) as response:
            token = await response.json()
            if response.status != 200 or not token.get("access_token"):
                raise RuntimeError(f"Google token xatosi: {token.get('error', response.status)}")
        async with session.get(GOOGLE_USERINFO, headers={"Authorization": f"Bearer {token['access_token']}"}) as response:
            info = await response.json()
            if response.status != 200:
                raise RuntimeError(f"Google profil xatosi: {response.status}")
    return {"sub": str(info.get("sub") or ""), "email": str(info.get("email") or "").lower(),
            "email_verified": info.get("email_verified") in (True, "true"), "name": str(info.get("name") or ""),
            "locale": str(info.get("locale") or "")}


def _back(path: str = "/app", *, error: str = "", cookie: Optional[str] = None, request=None,
          clear_state: bool = True, extra: str = "") -> web.Response:
    """Brauzerni saytga qaytaradi (manzil qat'iy: faqat `/app`)."""
    target = path + (f"?auth_error={error}" if error else "") + extra
    response = web.HTTPFound(target)
    if clear_state:
        response.del_cookie(STATE_COOKIE, path="/")
    return response


# ────────────────────────────────────────────────────────────────── endpointlar

async def auth_config(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "google": google_enabled(), "bot": webapp.BOT_USERNAME or "",
                              "languages": list(web_accounts.LANGUAGES)})


async def google_start(request: web.Request) -> web.Response:
    from webapp import api

    if not google_enabled():
        raise _back(error="google_off")
    if api._limited("gstart:" + api._ip(request), 20, 60):
        raise _back(error="rate")
    language = web_accounts.clean_language(request.query.get("lang"))
    intent, uid = "login", 0
    if request.query.get("intent") == "attach":
        uid = await api._user_id(request) or 0
        intent = "attach" if uid else "login"
    nonce = secrets.token_urlsafe(24)
    payload = {"n": nonce, "i": intent, "l": language, "u": int(uid), "t": time.time() + STATE_TTL}
    url = GOOGLE_AUTH + "?" + urlencode({
        "client_id": config.GOOGLE_CLIENT_ID, "redirect_uri": redirect_uri(), "response_type": "code",
        "scope": "openid email profile", "state": nonce, "prompt": "select_account", "access_type": "online"})
    response = web.HTTPFound(url)
    response.set_cookie(STATE_COOKIE, _seal(payload), max_age=STATE_TTL, httponly=True, samesite="Lax",
                        secure=api._secure(request), path="/")
    raise response


async def google_callback(request: web.Request) -> web.Response:
    from webapp import api

    if not google_enabled():
        raise _back(error="google_off")
    if api._limited("gcb:" + api._ip(request), 30, 60):
        raise _back(error="rate")
    payload = _open(request.cookies.get(STATE_COOKIE, ""))
    state = request.query.get("state", "")
    if not payload or not state or not hmac.compare_digest(str(payload.get("n", "")), state):
        raise _back(error="state")
    if request.query.get("error") or not request.query.get("code"):
        raise _back(error="cancelled")
    try:
        profile = await google_exchange(request.query["code"], redirect_uri())
    except Exception as exc:
        log.warning("Google bilan kirish bajarilmadi: %s", exc)
        raise _back(error="google_failed")
    if not profile.get("sub") or not profile.get("email") or not profile.get("email_verified"):
        raise _back(error="email")

    identity = await web_accounts.identity_by_subject("google", profile["sub"])
    if payload["i"] == "attach":
        return await _attach(request, payload, profile, identity)

    created = identity is None
    if created:
        telegram_id = await web_accounts.create_web_user("google", profile["sub"], profile["email"],
                                                         profile["name"], payload.get("l"))
    else:
        telegram_id = int(identity["telegram_id"])
    session = await web_accounts.create_session(telegram_id)
    response = web.HTTPFound("/app#/welcome" if created else "/app#/create")
    response.del_cookie(STATE_COOKIE, path="/")
    response.set_cookie(api.COOKIE, session, max_age=web_store.SESSION_TTL, httponly=True, samesite="Lax",
                        secure=api._secure(request), path="/")
    raise response


async def _attach(request: web.Request, payload: Dict, profile: Dict, identity: Optional[Dict]) -> web.Response:
    """Kirgan akkauntga Google ni ulash (kirgan odamning o'zi bosgan bo'lishi shart)."""
    from webapp import api

    uid = int(payload.get("u") or 0)
    if not uid or await api._user_id(request) != uid:
        raise _back(error="auth")
    if identity is None:
        if await web_accounts.identity_of(uid):
            raise _back("/app#/profile", error="has_google")
        await web_accounts.attach_identity(uid, "google", profile["sub"], profile["email"], profile["name"])
    elif int(identity["telegram_id"]) != uid:
        # Bu Google bilan avval alohida sayt akkaunti ochilgan bo'lsa, u shu (Telegramli) akkauntga qo'shiladi.
        try:
            await web_accounts.merge(int(identity["telegram_id"]), uid)
        except web_accounts.MergeError:
            raise _back("/app#/profile", error="google_taken")
    raise _back("/app#/profile", extra="")


async def profile_get(request: web.Request) -> web.Response:
    from webapp import api

    telegram_id = await api._require(request)
    data = await web_accounts.profile(telegram_id)
    if not data:
        return api._error("Akkaunt topilmadi", 404, "not_found")
    data["google_enabled"] = google_enabled()
    data["bot"] = webapp.BOT_USERNAME or ""
    return web.json_response({"ok": True, "profile": data, "languages": list(web_accounts.LANGUAGES)})


async def profile_post(request: web.Request) -> web.Response:
    from webapp import api

    telegram_id = await api._require(request)
    data = await api._json(request)
    try:
        await web_accounts.update_profile(telegram_id, data.get("name") if "name" in data else None,
                                          data.get("language") if "language" in data else None)
    except ValueError as exc:
        return api._error(str(exc), 400, "bad_request")
    return web.json_response({"ok": True, "profile": await web_accounts.profile(telegram_id)})


async def telegram_link(request: web.Request) -> web.Response:
    """Sayt akkauntini Telegramga ulash uchun bot havolasi (botda aniq tasdiq so'raladi)."""
    from webapp import api

    telegram_id = await api._require(request)
    if api._limited(f"tglink:{telegram_id}", 6, 60):
        return api._error("Juda tez-tez urinish. Bir daqiqa kuting.", 429, "rate")
    if not webapp.BOT_USERNAME:
        return api._error("Bot hali ishga tushmoqda, birozdan keyin urining.", 503, "bot")
    try:
        token = await web_accounts.start_link(telegram_id)
    except web_accounts.MergeError as exc:
        return api._error(str(exc), 409, "linked")
    return web.json_response({"ok": True, "url": f"https://t.me/{webapp.BOT_USERNAME}?start=weblink_{token}",
                              "expires_in": web_accounts.LINK_TTL})


def setup(app: web.Application) -> None:
    add = app.router.add_route
    add("GET", "/api/v1/auth/config", auth_config)
    add("GET", "/api/v1/auth/google/start", google_start)
    add("GET", CALLBACK_PATH, google_callback)
    add("GET", "/api/v1/profile", profile_get)
    add("POST", "/api/v1/profile", profile_post)
    add("POST", "/api/v1/profile/telegram-link", telegram_link)
