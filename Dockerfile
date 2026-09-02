FROM python:3.10-slim

# System deps needed to build dlib / face_recognition and run opencv-headless
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake \
    libopenblas-dev liblapack-dev \
    libx11-dev libgtk-3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app

COPY requirements.txt .
# IMPORTANT: face-recognition's own metadata requires the real "dlib" package,
# which has no prebuilt wheel on PyPI and would otherwise force pip to compile
# it from source (this is what was blowing past 8GB of RAM on Render's free
# build). dlib_bin provides a prebuilt "dlib" module already, so we install it
# first, then install face-recognition with --no-deps to stop pip from also
# fetching source dlib, then add back its other real dependencies explicitly.
RUN pip install --no-cache-dir "setuptools<81" && \
    pip install --no-cache-dir dlib_bin==19.24.6 && \
    pip install --no-cache-dir --no-deps face-recognition==1.3.0 && \
    pip install --no-cache-dir click numpy Pillow "face_recognition_models>=0.3.0" && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8000
EXPOSE 8000

CMD gunicorn -w 2 -k gthread -b 0.0.0.0:${PORT:-8000} wsgi:app
