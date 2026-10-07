import json, os, time, logging
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
TOPIC = os.getenv("MQTT_TOPIC", "iot/lab2/+/telemetry")
INFLUX_URL = os.getenv("INFLUX_URL", "http://localhost:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "my-super-token")
INFLUX_ORG = os.getenv("INFLUX_ORG", "iotlab")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "iot")

# Khoảng giá trị hợp lệ của từng cảm biến
RANGES = {"temperature": (-40, 80), "humidity": (0, 100), "distance_cm": (2, 400)}
FIELDS = ("temperature", "humidity", "distance_cm", "rssi", "seq")

influx = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
write_api = influx.write_api(write_options=SYNCHRONOUS)
last_seq = {}
stats = {"ok": 0, "bad": 0, "lost": 0}


def validate(p):
    for k in ("device_id", "ts"):
        if k not in p:
            return False, f"thiếu {k}"
    for k, (lo, hi) in RANGES.items():
        if k in p and not (lo <= p[k] <= hi):
            return False, f"{k} ngoài khoảng: {p[k]}"
    return True, ""


def on_connect(client, userdata, flags, reason_code, properties):
    logging.info("Đã kết nối MQTT (%s), subscribe %s", reason_code, TOPIC)
    client.subscribe(TOPIC, qos=1)        # subscribe lại mỗi lần kết nối lại


def on_message(client, userdata, msg):
    recv = int(time.time() * 1000)
    try:
        p = json.loads(msg.payload)
    except json.JSONDecodeError:
        stats["bad"] += 1
        logging.warning("JSON lỗi: %r", msg.payload[:80])
        return

    ok, err = validate(p)
    if not ok:
        stats["bad"] += 1
        logging.warning("Bỏ gói: %s", err)
        return

    dev = p["device_id"]
    if "seq" in p:                         # phát hiện mất gói
        if dev in last_seq and p["seq"] > last_seq[dev] + 1:
            lost = p["seq"] - last_seq[dev] - 1
            stats["lost"] += lost
            logging.warning("Mất %d gói", lost)
        last_seq[dev] = p["seq"]

    pt = Point("sensor_raw").tag("device_id", dev).time(p["ts"], WritePrecision.MS)
    for k in FIELDS:
        if k in p:
            pt.field(k, float(p[k]))
    pt.field("latency_ms", float(recv - p["ts"]))

    try:
        write_api.write(bucket=INFLUX_BUCKET, record=pt)
        stats["ok"] += 1
        if stats["ok"] % 10 == 0:
            logging.info("Đã ghi %d | lỗi %d | mất %d", stats["ok"], stats["bad"], stats["lost"])
    except Exception as e:
        logging.error("Ghi DB lỗi: %s", e)


# client_id cố định + clean_session=False: broker giữ tin QoS 1 khi subscriber offline
c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                client_id="lab2-subscriber", clean_session=False)
c.on_connect = on_connect
c.on_message = on_message
c.connect(MQTT_HOST, MQTT_PORT)
c.loop_forever()