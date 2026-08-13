import cv2
import os
import numpy as np
import pickle


def train_model(
    data_dir=None,
    model_save_path=None,
    label_map_path=None
):

    BASE_DIR = os.path.dirname(
        os.path.abspath(__file__)
    )

    if data_dir is None:
        data_dir = os.path.join(
            BASE_DIR,
            "static",
            "images"
        )

    if model_save_path is None:
        model_save_path = os.path.join(
            BASE_DIR,
            "trainer.yml"
        )

    if label_map_path is None:
        label_map_path = os.path.join(
            BASE_DIR,
            "label_map.pkl"
        )
    print("\n========================================")
    print("       STARTING MODEL TRAINING")
    print("========================================")

    # --------------------------------------------------
    # 1. Check LBPH recognizer
    # --------------------------------------------------
    try:
        recognizer = cv2.face.LBPHFaceRecognizer_create()
    except AttributeError:
        print("ERROR: cv2.face module not found!")
        print("Install:")
        print("pip install opencv-contrib-python")
        return False

    # --------------------------------------------------
    # 2. Check data directory
    # --------------------------------------------------
    if not os.path.exists(data_dir):
        print(f"ERROR: Data directory not found: {data_dir}")
        return False

    # --------------------------------------------------
    # 3. Store training images and labels
    # --------------------------------------------------
    faces = []
    ids = []

    label_to_id = {}
    id_to_label = {}

    current_id = 0

    # --------------------------------------------------
    # 4. Read each student's folder
    # --------------------------------------------------
    student_folders = sorted(os.listdir(data_dir))

    for item in student_folders:

        person_dir = os.path.join(data_dir, item)

        # Skip files
        if not os.path.isdir(person_dir):
            continue

        # Skip CSS or other non-student folders
        if item.lower() == "css":
            continue

        # Ignore hidden folders
        if item.startswith("."):
            continue

        label = item

        # --------------------------------------------------
        # Create integer ID for LBPH
        # --------------------------------------------------
        if label not in label_to_id:

            label_to_id[label] = current_id
            id_to_label[current_id] = label

            print(
                f"Student found -> "
                f"Roll: {label}, "
                f"Model ID: {current_id}"
            )

            current_id += 1

        person_id = label_to_id[label]

        image_count = 0

        # --------------------------------------------------
        # 5. Read student's face images
        # --------------------------------------------------
        for image_name in sorted(os.listdir(person_dir)):

            if not image_name.lower().endswith(
                (".jpg", ".jpeg", ".png")
            ):
                continue

            image_path = os.path.join(
                person_dir,
                image_name
            )

            # Read directly as grayscale
            img = cv2.imread(
                image_path,
                cv2.IMREAD_GRAYSCALE
            )

            if img is None:
                print(
                    f"WARNING: Could not read image: "
                    f"{image_path}"
                )
                continue

            # --------------------------------------------------
            # IMPORTANT:
            # Images captured by your application are already
            # cropped face images.
            #
            # Therefore DO NOT run Haar detection again.
            # --------------------------------------------------

            # Resize every training image to the same size.
            # This makes training and recognition consistent.
            img = cv2.resize(
                img,
                (200, 200)
            )

            # Improve contrast slightly
            img = cv2.equalizeHist(img)

            faces.append(img)
            ids.append(person_id)

            image_count += 1

        print(
            f"  {label}: "
            f"{image_count} training images loaded"
        )

    # --------------------------------------------------
    # 6. Check training data
    # --------------------------------------------------
    if len(faces) == 0:

        print("\nERROR: No training faces found.")
        print("Model was NOT changed.")
        return False

    if len(set(ids)) == 0:

        print("\nERROR: No valid student IDs found.")
        print("Model was NOT changed.")
        return False

    print("\n----------------------------------------")
    print(f"Total training images : {len(faces)}")
    print(f"Total students        : {len(label_to_id)}")
    print("----------------------------------------")

    # --------------------------------------------------
    # 7. Train LBPH model
    # --------------------------------------------------
    try:

        print("\nTraining LBPH recognizer...")

        recognizer.train(
            faces,
            np.array(ids, dtype=np.int32)
        )

        print("Training completed successfully.")

    except Exception as e:

        print("\nERROR during model training:")
        print(e)

        return False

    # --------------------------------------------------
    # 8. Save model
    # --------------------------------------------------
    try:

        recognizer.write(model_save_path)

        print(
            f"Model saved successfully: "
            f"{model_save_path}"
        )

    except Exception as e:

        print("\nERROR saving trainer.yml:")
        print(e)

        return False

    # --------------------------------------------------
    # 9. Save label map
    # --------------------------------------------------
    try:

        with open(label_map_path, "wb") as f:
            pickle.dump(id_to_label, f)

        print(
            f"Label map saved successfully: "
            f"{label_map_path}"
        )

    except Exception as e:

        print("\nERROR saving label_map.pkl:")
        print(e)

        return False

    # --------------------------------------------------
    # 10. Display final mapping
    # --------------------------------------------------
    print("\n========================================")
    print("        TRAINING SUCCESSFUL")
    print("========================================")

    print("\nStudent Model Mapping:")

    for model_id, roll in id_to_label.items():

        print(
            f"Model ID {model_id}  -->  Roll {roll}"
        )

    print("\n========================================\n")

    return True


# ------------------------------------------------------
# Run directly
# ------------------------------------------------------
if __name__ == "__main__":
    train_model()