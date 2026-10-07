import numpy as np
import pandas as pd
from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS
from sklearn.preprocessing import MinMaxScaler

URL, TOKEN, ORG, BUCKET = "http://localhost:8086", "my-super-token", "iotlab", "iot"
COLS = ["temperature", "humidity", "distance_cm"]
WINDOW = "-1h"          # khoảng thời gian đọc dữ liệu
RESAMPLE = "1min"       # cửa sổ resampling

client = InfluxDBClient(url=URL, token=TOKEN, org=ORG)

flux = f'''
from(bucket:"{BUCKET}")
  |> range(start: {WINDOW})
  |> filter(fn:(r)=> r._measurement=="sensor_raw")
  |> filter(fn:(r)=> r._field=="temperature" or r._field=="humidity" or r._field=="distance_cm")
  |> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")
'''
df = client.query_api().query_data_frame(flux)
if isinstance(df, list):
    df = pd.concat(df)
df = df.rename(columns={"_time": "time"}).set_index("time").sort_index()
df = df.reindex(columns=COLS)          # đảm bảo đủ cột dù có cột chưa từng có dữ liệu
print(f"Số bản ghi thô: {len(df)}")
print("Missing trước xử lý:\n", df.isna().sum(), "\n")

# 1) Missing values: nội suy theo thời gian
df = df.interpolate(method="time", limit=5).ffill().bfill()

# 2) Outlier (IQR): đánh dấu NaN rồi nội suy lại
outliers = {}
for c in COLS:
    q1, q3 = df[c].quantile([0.25, 0.75])
    iqr = q3 - q1
    mask = (df[c] < q1 - 1.5 * iqr) | (df[c] > q3 + 1.5 * iqr)
    outliers[c] = int(mask.sum())
    df.loc[mask, c] = np.nan
df = df.interpolate(method="time").ffill().bfill()
print("Số outlier phát hiện:", outliers, "\n")

# 3) Resampling theo cửa sổ thời gian
rs = df[COLS].resample(RESAMPLE).mean().interpolate()

# 4) Tạo đặc trưng: rolling mean, delta
for c in COLS:
    rs[f"{c}_roll5"] = rs[c].rolling(5, min_periods=1).mean()
    rs[f"{c}_delta"] = rs[c].diff().fillna(0)

# 5) Chuẩn hóa Min-Max
norm = pd.DataFrame(MinMaxScaler().fit_transform(rs[COLS]),
                    index=rs.index, columns=[f"{c}_norm" for c in COLS])
out = pd.concat([rs, norm], axis=1)
print(out.describe().T[["mean", "std", "min", "max"]])

# 6) Ghi vào measurement mới
write_api = client.write_api(write_options=SYNCHRONOUS)
write_api.write(bucket=BUCKET, record=out,
                data_frame_measurement_name="sensor_processed",
                data_frame_tag_columns=[])
print(f"\nĐã ghi {len(out)} dòng vào sensor_processed")