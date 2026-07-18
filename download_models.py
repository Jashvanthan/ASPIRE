import os
import urllib.request
import ssl

MODELS_DIR = "models"

def download_file(url, filename):
    os.makedirs(MODELS_DIR, exist_ok=True)
    filepath = os.path.join(MODELS_DIR, filename)
    if not os.path.exists(filepath):
        print(f"Downloading {filename}...")
        try:
            # Bypass SSL verification if needed
            context = ssl._create_unverified_context()
            with urllib.request.urlopen(url, context=context) as response, open(filepath, 'wb') as out_file:
                data = response.read()
                out_file.write(data)
            print(f"Downloaded {filename} successfully.")
        except Exception as e:
            print(f"Failed to download {filename}: {e}")
    else:
        print(f"{filename} already exists.")

if __name__ == "__main__":
    yunet_url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
    sface_url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx"
    minifasnet_url = "https://github.com/kprokopiuk/silent_face_anti_spoofing/raw/master/resources/anti_spoof_models/2.7_80x80_MiniFASNetV2.onnx"
    
    download_file(yunet_url, "face_detection_yunet_2023mar.onnx")
    download_file(sface_url, "face_recognition_sface_2021dec.onnx")
    download_file(minifasnet_url, "2.7_80x80_MiniFASNetV2.onnx")
    print("All models ready.")
