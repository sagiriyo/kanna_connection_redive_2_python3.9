import random
import string
from hoshino import Service
from nonebot import NoticeSession, on_command, logger
from ..database.dal import pcr_sqla
from ..database.models import WebAccount
from ..setting import WebSetting
from .api import *

sv = Service(
    name="环奈网页端管理",  # 功能名
    visible=False,  # 可见性
    enable_on_default=True,  # 默认启用
)


@on_command("apply_login", aliases=("网页端登录"), only_to_me=True)
async def apply_login(session: NoticeSession):
    if session.ctx.get("message_type") == "group":
        await session.send("请私聊bot发送吧~")
        return
    qq_id = str(session.ctx.user_id)
    temp_password = "".join(random.sample(string.ascii_letters + string.digits, 8))
    await pcr_sqla.web_add_user(WebAccount(account=qq_id, password=temp_password))
    await session.send(
        f"{WebSetting.web_host.value}:{WebSetting.web_port.value}/login?account={qq_id}&password={temp_password}",
        ensure_private=True,
    )
