import asyncio
import json
import secrets
import threading
import time
from pathlib import Path
from typing import Dict

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..util.tools import daoflag2str, anywhere_send

from ..clanbattle import clanbattle_info, notice_update_time
from ..util.auto_boss import clan_boss_info
from ..clanbattle.base import clanbattle_report
from ..database.dal import CookieCache, SLDao, pcr_sqla
import traceback
from loguru import logger as log

from ..basedata import NoticeType, Platform
from ..client import check_client, get_access_key, decrypt_access_key
from ..login import query
from ..database.models import ClanBattleMember, Account, RefreshAccount
from ..setting import WebSetting
from .util import *
from .web_model import *
from nonebot import on_startup

from sse_starlette.sse import EventSourceResponse

app = FastAPI()

# 静态文件服务
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")

origins = [
    "http://localhost",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(WebSetting.api_base.value, app)


@app.get("/")
async def serve_index():
    index_path = _static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "KCRR Web UI - API is running"}


@app.get("/login")
async def serve_login_page():
    index_path = _static_dir / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "KCRR Web UI - API is running"}

update_time: Dict[str, Dict[str, int]] = {"report": {}, "notice": {}}
report_time = update_time["report"]
notice_time = update_time["notice"]


@app.post("/login")
async def check_user(user: User, response: Response):
    if web_user := await pcr_sqla.web_check_user(user.account, user.password):
        if web_user.temp and time.time() - web_user.create_time > 7 * 24 * 3600:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED, "临时密码过期，请重新获取或修改密码"
            )
        token = secrets.token_urlsafe(16)
        response.set_cookie("token", token, expires=3600 * 24 * 7, httponly=True)
        await pcr_sqla.web_add_cookie(token, web_user.account)
    else:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "密码错误")


@app.get("/home")
async def home_info(token: CookieCache = Depends(verify_cookie)):
    user_id = int(token.user_id)
    response = HomeResponse()
    response.user_id = user_id
    if web_user := await pcr_sqla.web_query_user(user_id):
        response.priority = web_user.priority

    if pcr_user := (await pcr_sqla.query_account(user_id)):
        pcr_user = pcr_user[0]
        response.name = pcr_user.name
    if groups := await pcr_sqla.get_member_group(user_id):
        response.clan = [group.dict() for group in groups]
    return response.dict()


@app.get("/{group_id}/dashboard")
async def dashboard_info(group_id: int, token: CookieCache = Depends(verify_cookie)):
    now = int(time.time())
    boss_info = clan_boss_info.boss_info
    user_id = int(token.user_id)
    response = DashboardResponse()
    response.boss = [
        BossInfoCounter(
            name=boss_info[i].name,
            id=boss_info[i].boss_id,
        )
        for i in range(5)
    ]
    response.user_id = user_id
    if web_user := await pcr_sqla.web_query_user(user_id):
        response.priority = web_user.priority

    if clan_info := clanbattle_info.get(group_id, None):
        response.clan_name = clan_info.clan_name
        response.stage = f"{clan_info.period}面{clan_info.lap_num}周目"
        response.rank = clan_info.rank
        response.name = clan_info.user_id
        if clan_info.loop_check:
            response.state = "开启" + (
                "(高占用)" if now - clan_info.loop_check > 30 else ""
            )
            response.boss = [
                BossInfoCounter(
                    name=boss_info[i].name,
                    id=boss_info[i].boss_id,
                    fighter=boss.fighter_num,
                    current_hp=boss.current_hp,
                    max_hp=boss.max_hp,
                    lap=boss.lap_num,
                )
                for i, boss in enumerate(clan_info.boss)
            ]
    if dao_data := await pcr_sqla.get_day_rcords(now, group_id):
        response.dao, response.report = await get_day_dao(dao_data)
    if dao_data := await pcr_sqla.get_day_rcords(now - 3600 * 24, group_id):
        response.yesterday_dao, _ = await get_day_dao(dao_data)

    if subscribes := await pcr_sqla.get_notice(NoticeType.subscribe.value, group_id):
        for subscribe in subscribes:
            response.boss[subscribe.boss - 1].subscribe += 1
    if applies := await pcr_sqla.get_notice(NoticeType.apply.value, group_id):
        for apply in applies:
            response.boss[apply.boss - 1].apply += 1
    if trees := await pcr_sqla.get_notice(NoticeType.tree.value, group_id):
        for tree in trees:
            response.boss[tree.boss - 1].tree += 1
    response.day_num = await pcr_sqla.get_clan_day(group_id)
    return response.dict()


@app.get("/{group_id}/notice")
async def clan_notice(group_id: int, token: CookieCache = Depends(verify_cookie)):
    user_id = int(token.user_id)
    response = NoticeResponse()
    response.user_id = user_id
    if web_user := await pcr_sqla.web_query_user(user_id):
        response.priority = web_user.priority
    if subscribe := await pcr_sqla.get_notice(NoticeType.subscribe.value, group_id):
        response.subscribe = subscribe
    if apply := await pcr_sqla.get_notice(NoticeType.apply.value, group_id):
        response.apply = apply
    if tree := await pcr_sqla.get_notice(NoticeType.tree.value, group_id):
        response.tree = tree
    return response.dict()


@app.get("/{group_id}/report")
async def clan_report(group_id: int, token: CookieCache = Depends(verify_cookie)):
    user_id = int(token.user_id)
    response = ReportResponse()
    response.user_id = user_id
    if web_user := await pcr_sqla.web_query_user(user_id):
        response.priority = web_user.priority
    if info := await pcr_sqla.get_all_records(group_id):
        players, all_damage, all_score = clanbattle_report(
            info, await pcr_sqla.get_max_dao(group_id)
        )
        response.all = [
            DaoInfo(
                name=member[1],
                damage=member[3],
                score=member[4],
                dao=member[2],
                damage_rate=f"{member[3]/all_damage*100:.2f}%",
                score_rate=f"{member[4]/all_score*100:.2f}%",
            )
            for member in players
        ]
        response.detail = [
            DaoInfo(
                name=player.name,
                damage=player.damage,
                score=int(
                    clan_boss_info.get_boss_rate(player.lap, player.boss)
                    * player.damage
                ),
                type=daoflag2str(player.flag),
                date=player.time,
                boss=player.boss,
                lap=player.lap,
                dao_id=player.battle_log_id,
            )
            for player in info[::-1]
        ]
    if pcr_user := (await pcr_sqla.query_account(user_id)):
        pcr_user = pcr_user[0]
        response.name = pcr_user.name
        if info := await pcr_sqla.get_player_records(pcr_user.viewer_id, 5, group_id):
            knife = 0
            for dao in info:
                knife += 1 if dao.flag == 0 else 0.5
                response.me.append(
                    DaoInfo(
                        dao=knife,
                        damage=dao.damage,
                        score=int(
                            clan_boss_info.get_boss_rate(dao.lap, dao.boss) * dao.damage
                        ),
                        type=daoflag2str(dao.flag),
                        boss=dao.boss,
                        lap=dao.lap,
                        date=dao.time,
                        dao_id=dao.battle_log_id,
                    )
                )
        response.me = response.me[::-1]
    return response.dict()


@app.post("/set_notice")
async def set_notice(notice: NoticeCache, token: CookieCache = Depends(verify_cookie)):
    user_id = int(token.user_id)
    notice.user_id = user_id
    if notice.notice_type == NoticeType.sl.value:
        if not await pcr_sqla.add_sl(
            SLDao(group_id=notice.group_id, user_id=user_id, time=int(time.time()))
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "已经sl过了")
    else:
        await pcr_sqla.add_notice(notice)
    notice_update_time[int(notice.group_id)] = int(time.time())
    await anywhere_send(
        get_notice_msg(
            notice.notice_type, user_id, notice.boss, notice.lap, notice.text
        ),
        group_id=notice.group_id,
    )
    return "成功"


@app.post("/delete_notice")
async def set_notice(notice: NoticeCache, token: CookieCache = Depends(verify_cookie)):
    user_id = int(token.user_id)
    notice.user_id = user_id
    if notice.notice_type == NoticeType.sl.value:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "那你自己心里清楚")
    else:
        await pcr_sqla.delete_notice(
            notice.notice_type,
            notice.group_id,
            notice.boss,
            user_id=user_id,
        )
    notice_update_time[int(notice.group_id)] = int(time.time())
    await anywhere_send(
        cancel_notice_msg(notice.notice_type, user_id, notice.boss, user_id),
        group_id=notice.group_id,
    )
    return "取消成功"


@app.post("/delete_notice_special")
async def set_notice(
    notice: SpecialNoticeForm, token: CookieCache = Depends(verify_cookie)
):
    user_id = int(token.user_id)
    if user_id != notice.user_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "权限不足，如果管理请等待权限系统完善"
        )
    else:
        await pcr_sqla.delete_notice(
            notice.notice_type,
            notice.group_id,
            notice.boss,
            user_id=user_id,
            lap=notice.lap,
        )
    notice_update_time[int(notice.group_id)] = int(time.time())
    await anywhere_send(
        cancel_notice_msg(
            notice.notice_type, notice.user_id, notice.boss, operator=user_id
        ),
        group_id=notice.group_id,
    )
    return "取消成功"


@app.get("/{group_id}/renew_dashboard")
async def renew_dashboard(group_id: int, token: CookieCache = Depends(verify_cookie)):
    async def dashboard_generator():
        report_time[token.token] = int(time.time())
        notice_time[token.token] = int(time.time())
        while True:
            await asyncio.sleep(10)
            if clan_info := clanbattle_info.get(group_id, None):
                if clan_info.dao_update_time > report_time[token.token]:
                    report_time[token.token] = clan_info.dao_update_time
                    yield json.dumps(await dashboard_info(group_id, token))
                    continue
            if update_time := notice_update_time.get(group_id, 0):
                if update_time > notice_time[token.token]:
                    notice_time[token.token] = update_time
                    yield json.dumps(await dashboard_info(group_id, token))

    return EventSourceResponse(content=dashboard_generator())


@app.get("/{group_id}/renew_report")
async def renew_report(group_id: int, token: CookieCache = Depends(verify_cookie)):
    async def report_generator():
        report_time[token.token] = int(time.time())
        while True:
            await asyncio.sleep(10)
            if clan_info := clanbattle_info.get(group_id, None):
                if clan_info.dao_update_time > report_time[token.token]:
                    yield json.dumps(await clan_report(group_id, token))
                    report_time[token.token] = clan_info.dao_update_time
            if not report_time[token.token]:
                yield json.dumps(await clan_report(group_id, token))
                report_time[token.token] = int(time.time())

    return EventSourceResponse(content=report_generator())


@app.get("/{group_id}/renew_notice")
async def renew_notice(group_id: int, token: CookieCache = Depends(verify_cookie)):
    async def notice_generator():
        notice_time[token.token] = int(time.time())
        while True:
            await asyncio.sleep(10)
            if update_time := notice_update_time.get(group_id, 0):
                if update_time > notice_time[token.token]:
                    yield json.dumps(await clan_notice(group_id, token))
                    notice_time[token.token] = update_time

    return EventSourceResponse(content=notice_generator())


@app.post("/correct_dao")
async def events(correct: CorrectDaoInfo, token: CookieCache = Depends(verify_cookie)):
    if await pcr_sqla.correct_dao(
        correct.dao_id,
        0 if correct.type == "完整刀" else 1 if correct.type == "尾刀" else 0.5,
        correct.group_id,
    ):
        report_time[token.token] = 0
        return "修改成功"
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "请检查你输入了正确的出刀编号")


@app.post("/change_password")
async def change_password(
    form: ChangePasswordForm, token: CookieCache = Depends(verify_cookie)
):
    if form.new_password != form.confirm_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "两次密码不一致")
    if len(form.new_password) < 4:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "密码长度不能小于4位")
    await pcr_sqla.web_update_password(token.user_id, form.new_password)
    return "密码修改成功"


@app.get("/account_info")
async def account_info(token: CookieCache = Depends(verify_cookie)):
    user_id = int(token.user_id)
    result = {"user_id": user_id, "name": "", "viewer_id": None, "platform": None, "clans": []}
    if accounts := await pcr_sqla.query_account(user_id):
        acc = accounts[0]
        result["name"] = acc.name or ""
        result["viewer_id"] = acc.viewer_id
        result["platform"] = acc.platform
    if groups := await pcr_sqla.get_member_group(user_id):
        result["clans"] = [
            {"group_id": g.group_id, "group_name": g.group_name}
            for g in groups
        ]
    # 监控状态
    monitor_list = []
    for gid, info in clanbattle_info.items():
        account_name = ""
        if info.user_id:
            try:
                monitor_accounts = await pcr_sqla.query_account(info.user_id)
                if monitor_accounts:
                    account_name = monitor_accounts[0].name or str(monitor_accounts[0].viewer_id)
            except Exception:
                pass
        monitor_list.append({
            "group_id": gid,
            "active": bool(info.loop_check),
            "user_id": info.user_id,
            "rank": info.rank,
            "clan_name": info.clan_name,
            "account_name": account_name,
        })
    result["monitors"] = monitor_list
    return result


@app.post("/bind_clan")
async def bind_clan(
    form: BindClanForm, token: CookieCache = Depends(verify_cookie)
):
    user_id = int(token.user_id)
    await pcr_sqla.add_member(
        ClanBattleMember(
            group_id=form.group_id,
            user_id=user_id,
            group_name=form.group_name,
        )
    )
    return "绑定公会成功"


@app.post("/unbind_clan")
async def unbind_clan(
    form: UnbindClanForm, token: CookieCache = Depends(verify_cookie)
):
    user_id = int(token.user_id)
    await pcr_sqla.delete_member(form.group_id, user_id)
    return "解绑公会成功"


async def _get_clan_info(acc: Account):
    """尝试获取账号所在公会信息，失败返回 None"""
    for attempt in range(2):
        try:
            client = await query(acc, is_force=True)
            home = await client.home_index()
            if home.user_clan and home.user_clan.clan_id:
                return {
                    "clan_name": home.user_clan.clan_name,
                    "clan_id": home.user_clan.clan_id,
                }
            return None
        except Exception as e:
            log.warning(f"查询账号 {acc.viewer_id} 公会信息失败(第{attempt+1}次): {e}")
    return None


@app.get("/accounts")
async def list_accounts(token: CookieCache = Depends(verify_cookie)):
    user_id = int(token.user_id)
    accounts = await pcr_sqla.query_account(user_id)
    platform_map = {0: "B服", 1: "渠道服", 2: "台服"}
    result = []
    for acc in accounts:
        item = {
            "id": acc.id,
            "viewer_id": acc.viewer_id,
            "platform": acc.platform,
            "platform_name": platform_map.get(acc.platform, "未知"),
            "name": acc.name or "",
            "clan_name": None,
            "clan_id": None,
        }
        clan = await _get_clan_info(acc)
        if clan:
            item["clan_name"] = clan["clan_name"]
            item["clan_id"] = clan["clan_id"]
        result.append(item)
    return result


@app.post("/bind_account")
async def bind_account(
    form: BindAccountForm, token: CookieCache = Depends(verify_cookie)
):
    user_id = int(token.user_id)
    try:
        if form.platform == "b":
            if not form.bili_account or not form.bili_password:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "请输入B站账号和密码")
            bili_account = RefreshAccount(account=form.bili_account, password=form.bili_password)
            uid, access_key = await get_access_key(
                bili_account.account, bili_account.password, user_id
            )
            account = Account(
                user_id=user_id,
                platform=Platform.b_id.value,
                account=uid,
                password=access_key,
                refresh=bili_account.account,
            )
            client = await query(account, True)
            if load_index := await check_client(client):
                account.viewer_id = load_index.user_info.viewer_id
                account.name = load_index.user_info.user_name
                await pcr_sqla.add_account(user_id, account.dict(exclude_none=True))
                await pcr_sqla.add_refresh(bili_account)
                return {
                    "message": "绑定成功",
                    "name": account.name,
                    "viewer_id": account.viewer_id,
                }
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "绑定失败，请检查账号密码")

        elif form.platform == "qu":
            if not form.login_id or not form.token:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "请输入login_id和token")
            password = form.token
            if form.token2:
                password = decrypt_access_key(f"{form.token} {form.token2}")
            account = Account(
                user_id=user_id,
                platform=Platform.qu_id.value,
                account=form.login_id,
                password=password,
            )
            client = await query(account, True)
            if load_index := await check_client(client):
                account.viewer_id = load_index.user_info.viewer_id
                account.name = load_index.user_info.user_name
                await pcr_sqla.add_account(user_id, account.dict(exclude_none=True))
                return {
                    "message": "绑定成功",
                    "name": account.name,
                    "viewer_id": account.viewer_id,
                }
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "绑定失败，请检查数据是否完整")

        elif form.platform == "tw":
            if not form.short_udid or not form.udid or not form.viewer_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "请输入short_udid、udid和viewer_id")
            account = Account(
                user_id=user_id,
                platform=Platform.tw_id.value,
                viewer_id=form.viewer_id,
                account=form.short_udid,
                password=form.udid,
            )
            client = await query(account, True)
            if load_index := await check_client(client):
                account.name = load_index.user_info.user_name
                await pcr_sqla.add_account(user_id, account.dict(exclude_none=True))
                return {
                    "message": "绑定成功",
                    "name": account.name,
                    "viewer_id": account.viewer_id,
                }
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "绑定失败，请检查数据是否完整")

        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "不支持的服务器类型")
    except HTTPException:
        raise
    except Exception as e:
        log.error(traceback.format_exc())
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"绑定失败: {str(e)}")


@app.post("/unbind_account")
async def unbind_account(
    form: UnbindAccountForm, token: CookieCache = Depends(verify_cookie)
):
    user_id = int(token.user_id)
    await pcr_sqla.delete_account(form.account_id, user_id)
    return "解绑账号成功"


@app.post("/cancel_monitor")
async def cancel_monitor(
    form: CancelMonitorForm, token: CookieCache = Depends(verify_cookie)
):
    user_id = int(token.user_id)
    group_id = form.group_id
    if group_id not in clanbattle_info:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "该群未开启出刀监控")
    clan_info = clanbattle_info[group_id]
    if user_id != clan_info.user_id:
        web_user = await pcr_sqla.web_query_user(user_id)
        if not web_user or web_user.priority < 1:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "你不是监控人或管理员")
    clan_info.loop_num += 1
    return "已取消出刀监控"


@app.get("/my_clans")
async def my_clans(token: CookieCache = Depends(verify_cookie)):
    user_id = int(token.user_id)
    accounts = await pcr_sqla.query_account(user_id)
    if not accounts:
        return []
    platform_map = {0: "B服", 1: "渠道服", 2: "台服"}
    # Get already bound groups
    bound_groups = set()
    if groups := await pcr_sqla.get_member_group(user_id):
        bound_groups = {g.group_id for g in groups}
    clans = []
    seen_clan_ids = set()
    for acc in accounts:
        try:
            client = await query(acc, is_force=True)
            home = await client.home_index()
            if home.user_clan and home.user_clan.clan_id:
                clan_id = home.user_clan.clan_id
                if clan_id in seen_clan_ids:
                    continue
                seen_clan_ids.add(clan_id)
                clans.append({
                    "clan_id": clan_id,
                    "clan_name": home.user_clan.clan_name or "未知公会",
                    "member_count": home.user_clan.clan_member_count or 0,
                    "account_name": acc.name or str(acc.viewer_id),
                    "platform": acc.platform,
                    "platform_name": platform_map.get(acc.platform, "未知"),
                    "already_bound": clan_id in bound_groups,
                })
        except Exception as e:
            log.warning(f"查询账号 {acc.viewer_id} 公会信息失败: {e}")
            continue
    return clans


@on_startup
async def kanna_web():
    web = threading.Thread(
        target=uvicorn.run, kwargs={"app": app, "host": "0.0.0.0", "port": 12138}
    )
    web.start()
