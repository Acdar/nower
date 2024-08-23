
import sys

from arknights_mower.utils import path

if len(sys.argv) == 2:
        path.global_space = sys.argv[1]

from arknights_mower.utils import config

conf = config.conf
tray = conf.webview.tray
token = conf.webview.token
host = "0.0.0.0" if token else "127.0.0.1"

from arknights_mower.utils.email import send_message

send_message(
                "textarknights-mower推送测试",
                "基建报告",
                "INFO",
                None,
            )
# response = requests.get(
#             "http://sft.acdar.dev/message/push?pushkey=PDU1TAn8qbi7q3bEKnylNp0cFPPWhmBB9BwbN",
#             params={
#                 "text": "arknights-mower推送测试",
#                 "desp": "arknights-mower推送测试",
#             },
#         )
