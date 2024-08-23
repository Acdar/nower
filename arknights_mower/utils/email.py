import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from threading import Thread
from time import sleep
from typing import Literal, Optional

import cv2
from jinja2 import Environment, FileSystemLoader, select_autoescape

from arknights_mower.utils import config
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.log import logger

from arknights_mower.utils import config
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.image import img2bytes
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path

from markdownify import markdownify as md
import requests
import tinify

tinify.key = "7mPMFzdQw7CNNwv51QCc4QdgrgYHvb7h"
template_dir = get_path("@internal/arknights_mower/templates")
env = Environment(loader=FileSystemLoader(template_dir), autoescape=select_autoescape())

task_template = env.get_template("task.html")
maa_template = env.get_template("maa.html")
recruit_template = env.get_template("recruit_template.html")
recruit_rarity = env.get_template("recruit_rarity.html")
report_template = env.get_template("report_template.html")
version_template = env.get_template("version.html")


class Email:
    def __init__(self, body, subject, attach_image):
        conf = config.conf
        msg = MIMEMultipart()
        msg.attach(MIMEText(body, "html"))
        msg["Subject"] = subject
        msg["From"] = conf.account
        msg["To"] = ", ".join(conf.recipient)

        if attach_image is not None:
            if not conf.server_push_enable:
                attachment = img2bytes(attach_image)
                image_content = MIMEImage(attachment.tobytes())
                image_content.add_header(
                    "Content-Disposition", "attachment", filename="image.jpg"
                )
                msg.attach(image_content)
        self.msg = msg

        if conf.custom_smtp_server.enable:
            self.smtp_server = conf.custom_smtp_server.server
            self.port = conf.custom_smtp_server.ssl_port
            self.encryption = conf.custom_smtp_server.encryption
        else:
            self.smtp_server = "smtp.qq.com"
            self.port = 465
            self.encryption = "tls"

    def send(self):
        if self.encryption == "starttls":
            s = smtplib.SMTP(self.smtp_server, self.port, timeout=10)
            s.starttls()
        else:
            s = smtplib.SMTP_SSL(self.smtp_server, self.port, timeout=10)
        conf = config.conf
        if conf.mail_enable:
            s.login(conf.account, conf.pass_code)
            recipient = conf.recipient or [conf.account]
            s.send_message(self.msg, conf.account, recipient)
            s.quit()


def send_message(
    body="",
    subject="",
    level: Literal["INFO", "WARNING", "ERROR"] = "INFO",
    attach_image: Optional[tp.Image] = None,
):
    """异步发送邮件

    Args:
        body: 邮件内容
        subject: 邮件标题
        level: 通知等级
        attach_image: 图片附件
    """
    conf = config.conf
    if conf.notification_level == "WARNING" and level == "INFO":
        return
    if conf.notification_level == "ERROR" and level != "ERROR":
        return
    if subject == "":
        subject = body.split("\n")[0].strip()
    subject = conf.mail_subject + subject
    email = None
    if conf.mail_enable:
        email = Email(body, subject, attach_image)
    if conf.server_push_enable:
        send_key = conf.sendKey
        url = f"http://sft.acdar.dev/message/push?pushkey={send_key}"
        body = md(body)
        if attach_image is not None:
            image_url = upload_message(attach_image)
            body += f'\n\n![Image]({image_url})'

        try:
            response = requests.post(
                url,
                json={
                    "text": subject, 
                    "desp": body,
                }
            ).json()
            if response["code"] != 0:
                logger.error(f"pushdeer通知发送失败：{response['message']}")
        except Exception as e:
            logger.exception("pushdeer通知发送失败：" + str(e))
    if email:
        def send_message_sync(email):
            for i in range(3):
                try:
                    email.send()
                    break
                except Exception as e:
                    logger.exception("邮件发送失败：" + str(e))
                    sleep(2**i)

        Thread(target=send_message_sync, args=(email,)).start()

def upload_message(image):
    try:
        # 将图像转换为字节格式
        _, image_buffer = cv2.imencode('.png', image)
        compressed_image = tinify.from_buffer(image_buffer.tobytes()).to_buffer()
        # 上传到服务器
        files = {
            'file': ('image.png', compressed_image, 'image/png')
        }
        response = requests.post("https://photo.acdar.dev/upload", files=files)
        if response.status_code == 200:
            return "https://photo.acdar.dev"+response.json()[0]["src"]
    except Exception as e:
            logger.exception("图片上传失败" + str(e))
