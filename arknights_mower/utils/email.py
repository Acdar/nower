import os
import smtplib
from datetime import datetime, timedelta
from email import encoders
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from threading import Thread
from time import monotonic, sleep
from typing import Literal, Optional

import cv2
import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

try:
    import tinify
except ImportError:
    # tinify / markdownify 都是发通知时才用到的可选依赖，缺失时不能让 import email
    # 失败：email 位于 __main__ → base_schedule → credit → graph → solver 的导入链上，
    # 缺一个可选包会让「开始执行」直接 500 且不留任何日志。
    tinify = None

try:
    from markdownify import markdownify as md
except ImportError:
    md = None

from arknights_mower.utils import config, log
from arknights_mower.utils import typealias as tp
from arknights_mower.utils.image import img2bytes
from arknights_mower.utils.log import logger
from arknights_mower.utils.path import get_path

if tinify is not None:
    tinify.key = "7mPMFzdQw7CNNwv51QCc4QdgrgYHvb7h"
template_dir = get_path("@internal/arknights_mower/templates")
env = Environment(loader=FileSystemLoader(template_dir), autoescape=select_autoescape())

task_template = env.get_template("task.html")
maa_template = env.get_template("maa.html")
recruit_template = env.get_template("recruit_template.html")
recruit_rarity = env.get_template("recruit_rarity.html")
report_template = env.get_template("report_template.html")
version_template = env.get_template("version.html")
notification_template = env.get_template("notification.html")

_SCREENSHOT_MAX_BYTES = 1024 * 1024
_SCREENSHOT_MAX_AGE = 30
_SCREENSHOT_FUTURE_GRACE = 1
_BADGE_COLORS = {
    "INFO": ("#e6f5ec", "#0c7a43"),
    "WARNING": ("#fef3c7", "#b45309"),
    "ERROR": ("#fee2e2", "#b91c1c"),
}


class Email:
    def __init__(
        self,
        body,
        subject,
        attach_image,
        attach_files=None,
        *,
        inline_image=None,
        configuration=None,
    ):
        conf = configuration if configuration is not None else config.conf
        self.account = conf.account
        self.pass_code = conf.pass_code
        self.recipients = tuple(
            address for address in conf.recipient if address.strip()
        )
        msg = MIMEMultipart()
        if inline_image is None:
            msg.attach(MIMEText(body, "html"))
        else:
            related = MIMEMultipart("related")
            related.attach(MIMEText(body, "html"))
            related.attach(inline_image)
            msg.attach(related)
        msg["Subject"] = subject
        msg["From"] = conf.account
        msg["To"] = ", ".join(conf.recipient)

        if attach_image is not None:
            attachment = img2bytes(attach_image)
            image_content = MIMEImage(attachment.tobytes())
            image_content.add_header(
                "Content-Disposition", "attachment", filename="image.jpg"
            )
            msg.attach(image_content)

        if attach_files:
            for file_path in attach_files:
                if os.path.isfile(file_path):
                    with open(file_path, "rb") as file:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(file.read())
                        encoders.encode_base64(part)
                        part.add_header(
                            "Content-Disposition",
                            "attachment",
                            filename=os.path.basename(file_path),
                        )
                        msg.attach(part)

        self.msg = msg

        if conf.custom_smtp_server.enable:
            self.smtp_server = conf.custom_smtp_server.server
            self.port = conf.custom_smtp_server.ssl_port
            self.encryption = conf.custom_smtp_server.encryption
        else:
            self.smtp_server = "smtp.qq.com"
            self.port = 465
            self.encryption = "tls"

    def send(self, recipient=None):
        if self.encryption == "starttls":
            s = smtplib.SMTP(self.smtp_server, self.port, timeout=10)
            s.starttls()
        else:
            s = smtplib.SMTP_SSL(self.smtp_server, self.port, timeout=10)
        s.login(self.account, self.pass_code)
        if not recipient:
            recipient = list(self.recipients) or [self.account]
        s.send_message(self.msg, self.account, recipient)
        s.quit()


def _notification_screenshot(notification_at, conf, screenshot_source):
    try:
        owner = getattr(screenshot_source, "_screenshot_owner", None)
        if owner is None:
            return None, None
        store = log.get_screenshot_store()
        frame = store.latest() if store is not None else None
        if frame is None:
            return None, None
        if (
            frame.capture_owner is not owner
            or frame.configuration_ref is None
            or frame.configuration_ref() is not conf
        ):
            return None, None
        if frame.capture_started_at is None or frame.capture_wall_ns is None:
            return None, None
        age = notification_at - frame.capture_started_at
        if not -_SCREENSHOT_FUTURE_GRACE <= age <= _SCREENSHOT_MAX_AGE:
            return None, None
        if (
            not isinstance(frame.data, bytes)
            or not 0 < len(frame.data) <= _SCREENSHOT_MAX_BYTES
        ):
            return None, None
        image = MIMEImage(frame.data)
        subtype = image.get_content_subtype()
        if subtype not in ("jpeg", "png"):
            return None, None
        image.add_header("Content-ID", "<mower-screenshot>")
        extension = "jpg" if subtype == "jpeg" else "png"
        image.add_header(
            "Content-Disposition", "inline", filename=f"screenshot.{extension}"
        )
        captured = datetime.fromtimestamp(frame.capture_wall_ns / 10**9) + timedelta(
            hours=getattr(conf, "timezone_offset", 0)
        )
        return image, captured.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as exc:
        logger.warning("无法读取邮件截图：%s", exc)
        return None, None


def render_notification(
    body,
    title,
    level="INFO",
    *,
    body_is_html=False,
    has_screenshot=False,
    screenshot_time=None,
):
    if body_is_html:
        body_html = Markup(body)
    else:
        lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        body_html = Markup("<br>").join(escape(line) for line in lines)
    badge_bg, badge_text = _BADGE_COLORS.get(level, _BADGE_COLORS["INFO"])
    return notification_template.render(
        title=title,
        level=level,
        badge_bg=badge_bg,
        badge_text=badge_text,
        body=body_html,
        has_screenshot=has_screenshot,
        screenshot_time=screenshot_time,
    )


def send_message(
    body="",
    subject="",
    level: Literal["INFO", "WARNING", "ERROR"] = "INFO",
    attach_image: Optional[tp.Image] = None,
    *,
    archive_screenshots: bool = False,
    body_is_html: bool = False,
    screenshot_source=None,
):
    """错误通知先写日志，画面相关异常显式归档，再按配置异步发送邮件。

    Args:
        body: 邮件内容
        subject: 邮件标题
        level: 通知等级
        attach_image: 图片附件
        archive_screenshots: 画面相关异常可请求归档或附带截图
        body_is_html: 正文为可信的模板片段
        screenshot_source: 产生当前画面的设备
    """
    notification_at = monotonic()
    conf = config.conf
    if level == "ERROR":
        detail = f"{subject}：{body}" if subject and body else subject or body
        logger.error("%s", detail, extra={"archive_screenshots": archive_screenshots})
    notification_level = getattr(conf, "notification_level", "INFO")
    if notification_level == "WARNING" and level == "INFO":
        return
    if notification_level == "ERROR" and level != "ERROR":
        return
    if subject == "":
        subject = body.split("\n")[0].strip()
    title = subject
    subject = getattr(conf, "mail_subject", "") + title

    email = None
    if getattr(conf, "mail_enable", False):
        inline_image, screenshot_time = None, None
        if (
            getattr(conf, "mail_attach_error_screenshot", False)
            and level in ("WARNING", "ERROR")
            and archive_screenshots
            and screenshot_source is not None
        ):
            inline_image, screenshot_time = _notification_screenshot(
                notification_at, conf, screenshot_source
            )
        rendered = render_notification(
            body,
            title,
            level,
            body_is_html=body_is_html,
            has_screenshot=inline_image is not None,
            screenshot_time=screenshot_time,
        )
        email = Email(
            rendered,
            subject,
            attach_image,
            inline_image=inline_image,
            configuration=conf,
        )
    if getattr(conf, "server_push_enable", False):

        def send_pushdeer_sync():
            send_key = getattr(conf, "sendKey", "")
            url = f"https://sft.acdar.dev/message/push?pushkey={send_key}"
            push_body = md(body) if md is not None else body
            if attach_image is not None:
                image_url = upload_message(attach_image)
                if image_url:
                    push_body += f"\n\n![Image]({image_url})"

            try:
                response = requests.post(
                    url,
                    json={
                        "text": subject,
                        "desp": push_body,
                    },
                ).json()
                if response["code"] != 0:
                    logger.error(f"pushdeer通知发送失败：{response['message']}")
            except Exception as e:
                logger.exception("pushdeer通知发送失败：" + str(e))

        Thread(target=send_pushdeer_sync).start()
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
    if tinify is None:
        # 没有 tinify 就不压缩也不上传，消息正文少一张图，比整个 mower 起不来好得多。
        logger.warning("未安装 tinify，跳过推送图片上传")
        return None
    try:
        # 将图像转换为字节格式
        _, image_buffer = cv2.imencode(".png", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
        compressed_image = tinify.from_buffer(image_buffer.tobytes()).to_buffer()
        # 上传到服务器
        files = {"file": ("image.png", compressed_image, "image/png")}
        response = requests.post("https://photo.acdar.dev/upload", files=files)
        if response.status_code == 200:
            return "https://photo.acdar.dev" + response.json()[0]["src"]
    except Exception as e:
        logger.exception("图片上传失败" + str(e))
