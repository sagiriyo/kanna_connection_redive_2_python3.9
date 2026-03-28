import time
from typing import List, Tuple, Union
from nonebot import MessageSegment
from fastapi import Cookie, HTTPException, status

from ..basedata import NoticeType
from ..clanbattle.base import day_report
from ..database.dal import pcr_sqla
from ..database.models import CookieCache, RecordDao


async def verify_cookie(token: str = Cookie(None)) -> CookieCache:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "请先登录")
    if cookie := await pcr_sqla.web_query_cookie(token):
        if time.time() - cookie.time < 3600 * 7 * 24:
            return cookie
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "登录过期")


async def get_day_dao(dao_data: List[RecordDao]) -> Tuple[int, list]:
    total = 0
    state = {3: [], 2.5: [], 2: [], 1.5: [], 1: [], 0.5: [], 0: []}
    report_info = await day_report(dao_data, {})
    for member in report_info:
        name = member[1]
        dao = min(member[2], 3)
        state[dao].append(name)
        total += dao

    return total, [{"dao_num": dao, "names": state[dao]} for dao in state if state[dao]]


def get_notice_msg(type: int, user_id: int, boss: int, lap: int, msg: str) -> str:
    at_msg = MessageSegment.at(user_id)
    if type == NoticeType.subscribe.value:
        resp = "预约了"
    elif type == NoticeType.apply.value:
        resp = "申请了"
    elif type == NoticeType.tree.value:
        resp = "挂树在了"
    elif type == NoticeType.sl.value:
        return at_msg + "SL了" + (f"\n留言: {msg}" if msg else "")

    resp += f"第{lap}周目" if lap else "当前周目"
    resp += f"{boss}王"
    resp += f"\n留言: {msg}" if msg else ""
    return at_msg + resp


def cancel_notice_msg(
    type: int, user_id: int, boss: int, operator: int = 114514
) -> str:
    operator_msg = (MessageSegment.at(operator) + "使") if operator != user_id else ""
    if type == NoticeType.subscribe.value:
        resp = "取消预约了"
    elif type == NoticeType.apply.value:
        resp = "取消申请了"
    elif type == NoticeType.tree.value:
        resp = "取消挂树在了"
    resp += f"{boss}王"
    return operator_msg + MessageSegment.at(user_id) + resp
