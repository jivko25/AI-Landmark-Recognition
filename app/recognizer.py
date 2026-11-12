"""Local landmark classifier: Google Landmarks (Europe) TFLite model from Kaggle."""

import threading
import zipfile

import numpy as np
from ai_edge_litert.interpreter import Interpreter

from app.schemas import Candidate


class LandmarkRecognizer:
    INPUT_SIZE = 321

    def __init__(self, model_path):
        # The .tflite file is also a zip archive that carries the label list.
        with zipfile.ZipFile(model_path) as z:
            self.names = z.read("probability-labels-en.txt").decode("utf-8").splitlines()
        self.interpreter = Interpreter(model_path=str(model_path))
        self.interpreter.allocate_tensors()
        self._input = self.interpreter.get_input_details()[0]["index"]
        self._output = self.interpreter.get_output_details()[0]["index"]
        # The interpreter is not thread-safe and FastAPI runs sync endpoints in a thread pool.
        self._lock = threading.Lock()
        self.landmarks_known = len(set(self.names))

    def predict(self, img, top):
        x = np.array(img.resize((self.INPUT_SIZE, self.INPUT_SIZE)), dtype=np.uint8)[None]
        with self._lock:
            self.interpreter.set_tensor(self._input, x)
            self.interpreter.invoke()
            scores = self.interpreter.get_tensor(self._output)[0].copy()

        # One landmark can have several class ids; keep the best score per name.
        best = {}
        for i in np.argsort(scores)[::-1][: top * 20]:
            best.setdefault(self.names[i], float(scores[i]))
            if len(best) == top:
                break
        return [Candidate(name=name, score=round(score, 4)) for name, score in best.items()]
