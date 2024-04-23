"""
@brief: Vehicle reidentification using YOLOv8 and feature-based similarity
@author: Harshit Kumar, Khushi Neema
"""

import cv2
import os
import argparse
from ultralytics import YOLO
from torchvision import models
from torchreid.utils import FeatureExtractor
from feature_extraction import *
from similarity import *

parser = argparse.ArgumentParser()
parser.add_argument("-i", "--input", required=True, help="path to input video")
parser.add_argument("-r", "--reference_img", required=True, help="path to reference image")
parser.add_argument("-f", "--feature", default="hog", choices=["hog", "histogram", "resnet", "osnet", "composite"],
                    help="Feature type to use for comparison")
args = parser.parse_args()

# Similarity thresholds
hog_threshold = 0.5
histogram_threshold = 0.7
cosine_threshold = 0.1

# Initialize YOLO model
model = YOLO("yolov8n.pt")
cap = cv2.VideoCapture(args.input)

# Directory for saving images of matched vehicles
save_dir = "images/"
os.makedirs(save_dir, exist_ok=True)

# Load reference vehicle image and resize
reference_image_path = args.reference_img
reference_image = cv2.imread(reference_image_path)
if reference_image is None:
    raise FileNotFoundError(f"Reference image at {reference_image_path} not found.")

if args.feature == "hog" or args.feature == "histogram":
    # Standardize image size for feature extraction
    standard_size = (128, 64)  # Typical size used for HOG feature extraction
    # Resize reference image
    reference_image = cv2.resize(reference_image, standard_size)

# Compute features for the reference image
if args.feature == "hog":
    reference_hog_features = compute_hog_features(reference_image)
elif args.feature == "histogram":
    reference_color_histogram = compute_color_histogram(reference_image)
elif args.feature == "resnet":
    # Load a pre-trained ResNet model
    model_resnet = models.resnet50(pretrained=True)
    model_resnet.eval()  # Set model to evaluation mode
    reference_dnn_features = extract_dnn_features(model_resnet, reference_image)
elif args.feature == "osnet":
    model_torchreid = FeatureExtractor(
        model_name='osnet_x1_0',
        model_path='osnet_x1_0_imagenet.pth',
        device='cpu'
    )
    reference_dnn_features = extract_torchreid_features(model_torchreid, reference_image)

# get vehicle classes: bicycle, car, motorcycle, airplane, bus, train, truck, boat
# class_list = [1, 2, 3, 4, 5, 6, 7, 8]
class_list = [2]
# Tracking and matching
frame_count = 0  # Initialize a frame counter
while cap.isOpened():
    success, frame = cap.read()
    if not success:
        break

    frame_count += 1  # Increment the frame counter
    results = model.track(frame, show=False, verbose=False, conf=0.4, classes=class_list, persist=True)
    if results[0].boxes.id is not None:
        boxes = results[0].boxes.xyxy.cpu()  # Use xyxy format
        track_ids = results[0].boxes.id.cpu().numpy().astype(int)
        annotated_frame = results[0].plot()

        for i, box in enumerate(boxes):
            x1, y1, x2, y2 = map(int, box)  # Use xyxy format
            crop_img = frame[y1:y2, x1:x2]  # Use xyxy format

            # save all image
            # crop_name = f"frame_{frame_count}_ID_{results[0].boxes.id[i]}.jpg"
            # crop_path = os.path.join(save_dir, crop_name)
            # cv2.imwrite(crop_path, crop_img)

            # resize image for non-DNN features
            if args.feature == "hog" or args.feature == "histogram":
                crop_img = cv2.resize(crop_img, standard_size)  # Resize to standard size

            match = False
            if args.feature == "hog":
                # Compare HOG features
                hog_features = compute_hog_features(crop_img)
                l2_dist = l2_distance(hog_features, reference_hog_features)
                match = l2_dist < hog_threshold
            elif args.feature == "histogram":
                # Compare color histograms
                color_histogram = compute_color_histogram(crop_img)
                hist_dist = histogram_distance(color_histogram, reference_color_histogram)
                match = hist_dist > histogram_threshold
            elif args.feature == "resnet":
                # Compare DNN features
                dnn_features = extract_dnn_features(model_resnet, crop_img)
                cosine_dist = cosine_distance(dnn_features, reference_dnn_features)
                match = cosine_dist < cosine_threshold
            elif args.feature == "osnet":
                dnn_features = extract_torchreid_features(model_torchreid, crop_img)
                cosine_dist = cosine_distance(dnn_features, reference_dnn_features)
                match = cosine_dist < cosine_threshold
            
            if match:
                # id
                print(f"Matched vehicle with ID: {track_ids[0]}")
                # Draw a green rectangle around matched vehicles
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), (0, 255, 0), 3)  # Use xyxy format
                cv2.putText(annotated_frame, 'Matched', (x1, y2), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 3)

                crop_name = f"frame_{frame_count}_ID_{results[0].boxes.id[i]}_{args.feature}.jpg"
                crop_path = os.path.join(save_dir, crop_name)
                cv2.imwrite(crop_path, crop_img)


        cv2.imshow(f"YOLOv8 Tracking with ReID Matching - {args.feature}", annotated_frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

cap.release()
cv2.destroyAllWindows()