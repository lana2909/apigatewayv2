from flask import Flask, request, render_template, redirect, url_for, jsonify
import boto3
import os
import requests
from dotenv import load_dotenv
import logging

# Load env
load_dotenv()

app = Flask(__name__)

# =========================
# ENV CONFIG
# =========================
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN")
AWS_REGION = os.getenv("AWS_REGION")
S3_BUCKET = os.getenv("S3_BUCKET_NAME")
API_URL = os.getenv("API_GATEWAY_URL")

# Logging path (EFS)
LOG_PATH = os.getenv("LOG_PATH", "/mnt/efs/log/app.log")

# =========================
# LOGGING CONFIG
# =========================
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("LKS-APP")

logger.info("===== APPLICATION STARTED =====")
logger.info(f"API_GATEWAY_URL={API_URL}")
logger.info(f"S3_BUCKET_NAME={S3_BUCKET}")
logger.info(f"AWS_REGION={AWS_REGION}")
logger.info(f"LOG_PATH={LOG_PATH}")

# =========================
# AWS CLIENT
# =========================
s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    aws_session_token=AWS_SESSION_TOKEN,
    region_name=AWS_REGION,
)

# =========================
# ROUTES
# =========================

@app.route("/")
def index():
    logger.info("Accessing index page")

    try:
        response = requests.get(API_URL, timeout=10)
        logger.info("Request to API Gateway success")
        users = response.json()
    except Exception as e:
        logger.error(f"Failed to fetch users from API Gateway: {str(e)}")
        users = []

    return render_template(
        "index.html",
        users=users,
        s3_bucket=f"https://{S3_BUCKET}.s3.{AWS_REGION}.amazonaws.com/"
    )

@app.route("/users", methods=["POST"])
def add_user():
    logger.info("Add user request received")

    name = request.form["name"]
    email = request.form["email"]
    institution = request.form["institution"]
    position = request.form["position"]
    phone = request.form["phone"]
    image = request.files["image"]

    logger.info(f"User data: {email} | {name}")

    # 1️⃣ Cek apakah email sudah ada
    try:
        check_response = requests.get(f"{API_URL}?email={email}", timeout=10)
        logger.info(f"Email check status: {check_response.status_code}")
    except Exception as e:
        logger.error(f"Email check failed: {str(e)}")
        return jsonify({"error": "API Gateway unreachable"}), 500

    if check_response.status_code == 409:
        logger.warning(f"Email already exists: {email}")
        return jsonify({"error": "Email already exists"}), 409

    # 2️⃣ Upload image ke S3
    image_url = ""
    if image:
        image_filename = f"users/{image.filename}"
        logger.info(f"Uploading image: {image_filename}")

        try:
            s3_client.upload_fileobj(image, S3_BUCKET, image_filename)
            image_url = f"https://{S3_BUCKET}.s3-{AWS_REGION}.amazonaws.com/{image_filename}"
            logger.info(f"Image uploaded: {image_url}")
        except Exception as e:
            logger.error(f"S3 upload failed: {str(e)}")
            return jsonify({"error": str(e)}), 500

    # 3️⃣ Simpan user ke DB via API Gateway
    user_data = {
        "name": name,
        "email": email,
        "institution": institution,
        "position": position,
        "phone": phone,
        "image_url": image_url,
    }

    logger.info(f"Sending user data to API Gateway: {email}")

    try:
        response = requests.post(API_URL, json=user_data, timeout=10)
        logger.info(f"API response status: {response.status_code}")
    except Exception as e:
        logger.error(f"POST to API Gateway failed: {str(e)}")
        return jsonify({"error": "Failed connect to API"}), 500

    if response.status_code == 409:
        logger.warning(f"API conflict email: {email}")
        return jsonify({"error": "Email already exists"}), 409

    logger.info(f"User created successfully: {email}")
    return redirect(url_for("index"))

@app.route("/users/<int:user_id>/delete", methods=["DELETE"])
def delete_user(user_id):
    logger.info(f"Delete user request: {user_id}")

    try:
        response = requests.delete(f"{API_URL}/{user_id}", timeout=10)
        logger.info(f"Delete status: {response.status_code}")
    except Exception as e:
        logger.error(f"Delete failed: {str(e)}")
        return jsonify({"error": "API unreachable"}), 500

    if response.status_code == 204:
        logger.info(f"User deleted: {user_id}")
        return jsonify({"message": "User deleted successfully"}), 200

    try:
        return jsonify(response.json()), response.status_code
    except Exception:
        logger.error("Unexpected empty response from API")
        return jsonify({"error": "Unexpected empty response"}), response.status_code

@app.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    logger.info(f"Get user: {user_id}")

    try:
        response = requests.get(f"{API_URL}/{user_id}", timeout=10)
        logger.info(f"Get user status: {response.status_code}")
        return jsonify(response.json()), response.status_code
    except Exception as e:
        logger.error(f"Get user failed: {str(e)}")
        return jsonify({"error": "API unreachable"}), 500

@app.route("/users/<int:user_id>", methods=["PUT", "PATCH"])
def update_user(user_id):
    logger.info(f"Update user: {user_id}")

    data = request.json
    try:
        response = requests.put(f"{API_URL}/{user_id}", json=data, timeout=10)
        logger.info(f"Update status: {response.status_code}")
    except Exception as e:
        logger.error(f"Update failed: {str(e)}")
        return jsonify({"error": "API unreachable"}), 500

    if response.status_code == 200:
        logger.info(f"User updated: {user_id}")
        return jsonify({"message": "User updated", "data": response.json()})
    else:
        logger.warning(f"Update failed status: {response.status_code}")
        return jsonify({"error": "Failed to update user"}), response.status_code

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    logger.info("Starting Flask server")
    app.run(debug=True, host='0.0.0.0', port=5000)
