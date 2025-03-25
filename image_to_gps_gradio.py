import os
import zipfile
import shutil
import exifread
import pandas as pd
import gradio as gr
from pillow_heif import register_heif_opener
from PIL import Image


# HEICファイルをPioolwで扱えるようにする
register_heif_opener()


class ImageGpsExtractor:
    def __init__(self, output_folder: str):
        self.output_folder = output_folder
        self.unzip_path = f"{output_folder}/unzip"
        os.makedirs(self.unzip_path, exist_ok=True)


    def extract_zip(self, zip_file_path:str) -> str:
        """
        zipファイルを展開する。

        Args:
            zip_file_path (str): アップロードしたzipファイルのパス

        Returns:
            str: 展開済みフォルダのパス
        """
        # 既存のディレクトリが存在する場合は削除
        if os.path.exists(self.unzip_path):
            shutil.rmtree(self.unzip_path)

        with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
            zip_ref.extractall(self.unzip_path)
        return self.unzip_path

    def  get_gps_info(self, file_path: str) -> tuple:
        """
        画像からGPS情報と撮影日を取得する。

        Args:
            file_path (str): ファイルのパス

        Returns:
            tuple: (緯度 (float), 経度 (float), 撮影日 (str))
        """
        # HEICファイルをJPEG互換形式で開く
        if file_path.lower().endswith(".heic"):
            jpg_path = f"{self.output_folder}/jpg"
            # 既存のディレクトリが存在する場合は削除
            if os.path.exists(jpg_path):
                shutil.rmtree(jpg_path)
            os.makedirs(jpg_path, exist_ok=True)
            image = Image.open(file_path)
            temp_path = f"{jpg_path}/{os.path.splitext(os.path.basename(file_path))[0]}.jpg"

            # EXIFデータを保存時に引き継ぐ
            if "exif" in image.info:
                image.save(temp_path, format="JPEG", exif=image.info["exif"])
            else:
                image.save(temp_path, format="JPEG")
            
            file_path = temp_path

        with open(file_path, "rb") as f:
            # EXIFデータを読み取る
            tags = exifread.process_file(f)

            # GPS情報を取得
            gps_latitude = tags.get("GPS GPSLatitude")
            gps_latitude_ref = tags.get("GPS GPSLatitudeRef")
            gps_longitude = tags.get("GPS GPSLongitude")
            gps_longitude_ref = tags.get("GPS GPSLongitudeRef")

            # 撮影日を取得
            date_time = tags.get("EXIF DateTimeOriginal")

            lat, lon = None, None
            # 位置情報が存在する場合のみ処理
            if gps_latitude and gps_latitude_ref and gps_longitude and gps_longitude_ref:
                # DMS形式を十進法に変換
                lat = self.convert_to_degrees(gps_latitude)
                lon = self.convert_to_degrees(gps_longitude)

                # 北緯・南緯、東経・西経を考慮して符号を修正
                if gps_latitude_ref.values != "N":
                    lat = -lat
                if gps_longitude_ref.values != "E":
                    lon = -lon
            
            # 撮影日が存在しない場合は None
            date_time = str(date_time) if date_time else None
            
            return lat, lon, date_time

    def convert_to_degrees(self, value) -> float:
        """
        DMS形式を十進法に変換する。

        Args:
            value (exifread.class.IfdTag): DMS形式の値

        Returns:
            float: 十進法に変換された座標
        """
        d = float(value.values[0].num) / float(value.values[0].den)
        m = float(value.values[1].num) / float(value.values[1].den)
        s = float(value.values[2].num) / float(value.values[2].den)

        return d + (m / 60.0) + (s / 3600.0)

    def extract_gps_from_images(self, folder: str) -> list[dict]:
        """
        指定したフォルダ内の画像からGPS情報を抽出する。

        Args:
         folder (str): zipファイルを展開したフォルダのパス

        Returns:
            list[dict]: 以下のキーを持つ辞書のリスト:
                - "File" (str): ファイル名
                - "Latitude" (float): 緯度
                - "Longitude" (float): 経度
                - "DateTime" (str): 撮影日時
        """
        data = []

        # 指定したフォルダ内のすべてのファイルをスキャン
        for root, _, files in os.walk(folder):
            for file in files:
                if file.lower().endswith((".jpg", ".jpeg", ".png", ".heic")):
                    file_path = os.path.join(root, file)

                    # 画像からGPS情報を取得
                    lat, lon, date_time = self.get_gps_info(file_path)

                    # GPS情報が取得できた場合のみデータに追加
                    if lat and lon:
                        data.append({
                            "File": file,
                            "Latitude": lat,
                            "Longitude": lon,
                            "DateTime": date_time
                        })
        
        return data

    def save_to_csv(self, data: list[dict]) -> str:
        """
        取得したGPS情報をcsvファイルに保存する。

        Args:
            data (list[dict]): 取得したGPS情報のリスト

        Returns:
            str: csvファイルのパス
        """
        df = pd.DataFrame(data)

        # 日時で昇順にソート
        df["DateTime"] = pd.to_datetime(df["DateTime"], format="%Y:%m:%d %H:%M:%S", errors="coerce")
        df = df.sort_values(by="DateTime", ascending=True)

        csv_path = f"{self.output_folder}/gps_data.csv"
        df.to_csv(csv_path, index=False)

        return csv_path



# インスタンス生成
extractor = ImageGpsExtractor(output_folder="output")



def process_zip(zip_file):
    # ファイルがNoneの場合
    if zip_file is None:
        raise ValueError("ファイルをアップロードしてください。")

    # 拡張子を確認
    if not zip_file.lower().endswith(".zip"):
        raise ValueError("アップロード可能なファイルは .zip のみです。")

    # 画像からGPS情報を抽出
    extracted_path = extractor.extract_zip(zip_file)
    data = extractor.extract_gps_from_images(extracted_path)

    if not data:
        raise ValueError("GPS情報が含まれる画像が見つかりませんでした。")

    csv_path = extractor.save_to_csv(data)

    return csv_path



# インターフェースを作成
interface = gr.Interface(
    fn=process_zip,
    inputs=gr.File(label="ZIPファイルをアップロード", type="filepath"),
    outputs=[gr.File(label="処理後のCSVファイルをダウンロード")],
    title="GPS情報抽出アプリ",
    description="ZIPファイルに含まれる画像 (JPG, PNG, HEIC) からGPS情報を抽出してCSVに保存"
)


# 起動
if __name__ == "__main__":
    interface.launch()
