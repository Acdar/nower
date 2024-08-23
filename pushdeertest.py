
import cv2
import requests
from arknights_mower.utils.email import send_message
import tinify
from PIL import Image

from arknights_mower.utils.image import img2bytes
tinify.key = "7mPMFzdQw7CNNwv51QCc4QdgrgYHvb7h"
send_message(
                "<table><tr><th>时间</th><th>任务</th><th>备注</th></tr><tr><td>23:06:14</td> <td>肥鸭</td> <td></td></tr><tr><td>23:58:35</td><td>B101</td><td>但书, Current</td></tr><tr><td>00:08:12</td><td>B201</td><td>但书, Current</td></tr><tr><td>03:51:17</td><td>会客室</td><td>伊内丝, Current</td></tr><tr><td>13:26:22</td><td>趴体</td><td></td></tr></table>",
                "基建报告",
                "INFO",
                cv2.imread("D:/Program Files/Ark/mower source/arknights-mower/screenshot/1723571242613789700.jpg")
        )
# headers = {
#         "Authorization": "Bearer 2|fL9p8af352BdPSCWGqJySas29zCe3vqnm2pb4yCr",
#         "Accept": "application/json",
#         "Content-Type": "multipart/form-data",
# }
# with open("D:/Program Files/Ark/mower source/arknights-mower/screenshot/8/20240705133422.png", "rb") as image_file:
#         data = {
#                 'file': tinify.from_buffer(image_file.read()).to_buffer(),
#         }
# response = requests.post("https://photo.acdar.dev/upload",  files=data)
# if response.status_code == 200:
#         print (response.text)
#         print ("https://photo.acdar.dev"+response.json()[0]["src"])

# response = requests.get(
#         "http://sft.acdar.dev/message/push?pushkey=PDU1TAn8qbi7q3bEKnylNp0cFPPWhmBB9BwbN",
#         params={
#                 "text": "arknights-mower推送测试",
#                 "desp": "arknights-mower推送测试",
#         },
#         )
