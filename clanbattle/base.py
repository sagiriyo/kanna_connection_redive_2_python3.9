import time
from typing import Dict, List, Union

from hoshino.modules.priconne._pcr_data import CHARA_NAME

from ...convert2img.convert2img import grid2imgb64
from ..basedata import FilePath, stage_dict
from ..client.common import InventoryInfo
from ..database.models import RecordDao
from ..util.auto_boss import clan_boss_info
from ..util.text2img import image_draw
from ..util.tools import daoflag2str


async def units2workid(*args):
    return []


try:
    from ..fendao.timeaxis import units2workid
except Exception:
    units2workid = units2workid

run_path = str(FilePath.run_group.value)


def find_item(item_list: List[InventoryInfo], id: int) -> int:
    if item_list:
        for item in item_list:
            if item.id == id:
                return item.stock
    return 0


def float2int(num: float) -> Union[int, float]:
    # 去小数点后面的0
    return int(num) if num == int(num) else num


def format_time(time: float) -> str:
    time = int(time)
    time_str = ""
    if hour := time // 3600:
        time_str += f"{hour}小时"
    if minute := time % 3600 // 60:
        time_str += f"{minute}分钟"
    if second := time % 60:
        time_str += f"{second}秒"
    return time_str


def format_bignum(num: int) -> str:
    return f"{num // 10000}万" if num > 10000 else num


def format_precent(num: int) -> str:
    return "血皮" if num < 0.00005 else f"{num * 100:.2f}%"


def clanbattle_report(info: List[RecordDao], max_dao: int) -> tuple:
    all_damage = 0
    all_score = 0
    player_info = {
        player.pcrid: {
            "name": player.name,
            "knife": 0,
            "damage": 0,
            "score": 0,
        }
        for player in info
    }
    for player in info:
        player_info[player.pcrid]["knife"] += 1 if player.flag == 0 else 0.5
        player_info[player.pcrid]["damage"] += player.damage
        all_damage += player.damage
        boss_rate = clan_boss_info.get_boss_rate(player.lap, player.boss)
        player_info[player.pcrid]["score"] += boss_rate * player.damage
        all_score += boss_rate * player.damage
    players = [
        (
            pcr_id,
            player_info[pcr_id]["name"],
            min(float2int(player_info[pcr_id]["knife"]), max_dao),
            player_info[pcr_id]["damage"],
            int(player_info[pcr_id]["score"]),
        )
        for pcr_id in player_info
    ]
    players.sort(key=lambda x: x[4], reverse=True)
    return players, all_damage, int(all_score)


async def day_report(info: List[RecordDao], all_player: Dict[int, str]) -> dict:
    player_info = {
        player: {"name": all_player[player], "knife": 0} for player in all_player
    }
    for player in info:
        if player.pcrid not in player_info:
            player_info[player.pcrid] = {
                "name": player.name,
                "knife": 0,
            }
        player_info[player.pcrid]["knife"] += 1 if player.flag == 0 else 0.5
    return [
        (pcr_id, player_info[pcr_id]["name"], float2int(player_info[pcr_id]["knife"]))
        for pcr_id in player_info
    ]


async def get_stat(data: list) -> str:
    member_dao = []
    stat = {3: [], 2.5: [], 2: [], 1.5: [], 1: [], 0.5: [], 0: []}
    total = 0
    for member in data:
        name = member[1]
        dao = min(member[2], 3)
        stat[dao].append(name)
        total += dao
        member_dao.append(name)
    reply = ["以下是出刀次数统计：\n", f"总计出刀：{total}"]
    for k, v in stat.items():
        if len(v) > 0:
            reply.extend((f"\n----------\n以下是出了{k}刀的成员：", "|".join(v)))
    msg = "".join(reply)
    return image_draw(msg)


def cuidao(data: list) -> str:
    if member_dao := [member[1] for member in data if member[2] < 3]:
        msg = "以下是还没满三刀的人：\n" + "\n".join(member_dao)
        return image_draw(msg)
    return "今天所有刀都出啦。下班下班。"


async def get_cbreport(data: list, total_damage: int, total_score: int) -> str:
    reply = []
    for index, member in enumerate(data):
        name = member[1]
        knife = member[2]
        damage = member[3]
        score = member[4]
        rate_damage = f"{member[3]/total_damage*100:.2f}%"
        rate_score = f"{member[4]/total_score*100:.2f}%"
        reply.append(
            [
                str(index + 1),
                name,
                str(knife),
                str(damage),
                str(score),
                str(rate_damage),
                str(rate_score),
            ]
        )
    return grid2imgb64(
        reply, ["排名", "昵称", "出刀次数", "造成伤害", "分数", "伤害占比", "分数占比"]
    )


async def get_kpireport(data: list) -> str:
    return grid2imgb64(
        [
            [str(index + 1), member[1], str(member[0]), str(member[2]), str(member[3])]
            for index, member in enumerate(data)
        ],
        ["排名", "昵称", "游戏id", "等效出刀", "补正"],
    )


async def get_plyerreport(data: List[RecordDao]) -> str:
    reply = []
    knife = 0
    for dao in data:
        time_str = time.strftime("%Y/%m/%d-%H:%M:%S", time.localtime(dao.time))
        knife += 1 if dao.flag == 0 else 0.5
        item = daoflag2str(dao.flag)
        score = int(clan_boss_info.get_boss_rate(dao.lap, dao.boss) * dao.damage)
        reply.append(
            [
                time_str,
                str(knife),
                f"{dao.damage}",
                f"{dao.lap}周目{dao.boss}王",
                str(score),
                item,
                str(dao.battle_log_id),
            ]
        )
    return grid2imgb64(
        reply[::-1],
        ["日期", "出刀次数", "造成伤害", "BOSS", "得分", "类型", "出刀编号"],
    )


async def dao_detial(info: RecordDao) -> str:
    stage = clan_boss_info.lap2stage(info.lap)
    stage_num = stage_dict[stage]
    msg = f"{stage}面{stage_num}阶段，{info.lap}周目，{info.boss}王"
    if info.unit1:
        msg += f"\n{CHARA_NAME[info.unit1 // 100][0]} 星级:{info.unit1_rarity} RANK:{info.unit1_rank} 等级:{info.unit1_level} 专武:{info.unit1_unique_equip} 造成伤害:{info.unit1_damage}"
    if info.unit2:
        msg += f"\n{CHARA_NAME[info.unit2 // 100][0]} 星级:{info.unit2_rarity} RANK:{info.unit2_rank} 等级:{info.unit2_level} 专武:{info.unit2_unique_equip} 造成伤害:{info.unit2_damage}"
    if info.unit3:
        msg += f"\n{CHARA_NAME[info.unit3 // 100][0]} 星级:{info.unit3_rarity} RANK:{info.unit3_rank} 等级:{info.unit3_level} 专武:{info.unit3_unique_equip} 造成伤害:{info.unit3_damage}"
    if info.unit4:
        msg += f"\n{CHARA_NAME[info.unit4 // 100][0]} 星级:{info.unit4_rarity} RANK:{info.unit4_rank} 等级:{info.unit4_level} 专武:{info.unit4_unique_equip} 造成伤害:{info.unit4_damage}"
    if info.unit5:
        msg += f"\n{CHARA_NAME[info.unit5 // 100][0]} 星级:{info.unit5_rarity} RANK:{info.unit5_rank} 等级:{info.unit5_level} 专武:{info.unit5_unique_equip} 造成伤害:{info.unit5_damage}"

    predict_work = await units2workid(
        [info.unit1, info.unit2, info.unit3, info.unit4, info.unit5],
        stage_num,
        info.boss,
    )
    msg += "\n可能作业：" + (str(predict_work) if predict_work else "未收录轴")
    return msg
