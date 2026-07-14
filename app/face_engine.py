import numpy as np
import cv2
import face_recognition

def bytes_to_ndarray(jpeg_bytes: bytes):
    data = np.frombuffer(jpeg_bytes, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    return img

def compute_encodings_from_bgr(img_bgr):
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    boxes = face_recognition.face_locations(rgb, model="hog")
    if not boxes:
        return []
    encs = face_recognition.face_encodings(rgb, boxes)
    return encs

def compute_boxes_and_encodings_from_bgr(img_bgr):
    """Like compute_encodings_from_bgr but also returns the face bounding boxes,
    needed to crop the same region across two frames for liveness checking."""
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    boxes = face_recognition.face_locations(rgb, model="hog")
    if not boxes:
        return [], []
    encs = face_recognition.face_encodings(rgb, boxes)
    return boxes, encs

def average_encoding(encodings):
    if not encodings:
        return None
    arr = np.array(encodings)
    return arr.mean(axis=0)

def match_encoding(encoding, known_encodings, tolerance=0.45):
    # Returns index of best match or -1
    if not known_encodings:
        return -1, None
    dists = face_recognition.face_distance(np.array(known_encodings), encoding)
    idx = int(np.argmin(dists))
    if dists[idx] <= tolerance:
        return idx, float(dists[idx])
    return -1, float(dists[idx])


def check_liveness(img1_bgr, img2_bgr, box, motion_threshold=4.0):
    """
    Lightweight liveness / anti-spoofing check using two frames captured ~800ms apart.

    Idea: a real face in front of a live camera always has tiny involuntary motion
    (blinking, breathing, micro head movement). A printed photo or a phone screen
    held perfectly still in front of the camera will show almost zero pixel change
    in the face region between the two frames.

    Returns True (live) if the mean absolute pixel difference inside the face
    bounding box, across the two frames, exceeds `motion_threshold`. Returns False
    if the region looks static (likely a photo/replay attack). Returns None if the
    check could not be performed (e.g. missing second frame or box out of bounds).

    NOTE: this is a best-effort heuristic, not a certified anti-spoofing system.
    It stops the most common "hold up a printed photo perfectly still" attack, but
    a moving video replay could still defeat it. For stronger guarantees, use the
    blink-detection helper below (requires dlib + a 68-point landmark model).
    """
    if img2_bgr is None or box is None:
        return None

    top, right, bottom, left = box
    h1, w1 = img1_bgr.shape[:2]
    h2, w2 = img2_bgr.shape[:2]
    top, left = max(0, top), max(0, left)
    bottom, right = min(h1, h2, bottom), min(w1, w2, right)
    if bottom <= top or right <= left:
        return None

    face1 = cv2.cvtColor(img1_bgr[top:bottom, left:right], cv2.COLOR_BGR2GRAY)
    face2 = cv2.cvtColor(img2_bgr[top:bottom, left:right], cv2.COLOR_BGR2GRAY)
    if face1.shape != face2.shape:
        face2 = cv2.resize(face2, (face1.shape[1], face1.shape[0]))

    diff = cv2.absdiff(face1, face2)
    mean_diff = float(np.mean(diff))
    return mean_diff >= motion_threshold



# --- Blink detection helpers (optional, uses dlib shape predictor) ---
def eye_aspect_ratio(eye):
    # eye: array-like of 6 (x,y) points
    import numpy as np
    A = ((eye[1][0]-eye[5][0])**2 + (eye[1][1]-eye[5][1])**2) ** 0.5
    B = ((eye[2][0]-eye[4][0])**2 + (eye[2][1]-eye[4][1])**2) ** 0.5
    C = ((eye[0][0]-eye[3][0])**2 + (eye[0][1]-eye[3][1])**2) ** 0.5
    if C == 0: return 0.0
    return (A + B) / (2.0 * C)

def detect_blinks_bounding(img_bgr, predictor_path=None, threshold=0.20):
    """Detect whether eyes are blinking (returns True if blink detected).
    Requires dlib and a facial landmarks predictor. If predictor_path is None or not found,
    this function returns None (unsupported).
    """
    try:
        import dlib
        import numpy as np
    except Exception:
        return None

    if predictor_path is None:
        # look for default in data/
        predictor_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'shape_predictor_68_face_landmarks.dat')
    if not os.path.exists(predictor_path):
        return None

    detector = dlib.get_frontal_face_detector()
    predictor = dlib.shape_predictor(predictor_path)
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    rects = detector(gray, 0)
    if not rects:
        return False
    # indices for left and right eye in 68-point model
    LEFT_EYE = list(range(36, 42))
    RIGHT_EYE = list(range(42, 48))

    for r in rects:
        shape = predictor(gray, r)
        coords = [(shape.part(i).x, shape.part(i).y) for i in range(68)]
        left = [coords[i] for i in LEFT_EYE]
        right = [coords[i] for i in RIGHT_EYE]
        lar = eye_aspect_ratio(left)
        rar = eye_aspect_ratio(right)
        if (lar + rar) / 2.0 < threshold:
            return True
    return False
