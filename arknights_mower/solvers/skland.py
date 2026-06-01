import datetime
import os

import pandas as pd
import requests

from arknights_mower.utils import config
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path
from arknights_mower.utils.skland import (
    ak_sign_url,
    ef_sign_url,
    get_ak_binding_list,
    get_cred_by_token,
    get_ef_binding_list,
    get_ef_sign_header,
    get_sign_header,
    header,
    header_login,
    log,
    token_password_url,
)


class SKLand:
    def __init__(self):
        self.record_path = get_path("@app/tmp/skland.csv")
        self.record_path_ef = get_path("@app/tmp/skland_ef.csv")

        self.reward = []
        self.reward_ef = []

        self.sign_token = ""
        self.all_recorded = True
        self.all_recorded_ef = True

    def start(self):

        for item in config.conf.skland_info:
            ak_recorded = self.has_record(item.account, self.record_path)
            ef_recorded = False
            if hasattr(item, "sign_in_endfield") and item.sign_in_endfield:
                ef_recorded = self.has_record(item.account, self.record_path_ef)
            else:
                ef_recorded = True

            if ak_recorded and ef_recorded:
                continue

            self.all_recorded = self.all_recorded and ak_recorded
            self.all_recorded_ef = self.all_recorded_ef and ef_recorded

            self.save_param(get_cred_by_token(log(item)))

            if not ak_recorded:
                for i in get_ak_binding_list(self.sign_token):
                    body = {"gameId": 1, "uid": i.get("uid")}
                    resp = requests.post(
                        ak_sign_url,
                        headers=get_sign_header(
                            ak_sign_url, "post", body, self.sign_token, header
                        ),
                        json=body,
                    ).json()
                    if resp["code"] != 0:
                        self.reward.append(
                            {"nickName": item.account, "reward": resp.get("message")}
                        )
                        logger.info(f"{i.get('nickName')}：{resp.get('message')}")
                        continue
                    awards = resp["data"]["awards"]
                    for j in awards:
                        res = j["resource"]
                        self.reward.append(
                            {
                                "nickName": item.account,
                                "reward": "{}×{}".format(
                                    res["name"], j.get("count") or 1
                                ),
                            }
                        )
                        logger.info(
                            f"{i.get('nickName')}获得了{res['name']}×{j.get('count') or 1}"
                        )

            if (
                hasattr(item, "sign_in_endfield")
                and item.sign_in_endfield
                and not ef_recorded
            ):
                for i in get_ef_binding_list(self.sign_token):
                    role = i.get("defaultRole") or (i.get("roles") and i["roles"][0])
                    body = {
                        "gameId": 3,
                        "sk-game-role": f"3_{role['roleId']}_{role['serverId']}",
                    }
                    resp = requests.post(
                        ef_sign_url,
                        headers=get_ef_sign_header(
                            ef_sign_url, "post", body, self.sign_token, header
                        ),
                        json=body,
                    ).json()
                    if resp["code"] != 0:
                        self.reward_ef.append(
                            {"nickName": item.account, "reward": resp.get("message")}
                        )
                        logger.info(f"{role.get('nickName')}：{resp.get('message')}")
                        continue
                    awards_result = []
                    result_data: dict = resp["data"]
                    result_info_map: dict = result_data["resourceInfoMap"]
                    for a in result_data["awardIds"]:
                        award_id = a["id"]
                        awards = result_info_map[award_id]
                        award_name = awards["name"]
                        award_count = awards["count"]
                        awards_result.append(f"{award_name}×{award_count}")
                    logger.info(f"{role.get('nickName')}获得了{awards_result}")
        if len(self.reward) > 0 or len(self.reward_ef) > 0:
            return self.record_log()
        if self.all_recorded and self.all_recorded_ef:
            return True
        return False

    def save_param(self, cred_resp):
        header["cred"] = cred_resp["cred"]
        self.sign_token = cred_resp["token"]

    def log(self, account):
        r = requests.post(
            token_password_url,
            json={"phone": account.account, "password": account.password},
            headers=header_login,
        ).json()
        if r.get("status") != 0:
            raise Exception(f"获得token失败：{r['msg']}")
        return r["data"]["token"]

    def record_log(self):
        self.test_writecsv = True
        date_str = datetime.datetime.now().strftime("%Y/%m/%d")
        if self.reward:
            logger.info(f"存入{date_str}的明日方舟数据{self.reward}")
            try:
                for item in self.reward:
                    res_df = pd.DataFrame(item, index=[date_str])
                    res_df.to_csv(
                        self.record_path, mode="a", header=False, encoding="gbk"
                    )
            except Exception as e:
                logger.exception(e)

        if self.reward_ef:
            logger.info(f"存入{date_str}的终末地数据{self.reward_ef}")
            try:
                for item in self.reward_ef:
                    res_df = pd.DataFrame(item, index=[date_str])
                    res_df.to_csv(
                        self.record_path_ef, mode="a", header=False, encoding="gbk"
                    )
            except Exception as e:
                logger.exception(e)

        return True

    def has_record(self, phone: str, path: str):
        try:
            if os.path.exists(path) is False:
                logger.debug(f"无森空岛记录 {path}")
                return False
            df = pd.read_csv(path, header=None, encoding="gbk", on_bad_lines="skip")

            for item in df.iloc:
                if item[0] == datetime.datetime.now().strftime("%Y/%m/%d"):
                    if item[1].astype(str) == phone:
                        logger.info(f"{phone}在{path}今天签到过了")
                        return True
            return False
        except PermissionError:
            logger.info(f"{path}正在被占用")
        except pd.errors.EmptyDataError:
            return False

    # 用于测试连接
    def test_connect(self):
        res = []
        for item in config.conf.skland_info:
            if item.arknights_isCheck or item.endfield_isCheck:
                try:
                    self.save_param(get_cred_by_token(log(item)))
                    for i in get_ak_binding_list(self.sign_token):
                        if i["uid"]:
                            res.append(
                                "{}明日方舟连接成功".format(
                                    i["nickName"] + "({})".format(i["channelName"])
                                )
                            )
                    if hasattr(item, "sign_in_endfield") and item.sign_in_endfield:
                        for ef in get_ef_binding_list(self.sign_token):
                            if ef["uid"]:
                                res.append(
                                    "{}终末地连接成功".format(
                                        ef["defaultRole"]["nickname"]
                                        + "({})".format(ef["channelName"])
                                    )
                                )
                except Exception as e:
                    msg = "{}无法连接-{}".format(item.account, e)
                    logger.exception(msg)
                    res.append(msg)
        return res

    # 用于测试签到
    def test_sign(self):
        res = []

        try:
            for item in config.conf.skland_info:
                if (not item.account or not item.password) and (
                    item.arknights_isCheck or item.endfield_isCheck
                ):
                    res.append("账号{}配置不完整，请检查".format(item.account))
                    return res
            if bool(self.start()):
                for info in self.reward:
                    res.append(
                        "{}{}签到成功".format(
                            info.get("nickname") or info.get("nickName"),
                            info.get("game"),
                        )
                    )
                if not self.test_writecsv:
                    res.append(
                        "签到数据写入失败，可能是根目录下的tmp文件夹不存在或tmp/skland.csv被占用"
                    )
                    self.test_writecsv = True
                return res
        except Exception as e:
            msg = "测试出错-{}".format(e)
            logger.exception(msg)
            res.append(msg)
        res.append("勾选的账号今天均已签到~")
        return res
