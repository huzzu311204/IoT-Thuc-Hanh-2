import json, time, random
import paho.mqtt.client as mqtt

c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
c.connect("localhost", 1883)
c.loop_start()

seq = 0
while True:
    p = {"device_id": "esp32-01", "ts": int(time.time() * 1000), "seq": seq,
         "temperature": round(random.gauss(28, 0.5), 2),
         "humidity": round(random.gauss(70, 2), 2),
         "distance_cm": round(random.gauss(100, 3), 2)}
    r = random.random()
    if r < 0.03:
        p["temperature"] = 75.0      # outlier (vẫn trong khoảng hợp lệ -40..80)
    if r > 0.97:
        del p["humidity"]            # missing
    c.publish("iot/lab2/esp32-01/telemetry", json.dumps(p), qos=1)
    print(p)
    seq += 1
    time.sleep(1)