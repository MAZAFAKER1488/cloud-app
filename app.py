import os
import socket
import uuid
from datetime import datetime, timezone

import boto3
from botocore.config import Config
from flask import Flask, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

TABLE_NAME = os.environ["TABLE_NAME"]
BUCKET_NAME = os.environ["BUCKET_NAME"]
REGION = os.environ.get("AWS_REGION", "us-east-1")
APP_TITLE = os.environ.get("APP_TITLE", "Облачный каталог")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)
s3 = boto3.client("s3", region_name=REGION, config=Config(signature_version="s3v4"))

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


@app.route("/")
def index():
    response = table.scan()
    items = response["Items"]
    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response["Items"])
    items.sort(key=lambda i: i.get("created_at", ""), reverse=True)
    for item in items:
        key = item.get("file_key")
        if key:
            item["file_url"] = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": BUCKET_NAME, "Key": key},
                ExpiresIn=300,
            )
    return render_template("index.html", title=APP_TITLE, items=items, host=socket.gethostname())


@app.route("/add", methods=["POST"])
def add():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    if not title:
        return redirect(url_for("index"))
    item_id = str(uuid.uuid4())
    item = {
        "id": item_id,
        "title": title,
        "description": description,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }
    file = request.files.get("file")
    if file and file.filename:
        name = secure_filename(file.filename) or "file"
        key = f"uploads/{item_id}/{name}"
        s3.upload_fileobj(
            file, BUCKET_NAME, key,
            ExtraArgs={"ContentType": file.mimetype or "application/octet-stream"},
        )
        item["file_key"] = key
        item["file_name"] = name
    table.put_item(Item=item)
    return redirect(url_for("index"))


@app.route("/health")
def health():
    return "ok", 200
