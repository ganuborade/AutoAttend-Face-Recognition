import cv2
import os
import numpy as np
import pickle

def train_model(data_dir="static/images", model_save_path="trainer.yml", label_map_path="label_map.pkl"):
    print("Starting training process...")
    
    # Check if cv2.face is available
    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
    except AttributeError:
        print("ERROR: cv2.face module not found!")
        print("Please install opencv-contrib-python using: pip install opencv-contrib-python")
        return False
        
    detector = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    
    faces = []
    ids = []
    
    # We need to map string labels (like '12', 'CS101') to integer IDs for LBPH
    label_to_id = {}
    id_to_label = {}
    current_id = 0
    
    if not os.path.exists(data_dir):
        print(f"Data directory {data_dir} not found.")
        return False

    for item in os.listdir(data_dir):
        person_dir = os.path.join(data_dir, item)
        
        # Skip if not a directory or if it's not a valid student folder (e.g., 'css')
        if not os.path.isdir(person_dir) or item == 'css':
            continue
            
        label = item
        if label not in label_to_id:
            label_to_id[label] = current_id
            id_to_label[current_id] = label
            current_id += 1
            
        person_id = label_to_id[label]
        
        for image_name in os.listdir(person_dir):
            if not image_name.endswith(('.jpg', '.jpeg', '.png')):
                continue
                
            image_path = os.path.join(person_dir, image_name)
            img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            
            if img is None:
                continue
                
            # Optionally detect faces in the stored images to only train on the face
            # This is safer than training on the whole image which might contain background
            img_numpy = np.array(img, 'uint8')
            detected_faces = detector.detectMultiScale(img_numpy, scaleFactor=1.2, minNeighbors=5)
            
            for (x, y, w, h) in detected_faces:
                faces.append(img_numpy[y:y+h, x:x+w])
                ids.append(person_id)
                # If we assume images are already cropped, we could just use img_numpy
                
    if len(faces) == 0:
        print("No faces found to train.")
        return False
        
    print(f"Training on {len(faces)} faces for {len(label_to_id)} students...")
    recognizer.train(faces, np.array(ids))
    recognizer.write(model_save_path)
    
    with open(label_map_path, 'wb') as f:
        pickle.dump(id_to_label, f)
        
    print(f"Model trained and saved to {model_save_path}")
    print(f"Label map saved to {label_map_path}")
    return True

if __name__ == "__main__":
    train_model()
