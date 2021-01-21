import time
import json
import boto3
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, FlexSendMessage

LINE_CHANNNEL_ACCES_TOKEN = "gf0oOfj7l+UGJKB8I1slxuzwQlfb8tEz6vWYdWUEiRtuf5yG4SWQjT02Y+j4IUoA9UDqIsJUrOMqXRVFcZ208oj4QsYsGVEFZlPm/0yf1yqQoRCkudrEegcaNW5fTbEsHxqkJIfzGniKcxBk5AaEaQdB04t89/1O/w1cDnyilFU="
LINE_CHANNEL_SECRET = "2c13b6fe2cd19c6ee4b62c53a82010b8"
AWS_S3_BUCKET_NAME = "asahi-line-bot-backet"
QUESTIONNAIRE_INTERVAL = 600

line_bot_api = LineBotApi(LINE_CHANNNEL_ACCES_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)
s3 = boto3.resource('s3')
bucket = s3.Bucket(AWS_S3_BUCKET_NAME)

# EB looks for an 'application' callable by default.
application = Flask(__name__)

@application.route('/')
def index():
    return "Hello"

@application.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']
    # get request body as text
    body = request.get_data(as_text=True)
    application.logger.info("Request body: " + body)
    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    message_text = event.message.text
    user_id = event.source.user_id
    profile = line_bot_api.get_profile(user_id)
    display_name = profile.display_name
    running_status_json_key = "running_status_{}.json".format(display_name)
    running_status_obj = s3.Object(AWS_S3_BUCKET_NAME, running_status_json_key)
    running_status = {'running': False}
    running_status_obj.put(Body = json.dumps(running_status, indent=4))
    # running_status_byte_obj = running_status_obj.get()['Body'].read().decode('utf-8')
    # running_status_json_obj = json.loads(running_status_byte_obj)
    # running = running_status_json_obj["running"]
    log_json_key = "log_{}.json".format(display_name)
    log_obj = s3.Object(AWS_S3_BUCKET_NAME, log_json_key)
    if message_text == "開始" and not running:
        running_status = {'running': True}
        running_status_obj.put(Body = json.dumps(running_status, indent=4))
        if not exists_s3_obj_key(log_json_key):
            log_json = []
            log_obj.put(Body = json.dumps(log_json, indent=4))
        flex_message_key = "flex_message.json"
        flex_message_obj = s3.Object(AWS_S3_BUCKET_NAME, flex_message_key)
        flex_message_byte_obj = flex_message_obj.get()['Body'].read().decode('utf-8')
        flex_message_json_obj = json.loads(flex_message_byte_obj)
        flex_message = FlexSendMessage(alt_text="sleepiness_logging", contents=flex_message_json_obj)
        while True:
            running_status_byte_obj = running_status_obj.get()['Body'].read().decode('utf-8')
            running_status_json_obj = json.loads(running_status_byte_obj)
            running = running_status_json_obj["running"]
            if running:
                line_bot_api.push_message(user_id, flex_message)
                time.sleep(QUESTIONNAIRE_INTERVAL)
            else:
                break
    elif message_text == "終了":
        running_status_json = {'running': False}
        running_status_obj.put(Body = json.dumps(running_status_json, indent=4))
        message = TextSendMessage(text="回答ありがとうございました!\nお疲れ様でした!!")
        line_bot_api.push_message(user_id, message)
    elif message_text in "01":
        current_unix_time = time.time()
        log_json_key = "log_{}.json".format(display_name)
        log_obj = s3.Object(AWS_S3_BUCKET_NAME, log_json_key)
        log_byte_obj = log_obj.get()['Body'].read().decode('utf-8')
        log_json = json.loads(log_byte_obj)
        log_json = [
            *log_json,
            {
                "answered_at": current_unix_time, 
                "value": message_text,
            }
        ]
        log_obj.put(Body = json.dumps(log_json, indent=4))
        message = TextSendMessage(text="回答ありがとうございます...!!!")
        line_bot_api.push_message(user_id, message)
    else:
        running_status_byte_obj = running_status_obj.get()['Body'].read().decode('utf-8')
        running_status_json_obj = json.loads(running_status_byte_obj)
        running = running_status_json_obj["running"]
        if running:
            message = TextSendMessage(text="とっても残念ですが無効な回答です...\n回答を終了する場合は「終了」と送ってくださいね。")
        else:
            message = TextSendMessage(text="回答を始める場合は「開始」と送ってくださいね。")
        line_bot_api.push_message(user_id, message)

def exists_s3_obj_key(key):
    objs = list(bucket.objects.filter(Prefix=key))
    if len(objs) > 0 and objs[0].key == key:
        return True
    else:
        return False

# run the app.
if __name__ == "__main__":
    # Setting debug to True enables debug output. This line should be
    # removed before deploying a production app.
    application.debug = True
    application.run()