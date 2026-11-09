import csv
import datetime
import os

import requests

from arknights_mower.utils import config, csv_utils
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path
from arknights_mower.utils.skland import (
    ak_sign_url,
    ef_sign_url,
    get_binding_list,
    get_cred_by_token,
    get_ef_sign_header,
    get_sign_header,
    header,
    header_login,
    log,
    token_password_url,
)
from arknights_mower.utils.skland_log import redact_signing_text


class SKLand:
    def __init__(self):
        self.record_path = get_path("@app/tmp/skland.csv")
        self.record_path_ef = get_path("@app/tmp/skland_ef.csv")

        self.reward = []
        self.reward_ef = []

        self.sign_token = ""
        self.all_recorded = True
        self.all_recorded_ef = True
        self._log_secrets = set()

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

            self._log_secrets.add(item.account)
            login_token = log(item)
            if login_token:
                self._log_secrets.add(login_token)
            self.save_param(get_cred_by_token(login_token))

            if not ak_recorded:
                for i in get_binding_list(self.sign_token):
                    if i.get("gameId") != 1 or not i.get("uid"):
                        continue
                    if nickname := i.get("nickName"):
                        self._log_secrets.add(nickname)
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
                            {
                                "nickName": item.account,
                                "game": "明日方舟{}".format(i.get("channelName")),
                                "reward": resp.get("message"),
                                "status": "failure",
                                "code": resp["code"],
                            }
                        )
                        logger.info(
                            "明日方舟签到失败（状态码：%s）：%s",
                            resp["code"] if isinstance(resp["code"], int) else "未知",
                            redact_signing_text(
                                resp.get("message", ""),
                                self.sign_token,
                                *self._log_secrets,
                            ),
                        )
                        continue
                    awards = resp["data"]["awards"]
                    for j in awards:
                        res = j["resource"]
                        self.reward.append(
                            {
                                "nickName": item.account,
                                "game": "明日方舟{}".format(i.get("channelName")),
                                "reward": "{}×{}".format(
                                    res["name"], j.get("count") or 1
                                ),
                                "status": "success",
                                "code": resp["code"],
                            }
                        )
                        logger.info(
                            f"明日方舟{i.get('channelName')}签到获得了{res['name']}×{j.get('count') or 1}"
                        )

            if (
                hasattr(item, "sign_in_endfield")
                and item.sign_in_endfield
                and not ef_recorded
            ):
                for i in get_binding_list(self.sign_token):
                    if i.get("gameId") != 3:
                        continue
                    role = i.get("defaultRole") or (i.get("roles") and i["roles"][0])
                    if not role:
                        continue
                    if nickname := role.get("nickname"):
                        self._log_secrets.add(nickname)
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
                            {
                                "nickName": item.account,
                                "game": "终末地{}".format(i.get("channelName")),
                                "reward": resp.get("message"),
                                "status": "failure",
                                "code": resp["code"],
                            }
                        )
                        logger.info(
                            "终末地签到失败（状态码：%s）：%s",
                            resp["code"] if isinstance(resp["code"], int) else "未知",
                            redact_signing_text(
                                resp.get("message", ""),
                                self.sign_token,
                                *self._log_secrets,
                            ),
                        )
                        continue
                    result_data: dict = resp["data"]
                    result_info_map: dict = result_data["resourceInfoMap"]
                    for a in result_data["awardIds"]:
                        res = result_info_map[a["id"]]
                        self.reward_ef.append(
                            {
                                "nickName": item.account,
                                "game": "终末地{}".format(i.get("channelName")),
                                "reward": "{}×{}".format(
                                    res["name"], res.get("count") or 1
                                ),
                                "status": "success",
                                "code": resp["code"],
                            }
                        )
                        logger.info(
                            f"终末地{i.get('channelName')}签到获得了{res['name']}×{res.get('count') or 1}"
                        )
        if len(self.reward) > 0 or len(self.reward_ef) > 0:
            return self.record_log()
        if self.all_recorded:
            return True
        return False

    def save_param(self, cred_resp):
        header["cred"] = cred_resp["cred"]
        self.sign_token = cred_resp["token"]
        self._log_secrets.update((cred_resp["cred"], cred_resp["token"]))

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
        reward_ef = getattr(self, "reward_ef", [])
        entries = [*self.reward, *reward_ef]
        secrets = self._log_secrets | {
            entry.get("nickname") or entry.get("nickName")
            for entry in entries
            if entry.get("nickname") or entry.get("nickName")
        }
        safe_entries = [
            {
                key: value
                if key == "code" and isinstance(value, int)
                else redact_signing_text(value, *secrets)
                for key, value in entry.items()
            }
            for entry in entries
        ]
        logger.debug("%s的森空岛签到结果：%s", date_str, safe_entries)
        targets = [(self.record_path, self.reward)]
        record_path_ef = getattr(self, "record_path_ef", None)
        if record_path_ef and reward_ef:
            targets.append((record_path_ef, reward_ef))
        for path, records in targets:
            if not records:
                continue
            try:
                for record in records:
                    csv_utils.append_dated_row(
                        path,
                        date_str,
                        record,
                        header=False,
                        encoding="gbk",
                    )
            except Exception as e:
                self.test_writecsv = False
                logger.error("森空岛签到记录写入失败（%s）", type(e).__name__)
        lines = [
            f"已保存 {date_str} 的森空岛签到记录，共 {len(entries)} 条："
            if self.test_writecsv
            else f"{date_str} 的森空岛签到记录保存失败，本次签到结果如下："
        ]
        accounts = {}
        for original, safe in zip(entries, safe_entries):
            account = original.get("nickname") or original.get("nickName")
            accounts.setdefault(account, []).append(safe)
        for results in accounts.values():
            account = results[0].get("nickname") or results[0].get("nickName")
            lines.append(f"    账号 {account or '未标明账号'}：")
            for result in results:
                game = result.get("game", "未标明游戏")
                reward = result.get("reward") or "未返回结果"
                if result.get("status") == "success" and result.get("code") == 0:
                    outcome = f"签到成功，{reward}"
                elif result.get("status") == "failure":
                    outcome = f"签到失败，{reward}"
                else:
                    outcome = f"签到结果，{reward}"
                lines.append(f"        {game}：{outcome}")
        logger.info("%s", "\n".join(lines))
        return True

    def has_record(self, phone: str, path: str):
        try:
            if os.path.exists(path) is False:
                logger.debug(f"无森空岛记录 {path}")
                return False
            today = datetime.datetime.now().strftime("%Y/%m/%d")
            with open(path, encoding="gbk", newline="") as f:
                for row in csv.reader(f):
                    if len(row) < 2:
                        continue
                    if row[0] == today and str(row[1]) == phone:
                        logger.info(f"{phone}在{path}今天签到过了")
                        return True
            return False
        except PermissionError:
            logger.info(f"{path}正在被占用")
            return False
        except (csv.Error, UnicodeDecodeError, OSError):
            return False

    # 用于测试连接
    def test_connect(self):
        res = []
        for item in config.conf.skland_info:
            if item.arknights_isCheck or item.endfield_isCheck:
                try:
                    self.save_param(get_cred_by_token(log(item)))
                    for i in get_binding_list(self.sign_token):
                        if i.get("gameId") == 1 and i.get("uid"):
                            res.append(
                                "{}明日方舟连接成功".format(
                                    i["nickName"] + "({})".format(i["channelName"])
                                )
                            )
                    if hasattr(item, "sign_in_endfield") and item.sign_in_endfield:
                        for ef in get_binding_list(self.sign_token):
                            if ef.get("gameId") != 3 or not ef.get("uid"):
                                continue
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
                entries = [*self.reward, *getattr(self, "reward_ef", [])]
                if entries:
                    for info in entries:
                        res.append(
                            "{}{}签到成功".format(
                                info.get("nickname") or info.get("nickName"),
                                info.get("game"),
                            )
                        )
                    if not self.test_writecsv:
                        res.append("签到数据写入失败")
                        self.test_writecsv = True
                else:
                    res.append("勾选的账号今天均已签到~")
                return res
            else:
                res.append("签到未完成，请检查账号配置或网络")
                return res
        except Exception as e:
            msg = "测试出错-{}".format(e)
            logger.error(
                "森空岛测试签到失败（%s）：%s",
                type(e).__name__,
                redact_signing_text(e, *self._log_secrets),
            )
            res.append(msg)
        return res
