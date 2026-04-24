from typing import List
from pydantic import BaseModel

from ..database.models import NoticeCache


class User(BaseModel):
    account: str
    password: str


class BossInfoCounter(BaseModel):
    name: str = ""
    id: int = 0
    current_hp: int = 0
    max_hp: int = 0
    lap: int = 0
    subscribe: int = 0
    apply: int = 0
    fighter: int = 0
    tree: int = 0


class HomeResponse(BaseModel):
    priority: int = 0
    user_id: int = 0
    name: str = "无？你绑定账号了嘛？"
    status: str = "成员"
    saying: str = (
        "我们不必为他人隐藏本性而感到愤怒，因为你自己也在隐藏本性。——拉罗什富科《箴言集》"
    )
    clan: List[int] = []


class DashboardResponse(BaseModel):
    priority: int = 0
    clan_priority: int = 0
    user_id: int = 1791800364
    name: str = "无"
    clan_name: str = "环奈连结"
    stage: str = "暂无信息"
    dao: int = 0
    yesterday_dao: int = 0
    rank: int = 114514
    state: str = "关闭"
    boss: List[BossInfoCounter] = []
    report: list = []
    day_num: int = 0


class NoticeResponse(BaseModel):
    priority: int = 0
    user_id: int = 1791800364
    subscribe: List[NoticeCache] = []
    apply: List[NoticeCache] = []
    tree: List[NoticeCache] = []


class DaoInfo(BaseModel):
    name: str = ""
    damage: int = 0
    score: int = 0
    type: str = ""
    date: int = 0
    boss: int = 0
    lap: int = 0
    dao_id: int = 0
    damage_rate: str = ""
    score_rate: str = ""
    dao: float = 0


class ReportResponse(BaseModel):
    priority: int = 0
    user_id: int = 1791800364
    name: str = ""
    all: List[DaoInfo] = []
    detail: List[DaoInfo] = []
    me: List[DaoInfo] = []


class SpecialNoticeForm(BaseModel):
    group_id: str
    boss: int
    notice_type: int
    lap: int
    user_id: int


class CorrectDaoInfo(BaseModel):
    type: str
    dao_id: int
    group_id: int


class ChangePasswordForm(BaseModel):
    new_password: str
    confirm_password: str


class BindClanForm(BaseModel):
    group_id: int
    group_name: str = "公会"


class UnbindClanForm(BaseModel):
    group_id: int
